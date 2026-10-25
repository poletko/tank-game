@echo off
rem Tank Arena launcher for Windows (needs Python 3 with pygame). Pass --windowed to start in a window.
cd /d "%~dp0"
python -c "import pygame" 2>nul || (echo pygame missing: run  pip install pygame & pause & exit /b 1)
python tanks.py %*
