"""SEC-003: mesh credentials must reach lightctl through the environment.

The bar widget spawns `lightctl` on every poll; anything in argv is readable by
every other local user via `ps` / /proc/<pid>/cmdline, so the credentials are
passed as LIGHT_MAC / MESH_NAME / MESH_PASSWORD instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from awoxlight import ctl  # noqa: E402

PANEL = Path(__file__).resolve().parent.parent / "Panel.qml"


@pytest.fixture
def captured(monkeypatch):
    seen: list[dict] = []

    def fake_request(req, start=True, timeout=30.0):
        seen.append(req)
        return {"ok": True, "state": {"bluetooth": True, "available": False}}

    monkeypatch.setattr(ctl, "request", fake_request)
    return seen


def test_credentials_come_from_the_environment(captured, monkeypatch, capsys):
    monkeypatch.setenv("LIGHT_MAC", "a4:c1:38:aa:bb:cc")
    monkeypatch.setenv("MESH_NAME", "R-D9C2DB")
    monkeypatch.setenv("MESH_PASSWORD", "s3cret")

    argv = ["status", "--json"]
    assert ctl.main(list(argv)) == 0

    assert len(captured) == 1
    req = captured[0]
    assert req["cmd"] == "status"
    assert req["mac"] == "A4:C1:38:AA:BB:CC"  # uppercased
    assert req["mesh_name"] == "R-D9C2DB"
    assert req["mesh_password"] == "s3cret"
    # The credentials came from the environment, not from the command line.
    assert not any(a.startswith("--mesh") or a == "--mac" for a in argv)
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_options_still_win_for_interactive_users(captured, monkeypatch):
    monkeypatch.setenv("LIGHT_MAC", "a4:c1:38:aa:bb:cc")
    monkeypatch.delenv("MESH_NAME", raising=False)
    monkeypatch.delenv("MESH_PASSWORD", raising=False)

    ctl.main(["--mesh-name", "R-OTHER", "--mesh-password", "1234", "on", "--json"])
    assert captured[0]["mesh_name"] == "R-OTHER"
    assert captured[0]["mesh_password"] == "1234"


def test_unconfigured_env_yields_empty_lamp(captured, monkeypatch):
    for name in ("LIGHT_MAC", "MESH_NAME", "MESH_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    ctl.main(["status", "--json"])
    assert captured[0]["mac"] == ""
    assert captured[0]["mesh_name"] == ""
    assert captured[0]["mesh_password"] == ""


def test_panel_never_puts_credentials_in_argv():
    src = PANEL.read_text()
    for flag in ("--mesh-password", "--mesh-name", "--mac"):
        assert f'"{flag}"' not in src, f"{flag} must not appear in a spawned command line"
    assert "MESH_PASSWORD: meshPassword" in src
    assert "environment: root.lampEnv" in src
    assert src.count("environment: root.lampEnv") == 2
