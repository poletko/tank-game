#!/usr/bin/env bash
# Tank Arena launcher. Pass --windowed to start in a window.
cd "$(dirname "$0")"
python3 -c "import pygame" 2>/dev/null || { echo "pygame missing: sudo apt install python3-pygame  (or: pip install pygame)"; exit 1; }
exec python3 tanks.py "$@"
