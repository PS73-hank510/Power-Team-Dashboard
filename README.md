# Power Systems Monitoring Dashboard

A Python desktop application for real-time monitoring, control, and logging of a hardware test bench. Connects to one or more VISA-compatible power supplies and electronic loads, displays live telemetry graphs, enforces safety limits with Microsoft Teams alerts, and logs all data to timestamped CSV files.

---

## Hardware Topology

```
Laptop ──VISA──► Power Supply 1 ──┐
               Power Supply 2 ──┤──► Device Under Test ──► Load 1 ──VISA──► Laptop
               ...               ┘                         Load 2 ──VISA──► Laptop
```

Multiple power supplies and loads are supported. Running with no load at all (PSU-only mode) is also supported.

---

## Features

| Feature | Details |
|---------|---------|
| **Live telemetry graphs** | Scrolling pyqtgraph plots for V/I/P (PSU) and V/I (Load). Configurable time window: 10 s / 30 s / 60 s / 120 s / All. |
| **Multi-instrument** | Connect any number of power supplies and loads. Each gets its own panel and colour-coded graph curve. |
| **PSU-only mode** | Run a test with no load connected — just tick "No load" in the Connection panel. |
| **Safety limits** | Per-parameter upper and lower limits. Visual dashed lines on graphs. |
| **Teams alerts** | Limit breaches and communication errors sent to a Microsoft Teams channel via Webhook (Adaptive Card). 60 s throttle per parameter to prevent spam. |
| **CSV logging** | Continuous `session_YYYYMMDD_HHMMSS.csv` with flush-on-write for crash safety. |
| **Hard failsafe** | While a test is RUNNING: all parameter inputs are locked, the app cannot be closed, and no commands can disturb the test. |
| **Configurable** | Poll rate, Teams URL, log folder, instrument output/input control — all via the Settings dialog. |
| **Standalone .exe** | Ships as a self-contained Windows executable via PyInstaller. No Python required on the target machine. |
| **Portable** | `config.json` and `logs/` live beside the executable. Copy the folder to any machine and it works. |

---

## Screenshots

> *The dashboard with connection panel, live graphs, and alert log.*

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Power Systems Monitoring Dashboard                                          │
├──────────────────────┬──────────────────────────────────────────────────────┤
│  Connection          │  PSU Telemetry (V / I / P)                           │
│  ┌────────────────┐  │  ┌─────────────────────────────────────────────────┐ │
│  │ PSU 1: [____]  │  │  │                      ~~~~                       │ │
│  │ + Add PSU      │  │  │              ~~~~~~~~~~~                         │ │
│  │ Load 1: [____] │  │  └─────────────────────────────────────────────────┘ │
│  │ + Add Load     │  │  Load Telemetry (V / I)                              │
│  │ ☐ No load      │  │  ┌─────────────────────────────────────────────────┐ │
│  │ [Connect]      │  │  │          ~~~~~~~~~                               │ │
│  ├────────────────┤  │  └─────────────────────────────────────────────────┘ │
│  │ Power Supply 1 │  ├──────────────────────────────────────────────────────┤
│  │ Vset  [ 12.0 V]│  │  Alerts Log                                          │
│  │ Ilim  [  2.0 A]│  │  [10:23:41] Test started. Logging to: session_...   │
│  ├────────────────┤  │  [10:23:40] Instruments connected: 1 PSU(s), 1 load │
│  │ Limits  [Apply]│  └──────────────────────────────────────────────────────┤
│  │ [▶ START TEST] │                                                          │
└──────────────────────┴──────────────────────────────────────────────────────┘
```

---

## Requirements

- **Windows 10/11** (primary target; also runs on Linux/macOS for development)
- **Python 3.11+**
- A VISA-compatible instrument (USB, GPIB, TCP/IP, Serial)

---

## Quick Start

### Developer setup

```bat
git clone https://github.com/PS73-hank510/Power-Team-Dashboard.git
cd Power-Team-Dashboard

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python main.py
```

Or use the included convenience script:

```bat
setup.bat          :: creates venv + installs dependencies
run.bat            :: activates venv and launches the app
```

### Standalone .exe (no Python needed)

```bat
build.bat
```

Output: `dist\PowerTeamDashboard\PowerTeamDashboard.exe`  
Copy the entire `dist\PowerTeamDashboard\` folder to the target machine and run the `.exe`. `config.json` and `logs\` are created beside it on first launch.

---

## Usage

### 1. Connect instruments

1. Click **Scan for Instruments** to discover available VISA resources.
2. Enter the VISA address for each Power Supply in the **PSU** rows. Click **+ Add PSU** to add more.
3. Enter the VISA address for each Load in the **Load** rows. Click **+ Add Load** to add more.
4. Tick **"No load (PSU-only test)"** if you are not using any electronic load.
5. Click **Connect**.

### 2. Configure setpoints and limits

- **Power Supply panel**: set voltage and current limit for each PSU.
- **Electronic Load panel**: select mode (CC / CV / CR / CP) and set value.
- **Limits panel**: enter upper and/or lower bounds per parameter. Click **Apply Limits**. Leave a field blank to disable that side. Active limits appear as dashed lines on the graphs.

### 3. Run a test

- Click **▶ START TEST**.  
  All inputs are immediately locked. The test runs, graphs scroll, and data is logged.
- Click **⏹ STOP TEST** when done.  
  Inputs are unlocked and a new test can be started.

### 4. Review data

- CSV files are written to the configured **Log directory** (default: `logs\` beside the executable).
- Right-click either graph for **Save image (PNG)** or **Export data as CSV** of the current time window.

---

## Configuration

Open **Settings → Open Settings…** to configure:

| Setting | Description |
|---------|-------------|
| Poll rate | Sampling frequency: 0.5 / 1 / 2 / 5 / 10 Hz |
| Control PSU output | Automatically send `OUTPUT ON/OFF` on test start/stop |
| Control Load input | Automatically send `INPUT ON/OFF` on test start/stop |
| Log directory | Where CSV files are written |
| Teams Webhook URL | Microsoft Teams Workflow webhook for limit/error alerts |

All settings are saved in `config.json` beside the executable and persist between sessions.

### Microsoft Teams alerts

1. In your Teams channel, click **…** → **Workflows**.
2. Search for *"Post to a channel when a webhook request is received"* and complete the wizard.
3. Copy the webhook URL and paste it into **Settings → Webhook URL**.

---

## Project Structure

```
Power-Team-Dashboard/
├── main.py                      # Entry point
├── main.spec                    # PyInstaller build spec
├── requirements.txt
├── setup.bat / run.bat / build.bat
├── assets/
│   └── icon.ico                 # Application icon
├── src/
│   ├── config/
│   │   └── settings_manager.py  # Config persistence + APP_ROOT detection
│   ├── core/
│   │   ├── models.py            # TelemetrySample, LimitPair, TestState
│   │   ├── csv_logger.py        # Crash-safe CSV writer
│   │   ├── limit_checker.py     # Per-parameter breach detection
│   │   ├── poller.py            # QThread instrument poller
│   │   └── test_controller.py   # State machine + orchestration hub
│   ├── gui/
│   │   ├── main_window.py       # Top-level window + failsafe close
│   │   ├── connection_panel.py  # Dynamic VISA string rows
│   │   ├── psu_panel.py         # PSU setpoints + live readings
│   │   ├── load_panel.py        # Load mode/value + live readings
│   │   ├── limits_panel.py      # Limit configuration
│   │   ├── control_bar.py       # Start / Stop button + status
│   │   ├── graph_panel.py       # Live pyqtgraph plots
│   │   ├── alerts_log_widget.py # Timestamped event log
│   │   └── settings_dialog.py   # Settings modal
│   ├── instruments/
│   │   ├── base.py              # Abstract BaseInstrument + CommunicationError
│   │   ├── power_supply.py      # PowerSupply (SCPI)
│   │   └── electronic_load.py   # ElectronicLoad (SCPI)
│   └── notifications/
│       └── teams_notifier.py    # Microsoft Teams Adaptive Card sender
└── tests/
    ├── conftest.py              # Shared mock fixtures
    ├── test_settings_manager.py
    ├── test_csv_logger.py
    ├── test_limit_checker.py
    ├── test_teams_notifier.py
    ├── test_instruments.py
    ├── test_poller.py
    ├── test_test_controller.py
    └── test_main_window.py
```

---

## Architecture

The application follows a strict layering rule: **no Qt imports in `src/core/` or `src/instruments/`** except in `poller.py` (QThread) and `test_controller.py` (QObject). All cross-thread communication uses Qt signals — no shared mutable state, no queues.

```
models.py  (shared dataclasses — imported everywhere)
    │
    ├── settings_manager.py ──► config.json / logs/
    ├── csv_logger.py
    ├── limit_checker.py
    ├── teams_notifier.py
    └── instruments/base.py
            ├── power_supply.py
            └── electronic_load.py
                    │
                    └── poller.py  (QThread — first Qt dependency)
                            │
                            └── test_controller.py  (QObject, state machine)
                                    │
                                    └── main_window.py  (QMainWindow)
```

**State machine** (`TestState`):

```
DISCONNECTED ──connect──► CONNECTED ──start──► RUNNING ──stop──► STOPPED
                               ▲                                      │
                               └──────────────────────────────────────┘
```

---

## Development

### Running tests

```bat
pytest tests\ -v
pytest tests\ -v --cov=src --cov-report=term-missing
```

### Adding a new instrument type

1. Subclass `BaseInstrument` in `src/instruments/`.
2. Override the `CMD_*` class attributes with your instrument's SCPI command strings.
3. No changes needed to the poller, controller, or GUI — just pass your instances to `connect_instruments()`.

### Customising SCPI commands

All SCPI strings are class-level attributes on `PowerSupply` and `ElectronicLoad`. Override them in a subclass without touching any other code:

```python
class MyPsu(PowerSupply):
    CMD_MEASURE_VOLTAGE = "MEAS:VOLT?"
    CMD_SET_VOLTAGE     = "VOLT {value}"
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6` | GUI framework |
| `pyqtgraph` | Live scrolling graphs |
| `pyvisa` | VISA instrument communication API |
| `pyvisa-py` | Pure-Python VISA backend (no NI-VISA required) |
| `httpx` | HTTP client for Teams webhook |
| `pyinstaller` | Standalone .exe packaging |
| `pytest`, `pytest-qt` | Testing |

---

## License

Internal tool — © Piersight. All rights reserved.
