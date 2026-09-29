#!/bin/bash
# Linux and Steam Deck. Double-click in Desktop Mode, or run from a terminal.
cd "$(dirname "$0")" || exit 1

command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required."; exit 1; }
python3 -c "import lz4" 2>/dev/null || {
    echo "Installing the one dependency (lz4)..."
    python3 -m pip install --quiet --user lz4 || {
        echo "Could not install lz4. Try:  python3 -m pip install --user lz4"; exit 1; }
}

exec python3 kitchen.py "$@"
