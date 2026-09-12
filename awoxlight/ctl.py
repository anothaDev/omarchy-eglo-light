"""lightctl: talk to the daemon (starting it on demand).

  lightctl [lamp options] status [--json]
  lightctl [lamp options] on | off | toggle
  lightctl [lamp options] brightness <0-100>
  lightctl [lamp options] temp <0-100>          0 = cold white, 100 = warm white
  lightctl [lamp options] white [brightness] [temp]
  lightctl [lamp options] color <r> <g> <b> [brightness]
  lightctl [lamp options] color '#rrggbb'
  lightctl [lamp options] preset <0-6>
  lightctl scan [--json] [--wait SEC]           lamps in range and their mesh
  lightctl stop                                 stop the daemon

Lamp options (or environment variables LIGHT_MAC, MESH_NAME, MESH_PASSWORD):
  --mac A4:C1:38:..   --mesh-name R-XXXXXX   --mesh-password 1234

Prefer the environment variables: command-line options are visible to every
other local user through `ps` / /proc, so --mesh-password leaks the secret.

A lamp paired with the Eglo/AwoX remote advertises its mesh name (R-XXXXXX)
and uses password 1234. A factory-fresh lamp is "unpaired" / 1234. A lamp set
up in the AwoX/Eglo app uses the credentials of that app account.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .config import LOCK_PATH, LOG_PATH, RUNTIME_DIR, SOCKET_PATH, require_runtime_dir

PKG_ROOT = Path(__file__).resolve().parent.parent


def _connect(timeout: float = 4.0) -> socket.socket | None:
    if SOCKET_PATH is None:
        return None
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(SOCKET_PATH))
        return s
    except OSError:
        s.close()
        return None


def _spawn_daemon() -> None:
    # The runtime dir must pre-exist and have been verified; we never create it.
    # O_NOFOLLOW|0600 so a planted symlink cannot redirect the log elsewhere.
    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    os.fchmod(fd, 0o600)  # a log left by an older version may be 0644
    out = os.fdopen(fd, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "awoxlight.daemon"],
        stdin=subprocess.DEVNULL, stdout=out, stderr=out,
        start_new_session=True, close_fds=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(PKG_ROOT), os.environ.get("PYTHONPATH", "")]))},
    )


MAX_REPLY_BYTES = 1_000_000  # a reply larger than this is a bug or an attack, never a real scan


def request(req: dict[str, Any], start: bool = True, timeout: float = 30.0) -> dict[str, Any]:
    try:
        require_runtime_dir()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    s = _connect()
    if s is None and start:
        _spawn_daemon()
        for _ in range(150):
            time.sleep(0.1)
            s = _connect()
            if s:
                break
    if s is None:
        return {"ok": False, "error": "daemon not running"}
    with s:
        s.settimeout(timeout)
        buf = b""
        deadline = time.monotonic() + timeout
        try:
            s.sendall((json.dumps(req) + "\n").encode())
            while not buf.endswith(b"\n"):
                # A slow trickle must not extend the wait past the total timeout.
                s.settimeout(max(0.1, deadline - time.monotonic()))
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_REPLY_BYTES:
                    return {"ok": False, "error": "reply too large"}
                if time.monotonic() >= deadline:
                    return {"ok": False, "error": "daemon did not answer (timeout)"}
        except (socket.timeout, OSError) as e:
            return {"ok": False, "error": f"daemon did not answer ({e.__class__.__name__})"}
    try:
        return json.loads(buf or b"{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": f"bad reply: {buf!r}"}


def stop_daemon() -> dict[str, Any]:
    resp = request({"cmd": "quit"}, start=False)
    for _ in range(50):  # make stop synchronous so a restart cannot race it
        if SOCKET_PATH is None or not SOCKET_PATH.exists():
            break
        time.sleep(0.1)
    else:
        # The socket path is still there: the daemon did not finish stopping, so
        # do not report success to a caller about to start a replacement.
        return {"ok": False, "error": "daemon did not stop"}
    return resp


def parse_color(args: list[str]) -> tuple[list[int], list[str]]:
    if args and args[0].startswith("#") and len(args[0]) == 7:
        h = args[0][1:]
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)], args[1:]
    return [int(x) for x in args[:3]], args[3:]


def human(state: dict[str, Any]) -> str:
    if not state.get("bluetooth", True):
        return "bluetooth unavailable"
    if state.get("error"):
        return f"error: {state['error']}"
    if not state.get("available") or "on" not in state:
        return "lamp not seen"
    if not state["on"]:
        return "off"
    if state["mode"] == "color":
        r, g, b = state["rgb"]
        return f"on, colour #{r:02x}{g:02x}{b:02x} at {state['brightness']}%"
    return f"on, white {state['brightness']}% (warmth {state['temp']}%)"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    lamp: dict[str, str] = {
        "mac": os.environ.get("LIGHT_MAC", ""),
        "mesh_name": os.environ.get("MESH_NAME", ""),
        "mesh_password": os.environ.get("MESH_PASSWORD", ""),
    }
    wait = 0.0
    rest: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--mac", "--mesh-name", "--mesh-password", "--wait") and i + 1 < len(argv):
            if a == "--wait":
                wait = float(argv[i + 1])
            else:
                lamp[a[2:].replace("-", "_")] = argv[i + 1]
            i += 2
        else:
            rest.append(a)
            i += 1
    cmd, args = (rest[0] if rest else "status"), rest[1:]
    lamp["mac"] = lamp["mac"].upper()

    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd == "stop":
        resp = stop_daemon()
    elif cmd == "scan":
        resp = request({"cmd": "scan", "wait": wait or 6.0}, timeout=60)
        if not as_json:
            if not resp.get("ok"):
                print("error:", resp.get("error"), file=sys.stderr)
                return 1
            if not resp.get("bluetooth", True):
                print("bluetooth unavailable:", resp.get("error", ""), file=sys.stderr)
                return 1
            for row in resp.get("lamps", []):
                creds = f"{row['mesh_name']} / {row['mesh_password']}" if row["mesh_name"] else "(app mesh: credentials from your AwoX account)"
                print(f"{row['mac']}  {row['name'] or '?':12}  rssi {row['rssi']:4}  {row['kind']:8}  {row.get('product', '?')} ({row.get('model', '?')})  {creds}")
            if not resp.get("lamps"):
                print("no lamps heard; power one on nearby and try again")
            return 0
    elif cmd in ("status", "on", "off", "toggle"):
        resp = request({"cmd": cmd, **lamp})
    elif cmd in ("brightness", "temp", "preset"):
        resp = request({"cmd": cmd, "value": float(args[0]), **lamp})
    elif cmd == "white":
        req: dict[str, Any] = {"cmd": "white", **lamp}
        if args:
            req["brightness"] = float(args[0])
        if len(args) > 1:
            req["temp"] = float(args[1])
        resp = request(req)
    elif cmd == "color":
        rgb, extra = parse_color(args)
        req = {"cmd": "color", "rgb": rgb, **lamp}
        if extra:
            req["brightness"] = float(extra[0])
        resp = request(req)
    else:
        print(__doc__)
        return 2

    if as_json:
        print(json.dumps(resp))
    elif resp.get("ok"):
        print(human(resp["state"]) if "state" in resp else "ok")
    else:
        print("error:", resp.get("error", "unknown"), file=sys.stderr)
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
