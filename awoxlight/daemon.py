"""Background daemon: holds links to AwoX/Eglo mesh lamps and tracks their state.

Listens on a Unix socket (JSON lines). One request per line, one reply per line.
Every lamp request carries the lamp identity:
  {"cmd": ..., "mac": "A4:C1:38:..", "mesh_name": "R-XXXXXX", "mesh_password": "1234"}

Commands:
  status                      -> {"ok": true, "state": {...}}
  on | off | toggle
  brightness  value 0-100
  temp        value 0-100      0 = cold white, 100 = warm white
  white       brightness, temp
  color       rgb [r, g, b], brightness
  preset      value 0-6        built-in colour sequences
  scan                        -> lamps heard recently (no identity needed)
  quit

Link strategy
-------------
A BLE connect costs 2-4 s; a command on an open link takes ~100 ms. So links
are held open. But a lamp freezes its state beacon while a central is
connected, so beacons are only trusted while disconnected, and the daemon
periodically (after some idle time) drops a link for a few seconds to pick up
a fresh beacon - that is how changes made with the remote or a wall switch get
noticed. Everything the daemon sets itself is applied optimistically.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import logging.handlers
import math
import os
import re
import signal
import sys
import time
from typing import Any, Optional

from bleak import BleakScanner

from . import config as C
from .client import AuthError, AwoxLight, LightState, parse_advertisement
from .devices import device_info

log = logging.getLogger("eglo-light")

WHITE_MAX = 0x7F
COLOR_MIN, COLOR_MAX = 0x0A, 0x64

# Anyone in radio range can advertise thousands of fake lamps under rotating
# addresses, so the scan path is bounded at every producer.
SEEN_MAX = 64        # advertisers kept in memory
SCAN_MAX_ROWS = 24   # rows handed to a client (strongest first)
LAMPS_MAX = 16       # lamps held in the registry (least recently asked for is evicted)

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
MESH_FIELD_MAX = 16  # the mesh protocol pads name/password into 16 bytes

# A client picks the scan wait, so it is clamped: an unbounded (or infinite)
# wait would pin a connection open and stall shutdown behind it.
SCAN_WAIT_MAX = 30.0


def pct(v: float, lo: float, hi: float) -> int:
    return int(round(max(0.0, min(100.0, (v - lo) * 100.0 / (hi - lo)))))


def unpct(p: float, lo: int, hi: int) -> int:
    return int(round(lo + max(0.0, min(100.0, p)) * (hi - lo) / 100.0))


def lamp_kind(name: str) -> str:
    """Classify a lamp by its advertised name (which is its mesh name)."""
    if name.startswith("R-"):
        return "remote"    # paired with an Eglo/AwoX remote: password is 1234
    if name == "unpaired":
        return "unpaired"  # factory state: mesh unpaired/1234
    return "app"           # app-created mesh: credentials live in the AwoX cloud account


def default_credentials(name: str) -> tuple[str, str]:
    kind = lamp_kind(name)
    if kind in ("remote", "unpaired"):
        return name, "1234"
    return "", ""


class Lamp:
    """State and link for one lamp."""

    def __init__(self, daemon: "Daemon", mac: str, mesh_name: str, mesh_password: str):
        self.daemon = daemon
        self.mac = mac
        self.mesh_name = mesh_name
        self.mesh_password = mesh_password
        self.state: Optional[LightState] = None
        self.seen_at = 0.0
        self.last_beacon: Optional[LightState] = None
        self.stale_snapshot: Optional[LightState] = None
        self.stale_until = 0.0
        self.last_command_at = 0.0
        self.last_request_at = time.monotonic()
        self.last_sync_at = time.monotonic()
        self.created_at = time.monotonic()
        self.lock = asyncio.Lock()  # serialises commands and resyncs
        self.connect_failures = 0
        self.light: Optional[AwoxLight] = None
        self.error = ""  # last link/auth problem, cleared on success
        self.keeper: Optional[asyncio.Task] = None
        self.closed = False  # set by close(); a link opened after it must not be kept
        self.product_id = 0

    @property
    def connected(self) -> bool:
        return bool(self.light and self.light.connected)

    # -- beacons ----------------------------------------------------------------
    def on_beacon(self, st: LightState, ignore_cached: bool):
        now = time.monotonic()
        self.seen_at = now
        if st.product_id:
            self.product_id = st.product_id
        if self.connected or ignore_cached:
            return  # frozen/cached content, not the lamp's live state
        self.last_beacon = st
        if now < self.stale_until and st == self.stale_snapshot:
            return  # lamp still advertising its pre-command state
        self.stale_until = 0.0
        if st != self.state:
            log.debug("%s beacon %s", self.mac, st)
        self.state = st

    # -- link -------------------------------------------------------------------
    async def ensure_connected(self) -> AwoxLight:
        if self.connected:
            return self.light  # type: ignore[return-value]
        async with self.daemon.connect_lock:
            if self.connected:
                return self.light  # type: ignore[return-value]
            if self.light:
                await self.light.disconnect()
                self.light = None
            if not self.mesh_name:
                self.error = "no mesh credentials"
                raise RuntimeError(self.error)
            heard_ago = time.monotonic() - self.seen_at if self.seen_at else None
            if heard_ago is None or heard_ago > 45.0:
                # No beacon lately: the lamp is off or out of range. Do not sit
                # in connect timeouts; the keeper retries once it is heard again.
                self.error = "lamp not reachable"
                raise RuntimeError(self.error)
            await self.daemon.stop_scan()
            try:
                last: Exception = RuntimeError("no attempt")
                for attempt in range(2):
                    light = AwoxLight(self.mac, self.mesh_name, self.mesh_password)
                    try:
                        await light.connect(timeout=8.0)
                        self.light = light
                        self.connect_failures = 0
                        self.seen_at = time.monotonic()
                        self.error = ""
                        log.info("%s link up", self.mac)
                        return light
                    except AuthError:
                        self.error = "mesh credentials rejected"
                        self.connect_failures += 1
                        raise
                    except Exception as e:  # noqa: BLE001
                        last = e
                        log.info("%s connect attempt %d failed: %s", self.mac, attempt + 1, e)
                        if "not found" in str(e).lower():
                            # BlueZ forgot the device; a short scan puts it back in its cache.
                            await BleakScanner.find_device_by_address(self.mac, timeout=4.0)
                        else:
                            await asyncio.sleep(0.5 * (attempt + 1))
                self.connect_failures += 1
                self.error = "lamp not reachable"
                raise RuntimeError(f"could not connect to lamp: {last}")
            finally:
                await self.daemon.start_scan()

    async def drop_link(self):
        if self.light:
            await self.light.disconnect()
            self.light = None
        await self.daemon.start_scan()

    async def resync(self):
        async with self.lock:
            log.debug("%s resync", self.mac)
            await self.drop_link()
            self.stale_snapshot = self.last_beacon
            self.stale_until = time.monotonic() + C.SYNC_WINDOW_SEC
            try:
                await asyncio.wait_for(self.daemon.stopping.wait(), timeout=C.SYNC_WINDOW_SEC)
            except asyncio.TimeoutError:
                pass
            self.last_sync_at = time.monotonic()

    async def link_keeper(self):
        while not self.daemon.stopping.is_set():
            now = time.monotonic()
            if not self.connected:
                if self.state is None and now - self.created_at < 4.0:
                    delay = 0.5  # give the first beacons a chance before connecting
                elif self.error == "mesh credentials rejected" and self.connect_failures >= 2:
                    delay = 60.0  # wrong credentials will not fix themselves; back off hard
                elif not self.seen_at or now - self.seen_at > 45.0:
                    delay = 3.0   # silent lamp: wait for a beacon instead of trying to connect
                else:
                    try:
                        await self.ensure_connected()
                    except Exception as e:  # noqa: BLE001
                        log.info("%s link down: %s", self.mac, e)
                    delay = 1.0 if self.connected else min(30.0, 2.0 * (2 ** min(self.connect_failures, 4)))
            else:
                if now - self.last_command_at > C.SYNC_IDLE_SEC and now - self.last_sync_at > C.SYNC_INTERVAL_SEC:
                    await self.resync()
                delay = 1.0
            try:
                await asyncio.wait_for(self.daemon.stopping.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def close(self):
        # Never called from inside run()/resync(), so taking the lock here is safe
        # and makes close() wait for an in-flight command (run() holds the lock
        # across ensure_connected()) instead of orphaning the link it opens.
        self.closed = True
        if self.keeper:
            self.keeper.cancel()
            self.keeper = None
        async with self.lock:
            if self.light:
                await self.light.disconnect()
                self.light = None

    # -- state ------------------------------------------------------------------
    def _optimistic(self, **changes):
        base = self.state or LightState(0, 1, True, WHITE_MAX, 0x40, COLOR_MAX, 255, 255, 255)
        fields = base.__dict__.copy()
        fields.update(changes)
        fields["product_id"] = self.product_id
        self.state = LightState(**fields)
        self.seen_at = time.monotonic()

    def state_json(self) -> dict[str, Any]:
        st = self.state
        seen_ago = (time.monotonic() - self.seen_at) if self.seen_at else None
        out: dict[str, Any] = {
            "mac": self.mac,
            "available": self.connected or (seen_ago is not None and seen_ago < 90),
            "connected": self.connected,
            "seen_ago": None if seen_ago is None else round(seen_ago, 1),
            "error": self.error,
            "bluetooth": self.daemon.bluetooth_ok,
            "device": device_info(self.product_id) if self.product_id else None,
        }
        if not st:
            return out
        color_mode = st.is_color_mode or st.mode in (2, 6)
        out.update({
            "on": st.on,
            "mode": "color" if color_mode else "white",
            "brightness": pct(st.color_brightness, COLOR_MIN, COLOR_MAX) if color_mode else pct(st.white_brightness, 1, WHITE_MAX),
            "temp": pct(st.white_temp, 0, WHITE_MAX),
            "rgb": [st.red, st.green, st.blue],
        })
        return out

    # -- commands ---------------------------------------------------------------
    async def run(self, cmd: str, req: dict[str, Any]) -> dict[str, Any]:
        async with self.lock:
            self.last_command_at = time.monotonic()
            if cmd == "toggle":
                cmd = "off" if (self.state and self.state.on) else "on"
            try:
                light = await self.ensure_connected()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": self.error or str(e), "state": self.state_json()}
            if self.closed:
                # Closed while we were connecting: drop the link we just opened,
                # nobody is left to keep or tear it down.
                await light.disconnect()
                self.light = None
                return {"ok": False, "error": "lamp closed", "state": self.state_json()}
            self.stale_snapshot = self.last_beacon
            self.stale_until = time.monotonic() + 15.0
            try:
                await self._apply(light, cmd, req)
            except Exception as e:  # noqa: BLE001
                log.warning("%s command %s failed: %s", self.mac, cmd, e)
                await self.drop_link()  # keeper reconnects
                return {"ok": False, "error": str(e), "state": self.state_json()}
            return {"ok": True, "state": self.state_json()}

    async def _apply(self, light: AwoxLight, cmd: str, req: dict[str, Any]):
        st = self.state
        color_mode = bool(st and (st.is_color_mode or st.mode in (2, 6)))
        if cmd == "on":
            await light.on()
            self._optimistic(mode=(3 if color_mode else 1), on=True)
        elif cmd == "off":
            await light.off()
            self._optimistic(mode=(2 if color_mode else 0), on=False)
        elif cmd == "brightness":
            p = float(req.get("value", 100))
            if color_mode:
                v = unpct(p, COLOR_MIN, COLOR_MAX)
                await light.set_color_brightness(v)
                self._optimistic(color_brightness=v)
            else:
                v = max(1, unpct(p, 0, WHITE_MAX))
                await light.set_white_brightness(v)
                self._optimistic(white_brightness=v)
        elif cmd == "temp":
            v = unpct(float(req.get("value", 50)), 0, WHITE_MAX)
            await light.set_white_temperature(v)
            self._optimistic(mode=1, on=True, white_temp=v)
        elif cmd == "white":
            b = max(1, unpct(float(req.get("brightness", 100)), 0, WHITE_MAX))
            t = unpct(float(req.get("temp", 50)), 0, WHITE_MAX)
            await light.set_white(t, b)
            self._optimistic(mode=1, on=True, white_brightness=b, white_temp=t)
        elif cmd == "color":
            r, g, b = (max(0, min(255, int(x))) for x in req.get("rgb", [255, 255, 255]))
            await light.set_color(r, g, b)
            self._optimistic(mode=3, on=True, red=r, green=g, blue=b)
            if "brightness" in req:
                v = unpct(float(req["brightness"]), COLOR_MIN, COLOR_MAX)
                await light.set_color_brightness(v)
                self._optimistic(color_brightness=v)
        elif cmd == "preset":
            n = max(0, min(6, int(req.get("value", 0))))
            await light.set_preset(n)
            self._optimistic(mode=7, on=True)
        else:
            raise ValueError(f"unknown command {cmd!r}")


class Daemon:
    def __init__(self):
        # Keyed by full identity: two clients may hold different credentials for
        # the same address, and neither may close the other's Lamp.
        self.lamps: dict[tuple[str, str, str], Lamp] = {}
        self.lamps_by_mac: dict[str, list[Lamp]] = {}
        self.seen: dict[str, dict[str, Any]] = {}  # every AwoX lamp heard, for setup scans
        self.scanner: Optional[BleakScanner] = None
        self.scan_lock = asyncio.Lock()
        self.connect_lock = asyncio.Lock()  # one BLE connect at a time (scanner is paused)
        self.beacon_ignore_until = 0.0      # BlueZ replays cached beacons on scan start
        self.bluetooth_ok = True
        self.bluetooth_error = ""
        self.last_request_at = time.monotonic()
        self.started_at = time.monotonic()
        self.stopping = asyncio.Event()
        self.clients: set[asyncio.Task] = set()  # one task per open connection

    # -- scanning ---------------------------------------------------------------
    def _on_adv(self, dev, adv):
        st = parse_advertisement(adv.manufacturer_data)
        if not st:
            return
        mac = dev.address.upper()
        now = time.monotonic()
        known = self.seen.get(mac)
        if known is None and len(self.seen) >= SEEN_MAX:
            # At capacity: only a stronger advertiser may displace the weakest
            # (oldest wins a tie), so a flood of weak fakes cannot grow memory.
            weak_mac, weak = min(self.seen.items(), key=lambda kv: (kv[1]["rssi"], -kv[1]["seen_at"]))
            if adv.rssi <= weak["rssi"]:
                return
            del self.seen[weak_mac]
        name = adv.local_name or dev.name or (known or {}).get("name") or ""
        self.seen[mac] = {"mac": mac, "name": name, "rssi": adv.rssi, "seen_at": now, "state": st}
        ignore_cached = time.monotonic() < self.beacon_ignore_until
        for lamp in list(self.lamps_by_mac.get(mac, ())):
            lamp.on_beacon(st, ignore_cached)

    async def start_scan(self):
        async with self.scan_lock:
            if self.scanner:
                return
            scanner = BleakScanner(self._on_adv)
            self.beacon_ignore_until = max(self.beacon_ignore_until, time.monotonic() + 1.0)
            try:
                await scanner.start()
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "InProgress" in msg or "in progress" in msg.lower():
                    log.debug("scan start busy, will retry: %s", msg)
                    return  # scan_watchdog retries shortly
                self.bluetooth_ok = False
                self.bluetooth_error = msg
                log.warning("scan start failed: %s", msg)
                return
            self.scanner = scanner
            if not self.bluetooth_ok:
                log.info("bluetooth back")
            self.bluetooth_ok = True
            self.bluetooth_error = ""

    async def stop_scan(self):
        async with self.scan_lock:
            if not self.scanner:
                return
            try:
                await self.scanner.stop()
            except Exception as e:  # noqa: BLE001
                log.debug("scan stop: %s", e)
            self.scanner = None

    async def scan_watchdog(self):
        """Retry scanning while Bluetooth is down so the bar notices when it returns."""
        while not self.stopping.is_set():
            await asyncio.sleep(5)
            if not self.scanner and not self.connect_lock.locked():
                await self.start_scan()
            cutoff = time.monotonic() - C.SEEN_TTL_SEC
            for mac in [m for m, d in self.seen.items() if d["seen_at"] < cutoff]:
                del self.seen[mac]

    # -- lamps ------------------------------------------------------------------
    async def lamp_for(self, req: dict[str, Any]) -> Lamp:
        mac = str(req.get("mac", "")).upper()
        if not mac:
            raise ValueError("no lamp configured")
        if not MAC_RE.match(mac):
            raise ValueError("invalid lamp address")
        name, password = str(req.get("mesh_name", "")), str(req.get("mesh_password", ""))
        if len(name.encode()) > MESH_FIELD_MAX or len(password.encode()) > MESH_FIELD_MAX:
            raise ValueError("mesh credentials too long")
        key = (mac, name, password)
        lamp = self.lamps.get(key)
        if lamp:
            lamp.last_request_at = time.monotonic()
            return lamp
        while len(self.lamps) >= LAMPS_MAX:
            await self._evict_lamp()
        lamp = Lamp(self, mac, name, password)
        seen = self.seen.get(mac)
        if seen:
            lamp.on_beacon(seen["state"], False)
        self.lamps[key] = lamp
        self.lamps_by_mac.setdefault(mac, []).append(lamp)
        lamp.keeper = asyncio.create_task(lamp.link_keeper())
        log.info("%s registered (mesh %s)", mac, name or "?")
        return lamp

    async def _evict_lamp(self):
        """Drop the least recently requested lamp, link and all."""
        key = min(self.lamps, key=lambda k: self.lamps[k].last_request_at)
        lamp = self.lamps.pop(key)
        peers = self.lamps_by_mac.get(lamp.mac)
        if peers is not None:
            self.lamps_by_mac[lamp.mac] = [l for l in peers if l is not lamp]
            if not self.lamps_by_mac[lamp.mac]:
                del self.lamps_by_mac[lamp.mac]
        log.info("%s evicted (mesh %s)", lamp.mac, lamp.mesh_name or "?")
        await lamp.close()  # close() waits for any in-flight command on this lamp

    def scan_json(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        rows = []
        for d in sorted(self.seen.values(), key=lambda d: -d["rssi"])[:SCAN_MAX_ROWS]:
            name, password = default_credentials(d["name"])
            info = device_info(d["state"].product_id)
            rows.append({
                "mac": d["mac"], "name": d["name"], "rssi": d["rssi"],
                "model": info["model"], "product": info["name"], "device_kind": info["kind"], "known": info["known"],
                "seen_ago": round(now - d["seen_at"], 1),
                "kind": lamp_kind(d["name"]),
                "mesh_name": name, "mesh_password": password,
            })
        return rows

    # -- requests ---------------------------------------------------------------
    async def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        cmd = str(req.get("cmd", "status"))
        self.last_request_at = time.monotonic()
        if cmd == "quit":
            self.stopping.set()
            return {"ok": True}
        if cmd == "scan":
            # Let a freshly started daemon hear the neighbourhood first. The wait
            # comes from the client, so it is clamped: non-finite (inf/NaN) and
            # negative values become 0 and the rest is capped, and the loop also
            # ends on shutdown so a scan can never hold the daemon open.
            try:
                wait = float(req.get("wait", 0))
            except (TypeError, ValueError):
                wait = 0.0
            if not math.isfinite(wait) or wait < 0:
                wait = 0.0
            wait = min(wait, SCAN_WAIT_MAX)
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline and self.bluetooth_ok and not self.stopping.is_set():
                await asyncio.sleep(0.2)
            return {"ok": True, "lamps": self.scan_json(), "bluetooth": self.bluetooth_ok, "error": self.bluetooth_error}
        lamp = await self.lamp_for(req)
        if cmd == "status":
            deadline = time.monotonic() + 2.5
            while lamp.state is None and time.monotonic() - lamp.created_at < 6.0 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            return {"ok": True, "state": lamp.state_json()}
        log.info("%s command %s", lamp.mac, json.dumps({k: v for k, v in req.items() if k not in ("mac", "mesh_name", "mesh_password")}))
        return await lamp.run(cmd, req)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        # Registered so shutdown can cancel a client parked in readline(); the
        # transport only detaches once this handler returns and closes it.
        task = asyncio.current_task()
        if task is not None:
            self.clients.add(task)
        try:
            while not reader.at_eof():
                try:
                    line = await reader.readline()
                except (ValueError, asyncio.LimitOverrunError) as e:
                    # Line past the stream limit: the buffer is unusable, so
                    # answer once and drop the connection.
                    log.info("oversized request dropped: %s", e)
                    try:
                        writer.write((json.dumps({"ok": False, "error": "request too long"}) + "\n").encode())
                        await writer.drain()
                    except (OSError, ConnectionResetError, BrokenPipeError):
                        pass
                    break
                if not line:
                    break
                try:
                    resp = await self.handle(json.loads(line))
                except Exception as e:  # noqa: BLE001
                    resp = {"ok": False, "error": str(e)}
                try:
                    writer.write((json.dumps(resp) + "\n").encode())
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    break
        finally:
            if task is not None:
                self.clients.discard(task)
            writer.close()

    async def idle_watchdog(self):
        while not self.stopping.is_set():
            await asyncio.sleep(30)
            if time.monotonic() - self.last_request_at > C.DAEMON_IDLE_EXIT_SEC:
                log.info("no clients for a while, exiting")
                self.stopping.set()

    async def serve(self):
        # The runtime dir was verified in main(); never created here.
        try:  # lstat, not exists(): unlink a symlink planted at the path instead of following it
            os.lstat(C.SOCKET_PATH)
            C.SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
        server = await asyncio.start_unix_server(self.handle_client, path=str(C.SOCKET_PATH))
        os.chmod(C.SOCKET_PATH, 0o600)
        loop = asyncio.get_running_loop()

        def on_signal():
            if self.stopping.is_set():
                # Second signal: something is wedging the drain. Free the path
                # so a successor can bind, then go without waiting further.
                try:
                    C.SOCKET_PATH.unlink()
                except OSError:
                    pass
                log.warning("second signal, exiting immediately")
                os._exit(1)
            self.stopping.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, on_signal)
        await self.start_scan()
        log.info("listening on %s", C.SOCKET_PATH)
        tasks = [asyncio.create_task(self.idle_watchdog()), asyncio.create_task(self.scan_watchdog())]
        await self.stopping.wait()
        # Shutdown is bounded: stop accepting, free the path, cancel the client
        # handlers (their transports only detach once the handler returns), then
        # wait a little for wait_closed() - never forever.
        server.close()
        try:
            C.SOCKET_PATH.unlink()  # free the path first so a successor can bind at once
        except FileNotFoundError:
            pass
        await asyncio.sleep(0.05)  # let an in-flight reply (e.g. to quit) flush
        for t in list(self.clients):
            t.cancel()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=5.0)
        except (TimeoutError, asyncio.TimeoutError):
            log.warning("clients did not detach in time, shutting down anyway")
        for t in tasks:
            t.cancel()

        async def teardown():
            for lamp in self.lamps.values():
                await lamp.close()
            await self.stop_scan()
        try:
            await asyncio.wait_for(teardown(), timeout=3.0)
        except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            log.info("teardown cut short: %s", e)


def main():
    # Everything we create (log, rotated log, socket) must be owner-only; the
    # RotatingFileHandler opens by pathname and honours the umask, so set it here.
    os.umask(0o077)
    try:
        C.require_runtime_dir()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    # Single instance. A racing spawner waits briefly for a stopping daemon to
    # let go of the lock, then gives up if another daemon is serving.
    # O_NOFOLLOW and no truncation: a planted symlink must not be followed or clobbered.
    lock = os.fdopen(
        os.open(C.LOCK_PATH, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600), "r+b"
    )
    os.fchmod(lock.fileno(), 0o600)  # files left by an older version may be 0644
    for _ in range(100):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            time.sleep(0.1)
    else:
        return 0
    handler = logging.handlers.RotatingFileHandler(C.LOG_PATH, maxBytes=256_000, backupCount=1)
    os.fchmod(handler.stream.fileno(), 0o600)
    handlers: list[logging.Handler] = [handler]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("EGLO_DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    asyncio.run(Daemon().serve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
