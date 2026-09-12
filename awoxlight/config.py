"""Runtime paths and tunables. Lamp identity (MAC, mesh credentials) is not
stored here: the Omarchy widget keeps it in its own settings and sends it with
every request, so one daemon can serve any number of lamps."""
from __future__ import annotations

import os
from pathlib import Path

# Runtime state (socket, log, lock) only ever lives in XDG_RUNTIME_DIR. There is
# deliberately no /tmp fallback: a predictable path in world-writable /tmp lets
# another local UID pre-create the directory and hijack the socket, log or lock.
NO_RUNTIME_DIR_MSG = (
    "XDG_RUNTIME_DIR is not set; run from a desktop session "
    "or set XDG_RUNTIME_DIR=/run/user/$UID"
)

_xdg = os.environ.get("XDG_RUNTIME_DIR") or ""
RUNTIME_DIR: Path | None = Path(_xdg) if _xdg else None
SOCKET_PATH: Path | None = RUNTIME_DIR / "eglo-light.sock" if RUNTIME_DIR else None
LOG_PATH: Path | None = RUNTIME_DIR / "eglo-light.log" if RUNTIME_DIR else None
LOCK_PATH: Path | None = RUNTIME_DIR / "eglo-light.lock" if RUNTIME_DIR else None


def runtime_dir() -> Path:
    """The runtime directory, or RuntimeError if the environment has none."""
    if RUNTIME_DIR is None:
        raise RuntimeError(NO_RUNTIME_DIR_MSG)
    return RUNTIME_DIR


def verify_runtime_dir(path: "Path | str | None" = None) -> Path:
    """Check that `path` is a real directory owned by us with no group/other
    access. Opened with O_NOFOLLOW so a symlink planted at the path is rejected
    rather than followed. Raises RuntimeError otherwise; never creates anything."""
    p = runtime_dir() if path is None else Path(path)
    try:
        fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as e:
        raise RuntimeError(f"runtime directory {p} is not usable: {e}") from e
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    if st.st_uid != os.getuid():
        raise RuntimeError(f"runtime directory {p} is not owned by uid {os.getuid()}")
    if st.st_mode & 0o077:
        raise RuntimeError(f"runtime directory {p} is accessible to other users (want mode 0700)")
    return p


def require_runtime_dir() -> Path:
    """runtime_dir() + verify_runtime_dir(); the one call sites should use."""
    return verify_runtime_dir(runtime_dir())

# Exit when nobody has talked to the daemon for this long (the bar polls it).
DAEMON_IDLE_EXIT_SEC = float(os.environ.get("EGLO_DAEMON_IDLE_EXIT_SEC", 600))
# A held link freezes the lamp's beacon; drop it now and then to resync.
SYNC_IDLE_SEC = float(os.environ.get("EGLO_SYNC_IDLE_SEC", 20))
SYNC_INTERVAL_SEC = float(os.environ.get("EGLO_SYNC_INTERVAL_SEC", 90))
SYNC_WINDOW_SEC = float(os.environ.get("EGLO_SYNC_WINDOW_SEC", 7))
# Forget lamps not heard from in this long (setup scan results).
SEEN_TTL_SEC = 60.0
