"""SEC-005: shutdown is bounded and every request has a wall-clock budget.

`serve()` used to wait for the server's context manager to close, which on
Python 3.14 blocks until every client transport has detached. One idle
connection - or a `scan` with a huge/infinite `wait` - hung `quit`/SIGTERM
forever, leaving the socket path and the flock behind. These tests drive the
real `Daemon` over a temporary socket (no Bluetooth: the scan hooks are stubbed).
"""
from __future__ import annotations

import asyncio
import json
import socket
import time

import pytest

from awoxlight import config as C
from awoxlight import daemon as D
from awoxlight.daemon import Daemon


@pytest.fixture
def sock_path(tmp_path, monkeypatch):
    """Point the daemon at a throwaway runtime dir and keep radio out of it."""
    path = tmp_path / "eglo-light.sock"
    monkeypatch.setattr(C, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(C, "SOCKET_PATH", path)
    monkeypatch.setattr(C, "LOG_PATH", tmp_path / "eglo-light.log")
    monkeypatch.setattr(C, "LOCK_PATH", tmp_path / "eglo-light.lock")

    async def noop(self):
        return None

    monkeypatch.setattr(Daemon, "start_scan", noop)
    monkeypatch.setattr(Daemon, "stop_scan", noop)
    return path


async def _wait_for_socket(path, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"daemon never bound {path}")


async def _open(path) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_unix_connection(str(path))


async def _ask(path, req: dict, timeout: float = 10.0) -> dict:
    reader, writer = await _open(path)
    try:
        writer.write((json.dumps(req) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    finally:
        writer.close()
    return json.loads(line or b"{}")


def test_quit_completes_with_an_idle_client_attached(sock_path):
    """An open connection that never speaks must not block shutdown."""

    async def scenario():
        d = Daemon()
        served = asyncio.create_task(d.serve())
        await _wait_for_socket(sock_path)

        # A client that connects and then says nothing, holding its transport.
        idle_reader, idle_writer = await _open(sock_path)

        started = time.monotonic()
        assert await _ask(sock_path, {"cmd": "quit"}) == {"ok": True}
        await asyncio.wait_for(served, timeout=6.0)
        elapsed = time.monotonic() - started

        idle_writer.close()
        return elapsed

    elapsed = asyncio.run(scenario())
    assert elapsed < 6.0
    assert not sock_path.exists()  # the path is freed for a successor


@pytest.mark.parametrize("wait", [1e12, "inf", float("inf"), -5, float("nan"), "nonsense"])
def test_scan_wait_is_clamped(sock_path, monkeypatch, wait):
    """A client-chosen wait cannot exceed the cap, and inf/NaN mean no wait."""
    monkeypatch.setattr(D, "SCAN_WAIT_MAX", 0.5)

    async def scenario():
        d = Daemon()
        served = asyncio.create_task(d.serve())
        await _wait_for_socket(sock_path)
        started = time.monotonic()
        resp = await _ask(sock_path, {"cmd": "scan", "wait": wait}, timeout=D.SCAN_WAIT_MAX + 2)
        elapsed = time.monotonic() - started
        await _ask(sock_path, {"cmd": "quit"})
        await asyncio.wait_for(served, timeout=6.0)
        return resp, elapsed

    resp, elapsed = asyncio.run(scenario())
    assert resp["ok"] is True and "lamps" in resp
    assert elapsed < D.SCAN_WAIT_MAX + 2


def test_a_long_scan_wait_does_not_outlive_shutdown(sock_path, monkeypatch):
    """Even inside the cap, a pending scan ends as soon as the daemon stops."""
    monkeypatch.setattr(D, "SCAN_WAIT_MAX", 30.0)

    async def scenario():
        d = Daemon()
        served = asyncio.create_task(d.serve())
        await _wait_for_socket(sock_path)
        scanning = asyncio.create_task(_ask(sock_path, {"cmd": "scan", "wait": 1e12}, timeout=8.0))
        await asyncio.sleep(0.2)
        started = time.monotonic()
        await _ask(sock_path, {"cmd": "quit"})
        await asyncio.wait_for(served, timeout=6.0)
        scanning.cancel()
        return time.monotonic() - started

    assert asyncio.run(scenario()) < 6.0
    assert not sock_path.exists()


def test_oversized_line_does_not_break_the_server(sock_path):
    """A 70 kB line past the stream limit is answered or dropped, not fatal."""

    async def scenario():
        d = Daemon()
        served = asyncio.create_task(d.serve())
        await _wait_for_socket(sock_path)

        reader, writer = await _open(sock_path)
        writer.write(b"x" * 70_000)  # no newline: over asyncio's 64 KiB limit
        try:
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            line = b""
        writer.close()
        if line:
            assert json.loads(line)["ok"] is False

        # The server is still healthy on a fresh connection.
        fresh = await _ask(sock_path, {"cmd": "scan", "wait": 0})
        assert fresh["ok"] is True

        await _ask(sock_path, {"cmd": "quit"})
        await asyncio.wait_for(served, timeout=6.0)

    asyncio.run(scenario())
    assert not sock_path.exists()


def test_stop_daemon_reports_failure_if_the_socket_survives(tmp_path, monkeypatch):
    """lightctl stop must not claim success while the socket path is still there."""
    from awoxlight import ctl

    path = tmp_path / "stuck.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path))
    srv.listen(1)
    monkeypatch.setattr(ctl, "SOCKET_PATH", path)
    monkeypatch.setattr(ctl, "request", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(ctl.time, "sleep", lambda _s: None)
    try:
        assert ctl.stop_daemon() == {"ok": False, "error": "daemon did not stop"}
    finally:
        srv.close()
