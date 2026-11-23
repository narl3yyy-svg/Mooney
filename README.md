<div align="center">

# 🌙 Moon Sweepers Toolkit

**Live, in-memory helpers for the single-player game *Moon Sweepers*.**
Add Moon Money and unlock more robot cleaning throughput, without touching a single game file.

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Game build](https://img.shields.io/badge/Moon%20Sweepers-v1.0.6-F28C28)
![Unity](https://img.shields.io/badge/Unity-6000.6.0f1-000000?logo=unity&logoColor=white)

</div>

---

## ✨ Features

| Tool | What it does |
|------|--------------|
| 💰 **Moon Money** (`MoonMoney.bat`) | Finds your wallet in the running game and adds up to **$1,000,000 per use**. It doesn't depend on how much money you have or how fast it's growing. |
| 🧹 **Cleaning Boost** (`CleaningBoost.bat`) | Raises the game's per-frame robot-cleaning budget so large J.O.O.N.A.S. fleets actually clean. Default is 2 ms; 6 ms roughly **doubles** robot dust throughput. |

**Safe by design**
- 🔒 **Memory only.** No game files or saves are edited; the game saves your new balance itself.
- 🎯 **Changes only what you ask for.** The money tool changes nothing but your wallet value, and the boost changes nothing but one settings value.
- ↩️ **Reversible.** Cleaning Boost resets to the game default with `r`, and it reverts on its own when you restart the game.
- 🧭 **No hardcoded addresses.** Everything is found at runtime, and the tools refuse to write if they can't find their target.

---

## 📋 Requirements

- Windows 10 or 11 (64-bit)
- [Python 3.10+](https://www.python.org/downloads/) on your `PATH`
- `numpy` (the launchers install it automatically on first run)
- *Moon Sweepers* running with a save loaded

---

## 🚀 Quick start

```powershell
git clone https://github.com/<your-username>/moon-sweepers-toolkit.git
cd moon-sweepers-toolkit
```

Then double-click a launcher. If Windows denies memory access, run it from an **Administrator** terminal.

### 💰 Moon Money

1. Launch the game, load your save and **leave it unpaused** so income keeps coming in.
2. Run **`MoonMoney.bat`**.
3. Wait about 1 minute while it locates the wallet. It finds the HUD wallet structure, then the live source value behind it.
4. Type an amount to add (`1` – `1,000,000`) and press **Enter**. Repeat as often as you like, or press **Enter** on an empty line to quit.

```text
Attached to MoonSweepers.exe (pid 13044).
  Looking for the wallet (about 20 s)...
  HUD wallet found at $526,768.43. Finding the source value...

Wallet found:
  0x24440CD66D0  $557,923.94
  ...

How much to add? (1 - 1,000,000, Enter/q to quit): 250000
  Done. Wallet is now $808,104.11 (added $250,000.00 this session).
```

> **Tip:** if more than one wallet is found, the tool asks for a rough amount (e.g. `500k`) to pick the right one.

### 🧹 Cleaning Boost

1. With the game running, run **`CleaningBoost.bat`**.
2. It shows the current budget and how much of it the game is actually using.
3. Enter a new value in milliseconds per frame (e.g. `6`), or `r` to reset to the default `2`.

```text
Current cleaning budget: 2.0 ms/frame (game default 2.0).
Cleaning time actually used: ~2.31 ms/frame (maxed out - raising it will help).

New budget in ms (e.g. 6; 'r' = reset to 2.0; Enter = quit; max 12.0): 6
  Budget now 6.0 ms/frame. Cleaning used: ~3.82 ms/frame.
```

The setting lasts until you restart the game, so run it again after each launch.

---

## 📊 Cleaning Boost benchmarks

Measured on a save with ~1,370 J.O.O.N.A.S. units:

| Budget | Robot dust cleaned |
|-------:|-------------------:|
| 2 ms *(default)* | ~630 m/s |
| **6 ms** | **~1,200 m/s** |
| 12 ms | ~1,300 m/s |

Gains flatten past about 6 ms because the game also has a **compiled-in limit** on robot strokes per frame and a **2,048-stroke robot queue**. Beyond roughly 1,300–1,400 units, extra J.O.O.N.A.S. animate but get no cleaning time. This tool doesn't change those limits.

> ⚠️ More cleaning per frame costs some FPS. If the game feels choppy, lower the budget.

---

## 🛠️ How it works

<details>
<summary><b>Moon Money</b></summary>

The wallet is a C# `System.Decimal`, not a float. The HUD keeps a snapshot struct laid out as:

```
[ double shownMoney ][ decimal money ][ decimal money (copy) ]
```

The tool finds that struct by its shape rather than by value, so it works at any balance and income rate. It then looks for the live **source** decimal that the snapshot is copied from every frame, and adds the amount to the source and both copies. Writing only the snapshot doesn't work, because the game overwrites it on the next frame.

The decimal's scale (digits after the point) shrinks as your balance grows (24 → 22 → …), and the tool handles any scale.
</details>

<details>
<summary><b>Cleaning Boost</b></summary>

The game is an IL2CPP Unity build. The tool:

1. Finds `global-metadata.dat` loaded in the game's memory.
2. Finds the runtime `FieldInfo` whose name points to `cleaningWorkBudgetMs`, which gives the owning class (`MoonCleaners.MoonSettings`) and the field offset.
3. Finds the live `MoonSettings` object and writes the new `float`.
4. Reads `MoonWorld.LastQueuedCleaningMs` to show how much of the budget is actually used.
</details>

### Project layout

```
├── MoonMoney.bat        # launcher: Moon Money
├── moon_money.py        # wallet finder + adder
├── CleaningBoost.bat    # launcher: Cleaning Boost
├── cleaning_boost.py    # cleaning budget tool
├── il2cpp_field.py      # runtime IL2CPP field/class lookup
├── memscan.py           # Windows process memory read/write/scan helpers
└── requirements.txt
```

---

## ✅ Tested on

| | Version |
|---|---|
| **Game** | Moon Sweepers **v1.0.6**, Steam build **26682829** (updated 22 Nov 2026) |
| **Engine** | Unity **6000.6.0f1**, IL2CPP (metadata v108) |
| **OS** | Windows 11 Pro (build 26100) |
| **Python** | 3.14.6 with numpy 2.5.1 |

> Game updates can change memory layouts or field names. If a tool can't find its target it stops **without writing anything**. Please open an issue with your game version.

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| `OpenProcess failed` | Run the `.bat` from an Administrator terminal. |
| `MoonSweepers.exe is not running` | Start the game and load a save first. |
| Wallet not found | Unpause the game so income is flowing, then retry. Give a rough amount if asked. |
| Money reverted after adding | Restart the tool so it re-scans (e.g. after loading a different save). |
| `python` not recognized | Install Python and tick **"Add python.exe to PATH"**. |

---

## ⚖️ Disclaimer

This project is fan-made and **not affiliated with or endorsed by** the developers of *Moon Sweepers*. Use it **in single-player only**. It changes your local game's memory, and in a shared crew session it would change your crewmates' game too. Use at your own risk; back up your save folder (`%USERPROFILE%\AppData\LocalLow\DragDropGames\MoonSweepers`) before experimenting.
