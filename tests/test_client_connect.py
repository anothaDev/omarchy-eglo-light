"""AwoxLight.connect() must never leave a BLE transport open on failure (SEC-008)."""
import asyncio

import pytest

from awoxlight import client as C
from awoxlight.client import AuthError, AwoxLight


class FakeBleak:
    def __init__(self, mac, adapter=None):
        self.mac = mac
        self.connects = 0
        self.disconnects = 0
        self.is_connected = False
        self.reply = b""
        self.write_error: Exception | None = None

    async def connect(self, timeout=None):
        self.connects += 1
        self.is_connected = True

    async def disconnect(self):
        self.disconnects += 1
        self.is_connected = False

    async def write_gatt_char(self, char, data, response=True):
        if self.write_error:
            raise self.write_error

    async def read_gatt_char(self, char):
        return self.reply

    async def start_notify(self, char, cb):
        pass


def _light(monkeypatch, reply: bytes, write_error: Exception | None = None) -> AwoxLight:
    made = {}

    def factory(mac, adapter=None):
        c = FakeBleak(mac, adapter)
        c.reply = reply
        c.write_error = write_error
        made["client"] = c
        return c

    monkeypatch.setattr(C, "BleakClient", factory)
    light = AwoxLight("A4:C1:38:11:22:33", "R-X", "1234")
    assert light._client is made["client"]
    return light


def test_empty_pair_reply_disconnects(monkeypatch):
    light = _light(monkeypatch, b"")
    with pytest.raises(Exception) as e:
        asyncio.run(light.connect())
    assert not isinstance(e.value, IndexError)
    assert light._client.disconnects == 1
    assert light.session_key is None


def test_short_pair_reply_disconnects(monkeypatch):
    light = _light(monkeypatch, b"\x0d\x01\x02\x03")
    with pytest.raises(RuntimeError, match="short pair reply"):
        asyncio.run(light.connect())
    assert light._client.disconnects == 1
    assert light.session_key is None


def test_auth_rejection_disconnects_and_raises_autherror(monkeypatch):
    light = _light(monkeypatch, b"\x0e" + bytes(15))
    with pytest.raises(AuthError):
        asyncio.run(light.connect())
    assert light._client.disconnects == 1
    assert light.session_key is None


def test_gatt_write_failure_disconnects(monkeypatch):
    light = _light(monkeypatch, b"\x0d" + bytes(15), write_error=RuntimeError("gatt write failed"))
    with pytest.raises(RuntimeError, match="gatt write failed"):
        asyncio.run(light.connect())
    assert light._client.disconnects == 1


def test_cancellation_during_pairing_disconnects(monkeypatch):
    light = _light(monkeypatch, b"\x0d" + bytes(15), write_error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(light.connect())
    assert light._client.disconnects == 1


def test_good_pair_reply_keeps_the_link(monkeypatch):
    light = _light(monkeypatch, b"\x0d" + bytes(15))
    asyncio.run(light.connect())
    assert light.session_key is not None
    assert light._client.disconnects == 0


def test_overlong_credentials_rejected_without_assert(monkeypatch):
    monkeypatch.setattr(C, "BleakClient", FakeBleak)
    with pytest.raises(ValueError, match="mesh credentials too long"):
        AwoxLight("A4:C1:38:11:22:33", "x" * 17, "1234")
    with pytest.raises(ValueError, match="mesh credentials too long"):
        AwoxLight("A4:C1:38:11:22:33", "R-X", "p" * 17)
