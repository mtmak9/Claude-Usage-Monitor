"""Tiny in-process internationalisation layer (Polish / English).

Usage::

    from .i18n import tr, set_language
    set_language("en")            # once, at startup, from config
    label.setText(tr("btn_save"))
    label.setText(tr("oauth_detected", plan="Max 5x", where="…"))

Strings are stored as ``(pl, en)`` tuples.  ``tr`` returns the active language's
string (falling back to Polish, then to the key itself) and applies ``str.format``
with any keyword arguments.  The active language is a module global, set once at
startup; changing it at runtime is supported but the app restarts to re-render
every widget cleanly (see ``MonitorApp._restart_app``).
"""
from __future__ import annotations

_LANG = "pl"


def set_language(lang: str | None) -> None:
    global _LANG
    _LANG = "en" if str(lang or "").lower().startswith("en") else "pl"


def get_language() -> str:
    return _LANG


def tr(key: str, **kwargs) -> str:
    pair = _STRINGS.get(key)
    if pair is None:
        text = key
    else:
        text = pair[1] if _LANG == "en" else pair[0]
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:  # pragma: no cover - never break the UI on a bad arg
            pass
    return text


_STRINGS: dict[str, tuple[str, str]] = {
    # -- generic / status ------------------------------------------------ #
    "connected": ("Połączono", "Connected"),
    "connecting": ("łączenie…", "connecting…"),
    "offline": ("offline", "offline"),
    "error_prefix": ("Błąd: {msg}", "Error: {msg}"),
    "reset": ("reset", "reset"),
    "now": ("teraz", "now"),
    "in_dh": ("za {d}d {h}h", "in {d}d {h}h"),
    "in_hm": ("za {h}h {m}m", "in {h}h {m}m"),
    "in_m": ("za {m}m", "in {m}m"),

    # -- tabs / prompts -------------------------------------------------- #
    "tab_today": ("DZIŚ", "TODAY"),
    "tab_week": ("TYDZIEŃ", "WEEK"),
    "tab_month": ("MIESIĄC", "MONTH"),
    "prompts_today": ("promptów dziś", "prompts today"),
    "prompts_week": ("promptów w tygodniu", "prompts this week"),
    "prompts_month": ("promptów w miesiącu", "prompts this month"),

    # -- tokens (Claude Code logs) --------------------------------------- #
    "card_tokens": ("TOKENY", "TOKENS"),
    "tokens_today": ("tokenów dziś (Claude Code)", "tokens today (Claude Code)"),
    "tokens_week": ("tokenów / 7 dni (Claude Code)", "tokens / 7 days (Claude Code)"),
    "tokens_month": ("tokenów / 30 dni (Claude Code)", "tokens / 30 days (Claude Code)"),
    "tokens_breakdown": ("wej {i} · wyj {o} · cache {c}", "in {i} · out {o} · cache {c}"),

    # -- overlay cards --------------------------------------------------- #
    "card_prompts": ("PROMPTY", "PROMPTS"),
    "card_limits": ("LIMITY", "LIMITS"),
    "card_subscription": ("SUBSKRYPCJA", "SUBSCRIPTION"),
    "card_credits": ("KREDYTY $", "CREDITS $"),
    "card_peak": ("PEAK HOURS", "PEAK HOURS"),
    "card_activity": ("AKTYWNOŚĆ", "ACTIVITY"),
    "limit_session": ("SESJA 5H", "SESSION 5H"),
    "limit_week": ("TYDZIEŃ 7D", "WEEK 7D"),
    "wk_prefix": ("tydz {pct}%", "wk {pct}%"),

    # -- subscription kv ------------------------------------------------- #
    "kv_status": ("Status", "Status"),
    "kv_cycle": ("Cykl", "Cycle"),
    "kv_renews": ("Odnowienie", "Renews"),
    "kv_remaining": ("Pozostało", "Remaining"),

    # -- credits --------------------------------------------------------- #
    "kv_spent": ("Wydano", "Spent"),
    "kv_monthly_limit": ("Limit miesięczny", "Monthly limit"),
    "kv_balance": ("Saldo", "Balance"),
    "credits_enabled": ("Włączone", "Enabled"),
    "credits_disabled": ("Wyłączone", "Disabled"),
    "credits_pct_limit": ("{pct}% limitu", "{pct}% of limit"),
    "credits_hint": (
        "Włącz „Usage credits” w ustawieniach Claude, aby śledzić saldo.",
        "Enable “Usage credits” in Claude settings to track your balance.",
    ),

    # -- peak ------------------------------------------------------------ #
    "peak_on": ("PEAK", "PEAK"),
    "peak_off": ("OFF-PEAK", "OFF-PEAK"),
    "peak_verb_peak": ("peak", "peak"),
    "peak_verb_off": ("off-peak", "off-peak"),
    "peak_in_hm": ("{verb} za {h}h {m}m", "{verb} in {h}h {m}m"),
    "peak_in_m": ("{verb} za {m}m", "{verb} in {m}m"),
    "act_minus24h": ("-24h", "-24h"),
    "act_now": ("teraz", "now"),

    # -- overlay tooltips ------------------------------------------------ #
    "tip_compact": ("Tryb kompaktowy / pełny", "Compact / full mode"),
    "tip_hide": ("Ukryj (działa dalej w zasobniku)", "Hide (keeps running in the tray)"),

    # -- tray ------------------------------------------------------------ #
    "tray_show": ("Pokaż / ukryj widżet", "Show / hide widget"),
    "tray_compact": ("Tryb kompaktowy / pełny", "Compact / full mode"),
    "tray_refresh": ("Odśwież teraz", "Refresh now"),
    "tray_history": ("Historia użycia…", "Usage history…"),
    "tray_settings": ("Ustawienia…", "Settings…"),
    "tray_about": ("O programie", "About"),
    "tray_quit": ("Zakończ", "Quit"),
    "tray_tip": ("Sesja {s}%  |  Tydzień {w}%", "Session {s}%  |  Week {w}%"),

    # -- notifications --------------------------------------------------- #
    "notify_session": ("Sesja 5h", "Session 5h"),
    "notify_week": ("Tydzień 7d", "Week 7d"),
    "notify_body": (
        "{label}: wykorzystano {pct}% (próg {th}%)",
        "{label}: {pct}% used (threshold {th}%)",
    ),

    # -- settings -------------------------------------------------------- #
    "settings_title": ("Ustawienia — Claude Usage Monitor", "Settings — Claude Usage Monitor"),
    "grp_auth": ("Autoryzacja", "Authorization"),
    "auth_type": ("Typ:", "Type:"),
    "auth_oauth": ("OAuth — subskrypcja (zalecane)", "OAuth — subscription (recommended)"),
    "auth_api_key": ("Klucz API", "API key"),
    "auth_demo": ("Tryb demo (bez klucza)", "Demo mode (no key)"),
    "lbl_oauth_token": ("Token OAuth:", "OAuth token:"),
    "lbl_account": ("Konto:", "Account:"),
    "btn_login": ("Zaloguj się przez Claude", "Sign in with Claude"),
    "btn_logout": ("Wyloguj", "Sign out"),
    "lbl_api_key": ("Klucz API:", "API key:"),
    "lbl_model_ping": ("Model ping:", "Ping model:"),
    "btn_test": ("Testuj połączenie", "Test connection"),
    "grp_display": ("Wygląd", "Appearance"),
    "lbl_opacity": ("Przezroczystość:", "Opacity:"),
    "chk_on_top": ("Zawsze na wierzchu", "Always on top"),
    "chk_compact": ("Domyślnie tryb kompaktowy", "Compact mode by default"),
    "lbl_language": ("Język:", "Language:"),
    "lang_pl": ("Polski", "Polish"),
    "lang_en": ("English", "English"),
    "grp_polling": ("Odświeżanie", "Refresh"),
    "lbl_interval": ("Interwał:", "Interval:"),
    "chk_smart": (
        "Inteligentne odświeżanie (szybciej przy wysokim użyciu)",
        "Smart refresh (faster when usage is high)",
    ),
    "grp_notifications": ("Powiadomienia", "Notifications"),
    "chk_notify_enabled": ("Włącz powiadomienia", "Enable notifications"),
    "chk_notify_80": ("Powiadom przy 80%", "Notify at 80%"),
    "chk_notify_90": ("Powiadom przy 90%", "Notify at 90%"),
    "chk_notify_100": ("Powiadom przy 100%", "Notify at 100%"),
    "grp_system": ("System", "System"),
    "chk_autostart": ("Uruchamiaj przy starcie Windows", "Start with Windows"),
    "chk_tray": ("Minimalizuj do zasobnika", "Minimize to tray"),
    "btn_cancel": ("Anuluj", "Cancel"),
    "btn_save": ("Zapisz", "Save"),
    "testing": ("Testowanie…", "Testing…"),
    "src_login": ("logowanie w aplikacji", "in-app sign-in"),
    "src_refreshed": ("logowanie w aplikacji (odświeżony)", "in-app sign-in (refreshed)"),
    "src_desktop": ("wykryta aplikacja Claude", "detected Claude app"),
    "src_env": ("zmienna środowiskowa", "environment variable"),
    "oauth_detected": ("✓ Wykryto ({plan}) — źródło: {where}", "✓ Detected ({plan}) — source: {where}"),
    "oauth_not_found": (
        "✗ Nie znaleziono lokalnego tokenu. Zaloguj się w Claude Code / aplikacji Claude.",
        "✗ No local token found. Sign in via Claude Code / the Claude app.",
    ),
    "lang_restart_title": ("Zmiana języka", "Language change"),
    "lang_restart_body": (
        "Język zostanie zmieniony po ponownym uruchomieniu.\nUruchomić ponownie teraz?",
        "The language will change after a restart.\nRestart now?",
    ),

    # -- login dialog ---------------------------------------------------- #
    "login_title": ("Zaloguj się przez Claude", "Sign in with Claude"),
    "login_steps": (
        "Otwarto stronę logowania Claude w przeglądarce.\n\n"
        "1.  Zaloguj się na swoje konto Claude (Pro / Max) i zatwierdź dostęp.\n"
        "2.  Skopiuj wyświetlony kod autoryzacyjny.\n"
        "3.  Wklej go poniżej i kliknij „Zaloguj”.",
        "Opened the Claude sign-in page in your browser.\n\n"
        "1.  Sign in to your Claude account (Pro / Max) and approve access.\n"
        "2.  Copy the authorization code shown.\n"
        "3.  Paste it below and click “Sign in”.",
    ),
    "login_reopen": ("Otwórz ponownie stronę logowania", "Reopen the sign-in page"),
    "login_paste_ph": ("Wklej tutaj kod autoryzacyjny…", "Paste the authorization code here…"),
    "login_btn": ("Zaloguj", "Sign in"),
    "login_opened": (
        "Otwarto przeglądarkę — zaloguj się i wklej kod.",
        "Browser opened — sign in and paste the code.",
    ),
    "login_need_code": ("Najpierw wklej kod autoryzacyjny.", "Paste the authorization code first."),
    "login_connecting": ("Łączenie z Claude…", "Connecting to Claude…"),
    "login_failed": ("Logowanie nie powiodło się. {err}", "Sign-in failed. {err}"),
    "login_success": ("Zalogowano pomyślnie.", "Signed in successfully."),

    # -- history window -------------------------------------------------- #
    "hist_title": ("Historia użycia — Claude Usage Monitor", "Usage history — Claude Usage Monitor"),
    "hist_heading": ("Historia użycia", "Usage history"),
    "hist_reload": ("Odśwież", "Refresh"),
    "hist_daily_prompts": ("Prompty dziennie (ostatnie 14 dni)", "Prompts per day (last 14 days)"),
    "hist_session_util": ("Wykorzystanie sesji 5h (ostatnie 24h)", "5h session utilisation (last 24h)"),
    "hist_details": ("Szczegóły dzienne", "Daily details"),
    "hist_col_date": ("Data", "Date"),
    "hist_col_prompts": ("Prompty", "Prompts"),
    "hist_col_peak_session": ("Szczyt sesji", "Session peak"),
    "hist_col_peak_week": ("Szczyt tyg.", "Week peak"),
    "hist_no_data": ("Brak danych", "No data"),
    "hist_too_few": ("Za mało danych (24h)", "Not enough data (24h)"),

    # -- about ----------------------------------------------------------- #
    "about_title": ("O programie — {app}", "About — {app}"),
    "about_desc1": (
        "Monitor limitów użycia Claude w czasie rzeczywistym.",
        "Real-time monitor of your Claude usage limits.",
    ),
    "about_desc2": (
        "Widżet zawsze na wierzchu + ikona w zasobniku.",
        "Always-on-top widget + system-tray icon.",
    ),
    "about_author": ("Autor", "Author"),
    "about_mode": ("Tryb", "Mode"),
    "about_data": ("Folder danych", "Data folder"),

    # -- client connection / errors ------------------------------------- #
    "cl_no_httpx": ("Brak biblioteki httpx", "httpx library missing"),
    "cl_no_httpx_pip": ("Brak biblioteki httpx (pip install httpx).", "httpx library missing (pip install httpx)."),
    "cl_mock_ok": (
        "Tryb demonstracyjny działa — brak połączenia sieciowego.",
        "Demo mode works — no network connection.",
    ),
    "cl_no_oauth": ("Nie znaleziono lokalnego tokenu OAuth.", "No local OAuth token found."),
    "cl_no_oauth_short": ("Nie znaleziono tokenu OAuth", "OAuth token not found"),
    "cl_oauth_expired": ("Token OAuth wygasł (401)", "OAuth token expired (401)"),
    "cl_connected_plan": (
        "Połączono ({plan}). Sesja {s}% / Tydzień {w}%",
        "Connected ({plan}). Session {s}% / Week {w}%",
    ),
    "cl_no_key": ("Nie podano klucza API.", "No API key provided."),
    "cl_connected": ("Połączono. Sesja {s}% / Tydzień {w}%", "Connected. Session {s}% / Week {w}%"),
    "cl_oauth_401": ("Token OAuth wygasł lub jest nieprawidłowy (401).", "OAuth token expired or invalid (401)."),
    "cl_key_401": ("Nieprawidłowy klucz API (401).", "Invalid API key (401)."),
    "cl_rate_limited": ("Połączono, ale limit chwilowo wyczerpany (429).", "Connected, but rate-limited for now (429)."),
    "cl_http_err": ("Błąd HTTP {code}.", "HTTP error {code}."),
    "cl_conn_err": ("Błąd połączenia: {exc}", "Connection error: {exc}"),

    # -- oauth_login exceptions ----------------------------------------- #
    "ol_no_httpx": ("Brak biblioteki httpx (pip install httpx).", "httpx library missing (pip install httpx)."),
    "ol_empty_code": ("Pusty kod autoryzacyjny.", "Empty authorization code."),
    "ol_net_err": ("Błąd sieci: {exc}", "Network error: {exc}"),
    "ol_rejected": ("Odrzucono ({code}): {detail}", "Rejected ({code}): {detail}"),
    "ol_bad_resp": ("Nieprawidłowa odpowiedź serwera.", "Invalid server response."),
    "ol_no_token": ("Brak access_token w odpowiedzi.", "No access_token in the response."),
}
