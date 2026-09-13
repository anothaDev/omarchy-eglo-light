#!/usr/bin/env bash
# Run the test suite in a throwaway virtualenv under .venv/ (git-ignored):
# the pinned runtime dependencies from requirements.txt plus pytest.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --disable-pip-version-check --require-hashes --only-binary=:all: --no-deps -r requirements.txt
  .venv/bin/pip install --quiet --disable-pip-version-check --only-binary=:all: pytest
fi
PYTHONPATH=. exec .venv/bin/python -m pytest -q tests "$@"
