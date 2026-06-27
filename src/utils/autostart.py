"""Windows auto-start management via the per-user Run registry key.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

All functions are no-ops (returning False) on non-Windows platforms so the rest
of the app stays portable.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .. import constants

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = constants.APP_ID

try:
    import winreg  # type: ignore

    _WINDOWS = True
except Exception:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore
    _WINDOWS = False


def _launch_command() -> str:
    """Return the command Windows should run at login.

    When frozen (PyInstaller) we point at the executable; otherwise we invoke
    the current Python interpreter against this project's entry module.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    entry = Path(constants.PROJECT_ROOT) / "src" / "main.py"
    return f'"{sys.executable}" "{entry}"'


def is_enabled() -> bool:
    if not _WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception as exc:  # pragma: no cover
        log.warning("autostart query failed: %s", exc)
        return False


def enable() -> bool:
    if not _WINDOWS:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(
                key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command()
            )
        return True
    except Exception as exc:  # pragma: no cover
        log.error("Could not enable autostart: %s", exc)
        return False


def disable() -> bool:
    if not _WINDOWS:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:  # pragma: no cover
        log.error("Could not disable autostart: %s", exc)
        return False


def set_enabled(enabled: bool) -> bool:
    return enable() if enabled else disable()
