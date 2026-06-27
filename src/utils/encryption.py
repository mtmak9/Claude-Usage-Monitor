"""Secure storage for the Anthropic API key.

Primary backend is the OS keyring (Windows Credential Manager via ``keyring``).
If keyring is unavailable we fall back to an obfuscated value in the JSON
config — not real security, but better than plain text and clearly logged.
"""
from __future__ import annotations

import base64
import logging

from .. import constants

log = logging.getLogger(__name__)

try:
    import keyring  # type: ignore

    _KEYRING_OK = True
except Exception:  # pragma: no cover
    keyring = None  # type: ignore
    _KEYRING_OK = False


def keyring_available() -> bool:
    return _KEYRING_OK


def save_api_key(api_key: str) -> bool:
    """Persist the API key. Returns True if stored in the secure keyring."""
    if not api_key:
        delete_api_key()
        return _KEYRING_OK
    if _KEYRING_OK:
        try:
            keyring.set_password(
                constants.KEYRING_SERVICE, constants.KEYRING_USERNAME, api_key
            )
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("Keyring write failed, falling back: %s", exc)
    return False


def load_api_key() -> str | None:
    """Read the API key from the keyring (returns None if absent)."""
    if _KEYRING_OK:
        try:
            return keyring.get_password(
                constants.KEYRING_SERVICE, constants.KEYRING_USERNAME
            )
        except Exception as exc:  # pragma: no cover
            log.warning("Keyring read failed: %s", exc)
    return None


def delete_api_key() -> None:
    if _KEYRING_OK:
        try:
            keyring.delete_password(
                constants.KEYRING_SERVICE, constants.KEYRING_USERNAME
            )
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Lightweight obfuscation fallback (NOT cryptographically secure)
# --------------------------------------------------------------------------- #
def obfuscate(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def deobfuscate(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")
    except Exception:
        return ""
