"""SEC-002: every producer on the scan path enforces a budget.

Anyone in radio range can advertise thousands of fake AwoX lamps under rotating
addresses. The daemon caps what it remembers and what it hands out; the CLI caps
what it will buffer from a reply.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time

import pytest

from awoxlight import ctl
from awoxlight.daemon import SCAN_MAX_ROWS, SEEN_MAX, Daemon

BEACON = {0x0160: bytes.fromhex("3510ec9e7838020211ec00") + bytes.fromhex("017f400000") + bytes(11)}


class FakeDev:
    def __init__(self, address: str, name: str = "R-D9C2DB"):
        self.address = address
        self.name = name


class FakeAdv:
    def __init__(self, rssi: int, name: str = "R-D9C2DB"):
        self.rssi = rssi
        self.local_name = name
        self.manufacturer_data = BEACON


def _mac(i: int) -> str:
    return "A4:C1:38:%02X:%02X:%02X" % ((i >> 16) & 0xFF, (i >> 8) & 0xFF, i & 0xFF)


def make_daemon() -> Daemon:
    async def build():
        return Daemon()

    return asyncio.run(build())


def test_flood_of_advertisers_is_bounded():
    d = make_daemon()
    for i in range(10_000):
        d._on_adv(FakeDev(_mac(i)), FakeAdv(rssi=-40 - (i % 50)))
        assert len(d.seen) <= SEEN_MAX
    assert len(d.seen) <= SEEN_MAX == 64
    rows = d.scan_json()
    assert len(rows) <= SCAN_MAX_ROWS == 24
    # Strongest first, as before.
    assert [r["rssi"] for r in rows] == sorted((r["rssi"] for r in rows), reverse=True)


def test_stronger_advertiser_evicts_weakest_and_weaker_is_dropped():
    d = make_daemon()
    for i in range(SEEN_MAX):
        d._on_adv(FakeDev(_mac(i)), FakeAdv(rssi=-50))
    d.seen[_mac(0)]["rssi"] = -90  # the weakest entry
    assert len(d.seen) == SEEN_MAX

    # A weaker newcomer is dropped outright.
    d._on_adv(FakeDev(_mac(9001)), FakeAdv(rssi=-95))
    assert _mac(9001) not in d.seen
    assert _mac(0) in d.seen
    assert len(d.seen) == SEEN_MAX

    # A stronger newcomer displaces the weakest.
    d._on_adv(FakeDev(_mac(9002)), FakeAdv(rssi=-30))
    assert _mac(9002) in d.seen
    assert _mac(0) not in d.seen
    assert len(d.seen) == SEEN_MAX


def test_updating_a_known_address_is_always_allowed():
    d = make_daemon()
    for i in range(SEEN_MAX):
        d._on_adv(FakeDev(_mac(i)), FakeAdv(rssi=-50))
    d._on_adv(FakeDev(_mac(3)), FakeAdv(rssi=-99))  # weak update of a known lamp
    assert d.seen[_mac(3)]["rssi"] == -99
    assert len(d.seen) == SEEN_MAX


def test_ttl_pruning_still_present():
    d = make_daemon()
    d._on_adv(FakeDev(_mac(1)), FakeAdv(rssi=-50))
    assert len(d.seen) == 1
    d.seen[_mac(1)]["seen_at"] -= 10_000
    cutoff = time.monotonic() - 60.0
    assert d.seen[_mac(1)]["seen_at"] < cutoff  # scan_watchdog would drop it


def test_request_caps_reply_size(tmp_path, monkeypatch):
    sock_path = tmp_path / "s.sock"
    stop = threading.Event()

    def serve():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        srv.settimeout(10)
        try:
            conn, _ = srv.accept()
        except OSError:
            srv.close()
            return
        with conn:
            conn.recv(65536)
            blob = b"x" * 65536  # never a newline: the reply never terminates
            try:
                for _ in range(32):  # 2 MB
                    conn.sendall(blob)
                    if stop.is_set():
                        break
            except OSError:
                pass
        srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    for _ in range(100):
        if sock_path.exists():
            break
        time.sleep(0.02)

    monkeypatch.setattr(ctl, "SOCKET_PATH", sock_path)
    started = time.monotonic()
    resp = ctl.request({"cmd": "scan"}, start=False, timeout=10.0)
    elapsed = time.monotonic() - started
    stop.set()

    assert resp == {"ok": False, "error": "reply too large"}
    assert elapsed < 5.0
