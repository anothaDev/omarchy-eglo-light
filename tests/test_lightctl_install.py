"""SEC-006: an interrupted or failed install must converge to a retry.

The first-run installer used to hold a lock *directory*; if it was killed the
directory stayed behind forever and every later launch reported
``{"installing": true}`` until the user deleted the data dir by hand. The lock
is now an ``flock`` on a file (released by the kernel when the holder dies) and
``install.failed`` expires after 10 minutes.

The tests run the real launcher under a throwaway XDG_DATA_HOME with a stub
``python3`` first on PATH, so no venv is ever created and no wheel downloaded.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIGHTCTL = ROOT / "bin" / "lightctl"

# `python3 -m venv` sleeps, so a second launch reliably observes a held lock;
# every other call (report()'s json.dumps) fails instantly.
STUB = """#!/usr/bin/env bash
for a in "$@"; do
  if [[ $a == venv ]]; then
    sleep 1.5
    echo "stub: refusing to build a venv" >&2
    exit 1
  fi
done
exit 1
"""


@pytest.fixture
def env(tmp_path):
    binpath = tmp_path / "stubbin"
    binpath.mkdir()
    stub = binpath / "python3"
    stub.write_text(STUB)
    stub.chmod(0o755)
    e = dict(os.environ)
    e["XDG_DATA_HOME"] = str(tmp_path / "share")
    e["PATH"] = f"{binpath}:{e['PATH']}"
    return e


def data_dir(env) -> Path:
    return Path(env["XDG_DATA_HOME"]) / "eglo-light"


def run(env):
    return subprocess.run(
        [str(LIGHTCTL), "--json", "status"],
        env=env, capture_output=True, text=True, timeout=30,
    )


def lock_is_free(path: Path) -> bool:
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_launcher_parses():
    subprocess.run(["bash", "-n", str(LIGHTCTL)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", "-S", "warning", str(LIGHTCTL)], check=True)


def test_stale_lock_file_does_not_wedge_the_launcher(env):
    data = data_dir(env)
    data.mkdir(parents=True)
    lock = data / "install.lock"
    # What a killed installer used to leave behind: the lock file exists but
    # nobody holds an flock on it.
    lock.write_text("2020-01-01T00:00:00+00:00 pid=1234\n")
    assert lock_is_free(lock)

    first = run(env)
    assert first.returncode == 3
    assert json.loads(first.stdout)["installing"] is True

    # The stale file did not block the retry, and the fresh installer now
    # really holds the lock: a second launch reports installing for that
    # reason, not because of a leftover file.
    second = run(env)
    assert second.returncode == 3
    assert json.loads(second.stdout)["installing"] is True
    assert not lock_is_free(lock)

    # When the (stubbed, failing) installer exits, the kernel frees the lock
    # and the failure is recorded.
    assert wait_for(lambda: lock_is_free(lock))
    assert wait_for(lambda: (data / "install.failed").exists())


def test_fresh_failure_is_reported(env):
    data = data_dir(env)
    data.mkdir(parents=True)
    (data / "install.failed").touch()
    (data / "install.log").write_text("ERROR: could not reach pypi.org\n")

    res = run(env)
    assert res.returncode == 1
    out = json.loads(res.stdout)
    assert out["failed"] is True
    assert "install.log" in out["error"]
    # No installer was started, so nothing holds the lock.
    assert lock_is_free(data / "install.lock")


def test_expired_failure_is_retried(env):
    data = data_dir(env)
    data.mkdir(parents=True)
    failed = data / "install.failed"
    failed.touch()
    old = time.time() - 20 * 60
    os.utime(failed, (old, old))

    res = run(env)
    assert res.returncode == 3
    assert json.loads(res.stdout)["installing"] is True
    # The expired marker was cleared and an install is running instead.
    assert not failed.exists()
    assert not lock_is_free(data / "install.lock")

    # ... and the retry's own failure re-arms the marker with a fresh mtime.
    assert wait_for(lambda: failed.exists())
    assert time.time() - failed.stat().st_mtime < 60
