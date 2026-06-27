"""Launcher entry point.

Importing the app as the ``src`` package (absolute import) keeps the package
context intact so every ``from . import ...`` inside ``src`` resolves — both when
run directly (``python run.py``) and, crucially, when frozen by PyInstaller
(building ``src/main.py`` directly fails with "No module named 'src'").
"""
from src.main import main

if __name__ == "__main__":
    raise SystemExit(main())
