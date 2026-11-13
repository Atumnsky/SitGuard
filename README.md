# SitGuard

A small Windows tray app that watches your webcam to tell whether you are
**sitting** at the screen. It starts timing when you sit down, reminds you to
stand up and move after 45 minutes of continuous sitting, and stops the clock
as soon as you stand.

[中文说明](README_ZH.md) · [Releases](https://github.com/Atumnsky/SitGuard/releases)

![Main window](screenshots/main_en.png)

> Windows 10/11 · Python 3.13 · Camera frames are processed locally only —
> nothing is saved or uploaded.

## Features

- **Sit/stand detection** using MediaPipe Pose (33 landmarks) plus face and
  shoulder position, with an optional two-point calibration for your own
  camera angle and body size.
- **Smart timing** — only sitting time counts; standing pauses the timer.
- **45-minute reminder** — full-screen break overlay with a sound alert
  (or sound-only mode), and it re-alerts every 5 minutes until you stand.
- **Break finishes when you stand** for 10 seconds, leave the frame for
  12 seconds, or click a button (instant).
- **3-minute rule** — standing for 3 minutes before the reminder restarts the
  sitting timer from zero.
- **Sound-only mode** — hide the full-screen reminder; the app still plays
  the alert and re-reminds you every 5 minutes while you keep sitting.
- **No main-window pop-up** — after you stand, only a small desktop toast
  confirms it; the main window stays in the tray.
- **Daily timeline & 7-day history** — see when you first sat, how long you
  sat/stood/were away, and browse previous days like a watch activity log.
- **Custom alert sound** — choose any `.wav` file, or keep the built-in tone.
- **Reliable autostart** — registers under `HKCU\...\Run` so it starts at
  login even if the Startup folder shortcut is missing.
- **Standing at the desk counts** — no need to walk away.
- **Bilingual UI** — 中文 / English, switchable instantly in Settings.
- **High-DPI ready** — per-monitor V2 awareness with crisp rendering on
  3.5K/200% displays, and preserves the logical window size when moved
  between monitors with different scaling.
- **Free resizing, timer-only mini mode** — drag the window to any size; below
  the full layout it collapses to a large timer. Double-click it (or click ⤢)
  to restore. The window size is remembered between runs.

- **Tray, autostart, daily stats**, single instance, fully local processing.
- **Camera auto-recovery** — if the feed stalls or the device drops after hours
  of running, a watchdog reconnects automatically; detectors are rebuilt hourly.
- **Snow / black frame detection** — corrupted camera output (TV-static noise or
  an all-black feed) is detected within seconds and the device is restarted.
- **Optional scheduled restart** — Settings → Restart camera every N minutes
  (0 = off) for drivers that degrade over long sessions.

![Mini timer](screenshots/mini.png)

![Activity history](screenshots/history.png)

![Break reminder](screenshots/break_overlay.png)

## Install from source

```bash
git clone https://github.com/Atumnsky/SitGuard.git
cd SitGuard
python -m pip install -r requirements.txt
python main.py
```

Requirements: **Windows 10/11** and **Python 3.13**. The face and pose models
are bundled in `models/`, so no extra downloads are needed. You can also
download the repository ZIP and double-click `StartSitGuard.vbs`.

## Calibrate once (recommended)

Camera angle and body size strongly affect posture detection. The calibration
records *your* sitting and standing profiles:

1. Open **Settings → Calibrate posture…**
2. Sit normally, click **Record sitting**, wait 2 seconds.
3. Stand the way you normally stand (it is fine to leave the frame),
   click **Record standing**, wait 2 seconds.
4. Click **Save calibration**.

If your standing pose is outside the frame, the app records “standing = out of
frame” and treats losing sight of you as standing up.

## Usage

- **Pause / Resume** — stop timing without quitting.
- **Test reminder** — preview the break overlay immediately.
- **Break overlay** — stand 10 s, leave the frame 12 s, click “I stood up”,
  or click “Close this reminder”.
- **Snooze** — postpone for 5 minutes.
- **Stand mode** — manual fallback if your camera angle defeats detection.
- **Tray** — closing the window keeps monitoring; right-click the tray icon
  to pause, take a break, toggle the camera, or quit.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| Remind after | 45 min | Popup after this much continuous sitting |
| Break duration | 5 min | Countdown length in the overlay |
| Reset sitting after away | 5 min | Sitting time resets after this absence |
| Finish break after standing | 10 s | Standing this long completes the break |
| Finish break when out of frame | 12 s | Leaving the frame also completes the break |
| Restart sitting after standing | 3 min | Standing this long restarts the sitting timer |
| Camera index | 0 | Try 1 for an external camera |
| Restart camera every | 0 (off) | Periodic soft reset for unstable drivers; try 45 min |
| Face detection sensitivity | 0.60 | Lower = more sensitive |
| Full-screen reminder | on | Off = sound only, with a repeat every 5 minutes |
| Alert sound | built-in | Choose a `.wav` file |
| Posture calibration | — | Record sitting/standing profiles |
| Language | 中文 | Chinese / English |

Config lives in `data/config.json` (git-ignored), daily stats in
`data/stats.json`.

## Tests

```bash
python -m unittest discover -s tests -p "test_engine.py" -v
```

Unit tests cover the timer state machine, posture heuristics, calibration
nearest-neighbour classification, out-of-frame handling and DPI scaling.
GitHub Actions runs them on every push.

## License and use

Copyright © 2026 Atumnsky. **All rights reserved.**

This repository is published as **source-available** for viewing and
reference only. No permission is granted to use, copy, modify, merge,
publish, distribute, sublicense, or sell copies of the software, in whole or
in part, without prior written permission from the copyright holder.

Third-party components and models remain under their own licenses and are
listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
