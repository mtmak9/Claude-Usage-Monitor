"""Interactive OAuth login for a Claude subscription account.

Implements the standard Authorization-Code-with-PKCE flow against the public
Claude OAuth client so that *any* user can authorise *their own* Claude account
from inside the app — no API key, nothing hard-coded.

We use the manual "show the code" redirect
(``https://console.anthropic.com/oauth/code/callback``): after the user approves
access, that page displays an authorization code which they paste back into the
app.  This avoids running a local callback HTTP server (and the firewall prompt /
loopback-registration uncertainty that comes with it).

Usage::

    session = LoginSession()
    webbrowser/QDesktopServices.open(session.authorize_url())
    creds = session.exchange(pasted_code)      # raises on failure
    oauth.save_login_credentials(creds)

Nothing here is hard-wired to a particular account; the token belongs to whoever
completes the browser login.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import webbrowser
from typing import Optional
from urllib.parse import urlencode

from .. import constants
from .oauth import OAuthCredentials

log = logging.getLogger(__name__)

try:
    import httpx  # type: ignore

    _HTTPX_OK = True
except Exception:  # pragma: no cover
    httpx = None  # type: ignore
    _HTTPX_OK = False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for an S256 PKCE exchange."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class LoginSession:
    """One interactive login attempt (carries the PKCE verifier + state)."""

    def __init__(self) -> None:
        self.verifier, self.challenge = generate_pkce()
        # IMPORTANT: Anthropic's authorize server requires ``state`` to equal the
        # PKCE verifier.  A separate random state is rejected at grant time with
        # "Authorization failed / Invalid request format" (verified live).
        self.state = self.verifier
        self.redirect_uri = constants.OAUTH_REDIRECT_URI

    # -- step 1: send the user to the browser --------------------------- #
    def authorize_url(self) -> str:
        params = {
            "code": "true",
            "client_id": constants.OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": constants.OAUTH_SCOPES,
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
            "state": self.state,
        }
        return f"{constants.OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def open_browser(self) -> bool:
        try:
            return bool(webbrowser.open(self.authorize_url()))
        except Exception as exc:  # pragma: no cover - environment dependent
            log.debug("webbrowser.open failed: %s", exc)
            return False

    # -- step 2: exchange the pasted code for tokens -------------------- #
    def exchange(self, pasted_code: str) -> OAuthCredentials:
        """Exchange a pasted ``code`` (or ``code#state``) for OAuth tokens.

        Raises ``RuntimeError`` with a human-readable message on any failure.
        """
        if not _HTTPX_OK:
            raise RuntimeError("Brak biblioteki httpx (pip install httpx).")

        text = (pasted_code or "").strip()
        if not text:
            raise RuntimeError("Pusty kod autoryzacyjny.")
        # The callback page typically shows "<code>#<state>".
        code, state = text, self.state
        if "#" in text:
            code, _, state_part = text.partition("#")
            state = state_part or self.state
        code = code.strip()

        payload = {
            "grant_type": "authorization_code",
            "client_id": constants.OAUTH_CLIENT_ID,
            "code": code,
            "state": state,
            "redirect_uri": self.redirect_uri,
            "code_verifier": self.verifier,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    constants.OAUTH_TOKEN_ENDPOINT,
                    json=payload,
                    headers={"content-type": "application/json"},
                )
        except Exception as exc:
            raise RuntimeError(f"Błąd sieci: {exc}") from exc

        if resp.status_code != 200:
            detail = _error_detail(resp)
            raise RuntimeError(f"Odrzucono ({resp.status_code}): {detail}")

        try:
            body = resp.json()
        except Exception as exc:
            raise RuntimeError("Nieprawidłowa odpowiedź serwera.") from exc

        access = body.get("access_token")
        if not access:
            raise RuntimeError("Brak access_token w odpowiedzi.")

        expires_in = body.get("expires_in")
        expires_at = (
            int((time.time() + float(expires_in)) * 1000) if expires_in else None
        )
        account = body.get("account") if isinstance(body.get("account"), dict) else {}
        return OAuthCredentials(
            access_token=access,
            refresh_token=body.get("refresh_token"),
            expires_at=expires_at,
            source="login",
            client_id=constants.OAUTH_CLIENT_ID,
            scopes=body.get("scope") or constants.OAUTH_SCOPES,
            subscription_type=(
                body.get("subscription_type") or account.get("subscription_type")
            ),
            rate_limit_tier=body.get("rate_limit_tier"),
        )


def _error_detail(resp) -> str:
    try:
        data = resp.json()
        return str(data.get("error_description") or data.get("error") or data)[:200]
    except Exception:
        return (resp.text or "")[:200]
