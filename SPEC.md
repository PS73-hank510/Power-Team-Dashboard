# Spec: Power Systems Monitoring Dashboard

## Objective

Build a Python desktop application for real-time monitoring, control, and logging of a hardware test bench consisting of a VISA-connected power supply and electronic load. The application must:

- Display live telemetry (voltage, current, power) from both instruments
- Allow the user to configure and control the electronic load mode (CC/CV/CR/CP) and values
- Enforce user-defined safety limits and alert a Microsoft Teams channel on breach
- Log all telemetry continuously to timestamped CSV files
- Display scrolling live graphs of all telemetry values
- Implement a hard failsafe: once a test is started, no parameters can be changed and the app cannot be closed until the test is explicitly stopped

**Hardware topology:**
```
Laptop ──VISA──► Power Supply ──► DUT ──► Electronic Load ──VISA──► Laptop
```

**User:** Hardware test engineer running controlled power/load cycle tests on a Device Under Test.

**Portability requirement:** The application must run on **any Windows laptop** without modification. No paths, settings, or identifiers may be hardcoded to a specific machine. The entire application — including its config, logs, and settings — must be self-contained and transferable (e.g., via USB drive or shared folder). A new user on a new machine should be able to run it by installing dependencies and launching `main.py`, with no code changes required.

**Success:** A test can be started, run unattended, and stopped cleanly — with full telemetry logs, live graphs, and Teams alerts throughout — without any risk of accidental parameter changes or silent failures.

---

## Tech Stack

| Component         | Technology                          |
|-------------------|-------------------------------------|
| Language          | Python 3.11+                        |
| GUI Framework     | PyQt6                               |
| Live Graphing     | pyqtgraph                           |
| VISA Comms        | pyvisa + pyvisa-py (pure Python backend) |
| HTTP (Teams)      | httpx                               |
| Config Persistence| JSON (stdlib)                       |
| Logging           | CSV (stdlib)                        |
| Path handling     | pathlib (stdlib) — no hardcoded paths |
| Packaging         | PyInstaller (optional standalone .exe) |
| Testing           | pytest + pytest-qt                  |

---

## Commands

```bash
# First-time setup on any machine
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Run the dashboard
python main.py

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Lint
flake8 src/ tests/ --max-line-length=100

# Format
black src/ tests/

# Build standalone .exe (primary distribution — no Python needed on target machine)
pyinstaller main.spec
# Output: dist/PowerTeamDashboard/PowerTeamDashboard.exe
```

Two convenience scripts are included for Windows:

`setup.bat` — first-time developer setup:
```bat
@echo off
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
echo Setup complete. Run: python main.py
pause
```

`build.bat` — build the distributable .exe:
```bat
@echo off
call venv\Scripts\activate
pyinstaller main.spec --clean
echo Build complete. Distribute: dist\PowerTeamDashboard\
pause
```

---

## Project Structure

```
power_team_dashboard/
├── main.py                        # Entry point — launches QApplication
├── main.spec                      # PyInstaller build spec — maintained in repo
├── setup.bat                      # First-time dev setup (creates venv, installs deps)
├── build.bat                      # Builds dist/PowerTeamDashboard/PowerTeamDashboard.exe
├── requirements.txt               # Pinned dependencies
├── SPEC.md                        # This file
├── assets/
│   └── icon.ico                   # App icon (bundled into .exe)
├── config.json                    # Auto-created at runtime; NOT committed to git
├── logs/                          # Auto-created at runtime; NOT committed to git
│   └── session_YYYYMMDD_HHMMSS.csv
│
├── src/
│   ├── __init__.py
│   │
│   ├── gui/                       # All PyQt6 UI widgets and windows
│   │   ├── __init__.py
│   │   ├── main_window.py         # Top-level QMainWindow; owns state machine
│   │   ├── connection_panel.py    # VISA resource string inputs + Connect/Disconnect
│   │   ├── psu_panel.py           # PSU live readings + voltage/current setpoint inputs
│   │   ├── load_panel.py          # Load mode selector + value inputs
│   │   ├── limits_panel.py        # Per-parameter limit configuration
│   │   ├── graph_panel.py         # Scrolling pyqtgraph live plots
│   │   ├── control_bar.py         # Start / Stop button + test status indicator
│   │   └── alerts_log_widget.py   # In-app alerts/event log panel
│   │
│   ├── instruments/               # VISA instrument abstraction layer
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract base class for all SCPI instruments
│   │   ├── power_supply.py        # PSU: measure V/I/P, set output, on/off
│   │   └── electronic_load.py     # Load: set mode + values, measure V/I, input on/off
│   │
│   ├── core/                      # Business logic — no Qt imports
│   │   ├── __init__.py
│   │   ├── test_controller.py     # State machine: DISCONNECTED→CONNECTED→RUNNING→STOPPED
│   │   ├── poller.py              # QThread that polls both instruments at configured rate
│   │   ├── limit_checker.py       # Evaluates telemetry samples against configured limits
│   │   └── csv_logger.py          # Opens session CSV, writes rows, flushes on every sample
│   │
│   ├── notifications/             # External alerting
│   │   ├── __init__.py
│   │   └── teams_notifier.py      # POST to Teams Workflow webhook; rate-limiting logic
│   │
│   └── config/                    # Settings persistence
│       ├── __init__.py
│       └── settings_manager.py    # Load/save config.json; typed dataclass for settings
│
└── tests/
    ├── conftest.py                # Shared fixtures (mock instruments, mock notifier)
    ├── test_limit_checker.py      # Unit tests for limit breach logic
    ├── test_csv_logger.py         # Unit tests for log file creation and row format
    ├── test_teams_notifier.py     # Unit tests for Teams payload + rate limiting
    ├── test_test_controller.py    # State machine transition tests
    └── test_instruments.py        # SCPI command formatting tests (mock VISA)
```

---

## Portability

### Rule: Everything is relative to the application root

```python
# src/config/settings_manager.py
from pathlib import Path

# APP_ROOT is always the directory containing main.py
# Works whether launched as: python main.py, .\dist\dashboard.exe, or from a USB drive
APP_ROOT = Path(__file__).resolve().parents[2]

CONFIG_FILE = APP_ROOT / "config.json"
LOGS_DIR    = APP_ROOT / "logs"
```

`APP_ROOT` is computed at runtime from `__file__` — it is **never** hardcoded to any absolute path like `C:\Users\...`. This means the entire project folder can be copied to any machine and it will work from wherever it is placed.

### VISA Backend — two options, both portable

| Option | How it works | Requirement on target machine |
|--------|-------------|-------------------------------|
| **pyvisa-py** (default) | Pure Python — no native driver needed | Just `pip install pyvisa-py` |
| **NI-VISA** | Uses National Instruments VISA runtime | NI-VISA must be installed separately |

The app defaults to `pyvisa-py` so it works out of the box. If a user has NI-VISA installed, pyvisa will use it automatically. The VISA backend is **not hardcoded** — pyvisa auto-detects what's available.

```python
import pyvisa
rm = pyvisa.ResourceManager()   # Uses NI-VISA if installed, pyvisa-py otherwise
# Do NOT pass a hardcoded backend path like ResourceManager('C:\...\visa.dll')
```

### VISA Resource String — entered by user, never hardcoded

The VISA resource string (e.g., `USB0::0x0957::0x2C07::MY12345::INSTR`) uniquely identifies an instrument on a specific machine. It **must** be entered by the user in the Connection panel and is stored in `config.json`. It is **never** hardcoded in source.

The Connection panel includes a **"Scan for Instruments"** button that calls `rm.list_resources()` and populates a dropdown — so the user doesn't need to know the resource string by heart.

### Distribution options

**Primary distribution: Standalone .exe via PyInstaller**

- Built with: `pyinstaller main.spec`
- Output: `dist/PowerTeamDashboard/PowerTeamDashboard.exe`
- Bundled: Python runtime + all dependencies (PyQt6, pyqtgraph, pyvisa, pyvisa-py, httpx)
- On first run: `config.json` and `logs/` are auto-created **next to the `.exe`**
- To deploy to a new machine: copy the entire `dist/PowerTeamDashboard/` folder — nothing else needed
- No Python installation required on the target machine
- No admin rights required to run (no installer, just a folder)

**`main.spec` key settings:**
```python
# main.spec (maintained in repository)
a = Analysis(
    ['main.py'],
    datas=[],                      # No bundled data files — config+logs live beside the .exe
    hiddenimports=[
        'pyvisa_py',               # pyvisa-py backend must be explicitly included
        'pyqtgraph',
    ],
    ...
)
exe = EXE(
    ...,
    name='PowerTeamDashboard',
    console=False,                 # No terminal window — GUI only
    icon='assets/icon.ico',        # App icon
)
```

**APP_ROOT detection for .exe vs script:**
```python
# src/config/settings_manager.py
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    # Running as PyInstaller .exe — APP_ROOT is next to the .exe
    APP_ROOT = Path(sys.executable).parent
else:
    # Running as Python script — APP_ROOT is the project root
    APP_ROOT = Path(__file__).resolve().parents[2]

CONFIG_FILE = APP_ROOT / "config.json"
LOGS_DIR    = APP_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
```

This single block makes the app work correctly whether launched as `python main.py` (development) or `PowerTeamDashboard.exe` (deployed), with no other code changes.

### What must NOT be machine-specific

| Item | Rule |
|------|------|
| File paths | Always relative to `APP_ROOT` via `pathlib.Path` |
| VISA resource strings | Always from `config.json`, never in source |
| Teams webhook URL | Always from `config.json`, never in source |
| Log directory | Always `APP_ROOT / "logs"` |
| Python version assumption | Specify `>=3.11` in `requirements.txt`, tested on 3.11 and 3.12 |
| Windows-specific API calls | None — use stdlib/PyQt6 only for OS interactions |

---

## Architecture: Key Design Decisions

### 1. Threading Model

```
Main Thread (Qt event loop)
    │
    ├── GUI widgets (read-only during RUNNING state)
    └── Signals received from PollWorker

PollWorker (QThread)
    │
    ├── Polls PSU via VISA every N ms
    ├── Polls Load via VISA every N ms
    └── Emits telemetry_sample signal → Main Thread
         └── Main Thread: update GUI + graphs + check limits + log
```

**Rule:** VISA calls happen only on PollWorker thread. Qt widgets are only touched on the main thread. Communication is via Qt signals only — never shared mutable state.

### 2. State Machine

```
DISCONNECTED
    │  (both VISA connections succeed)
    ▼
CONNECTED
    │  (Start button pressed)
    ▼
RUNNING ◄──────────────────────────────────────┐
    │  (communication loss — stays RUNNING,     │
    │   Teams alert sent, error logged)         │
    │                                           │
    │  (Stop button pressed)                    │
    ▼                                           │
STOPPED ───────────────────────────────────────┘
    │  (reconnect after stop)
    ▼
CONNECTED
```

**In RUNNING state:**
- All parameter input widgets → `setEnabled(False)`
- Start button label → "STOP TEST" (red)
- Window close event → intercepted, shows blocking warning dialog
- Load mode selector → disabled
- VISA resource string fields → disabled

### 3. SCPI Command Reference (Standard — Verify Against Your Instrument Manual)

**Power Supply:**
```
Query identity:        *IDN?
Set voltage:           VOLTage <value>
Set current limit:     CURRent <value>
Enable output:         OUTPut ON
Disable output:        OUTPut OFF
Measure voltage:       MEASure:VOLTage[:DC]?
Measure current:       MEASure:CURRent[:DC]?
Measure power:         MEASure:POWer?
```

**Electronic Load:**
```
Query identity:        *IDN?
Set CC mode:           FUNCtion CC  (or MODE CC on some instruments)
Set CV mode:           FUNCtion CV
Set CR mode:           FUNCtion CR
Set CP mode:           FUNCtion CP
Set CC value:          CURRent <value>
Set CV value:          VOLTage <value>
Set CR value:          RESistance <value>
Set CP value:          POWer <value>
Enable input:          INPut ON
Disable input:         INPut OFF
Measure voltage:       MEASure:VOLTage?
Measure current:       MEASure:CURRent?
```

> **⚠️ Note:** SCPI command names vary by manufacturer. The `base.py` instrument class exposes the command strings as configurable class attributes so they can be overridden per instrument without subclassing the full implementation.

### 4. Limit Checker

- Evaluated on every telemetry sample
- Per-parameter limit pair: `{ "psu_voltage": {"min": 9.0, "max": 15.0}, "psu_current": {"min": null, "max": 5.0}, ... }`
- `null` = limit disabled for that side
- State per parameter per side: `IN_RANGE` | `BREACH_ACTIVE`
- On transition `IN_RANGE → BREACH_ACTIVE`: send Teams alert — explicitly states "UPPER LIMIT BREACH" or "LOWER LIMIT BREACH" + parameter name + exact value + limit value + timestamp
- On transition `BREACH_ACTIVE → IN_RANGE`: send Teams "resolved" message
- **Rate limit:** Max 1 alert per parameter per side per 60 seconds (prevents spam if value oscillates around limit)
- Both upper and lower breach can be active simultaneously for the same parameter (e.g., value oscillating past both ends)

### 5. Teams Notification (Microsoft Workflow Webhook)

**Setup instructions (included in app Help menu):**
1. Open the target Teams channel → click `...` → `Workflows`
2. Search for "Post to a channel when a webhook request is received"
3. Complete setup, copy the webhook URL
4. Paste URL into dashboard Settings panel

**Payload format:**
```json
{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [{
        "type": "TextBlock",
        "text": "⚠️ LIMIT BREACH: PSU Voltage = 15.32 V (limit: 15.00 V)",
        "wrap": true,
        "color": "Attention"
      }]
    }
  }]
}
```

### 6. CSV Log Format

```
timestamp,source,parameter,value,unit
2024-01-15T10:23:45.123,PSU,voltage,12.04,V
2024-01-15T10:23:45.123,PSU,current,2.31,A
2024-01-15T10:23:45.123,PSU,power,27.81,W
2024-01-15T10:23:45.124,LOAD,voltage,11.98,V
2024-01-15T10:23:45.124,LOAD,current,2.29,A
```

Log file named: `logs/session_YYYYMMDD_HHMMSS.csv`
File opened at test start, flushed every sample, closed at test stop.

### 7. Live Graphs (pyqtgraph)

- Two graph groups: **PSU** (voltage, current, power) and **Load** (voltage, current, mode setpoint)
- Each parameter = one curve on a shared time axis
- Scrolling window: last 60 seconds (configurable 10s / 30s / 60s / 120s / All)
- Update rate matches poll rate
- Y-axis auto-scales with 10% headroom above max observed value
- Limit lines rendered as dashed horizontal lines on each graph

---

## GUI Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Power Systems Monitoring Dashboard            [Settings] [Help]    │
├──────────────────────────────┬──────────────────────────────────────┤
│  CONNECTION                  │  CONTROL                             │
│  PSU  VISA: [____________]   │  ┌─────────────────────────────────┐ │
│  Load VISA: [____________]   │  │  ▶ START TEST        [green]    │ │
│  [Connect]  [Disconnect]     │  └─────────────────────────────────┘ │
├──────────────────────────────┴──────────────────────────────────────┤
│  POWER SUPPLY                │  ELECTRONIC LOAD                     │
│  Voltage:  [12.00 V] setpt   │  Mode: [CC ▼] [CV] [CR] [CP]        │
│  Current:  [3.00 A]  setpt   │  Set Value: [2.00] A                 │
│  ─────────────────────────   │  ────────────────────────────────    │
│  Measured Voltage: 11.98 V   │  Measured Voltage: 11.95 V           │
│  Measured Current: 2.31 A    │  Measured Current: 2.29 A            │
│  Measured Power:   27.7 W    │                                      │
├──────────────────────────────┴──────────────────────────────────────┤
│  LIMITS             Min          Max                                │
│  PSU Voltage:    [  9.00]    [ 15.00]                               │
│  PSU Current:    [  0.00]    [  5.00]                               │
│  Load Current:   [  0.00]    [  4.50]     [Apply Limits]            │
├─────────────────────────────────────────────────────────────────────┤
│  LIVE TELEMETRY GRAPHS                                [Window: 60s] │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ PSU: Voltage ── Current ── Power                                ││
│  │ [scrolling graph]                                               ││
│  └─────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Load: Voltage ── Current                                        ││
│  │ [scrolling graph]                                               ││
│  └─────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│  EVENT LOG                                                          │
│  [10:23:45] Test started                                            │
│  [10:25:12] ⚠ PSU Voltage limit breached: 15.32V (limit 15.00V)   │
│  [10:25:18] ✓ PSU Voltage returned to range                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Code Style

```python
# Naming: snake_case for variables/functions, PascalCase for classes
# Max line length: 100 characters
# Type hints on all function signatures
# Docstrings on all public classes and methods

from dataclasses import dataclass
from typing import Optional
from enum import Enum, auto


class TestState(Enum):
    DISCONNECTED = auto()
    CONNECTED = auto()
    RUNNING = auto()
    STOPPED = auto()


@dataclass
class TelemetrySample:
    """A single timestamped measurement from one instrument."""
    timestamp: float          # time.time()
    source: str               # "PSU" or "LOAD"
    parameter: str            # "voltage", "current", "power"
    value: float
    unit: str                 # "V", "A", "W", "Ω"


@dataclass
class LimitPair:
    """Upper and lower limits for a single parameter. None = disabled."""
    min: Optional[float] = None
    max: Optional[float] = None


class LimitChecker:
    """Evaluates telemetry samples against upper and lower configured limits.

    Maintains per-parameter, per-side breach state to support rate-limited alerting.
    Upper and lower breaches are tracked independently.
    """

    def __init__(self, limits: dict[str, LimitPair]) -> None:
        self._limits = limits
        # breach state key: "PSU_voltage_upper" or "PSU_voltage_lower"
        self._breach_state: dict[str, bool] = {}

    def check(self, sample: TelemetrySample) -> list[str]:
        """Returns list of alert message strings for any new breaches or resolutions."""
        key = f"{sample.source}_{sample.parameter}"
        pair = self._limits.get(key)
        if pair is None:
            return []

        alerts = []
        alerts.extend(self._check_side(sample, pair.max, "upper", sample.value >))
        alerts.extend(self._check_side(sample, pair.min, "lower", sample.value <))
        return alerts

    def _check_side(self, sample, limit, side, breach_condition) -> list[str]:
        if limit is None:
            return []
        state_key = f"{sample.source}_{sample.parameter}_{side}"
        in_breach = breach_condition(limit)
        was_in_breach = self._breach_state.get(state_key, False)
        self._breach_state[state_key] = in_breach

        if in_breach and not was_in_breach:
            return [(
                f"{side.upper()} LIMIT BREACH: {sample.source} {sample.parameter} = "
                f"{sample.value:.3f} {sample.unit} "
                f"({'>' if side == 'upper' else '<'} {limit:.3f} {sample.unit})"
            )]
        if not in_breach and was_in_breach:
            return [f"RESOLVED: {sample.source} {sample.parameter} {side} limit back in range"]
        return []
```

**Key conventions:**
- No global mutable state
- Qt signals/slots for all cross-thread communication — no `threading.Event` or shared queues
- All VISA calls wrapped in try/except; connection loss surfaces via signal, never crashes the thread
- Config saved on every meaningful user change (not just on close)

---

## Testing Strategy

**Framework:** `pytest` + `pytest-qt` (for Qt widget testing)

**Test locations:** `tests/` — mirrors `src/` structure

**Coverage target:** 80% for `src/core/` and `src/notifications/`; 60% for `src/instruments/`; GUI tested manually

**Test levels:**

| Concern | Level | Approach |
|---|---|---|
| Limit breach logic | Unit | Pure Python, no Qt, no VISA |
| CSV logger | Unit | Writes to `tmp_path` fixture |
| Teams notifier payload | Unit | Mock `httpx.post`, assert JSON shape |
| Teams rate limiting | Unit | Mock time, verify throttle |
| State machine transitions | Unit | No Qt, assert state changes |
| SCPI command formatting | Unit | Mock `pyvisa.ResourceManager` |
| Poll thread + signal emission | Integration | `pytest-qt`, mock instruments |
| Failsafe (close blocked) | Integration | `pytest-qt`, simulate close event |

**Test example structure:**
```python
# tests/test_limit_checker.py
def test_breach_detected_on_first_exceedance():
    checker = LimitChecker({"PSU_voltage": 15.0})
    sample = TelemetrySample(time.time(), "PSU", "voltage", 15.32, "V")
    result = checker.check(sample)
    assert result is not None
    assert "15.320" in result
    assert "limit: 15.000" in result

def test_no_duplicate_alert_on_sustained_breach():
    checker = LimitChecker({"PSU_voltage": 15.0})
    sample = TelemetrySample(time.time(), "PSU", "voltage", 15.5, "V")
    checker.check(sample)         # First breach — alert
    result = checker.check(sample) # Still breached — no second alert
    assert result is None
```

---

## Boundaries

**Always:**
- Keep all VISA I/O on the PollWorker thread — never call VISA from the main/GUI thread
- Flush CSV log on every sample write — data must survive an unexpected process kill
- Check test state before applying any parameter change — refuse silently if RUNNING
- Wrap every VISA call in try/except and emit a `communication_error` signal on failure
- Save config to `config.json` whenever the user changes a setting
- Rate-limit Teams alerts — never send more than 1 alert per parameter per 60 seconds
- Use `pathlib.Path` for all file/directory references — always relative to `APP_ROOT`
- Use `pyvisa.ResourceManager()` with no hardcoded backend path

**Ask first:**
- Adding new Python dependencies to `requirements.txt`
- Changing the CSV log schema (would break compatibility with existing log files)
- Changing the Teams webhook payload format
- Adding a new instrument type beyond PSU and Load
- Changing where `config.json` or `logs/` are stored

**Never:**
- Call Qt widget methods from the PollWorker thread (causes crash)
- Allow parameter changes while state is RUNNING
- Allow app close while state is RUNNING without showing the warning dialog
- Silently swallow VISA communication errors — always log + alert
- Store the Teams webhook URL in source code or git history
- Hardcode any absolute file path, VISA resource string, machine name, or username
- Hardcode a VISA backend path (e.g., `ResourceManager('C:\\...')`)

---

## Success Criteria

1. **Telemetry display:** PSU and Load measured values (V, I, P) update on screen at the configured poll rate (≥ 1 Hz)
2. **Live graphs:** Both graph panels scroll in real time; new samples appear within one poll interval
3. **Limit breach alert:** Exceeding an upper or lower configured limit sends a Teams message within 5 seconds of the first breaching sample; the message explicitly states "UPPER" or "LOWER" breach with the exact value and the configured limit
4. **Limit resolution alert:** Returning within limits sends a Teams "resolved" message
5. **Failsafe — parameter lock:** Clicking Start disables all parameter inputs, setpoint fields, load mode selector, and VISA string fields
6. **Failsafe — close blocked:** Attempting to close the window while RUNNING shows a modal warning; the window does not close
7. **Failsafe — stop required:** Clicking Stop re-enables all inputs and allows normal close
8. **Communication loss:** If VISA query fails during a running test, a Teams alert is sent within 10 seconds and an error entry appears in the event log; the test state remains RUNNING
9. **Continuous logging:** CSV log file is written and flushed for every poll sample from test start to test stop
10. **Config persistence:** VISA resource strings, Teams webhook URL, limits, and last-used load mode are restored on next app launch
11. **Load mode control:** All four modes (CC/CV/CR/CP) are selectable from the GUI; the correct SCPI command is sent on selection (when not RUNNING)
12. **No Qt crashes from threading:** The app runs for 60+ minutes without a segfault or "QObject used from wrong thread" error
13. **Portability — fresh machine:** The app runs correctly on a machine that has never run it before, after only running `setup.bat` and entering VISA resource strings + Teams webhook URL in the GUI
14. **Portability — no hardcoded paths:** A full grep of the source for `C:\\`, `D:\\`, `Users`, `Admin`, or any absolute path returns zero results
15. **Portability — instrument scan:** The "Scan for Instruments" button in the Connection panel returns available VISA resources from `rm.list_resources()`
16. **Standalone .exe:** `pyinstaller main.spec` produces a `dist/PowerTeamDashboard/` folder that launches and connects to instruments on a machine with no Python installation, by simply double-clicking `PowerTeamDashboard.exe`
17. **Exe portability:** `config.json` and `logs/` are created next to `PowerTeamDashboard.exe`, not in any user-specific system path

---

## Open Questions

All questions resolved.

1. ✅ **Poll rate:** Configurable dropdown — `0.5 / 1 / 2 / 5 / 10 Hz`. Default `1 Hz`. Saved in `config.json`.

2. ✅ **PSU output control:** Checkbox in Settings — "Control PSU output on Start/Stop". Default off. When enabled: sends `OUTPut ON` on Start, `OUTPut OFF` on Stop. Saved in `config.json`.

3. ✅ **Load input control:** Separate checkbox in Settings — "Control Load input on Start/Stop". Default off. When enabled: sends `INPut ON` on Start, `INPut OFF` on Stop. Independent of PSU checkbox. Saved in `config.json`.

4. ✅ **Log directory:** Folder picker in Settings panel (browse button). Defaults to `logs/` beside the `.exe`. Saved in `config.json`. Allows pointing logs to a network drive, project folder, or USB stick.

5. ✅ **Limit types:** Both upper (max) and lower (min) limits per parameter. Each is optional — leave blank to disable that side. Alert message explicitly states "UPPER LIMIT BREACH" or "LOWER LIMIT BREACH" with the exact value and the breached limit.

6. ✅ **Graph export:** Right-click context menu on each graph with two options: "Save image..." (PNG) and "Export data as CSV...". Uses pyqtgraph's built-in export functionality.

7. ✅ **Distribution format:** Standalone `.exe` via PyInstaller. No Python installation required on target machines. See Distribution section above.
