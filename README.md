# ZomboidVault

Lightweight PySide6 desktop app to back up Project Zomboid saves. It lists worlds, creates/restores ZIP backups, and runs an optional auto-save timer. The entire app lives in `main.py` + `backup_manager.py` with one dependency (PySide6).

## Platform Support

**Developed and tested on Linux.** While the application has been designed with cross-platform compatibility in mind using PySide6 and platform-agnostic code (automatic path detection for Windows, macOS, and Linux), it has only been thoroughly tested on Linux systems.

The application *should* work seamlessly on Windows and macOS, as care has been taken to:
- Use `pathlib` for cross-platform path handling
- Implement OS-specific default directory detection
- Support platform-specific file managers and commands

**If you encounter any issues on Windows or macOS, please [open an issue](https://github.com/indepth666/ZomboidVault/issues).**

## Installation

### Linux & macOS

```bash
git clone https://github.com/indepth666/ZomboidVault.git
cd ZomboidVault
pip install -r requirements.txt
python main.py
```

### Windows

For convenience, a standalone `.exe` is available: download `ZomboidVault-Windows.exe` from the [Releases](https://github.com/indepth666/ZomboidVault/releases) page and run it directly.

Alternatively, use the same method as Linux/macOS above.

## Usage

- Left panel: select a world.
- Right panel: view backups, metadata, and auto-save settings.
- Toolbar (or hotkeys) handles refresh, create, restore, delete, and "open folder".

## Preferences

`Settings → Preferences` lets you customize:
- Zomboid data folder location.
- Whether closing the window minimizes to the system tray.
- Maximum `Backups` folder size (default 5 GB).
- Minimum backups to keep per world during auto-cleanup (default 3).

When the folder exceeds the limit, the app deletes the oldest backups per world without going below the minimum, then notifies you. If space is still tight, a warning prompts you to raise the limit or remove files manually.

## Tips

- The header above the world list shows the combined backup size for the selected world.
- Auto-save uses a single `QTimer`; leaving the window open is enough to keep periodic backups running.
- The toolbar’s folder icon opens the backups directory in your file manager for quick inspection.
