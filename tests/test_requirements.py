"""Supply-chain guard rails for the venv the bar plugin builds on first run.

Invariant: the installer only ever installs the exact, hash-verified
artefacts the maintainer reviewed. That needs two halves to stay true --
requirements.txt must pin every requirement with == and carry at least one
sha256 hash, and bin/lightctl must ask pip to enforce those pins.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
LIGHTCTL = ROOT / "bin" / "lightctl"


def _requirement_blocks():
    """Yield (line number, joined text) for each requirement in the file."""
    blocks = []
    start = 0
    buf = ""
    for lineno, raw in enumerate(REQUIREMENTS.read_text().splitlines(), 1):
        line = re.sub(r"(^|\s)#.*$", "", raw).strip()
        if not line and not buf:
            continue
        if not buf:
            start = lineno
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            blocks.append((start, buf.strip()))
        buf = ""
    if buf.strip():
        blocks.append((start, buf.strip()))
    return blocks


def test_requirements_file_is_not_empty():
    blocks = _requirement_blocks()
    assert blocks, "requirements.txt lists no requirements"
    names = {re.split(r"[=<>!\[ ]", text, maxsplit=1)[0].lower() for _, text in blocks}
    # bleak's Linux backend is a transitive dep, but the installer runs with
    # --no-deps, so it has to be pinned here explicitly or the venv is broken.
    assert {"bleak", "pycryptodome", "dbus-fast"} <= names, names


def test_every_requirement_is_pinned_and_hashed():
    for lineno, text in _requirement_blocks():
        where = f"requirements.txt:{lineno}: {text[:60]}"
        assert "==" in text.split("--hash")[0], f"{where} is not pinned with =="
        assert re.search(r"--hash=sha256:[0-9a-f]{64}\b", text), (
            f"{where} carries no --hash=sha256"
        )


def test_launcher_enforces_the_pins():
    script = LIGHTCTL.read_text()
    install = [ln for ln in script.splitlines() if "pip" in ln and "install" in ln]
    assert install, "no pip install line in bin/lightctl"
    for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", "--isolated"):
        assert flag in script, f"bin/lightctl does not pass {flag} to pip"
    assert re.search(r'-r "\$here/requirements\.txt"', script), (
        "bin/lightctl does not install from requirements.txt"
    )
    # No loose package names on the pip command line; -r is the only source.
    for line in install:
        assert "bleak" not in line and "pycryptodome" not in line, line
