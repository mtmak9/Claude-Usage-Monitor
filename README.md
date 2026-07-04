# Claude Usage Monitor

A Windows **system‑tray + always‑on‑top overlay** that shows your Claude
subscription usage in real time — your rolling **5‑hour** and **7‑day** limits,
plan, usage **credits ($)**, peak hours and activity — at a glance.

No API key required: sign in once with your **Claude account (Pro / Max)** and
the app reads your usage straight from the official endpoint.

<p align="center">
  <img src="assets/Screenshot.png" alt="Claude Usage Monitor overlay" width="270">
</p>

![version](https://img.shields.io/badge/version-1.3.4-blueviolet)
![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-green)
![license](https://img.shields.io/badge/license-MIT-orange)

> Not affiliated with Anthropic. This is a community tool.

## Features

- 🔐 **Sign in with your Claude account** (OAuth, PKCE) — one click, no API key
- 📊 Live **5h session** and **7d weekly** utilisation with reset countdowns
- 🔁 **Claude / Codex panel switch** directly on the overlay, with model status dots
- 🧮 **Usage credits ($)** card — spent / monthly limit / balance
- 🟢 **Tray icon** that changes colour (green → yellow → orange → red) with usage
- 🪟 **Floating overlay** — frameless, translucent, always‑on‑top, drag anywhere
- 🟣 Subscription gauge, **Peak hours** (US Pacific) and an **Activity** heat‑bar
- 🔔 Tray notifications for **90 % / 100 % session usage** and weekly thresholds
- 🔊 Dedicated sounds for 100 % limit hits and session renewals
- 🧷 **Single instance** — launching the app twice reuses the running instance
- 💾 **SQLite history** with a charts window (daily prompts + 24h trend)
- 🚀 Optional **auto‑start** with Windows
- 🧪 **Demo mode** — the whole UI runs on realistic synthetic data, no account

### Codex mode

The app can also switch to **Codex** from the overlay’s Claude/Codex model pills
or in **Settings → Authorization → Provider**. Codex mode reads local Codex
session logs from `%USERPROFILE%\.codex\sessions` and shows real Codex **5h / 7d
rate-limit utilisation**, reset times and generated-token activity. No OpenAI API
key is required; you only need to be signed in to Codex with ChatGPT on the same
Windows account.

For Codex, the large token counter shows **generated tokens**. The breakdown also
shows context/cache, but the headline avoids counting the repeated full working
context that Codex sends on each model turn.

## What's new in v1.3.4

- Added a separate `limit_hit.wav` sound for 100% session limit hits.
- Kept `session_renewed.wav` as a distinct renewal chime, so hit and reset events are easy to tell apart.

## What's new in v1.3.3

- Fixed repeated renewal chimes when Claude remains at 100% after the reset timestamp moves.
- Session-full notifications now fire once at 100%; the renewal sound only plays after the session actually drops below full usage.
- Notification delivery now falls back to native Windows toast when tray message balloons are unavailable.

## What's new in v1.3.2

- Claude and Codex now refresh in parallel even when only one provider is open in the detailed monitor.
- Inactive provider updates now refresh only its status pill, without switching or overwriting the active panel.
- Provider polling uses separate cooldowns, so Claude OAuth keeps its rate-limit-safe cadence while Codex local logs can refresh normally.

## What's new in v1.3.1

- Fixed Codex subscription gauge so it always tracks the weekly 7d limit, not the 5h session limit.
- Fixed stale Codex session windows: expired local 5h records no longer keep the UI pinned at 100%.
- Changed the overlay switch labels to provider names (`Claude` / `Codex`) instead of model names.

## What's new in v1.3.0

- Added Claude/Codex multi-provider monitoring with an overlay panel switch.
- Fixed provider mixing so Claude and Codex token counters cannot overwrite each other.
- Changed Codex token headline to generated tokens for a more useful reading.
- Added session notifications at 90 % and 100 %, plus a dedicated renewal chime.
- Added single-instance protection so only one app copy can run at once.
- Updated the build to include the dedicated WAV sound asset in the one-file exe.

## How it gets your usage

Pick an auth mode in **Settings → Authorization**:

First choose the **Provider**:

| Provider | What it shows | Data source |
|----------|---------------|-------------|
| **Claude** | Claude subscription/API usage, credits and peak-hours context | Claude OAuth endpoint or API-key headers |
| **Codex** | Codex 5h/7d rate limits and local token activity | local `%USERPROFILE%\.codex\sessions` JSONL logs |

| Mode | What it does | Needs |
|------|--------------|-------|
| **OAuth (subscription)** ⭐ | Calls `GET /api/oauth/usage` with your Claude token for real 5h/7d utilisation and credits | a Claude Pro/Max account |
| **API key** | Pings `/v1/messages` (`max_tokens=1`) and reads the `anthropic-ratelimit-*` headers | an `sk-ant-…` key |
| **Demo** | Synthetic data, no network | nothing |

**OAuth is the default and recommended mode** for subscribers — it shows the same
limits you see in the Claude app and costs nothing.

## Quick start

```powershell
git clone <your-fork-url> claude-usage-monitor
cd claude-usage-monitor

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m src.main
```

The widget appears top‑right and a circular icon appears in your tray. Only one
copy of the app can run at once; launching it again will bring the existing
widget forward when Windows exposes the window handle.
**Left‑click** the tray icon to show/hide the widget, **right‑click** for the menu.

## Signing in

Open **Settings** (right‑click tray → *Ustawienia…*) → **Authorization**:

1. Make sure **Type** is set to **OAuth — subskrypcja**.
2. Click **“Zaloguj się przez Claude”** (*Sign in with Claude*).
3. Your browser opens Claude’s consent page → click **Authorize**.
4. Copy the authorization code shown and paste it back into the app → **Zaloguj**.

That’s it — the widget switches to live data immediately.

If you already use **Claude Code** or the **Claude desktop app** on the same
Windows account, the monitor will **auto‑detect** that login and you can skip the
button entirely (the status line shows e.g. *“✓ Wykryto (Max 5x)”*).

## Privacy & security

This tool is built to be safe to publish and safe to run:

- **No credentials are bundled.** Nothing personal is hard‑coded anywhere in the
  source. Your token is obtained at runtime, by *you*, through the official
  Claude OAuth flow.
- **Tokens stay on your machine.** A token obtained via the in‑app login is
  cached only in `%APPDATA%\ClaudeMonitor\oauth_cache.json`. The app never sends
  it anywhere except Anthropic’s own API (`api.anthropic.com`,
  `console.anthropic.com`).
- **Auto‑detected tokens are read‑only.** When reading an existing Claude login,
  the app never modifies or rotates the source app’s tokens.
- **API keys** (if you use that mode) are stored in the **Windows Credential
  Manager**, not in plain text.
- Runtime data (DB, logs, config, token cache) lives in `%APPDATA%\ClaudeMonitor\`
  and is git‑ignored.

> A note for contributors: `.credentials.json`, `oauth_cache.json`, `*.db` and
> `*.log` are in `.gitignore` — please keep it that way and never commit a real
> token.

## Controls

- **Drag** the widget anywhere to reposition (position is remembered)
- Header **▾ / ▴** toggles compact / full layout
- Header **✕** hides the widget (the app keeps running in the tray)
- Tabs **DZIŚ / TYDZIEŃ / MIESIĄC** switch the prompt counter period (today / week / month)

## Building a standalone .exe

```powershell
pip install pyinstaller
python build.py            # one‑file windowed build in .\dist
python build.py --onedir   # faster‑starting folder build
```

## Project layout

```
src/
  main.py            app wiring & lifecycle
  config.py          layered config (TOML defaults + JSON user overrides)
  constants.py       paths, models, thresholds, endpoints
  api/
    client.py        usage/ratelimit fetching + mock generator
    oauth.py         token discovery, decryption, refresh
    oauth_login.py   interactive OAuth (PKCE) login flow
    usage.py         /api/oauth/usage JSON → UsageSnapshot
    headers.py, models.py, poller.py
  ui/                overlay, tray, settings, login dialog, history + components
  storage/           SQLite database + history queries
  utils/             notifications, autostart, keyring, peak hours
config/default.toml  shipped defaults
assets/              icon generator + screenshot
                     limit-hit / renewal WAVs + sound generator
```

## Requirements

- Windows 10 / 11, Python 3.10+
- See [`requirements.txt`](requirements.txt). Optional extras degrade gracefully:
  - `cryptography` — only needed to auto‑detect the **Claude desktop app’s**
    encrypted token; the in‑app login and the CLI’s plaintext token work without it.
  - `win10toast` — richer toasts; falls back to tray balloons.

The dedicated alert sounds are bundled as
[`assets/limit_hit.wav`](assets/limit_hit.wav) and
[`assets/session_renewed.wav`](assets/session_renewed.wav). They can be
regenerated with `python assets/generate_sounds.py`.

## Troubleshooting

- **“Invalid request format” after Authorize** — make sure you’re on the latest
  version; the login flow requires `state == code_verifier` (fixed in this repo).
- **Widget shows demo data** — no usable token was found. Use *Sign in with
  Claude*, or sign in via Claude Code / the desktop app on the same user.
- **Credits show “Wyłączone / —”** — the usage endpoint only returns a balance
  while *Usage credits* is **enabled** in your Claude billing settings; otherwise
  the values are `null`. This is an API limitation, not a bug.
- **No tray icon** — re‑enable “Show all icons” in taskbar settings; the overlay
  still runs.
- **Double-clicking the app does nothing** — another instance is already running;
  use the tray icon or the existing widget.
- **`ModuleNotFoundError: PyQt6`** — activate your venv and re‑run
  `pip install -r requirements.txt`.
- **Peak hours look off** — ensure `tzdata` is installed (it’s in requirements).

## Contributing

Issues and PRs welcome. The UI strings are currently in **Polish**; an English
localisation is a great first contribution — UI text lives in `src/ui/`. Please
keep secrets out of commits (see *Privacy & security*).

## License

[MIT](LICENSE). Provided as‑is, with no warranty. Not affiliated with Anthropic;
“Claude” is a trademark of Anthropic, PBC.
