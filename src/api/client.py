"""Usage-provider client.

Claude modes:

* ``oauth``   — the default for subscription users.  Reads the local Claude
                OAuth token and calls ``GET /api/oauth/usage`` with an
                ``Authorization: Bearer`` header to get real rolling 5h / 7d
                subscription utilisation.  **No API key required.**
* ``api_key`` — ``x-api-key`` auth with a stored ``sk-ant-…`` key.  Makes a
                *tiny* ``/v1/messages`` request (1 output token) purely to read
                the ``anthropic-ratelimit-*`` response headers.
* ``mock``    — no network at all; generates lively demo data so the whole UI
                can be exercised without credentials.

Codex mode reads local ``~/.codex/sessions`` JSONL files for rate limits and
token usage. It does not require an OpenAI API key.

Every failure path returns a snapshot carrying an ``error`` string rather than
raising, so the poller/UI never crash on a bad network or token.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .. import constants
from ..i18n import tr
from ..utils import peak_hours
from . import oauth
from .headers import parse_rate_limit_headers
from .models import ActivityData, UsageSnapshot
from .oauth import load_credentials
from .usage import parse_oauth_usage
from ..storage.codex_usage import CodexUsageReader
from ..storage.token_usage import TokenUsage, TokenUsageReader

log = logging.getLogger(__name__)

try:
    import httpx  # type: ignore

    _HTTPX_OK = True
except Exception:  # pragma: no cover
    httpx = None  # type: ignore
    _HTTPX_OK = False


class AnthropicClient:
    def __init__(self, config) -> None:
        self.config = config
        self._mock = MockGenerator()
        self._last_oauth_good: Optional[UsageSnapshot] = None
        self._token_reader = TokenUsageReader()
        self._codex_reader = CodexUsageReader()

    # ------------------------------------------------------------------ #
    # Credentials
    # ------------------------------------------------------------------ #
    def _api_key(self) -> Optional[str]:
        # Prefer the secure keyring, fall back to config value.
        try:
            from ..utils import encryption

            key = encryption.load_api_key()
            if key:
                return key
        except Exception:
            pass
        return self.config.get("auth.api_key") or None

    def effective_auth(self, provider: Optional[str] = None) -> str:
        """Resolve the auth mode actually usable right now."""
        provider = provider or self.config.provider
        if provider == "codex":
            return "codex"
        return self.effective_auth_for_provider("claude")

    def effective_auth_for_provider(self, provider: str) -> str:
        """Resolve the auth mode for an explicit provider."""
        if provider == "codex":
            return "codex"
        configured = self.config.auth_type
        if configured == "mock":
            return "mock"
        if configured == "oauth":
            return "oauth" if oauth.oauth_available() else "mock"
        if configured == "api_key":
            return "api_key" if self._api_key() else "mock"
        return "mock"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def fetch_snapshot(self, provider: Optional[str] = None) -> UsageSnapshot:
        provider = provider or self.config.provider
        if provider == "codex":
            return self._codex_snapshot()

        mode = self.effective_auth(provider)
        if mode == "mock":
            snap = self._mock.snapshot()
            snap.is_peak = peak_hours.is_peak()
            return snap

        if not _HTTPX_OK:
            return UsageSnapshot(error=tr("cl_no_httpx"), model=self.config.model)

        if mode == "oauth":
            return self._oauth_snapshot()

        # api_key mode — read the rate-limit headers off a 1-token ping.
        try:
            resp = self._ping_api_key()
        except httpx.HTTPStatusError as exc:  # 4xx/5xx — headers may still help
            snap = parse_rate_limit_headers(
                exc.response.headers,
                model=self.config.model,
                is_peak=peak_hours.is_peak(),
            )
            if exc.response.status_code == 429:
                snap.error = None  # rate-limited but headers are valid
            else:
                snap.error = f"HTTP {exc.response.status_code}"
            return snap
        except Exception as exc:
            return UsageSnapshot(error=str(exc), model=self.config.model)

        return parse_rate_limit_headers(
            resp.headers, model=self.config.model, is_peak=peak_hours.is_peak()
        )

    # ------------------------------------------------------------------ #
    # OAuth subscription-usage path
    # ------------------------------------------------------------------ #
    def _oauth_snapshot(self) -> UsageSnapshot:
        """Read 5h/7d subscription utilisation from ``/api/oauth/usage``."""
        creds = load_credentials()
        if not creds:
            return UsageSnapshot(error=tr("cl_no_oauth_short"), model=self.config.model)
        try:
            resp = self._fetch_oauth_usage(creds.access_token)
            # Token rejected? Refresh once and retry before giving up.
            if resp.status_code == 401 and creds.refresh_token:
                refreshed = oauth.refresh_credentials(creds)
                if refreshed:
                    creds = refreshed
                    resp = self._fetch_oauth_usage(creds.access_token)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            # The usage endpoint rate-limits aggressively (~1 req / 2 min).  A 429
            # isn't an error — the numbers haven't changed, so keep showing the
            # last good reading instead of flashing an offline state.
            if code == 429:
                stale = self._stale_snapshot()
                if stale is not None:
                    return stale
                return UsageSnapshot(error=None, model=self.config.model, is_stale=True)
            msg = tr("cl_oauth_expired") if code == 401 else tr("cl_http_err", code=code)
            return UsageSnapshot(error=msg, model=self.config.model)
        except Exception as exc:
            # Transient network blip — prefer last good data over a hard error.
            stale = self._stale_snapshot()
            if stale is not None:
                return stale
            return UsageSnapshot(error=str(exc), model=self.config.model)

        snap = parse_oauth_usage(
            data,
            model=self.config.model,
            plan_name=creds.plan_label(),
            is_peak=peak_hours.is_peak(),
        )
        self._last_oauth_good = snap
        return snap

    # ------------------------------------------------------------------ #
    # Codex local-usage path
    # ------------------------------------------------------------------ #
    def _codex_snapshot(self) -> UsageSnapshot:
        limits = self._codex_reader.latest_limits()
        if limits is None:
            return UsageSnapshot(error=tr("codex_no_data"), model="codex")

        snap = UsageSnapshot(
            timestamp=datetime.now(timezone.utc),
            model="codex",
            session_utilization=limits.session_percent,
            week_utilization=limits.week_percent,
            session_reset=limits.session_reset,
            week_reset=limits.week_reset,
            # Keep the subscription gauge consistent with Claude: it represents
            # the rolling weekly subscription limit, not the 5h session window.
            subscription_percent=limits.week_percent,
            plan_name=limits.plan_label,
            cycle_label=limits.plan_label,
            cycle_renews=limits.week_reset,
            is_peak=False,
        )
        return snap

    def _stale_snapshot(self) -> Optional[UsageSnapshot]:
        """A copy of the last good OAuth reading, flagged stale (or None)."""
        if self._last_oauth_good is None:
            return None
        import copy

        snap = copy.copy(self._last_oauth_good)
        snap.is_stale = True
        snap.is_peak = peak_hours.is_peak()
        return snap

    def _fetch_oauth_usage(self, token: str):
        headers = {
            "Authorization": f"Bearer {token or ''}",
            "anthropic-beta": constants.OAUTH_BETA_HEADER,
            "anthropic-version": constants.ANTHROPIC_VERSION,
            "content-type": "application/json",
            "User-Agent": f"{constants.APP_NAME}/{constants.APP_VERSION}",
        }
        with httpx.Client(timeout=20.0) as client:
            return client.get(
                constants.API_BASE_URL + constants.OAUTH_USAGE_ENDPOINT,
                headers=headers,
            )

    def activity(self) -> ActivityData:
        """Activity arrays for the mock mode (real mode uses the DB history)."""
        return self._mock.activity()

    def token_usage(self, provider: Optional[str] = None) -> TokenUsage:
        """Token usage from the active provider's local logs (or demo numbers)."""
        provider = provider or self.config.provider
        if provider == "codex":
            return self._codex_reader.token_usage()
        if self.effective_auth(provider) == "mock":
            return self._mock.token_usage(provider="claude")
        usage = self._token_reader.read()
        usage.provider = "claude"
        return usage

    # ------------------------------------------------------------------ #
    # Connection test (used by the Settings dialog)
    # ------------------------------------------------------------------ #
    def test_connection(
        self,
        api_key: Optional[str] = None,
        auth_type: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Tuple[bool, str]:
        provider = provider or self.config.provider
        if provider == "codex":
            limits = self._codex_reader.latest_limits()
            if not limits:
                return False, tr("codex_no_data")
            return True, tr(
                "codex_connected",
                plan=limits.plan_label,
                s=f"{limits.session_percent:.0f}",
                w=f"{limits.week_percent:.0f}",
            )

        auth_type = auth_type or self.config.auth_type
        if auth_type == "mock":
            return True, tr("cl_mock_ok")
        if not _HTTPX_OK:
            return False, tr("cl_no_httpx_pip")
        try:
            if auth_type == "oauth":
                creds = load_credentials()
                if not creds:
                    return False, tr("cl_no_oauth")
                resp = self._fetch_oauth_usage(creds.access_token)
                if resp.status_code == 401 and creds.refresh_token:
                    refreshed = oauth.refresh_credentials(creds)
                    if refreshed:
                        creds = refreshed
                        resp = self._fetch_oauth_usage(creds.access_token)
                resp.raise_for_status()
                snap = parse_oauth_usage(
                    resp.json(), model=self.config.model, plan_name=creds.plan_label()
                )
                return True, tr(
                    "cl_connected_plan",
                    plan=creds.plan_label(),
                    s=f"{snap.session_percent:.0f}",
                    w=f"{snap.week_percent:.0f}",
                )

            key = api_key or self._api_key()
            if not key:
                return False, tr("cl_no_key")
            resp = self._ping_api_key(key)
            snap = parse_rate_limit_headers(resp.headers, model=self.config.model)
            return True, tr(
                "cl_connected",
                s=f"{snap.session_percent:.0f}",
                w=f"{snap.week_percent:.0f}",
            )
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 401:
                msg = tr("cl_oauth_401") if auth_type == "oauth" else tr("cl_key_401")
                return False, msg
            if code == 429:
                return True, tr("cl_rate_limited")
            return False, tr("cl_http_err", code=code)
        except Exception as exc:
            return False, tr("cl_conn_err", exc=exc)

    # ------------------------------------------------------------------ #
    # Low-level pings
    # ------------------------------------------------------------------ #
    def _payload(self) -> dict:
        return {
            "model": constants.PING_MODEL,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }

    def _ping_api_key(self, key: Optional[str] = None):
        key = key or self._api_key()
        headers = {
            "x-api-key": key or "",
            "anthropic-version": constants.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                constants.API_BASE_URL + constants.API_MESSAGES_ENDPOINT,
                headers=headers,
                json=self._payload(),
            )
            resp.raise_for_status()
            return resp


# --------------------------------------------------------------------------- #
# Mock data generator — produces realistic, slowly-evolving demo data.
# --------------------------------------------------------------------------- #
class MockGenerator:
    """Synthesises believable usage data driven by the time of day."""

    def __init__(self) -> None:
        self._session_start = datetime.now(timezone.utc) - timedelta(
            minutes=random.randint(20, 120)
        )
        self._prompts_today = random.randint(28, 52)
        # Spread demo prompts across a believable working day so the timeline /
        # activity sections always look populated (independent of the clock).
        self._prompt_times: list[float] = sorted(
            random.uniform(0.30, 0.92) for _ in range(self._prompts_today)
        )
        self._tick = 0

    @staticmethod
    def _day_fraction(dt: Optional[datetime] = None) -> float:
        local = peak_hours.to_pacific(dt)
        return (local.hour * 3600 + local.minute * 60 + local.second) / 86400.0

    def _maybe_add_prompt(self) -> None:
        # Roughly one new prompt every few refreshes while "working".
        if random.random() < 0.35:
            self._prompts_today += 1
            self._prompt_times.append(self._day_fraction())

    def snapshot(self) -> UsageSnapshot:
        self._tick += 1
        self._maybe_add_prompt()
        now = datetime.now(timezone.utc)

        # 5h session window — fills then resets.
        elapsed = (now - self._session_start).total_seconds()
        window = 5 * 3600
        if elapsed > window:
            self._session_start = now
            elapsed = 0.0
        session_progress = elapsed / window
        wobble = 0.06 * math.sin(self._tick / 4.0)
        session_util = max(0.0, min(100.0, session_progress * 78.0 + 8.0 + wobble * 100))

        # Weekly window — based on weekday progress (Mon=0).
        local = peak_hours.to_pacific(now)
        week_progress = (local.weekday() + self._day_fraction(now)) / 7.0
        week_util = max(0.0, min(100.0, week_progress * 88.0 + 6.0))
        opus_week = max(0.0, min(100.0, week_util * 0.85))

        # Subscription cycle — based on day of month.
        day = local.day
        sub_percent = min(100.0, (day / 30.0) * 90.0 + 5.0)

        snap = UsageSnapshot(
            timestamp=now,
            model=self.snapshot_model(),
            is_mock=True,
        )
        snap.session_utilization = round(session_util, 1)
        snap.week_utilization = round(week_util, 1)
        snap.opus_week_utilization = round(opus_week, 1)
        snap.session_reset = self._session_start + timedelta(seconds=window)
        snap.week_reset = self._end_of_week(local)

        # Synthetic request/token limits for the detailed view.
        snap.requests_limit = 1000
        snap.requests_remaining = int(1000 * (1 - session_util / 100.0))
        snap.tokens_limit = 2_000_000
        snap.tokens_remaining = int(2_000_000 * (1 - session_util / 100.0))

        snap.plan_name = "Max 20x"
        snap.subscription_percent = round(sub_percent, 1)
        snap.cycle_label = f"{local.strftime('%b')} {local.year}"
        snap.cycle_renews = self._end_of_month(local)

        # Demo usage credits ($) so the KREDYTY card is populated in mock mode.
        snap.credits_enabled = True
        snap.credits_limit = 100.0
        snap.credits_used = round(min(100.0, sub_percent) * 0.6, 2)
        snap.credits_balance = round(100.0 - snap.credits_used, 2)
        snap.credits_percent = round(snap.credits_used / 100.0 * 100.0, 1)
        snap.credits_currency = "USD"
        return snap

    def snapshot_model(self) -> str:
        return constants.DEFAULT_MODEL

    def token_usage(self, provider: str = "claude") -> TokenUsage:
        """Synthetic token usage so the TOKENS card is populated in demo mode."""
        act = self.activity()
        ti = self._prompts_today * 1800
        to = self._prompts_today * 5200
        tc = self._prompts_today * 240000
        return TokenUsage(
            provider=provider,
            totals=(ti + to + tc, (ti + to + tc) * 6, (ti + to + tc) * 22),
            inputs=(ti, ti * 6, ti * 22),
            outputs=(to, to * 6, to * 22),
            cache=(tc, tc * 6, tc * 22),
            hourly=act.hourly,
        )

    def activity(self) -> ActivityData:
        """Build activity arrays consistent with the generated prompts."""
        hourly = []
        for hour in range(24):
            # A strong afternoon peak with lighter morning + evening bumps so the
            # heat-bar reads as a realistic work day at any time of day.
            afternoon = math.exp(-((hour - 14) ** 2) / 10.0)
            morning = 0.55 * math.exp(-((hour - 10) ** 2) / 8.0)
            evening = 0.35 * math.exp(-((hour - 20) ** 2) / 12.0)
            intensity = (afternoon + morning + evening) * (0.75 + 0.45 * random.random())
            hourly.append(max(0.05, intensity))
        peak = max(hourly) or 1.0
        hourly = [round(v / peak, 3) for v in hourly]
        timeline = sorted(t for t in self._prompt_times if 0.0 <= t <= 1.0)
        return ActivityData(
            prompts_today=self._prompts_today,
            prompts_week=self._prompts_today * 6 + random.randint(0, 40),
            prompts_month=self._prompts_today * 22 + random.randint(0, 120),
            timeline=timeline,
            hourly=hourly,
        )

    # -- helpers -------------------------------------------------------- #
    @staticmethod
    def _end_of_week(local: datetime) -> datetime:
        days_left = 6 - local.weekday()
        end = (local + timedelta(days=days_left)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        return end.astimezone(timezone.utc)

    @staticmethod
    def _end_of_month(local: datetime) -> datetime:
        if local.month == 12:
            nxt = local.replace(year=local.year + 1, month=1, day=1)
        else:
            nxt = local.replace(month=local.month + 1, day=1)
        nxt = nxt.replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.astimezone(timezone.utc)
