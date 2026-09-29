#!/bin/bash
# Double-click to start the NMS Item Manifest.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo
    echo "  Python is not installed, and this tool needs it."
    echo "  Get it from   https://www.python.org/downloads/"
    echo
    read -r -p "Press return to close."
    exit 1
fi

python3 -c "import lz4" 2>/dev/null || {
    echo "Installing the one dependency (lz4)..."
    python3 -m pip install --quiet lz4 || {
        echo "Could not install lz4. Try:  python3 -m pip install lz4"
        read -r -p "Press return to close."; exit 1; }
}

python3 manifest.py "$@"
