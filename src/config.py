"""Configuration manager.

Loads layered configuration:

    embedded defaults (constants.DEFAULT_CONFIG)
        <- config/default.toml      (shipped defaults, optional)
        <- %APPDATA%/ClaudeMonitor/config.json   (user overrides, persisted)

The public surface is intentionally small: ``get`` / ``set`` with dotted keys,
plus a handful of typed convenience accessors used across the app.
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any

from . import constants

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# TOML loading (stdlib tomllib on 3.11+, tomli/​toml fallback, then give up)
# --------------------------------------------------------------------------- #
def _load_toml(path) -> dict:
    if not path.exists():
        return {}
    try:
        try:
            import tomllib  # Python 3.11+
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        except ModuleNotFoundError:
            try:
                import tomli  # type: ignore
                with open(path, "rb") as fh:
                    return tomli.load(fh)
            except ModuleNotFoundError:
                import toml  # type: ignore
                return toml.load(str(path))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not parse %s: %s", path, exc)
        return {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` into a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Mutable, persistent application configuration."""

    def __init__(self) -> None:
        self._data: dict = copy.deepcopy(constants.DEFAULT_CONFIG)
        # Layer the shipped TOML defaults on top of the embedded ones.
        self._data = _deep_merge(self._data, _load_toml(constants.DEFAULT_CONFIG_PATH))
        # Finally overlay the user's persisted JSON config.
        self._load_user()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load_user(self) -> None:
        path = constants.USER_CONFIG_PATH
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                user = json.load(fh)
            self._data = _deep_merge(self._data, user)
        except Exception as exc:
            log.warning("Could not read user config %s: %s", path, exc)

    def save(self) -> None:
        """Persist the full configuration to the user JSON file."""
        path = constants.USER_CONFIG_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except Exception as exc:
            log.error("Could not save config to %s: %s", path, exc)

    # ------------------------------------------------------------------ #
    # Generic dotted access
    # ------------------------------------------------------------------ #
    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted_key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):  # pragma: no cover - defensive
                raise KeyError(f"Cannot set {dotted_key}: {part} is not a section")
        node[parts[-1]] = value

    def as_dict(self) -> dict:
        return copy.deepcopy(self._data)

    # ------------------------------------------------------------------ #
    # Typed convenience accessors
    # ------------------------------------------------------------------ #
    @property
    def auth_type(self) -> str:
        # OAuth is the default for subscription users (see config/default.toml).
        return str(self.get("auth.auth_type", "oauth"))

    @property
    def model(self) -> str:
        return str(self.get("auth.model", constants.DEFAULT_MODEL))

    @property
    def opacity(self) -> float:
        try:
            return max(0.30, min(1.0, float(self.get("display.opacity", 0.95))))
        except (TypeError, ValueError):
            return 0.95

    @property
    def always_on_top(self) -> bool:
        return bool(self.get("display.always_on_top", True))

    @property
    def compact(self) -> bool:
        return bool(self.get("display.compact", False))

    @compact.setter
    def compact(self, value: bool) -> None:
        self.set("display.compact", bool(value))

    @property
    def language(self) -> str:
        return str(self.get("display.language", "pl"))

    @property
    def poll_interval(self) -> int:
        try:
            val = int(self.get("polling.interval", constants.DEFAULT_POLL_INTERVAL))
        except (TypeError, ValueError):
            val = constants.DEFAULT_POLL_INTERVAL
        return max(constants.MIN_POLL_INTERVAL, min(constants.MAX_POLL_INTERVAL, val))

    @property
    def smart_polling(self) -> bool:
        return bool(self.get("polling.smart_polling", True))

    @property
    def notifications_enabled(self) -> bool:
        return bool(self.get("notifications.enabled", True))

    @property
    def window_pos(self) -> tuple[int, int]:
        return int(self.get("display.pos_x", -1)), int(self.get("display.pos_y", -1))

    def set_window_pos(self, x: int, y: int) -> None:
        self.set("display.pos_x", int(x))
        self.set("display.pos_y", int(y))

    @property
    def active_tab(self) -> int:
        try:
            return int(self.get("display.active_tab", 0))
        except (TypeError, ValueError):
            return 0
