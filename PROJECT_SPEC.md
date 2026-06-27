# Claude Usage Monitor — Project Specification

A Windows system tray + always-on-top overlay widget that monitors Claude API
usage limits in real-time.

## Structure

```
Claude Usage Monitor/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── constants.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py           # Anthropic API client - lightweight ping, parses rate limit headers
│   │   ├── headers.py          # Parse anthropic-ratelimit-* headers
│   │   ├── oauth.py            # OAuth token reader
│   │   ├── poller.py           # QTimer-based periodic polling
│   │   └── models.py           # UsageSnapshot, SubscriptionInfo, DailyUsageRecord dataclasses
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── tray.py             # QSystemTrayIcon with color-coded icon + right-click menu
│   │   ├── overlay.py          # Main always-on-top floating widget with all sections
│   │   ├── settings_window.py  # Settings dialog
│   │   ├── history_window.py   # Usage history with charts
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── progress_bar.py   # Custom gradient animated progress bar
│   │   │   ├── circular_gauge.py # Circular percentage gauge (subscription %)
│   │   │   ├── peak_indicator.py # 24h peak/off-peak horizontal bar
│   │   │   ├── activity_chart.py # Mini activity heatmap
│   │   │   ├── prompt_counter.py # Animated counter with timeline
│   │   │   └── model_badge.py    # Model name badge
│   │   └── styles/
│   │       ├── __init__.py
│   │       ├── dark_theme.py     # QSS stylesheet generation
│   │       └── colors.py        # Color constants
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLite setup + CRUD
│   │   └── history.py           # History queries
│   └── utils/
│       ├── __init__.py
│       ├── notifications.py     # Windows toast notifications
│       ├── autostart.py         # Windows registry auto-start
│       ├── encryption.py        # Keyring wrapper
│       └── peak_hours.py        # Peak hours calculator (US Pacific time)
├── config/
│   └── default.toml
├── assets/                      # Generate simple colored circle icons programmatically
├── requirements.txt
├── build.py
├── README.md
└── PROJECT_SPEC.md
```

## Key Implementation Details

### API Client (api/client.py)
- Uses httpx to make a tiny API call to Anthropic.
- Parses ALL rate limit headers from the response.
- API key auth: `POST /v1/messages` with `model=claude-haiku-4-5-20251001`,
  `max_tokens=1`, `messages=[{"role":"user","content":"hi"}]`.
- OAuth: read utilization headers (`anthropic-ratelimit-5h-utilization` etc.).
- Returns a `UsageSnapshot` dataclass.
- Includes a **mock mode** that produces realistic, time-driven demo data so the
  UI works without any credentials.

### Overlay Widget (ui/overlay.py)
The most important part — modern dark theme. Background `#0a0e1a`, sections
`#111827`, rounded corners 12px.

Sections (top to bottom):
1. **TAB BAR**: "DZIŚ" / "TYDZIEŃ" / "MIESIĄC" pill tabs.
2. **PROMPTY**: Large animated number + timeline bar of today's prompts.
3. **Model badge**: "● Opus 4.8" with usage.
4. **LIMITY**:
   - "SESJA 5H" + gradient progress bar (green→yellow→red) + % + countdown.
   - "TYDZIEŃ 7D" + gradient progress bar + % + countdown.
5. **SUBSKRYPCJA**: Circular gauge + Status / Cykl / Odnowienie / Pozostało.
6. **PEAK HOURS**: OFF-PEAK/PEAK badge, 24h bar (green off-peak / orange peak),
   current-time marker.
7. **AKTYWNOŚĆ**: Mini bar chart of activity intensity over last 24h.

Widget properties:
- `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`.
- Semi-transparent background with rounded corners.
- Draggable by holding anywhere on the widget.
- Remembers position in config.
- ~280x600 expanded, ~280x200 compact.
- Smooth `QPropertyAnimation` on progress bars.

### System Tray (ui/tray.py)
- `QSystemTrayIcon` with programmatically generated colored circle icons.
- Green / Yellow / Orange / Red / Gray based on usage level.
- Left-click toggles overlay.
- Right-click menu: Show Widget, Compact/Expanded, Refresh, History, Settings,
  About, Quit.
- Tooltip: "Claude Monitor: Session 45% | Week 72%".

### Settings (ui/settings_window.py)
- Auth: API key input (password echo), auth type combo, Test button, model combo.
- Display: opacity slider, always-on-top, compact default, language.
- Polling: interval spinbox, smart polling checkbox.
- Notifications: enable, thresholds 80/90/100.
- System: autostart, minimize-to-tray.

### Storage (storage/database.py)
- SQLite in `%APPDATA%/ClaudeMonitor/usage.db`.
- `usage_snapshots(timestamp, requests_remaining, tokens_remaining, session_util,
  week_util, model, is_peak)`.
- `daily_summaries(date, total_prompts, peak_session_util, peak_week_util)`.

### Notifications (utils/notifications.py)
- `win10toast` with fallback to `QSystemTrayIcon.showMessage`.
- Triggers at 80% / 90% / 100%.
- De-duplicated per usage window.

### Colors
| Token | Hex |
|-------|-----|
| BG Primary | `#0a0e1a` |
| BG Secondary | `#111827` |
| BG Tertiary | `#1e293b` |
| Border | `#1e3a5f` |
| Text Primary | `#f1f5f9` |
| Text Secondary | `#94a3b8` |
| Blue | `#3b82f6` |
| Green | `#22c55e` |
| Yellow | `#eab308` |
| Red | `#ef4444` |
| Purple | `#8b5cf6` |

### Icons
Generated programmatically with `QPainter` — filled circles with status colors
(see `assets/generate_icons.py` and `ui/tray.py`).

## Non-functional requirements
- Complete, working code in every file.
- Every widget component renders properly.
- `QPropertyAnimation` for smooth progress transitions.
- Polished, professional overlay.
- Graceful error handling (no internet, invalid API key, missing tray).
- Demo/mock mode that works without an API key.
