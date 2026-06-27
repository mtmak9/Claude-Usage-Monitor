"""Build a standalone Windows executable with PyInstaller.

Usage:
    python build.py            # one-file windowed .exe in ./dist
    python build.py --onedir   # faster-starting folder build

It first (re)generates the icons, then invokes PyInstaller with sensible
defaults.  PyInstaller is intentionally *not* a runtime dependency — install it
only when you want to build:  ``pip install pyinstaller``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "ClaudeUsageMonitor"


def _generate_icons() -> None:
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "assets" / "generate_icons.py")], check=True
        )
    except Exception as exc:
        print(f"Icon generation skipped: {exc}")


def _has_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except Exception:
        return False


def main() -> int:
    onedir = "--onedir" in sys.argv

    if not _has_pyinstaller():
        print("PyInstaller is not installed. Run:  pip install pyinstaller")
        return 1

    _generate_icons()

    icon = ROOT / "assets" / "app.ico"
    sep = ";"  # Windows path separator for --add-data

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        NAME,
        # Make the project root importable so `import src` resolves at analysis.
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'config' / 'default.toml'}{sep}config",
        "--add-data",
        f"{ROOT / 'assets'}{sep}assets",
        # Collect the whole app package — its relative imports (and a few lazy
        # ones) would otherwise be missed when building from the launcher.
        "--collect-submodules",
        "src",
        # Hidden imports that PyInstaller's static analysis can miss.
        "--hidden-import",
        "keyring.backends.Windows",
        "--collect-submodules",
        "keyring",
        # Time-zone database for the US/Pacific peak-hour calculation.
        "--collect-data",
        "tzdata",
    ]
    if icon.exists():
        cmd += ["--icon", str(icon)]
    cmd += ["--onedir"] if onedir else ["--onefile"]
    cmd += [str(ROOT / "run.py")]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print(f"\nDone. Executable is in: {ROOT / 'dist'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
