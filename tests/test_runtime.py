"""SEC-001: runtime state must live only in a 0700 directory we own."""
from __future__ import annotations

import importlib
import os

import pytest

from awoxlight import config


def test_runtime_dir_raises_without_xdg(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    mod = importlib.reload(config)
    try:
        assert mod.RUNTIME_DIR is None
        assert mod.SOCKET_PATH is None and mod.LOG_PATH is None and mod.LOCK_PATH is None
        with pytest.raises(RuntimeError, match="XDG_RUNTIME_DIR"):
            mod.runtime_dir()
        with pytest.raises(RuntimeError, match="XDG_RUNTIME_DIR"):
            mod.require_runtime_dir()
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_no_tmp_fallback(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    mod = importlib.reload(config)
    try:
        assert "/tmp" not in str(mod.RUNTIME_DIR)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_verify_accepts_private_dir(tmp_path):
    d = tmp_path / "runtime"
    d.mkdir(mode=0o700)
    assert config.verify_runtime_dir(d) == d


def test_verify_rejects_group_or_other_access(tmp_path):
    d = tmp_path / "loose"
    d.mkdir(mode=0o755)
    with pytest.raises(RuntimeError, match="other users"):
        config.verify_runtime_dir(d)


def test_verify_rejects_symlink_to_dir(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="not usable"):
        config.verify_runtime_dir(link)


def test_verify_rejects_missing_and_non_dir(tmp_path):
    with pytest.raises(RuntimeError, match="not usable"):
        config.verify_runtime_dir(tmp_path / "nope")
    f = tmp_path / "file"
    f.write_text("x")
    with pytest.raises(RuntimeError, match="not usable"):
        config.verify_runtime_dir(f)


def test_verify_rejects_foreign_owner(tmp_path, monkeypatch):
    d = tmp_path / "runtime"
    d.mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(d).st_uid + 1)
    with pytest.raises(RuntimeError, match="not owned by"):
        config.verify_runtime_dir(d)


def test_request_reports_missing_runtime_dir(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    importlib.reload(config)
    from awoxlight import ctl
    mod = importlib.reload(ctl)
    try:
        resp = mod.request({"cmd": "status"}, start=True)
        assert resp["ok"] is False
        assert "XDG_RUNTIME_DIR" in resp["error"]
    finally:
        monkeypatch.undo()
        importlib.reload(config)
        importlib.reload(ctl)
