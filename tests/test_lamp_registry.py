"""Lamp registry identity, bounds and teardown (SEC-007 / SEC-008)."""
import asyncio

import pytest

from awoxlight import daemon as D
from awoxlight.daemon import Daemon, Lamp


def _beacon(state_bytes: bytes) -> dict[int, bytes]:
    head = bytes.fromhex("3510ec9e7838020211ec00")
    return {0x0160: head + state_bytes + bytes(11)}


class FakeDev:
    def __init__(self, address, name=""):
        self.address = address
        self.name = name


class FakeAdv:
    def __init__(self, manufacturer_data, rssi=-50, local_name="R-D9C2DB"):
        self.manufacturer_data = manufacturer_data
        self.rssi = rssi
        self.local_name = local_name


class FakeLight:
    def __init__(self):
        self.disconnects = 0
        self.connected = True

    async def disconnect(self):
        self.disconnects += 1
        self.connected = False


def make_daemon() -> Daemon:
    d = Daemon()

    async def noop():
        return None

    d.start_scan = noop     # type: ignore[method-assign]
    d.stop_scan = noop      # type: ignore[method-assign]
    return d


async def shutdown(d: Daemon):
    d.stopping.set()
    for lamp in list(d.lamps.values()):
        await lamp.close()


def run(coro_fn):
    async def main():
        d = make_daemon()
        try:
            return await coro_fn(d)
        finally:
            await shutdown(d)

    return asyncio.run(main())


MAC_A = "A4:C1:38:11:22:33"
MAC_B = "A4:C1:38:44:55:66"


def test_lamp_for_rejects_bad_identity():
    async def body(d: Daemon):
        for bad in ("", "not-a-mac", "A4:C1:38:11:22", "A4C13811223", "A4:C1:38:11:22:3G",
                    "A4:C1:38:11:22:33:44", "../../etc/passwd"):
            with pytest.raises(ValueError):
                await d.lamp_for({"mac": bad, "mesh_name": "R-X", "mesh_password": "1234"})
        with pytest.raises(ValueError, match="mesh credentials too long"):
            await d.lamp_for({"mac": MAC_A, "mesh_name": "x" * 17, "mesh_password": "1234"})
        with pytest.raises(ValueError, match="mesh credentials too long"):
            await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "p" * 17})
        # multi-byte characters count as bytes, not code points
        with pytest.raises(ValueError, match="mesh credentials too long"):
            await d.lamp_for({"mac": MAC_A, "mesh_name": "é" * 9, "mesh_password": "1234"})
        assert d.lamps == {}
        # lower case is accepted and normalised
        lamp = await d.lamp_for({"mac": MAC_A.lower(), "mesh_name": "R-X", "mesh_password": "1234"})
        assert lamp.mac == MAC_A

    run(body)


def test_same_mac_different_credentials_are_separate_lamps():
    async def body(d: Daemon):
        a = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "1234"})
        b = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "9999"})
        c = await d.lamp_for({"mac": MAC_A, "mesh_name": "other", "mesh_password": "1234"})
        assert a is not b and a is not c and b is not c
        assert not a.closed and not b.closed and not c.closed
        assert len(d.lamps) == 3
        assert d.lamps_by_mac[MAC_A] == [a, b, c]
        # asking again returns the very same object
        assert await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "1234"}) is a

    run(body)


def test_registry_is_capped_and_evicts_least_recently_requested():
    async def body(d: Daemon):
        lamps = []
        for i in range(D.LAMPS_MAX):
            lamp = await d.lamp_for({"mac": "A4:C1:38:00:00:%02X" % i, "mesh_name": "R-X", "mesh_password": "1234"})
            lamp.last_request_at = 1000.0 + i  # oldest first
            lamps.append(lamp)
        assert len(d.lamps) == D.LAMPS_MAX
        # touch the oldest so it is no longer the eviction candidate
        again = await d.lamp_for({"mac": "A4:C1:38:00:00:00", "mesh_name": "R-X", "mesh_password": "1234"})
        assert again is lamps[0]
        assert again.last_request_at > 1000.0

        fresh = await d.lamp_for({"mac": MAC_B, "mesh_name": "R-X", "mesh_password": "1234"})
        assert len(d.lamps) == D.LAMPS_MAX
        assert fresh in d.lamps.values()
        assert lamps[0] in d.lamps.values() and not lamps[0].closed
        assert lamps[1] not in d.lamps.values()          # it was the least recent
        assert lamps[1].closed and lamps[1].keeper is None
        assert "A4:C1:38:00:00:01" not in d.lamps_by_mac

    run(body)


def test_beacon_reaches_every_lamp_for_that_mac():
    async def body(d: Daemon):
        a = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "1234"})
        b = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "9999"})
        other = await d.lamp_for({"mac": MAC_B, "mesh_name": "R-X", "mesh_password": "1234"})
        d.beacon_ignore_until = 0.0
        d._on_adv(FakeDev(MAC_A.lower(), "R-X"), FakeAdv(_beacon(bytes.fromhex("017f400000"))))
        for lamp in (a, b):
            assert lamp.state is not None and lamp.state.on and lamp.state.white_temp == 0x40
        assert other.state is None
        assert MAC_A in d.seen

    run(body)


def test_close_while_connect_in_flight_disconnects_the_link(monkeypatch):
    fake = FakeLight()

    async def slow_connect(self):
        await asyncio.sleep(0.2)
        self.light = fake
        return fake

    monkeypatch.setattr(Lamp, "ensure_connected", slow_connect)

    async def body(d: Daemon):
        lamp = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "1234"})
        task = asyncio.create_task(lamp.run("on", {}))
        await asyncio.sleep(0.05)          # run() is inside ensure_connected()
        # a second client claims the same mac with different credentials
        other = await d.lamp_for({"mac": MAC_A, "mesh_name": "R-X", "mesh_password": "9999"})
        assert other is not lamp
        await lamp.close()                 # waits for the in-flight command
        resp = await task
        assert resp["ok"] is False
        assert fake.disconnects == 1       # the link opened under us was dropped
        assert lamp.light is None

    run(body)
