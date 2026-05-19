"""
PyInstaller build script for AbaqusToolkit.
Generates a single-file .exe for distribution.

Usage: python build.py
Output: dist/AbaqusToolkit.exe
"""

import sys
sys.path.insert(0, r"C:\tmp\pyside6")

import PyInstaller.__main__
from pathlib import Path

ROOT = Path(__file__).parent

PyInstaller.__main__.run([
    str(ROOT / "main.py"),
    "--name=AbaqusToolkit",
    "--onefile",
    "--windowed",
    "--add-data", f"{ROOT / 'resources' / 'style.qss'};resources",
    "--clean",
    "--noconfirm",
])
