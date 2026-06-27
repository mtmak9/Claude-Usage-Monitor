"""Discovery, refresh and secure reading of a local Claude OAuth credential.

Subscription users (Pro / Max) authenticate Claude Code / the Claude desktop app
with an OAuth token rather than an ``sk-ant-…`` API key.  That token unlocks the
``/api/oauth/usage`` endpoint which reports rolling 5-hour and 7-day utilisation
for the *subscription* — exactly what this monitor wants to show.

The token lives in one of several places depending on how the user signed in:

1. ``CLAUDE_CODE_OAUTH_TOKEN`` / ``ANTHROPIC_OAUTH_TOKEN`` environment variable
   (handy for testing / CI).
2. ``~/.claude/.credentials.json`` — written **in plain text** by the standalone
   Claude Code CLI under ``claudeAiOauth.accessToken``.
3. The Claude **desktop** app, which keeps the token *encrypted* in
   ``%APPDATA%/Claude/config.json`` under ``oauth:tokenCache`` (Chromium OSCrypt
   ``v10`` AES-256-GCM, the AES key itself DPAPI-protected inside ``Local State``).
   When the desktop app is in use it blanks the plaintext ``.credentials.json``,
   so this encrypted store is the *only* on-disk copy.
4. Our own refreshed-token cache in ``%APPDATA%/ClaudeMonitor/oauth_cache.json``
   (written only when we had to refresh an expired token ourselves).

Every failure path degrades gracefully to ``None`` so the caller can fall back to
API-key or mock mode.  Nothing here raises in normal operation.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import constants

log = logging.getLogger(__name__)

# Optional crypto stack — only needed to read the *desktop app's* encrypted
# token store.  Plaintext ``.credentials.json`` works without it.
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

    _CRYPTO_OK = True
except Exception:  # pragma: no cover - optional dependency
    AESGCM = None  # type: ignore
    _CRYPTO_OK = False

try:
    import httpx  # type: ignore

    _HTTPX_OK = True
except Exception:  # pragma: no cover
    httpx = None  # type: ignore
    _HTTPX_OK = False


# --------------------------------------------------------------------------- #
# Credential model
# --------------------------------------------------------------------------- #
@dataclass
class OAuthCredentials:
    """A resolved OAuth credential plus everything needed to refresh it."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None          # epoch *milliseconds*
    source: str = "?"                         # where we read it from (diagnostics)
    client_id: Optional[str] = None           # OAuth client that issued it
    scopes: Optional[str] = None
    subscription_type: Optional[str] = None   # "max" / "pro" / …
    rate_limit_tier: Optional[str] = None     # e.g. "default_claude_max_5x"

    # -- expiry helpers ------------------------------------------------- #
    def is_expired(self, skew_seconds: int = 120) -> bool:
        """True if the token has expired (or will within ``skew_seconds``)."""
        if not self.expires_at:
            return False  # unknown expiry — assume usable, let the API decide
        return (self.expires_at / 1000.0) <= (time.time() + skew_seconds)

    def plan_label(self) -> str:
        """A human-friendly plan name derived from the tier / sub type."""
        tier = (self.rate_limit_tier or "").lower()
        if "max_20" in tier:
            return "Max 20x"
        if "max_5" in tier:
            return "Max 5x"
        if "max" in tier or (self.subscription_type or "").lower() == "max":
            return "Max"
        if "pro" in tier or (self.subscription_type or "").lower() == "pro":
            return "Pro"
        if self.subscription_type:
            return self.subscription_type.title()
        return "Subskrypcja"


# --------------------------------------------------------------------------- #
# Windows DPAPI + OSCrypt (v10) decryption for the desktop app's token store
# --------------------------------------------------------------------------- #
def _dpapi_unprotect(blob: bytes) -> Optional[bytes]:
    """Decrypt a Windows DPAPI blob for the current user."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(blob, len(blob))
        blob_in = DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception as exc:  # pragma: no cover - non-Windows / failure
        log.debug("DPAPI unprotect failed: %s", exc)
        return None


def _read_text_shared(path: Path) -> Optional[str]:
    """Read a UTF-8 file even if another process holds it open (Windows)."""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(fd)
        return b"".join(chunks).decode("utf-8", "replace")
    except Exception as exc:
        log.debug("Could not read %s: %s", path, exc)
        return None


def _desktop_oscrypt_key() -> Optional[bytes]:
    """Unwrap the AES key the Claude desktop app uses for ``safeStorage``."""
    base = os.environ.get("APPDATA")
    if not base:
        return None
    local_state = Path(base) / "Claude" / "Local State"
    text = _read_text_shared(local_state)
    if not text:
        return None
    try:
        enc_key_b64 = json.loads(text)["os_crypt"]["encrypted_key"]
    except Exception:
        return None
    raw = base64.b64decode(enc_key_b64)
    if raw[:5] != b"DPAPI":
        return None
    return _dpapi_unprotect(raw[5:])


def _decrypt_v10(blob_b64: str, key: bytes) -> Optional[bytes]:
    """Decrypt a Chromium OSCrypt ``v10`` AES-256-GCM blob."""
    if not _CRYPTO_OK:
        return None
    try:
        raw = base64.b64decode(blob_b64)
        if raw[:3] != b"v10":
            return None
        nonce, ct = raw[3:15], raw[15:]
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("v10 decrypt failed: %s", exc)
        return None


def _load_desktop_cache_creds() -> list[OAuthCredentials]:
    """Decrypt the Claude desktop app's token cache into credential objects."""
    base = os.environ.get("APPDATA")
    if not base:
        return []
    cfg_path = Path(base) / "Claude" / "config.json"
    text = _read_text_shared(cfg_path)
    if not text:
        return []
    try:
        cfg = json.loads(text)
    except Exception:
        return []
    blob = cfg.get("oauth:tokenCache")
    if not blob:
        return []
    if not _CRYPTO_OK:
        log.info(
            "Desktop OAuth token found but 'cryptography' is not installed "
            "(pip install cryptography) — cannot decrypt it. Falling back."
        )
        return []
    key = _desktop_oscrypt_key()
    if not key:
        return []
    plaintext = _decrypt_v10(blob, key)
    if not plaintext:
        return []
    try:
        cache = json.loads(plaintext)
    except Exception:
        return []

    creds: list[OAuthCredentials] = []
    for cache_key, entry in cache.items() if isinstance(cache, dict) else []:
        if not isinstance(entry, dict):
            continue
        token = entry.get("token") or entry.get("accessToken")
        if not token:
            continue
        # cache_key looks like "<clientId>:<orgId>:<baseUrl>:<space-separated scopes>".
        # The baseUrl ("https://api.anthropic.com") and the scopes themselves both
        # contain ':' so we anchor on the URL: everything after "<scheme>://<host>:"
        # is the scope list.
        client_id = cache_key.split(":", 1)[0] if ":" in cache_key else None
        scopes = None
        m = re.search(r"https?://[^:]+:", cache_key)
        if m:
            scopes = cache_key[m.end():]
        creds.append(
            OAuthCredentials(
                access_token=token,
                refresh_token=entry.get("refreshToken") or entry.get("refresh_token"),
                expires_at=entry.get("expiresAt") or entry.get("expires_at"),
                source="desktop-cache",
                client_id=client_id,
                scopes=scopes,
                subscription_type=entry.get("subscriptionType"),
                rate_limit_tier=entry.get("rateLimitTier"),
            )
        )
    return creds


# --------------------------------------------------------------------------- #
# Plaintext .credentials.json (standalone Claude Code CLI)
# --------------------------------------------------------------------------- #
def _candidate_credential_files() -> list[Path]:
    home = Path.home()
    paths = [
        constants.CREDENTIALS_PATH,
        home / ".claude" / ".credentials.json",
        home / ".claude" / "credentials.json",
        home / ".config" / "claude" / "credentials.json",
    ]
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            paths.append(Path(base) / "Claude" / "credentials.json")
    # De-dupe preserving order.
    seen, unique = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _load_plaintext_creds() -> Optional[OAuthCredentials]:
    """Read ``claudeAiOauth`` from a plaintext credentials file, if present."""
    for path in _candidate_credential_files():
        text = _read_text_shared(path)
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
        if not isinstance(oauth, dict):
            continue
        token = oauth.get("accessToken") or oauth.get("access_token")
        if not token:  # desktop app blanks these — skip
            continue
        scopes = oauth.get("scopes")
        if isinstance(scopes, list):
            scopes = " ".join(scopes)
        return OAuthCredentials(
            access_token=token,
            refresh_token=oauth.get("refreshToken") or oauth.get("refresh_token"),
            expires_at=oauth.get("expiresAt") or oauth.get("expires_at"),
            source=str(path),
            client_id=constants.OAUTH_CLIENT_ID,
            scopes=scopes,
            subscription_type=oauth.get("subscriptionType"),
            rate_limit_tier=oauth.get("rateLimitTier"),
        )
    return None


# --------------------------------------------------------------------------- #
# Our own refreshed-token cache
# --------------------------------------------------------------------------- #
def _load_self_cache() -> Optional[OAuthCredentials]:
    path = constants.OAUTH_CACHE_PATH
    text = _read_text_shared(path)
    if not text:
        return None
    try:
        d = json.loads(text)
        return OAuthCredentials(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token"),
            expires_at=d.get("expires_at"),
            source="monitor-cache",
            client_id=d.get("client_id"),
            scopes=d.get("scopes"),
            subscription_type=d.get("subscription_type"),
            rate_limit_tier=d.get("rate_limit_tier"),
        )
    except Exception:
        return None


def _save_self_cache(creds: OAuthCredentials) -> None:
    try:
        constants.DATA_DIR.mkdir(parents=True, exist_ok=True)
        constants.OAUTH_CACHE_PATH.write_text(
            json.dumps(
                {
                    "access_token": creds.access_token,
                    "refresh_token": creds.refresh_token,
                    "expires_at": creds.expires_at,
                    "client_id": creds.client_id,
                    "scopes": creds.scopes,
                    "subscription_type": creds.subscription_type,
                    "rate_limit_tier": creds.rate_limit_tier,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("Could not write monitor OAuth cache: %s", exc)


# --------------------------------------------------------------------------- #
# Refresh flow
# --------------------------------------------------------------------------- #
def refresh_credentials(creds: OAuthCredentials) -> Optional[OAuthCredentials]:
    """Exchange a refresh token for a fresh access token.

    Best-effort.  We deliberately persist the result only to *our own* cache and
    never back into the desktop app's store, so a rotated refresh token can never
    desynchronise the user's main Claude session.
    """
    if not (_HTTPX_OK and creds.refresh_token):
        return None
    client_id = creds.client_id or constants.OAUTH_CLIENT_ID
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": client_id,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                constants.OAUTH_TOKEN_ENDPOINT,
                json=payload,
                headers={"content-type": "application/json"},
            )
        if resp.status_code != 200:
            log.warning("OAuth refresh failed: HTTP %s %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
    except Exception as exc:
        log.warning("OAuth refresh error: %s", exc)
        return None

    new_access = body.get("access_token")
    if not new_access:
        return None
    expires_in = body.get("expires_in")
    expires_at = int((time.time() + float(expires_in)) * 1000) if expires_in else None
    refreshed = OAuthCredentials(
        access_token=new_access,
        refresh_token=body.get("refresh_token") or creds.refresh_token,
        expires_at=expires_at,
        source="refreshed",
        client_id=client_id,
        scopes=creds.scopes,
        subscription_type=creds.subscription_type,
        rate_limit_tier=creds.rate_limit_tier,
    )
    _save_self_cache(refreshed)
    log.info("Refreshed OAuth access token (expires_in=%s).", expires_in)
    return refreshed


# --------------------------------------------------------------------------- #
# Public resolution API
# --------------------------------------------------------------------------- #
def _rank(creds: OAuthCredentials) -> tuple:
    """Higher is better: prefer claude_code scope, then later expiry."""
    has_cc = bool(creds.scopes and "claude_code" in creds.scopes)
    return (has_cc, creds.expires_at or 0)


def load_credentials() -> Optional[OAuthCredentials]:
    """Resolve the best usable OAuth credential, refreshing if necessary."""
    # 1) Environment variable beats everything (testing / CI override).
    env = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get(
        "ANTHROPIC_OAUTH_TOKEN"
    )
    if env:
        return OAuthCredentials(access_token=env, source="env")

    candidates: list[OAuthCredentials] = []

    # 2) A token from an in-app login or an earlier refresh.  Always considered:
    #    if it has expired the refresh path below will renew it (we keep its
    #    refresh token), so it must not be dropped here.
    self_cached = _load_self_cache()
    if self_cached:
        candidates.append(self_cached)

    # 3) Plaintext .credentials.json (standalone CLI login).
    plain = _load_plaintext_creds()
    if plain:
        candidates.append(plain)

    # 4) Encrypted desktop-app token cache.
    candidates.extend(_load_desktop_cache_creds())

    if not candidates:
        return None

    # Prefer non-expired credentials; fall back to expired ones we can refresh.
    valid = [c for c in candidates if not c.is_expired()]
    if valid:
        return sorted(valid, key=_rank, reverse=True)[0]

    # Everything on disk is expired — try to refresh the best candidate.
    best = sorted(candidates, key=_rank, reverse=True)[0]
    refreshed = refresh_credentials(best)
    return refreshed or best  # hand back the stale one; the API will 401 if dead


def read_oauth_token() -> Optional[str]:
    """Return a usable Claude OAuth access token, or ``None``.

    Backwards-compatible thin wrapper over :func:`load_credentials`.
    """
    creds = load_credentials()
    return creds.access_token if creds else None


def oauth_available() -> bool:
    return load_credentials() is not None


# --------------------------------------------------------------------------- #
# In-app login persistence (see api/oauth_login.py for the interactive flow)
# --------------------------------------------------------------------------- #
def save_login_credentials(creds: OAuthCredentials) -> None:
    """Persist credentials obtained from the in-app login to our own cache."""
    _save_self_cache(creds)


def has_local_login() -> bool:
    """True if the user authorised an account *through the app* (our cache)."""
    return _load_self_cache() is not None


def logout() -> None:
    """Forget the in-app login (our own cache only — never the source apps')."""
    try:
        path = constants.OAUTH_CACHE_PATH
        if path.exists():
            path.unlink()
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("Could not clear monitor OAuth cache: %s", exc)
