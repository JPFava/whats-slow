#!/usr/bin/env bash
# Usage: bash run.sh
# Extra options are passed through, for example: bash run.sh --seconds 20 --repeat 3
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed."
  echo "Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip"
  echo "Fedora: sudo dnf install python3"
  echo "macOS: install Python 3 from https://www.python.org/downloads/ or: brew install python"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Setting up a private Python environment in this folder..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --disable-pip-version-check -q -r requirements.txt
echo
echo "Watching the PC. A pause of several seconds is the measurement."
echo
python -m whats_slow --open "$@"
echo
echo "A copy is in the reports folder."
