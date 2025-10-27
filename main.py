#!/usr/bin/env python3
"""
ZomboidVault - Simple Zomboid backup manager
A minimalist backup manager in ~200 lines of code.

Features:
- Auto-save with QTimer
- Manual backup/restore
- Simple GUI with PySide6
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from collections import Counter

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QInputDialog,
    QMessageBox, QSpinBox, QGroupBox, QFormLayout, QSplitter,
    QSystemTrayIcon, QMenu, QDialog, QLineEdit, QFileDialog,
    QDialogButtonBox, QCheckBox, QDoubleSpinBox, QToolBar
)
from PySide6.QtCore import Qt, QTimer, QSettings, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QAction

from backup_manager import BackupManager


class WorldsPanel(QWidget):
    """Encapsulates the worlds list and refresh button."""

    world_selected = Signal(object)
    refresh_requested = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.title_label = QLabel("Your Worlds")
        self.title_label.setProperty("class", "header")
        header_row.addWidget(self.title_label)

        header_row.addStretch()

        self.game_status_label = QLabel("Game Inactive")
        status_font = QFont()
        status_font.setPointSize(11)
        status_font.setBold(True)
        self.game_status_label.setFont(status_font)
        self.game_status_label.setStyleSheet(
            "color: #636e72; padding: 4px 10px; background: #dfe6e9; border-radius: 12px;"
        )
        header_row.addWidget(self.game_status_label)

        layout.addLayout(header_row)

        self.worlds_list = QListWidget()
        self.worlds_list.itemSelectionChanged.connect(self._emit_selection)
        layout.addWidget(self.worlds_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "secondary")
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())
        layout.addWidget(refresh_btn)

    def set_worlds(self, worlds: list[dict], active_world_names: set[str]):
        self.worlds_list.clear()

        for world in worlds:
            is_active = world['name'] in active_world_names
            world['is_active'] = is_active
            status = " [ACTIVE]" if is_active else ""
            item_text = f"{world['name']} ({world['gamemode']}){status}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, world)
            self.worlds_list.addItem(item)

    def select_first(self):
        if self.worlds_list.count() > 0:
            self.worlds_list.setCurrentRow(0)

    def select_world_by_name(self, name: str) -> bool:
        for i in range(self.worlds_list.count()):
            item = self.worlds_list.item(i)
            world = item.data(Qt.UserRole)
            if world['name'] == name:
                self.worlds_list.setCurrentRow(i)
                return True
        return False

    def current_world(self):
        items = self.worlds_list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def clear(self):
        self.worlds_list.clear()
        self.world_selected.emit(None)
        self.update_backup_size(None)

    def _emit_selection(self):
        self.world_selected.emit(self.current_world())

    def update_backup_size(self, size_bytes: Optional[int]):
        if size_bytes is None:
            self.title_label.setText("Your Worlds")
            return

        size_mb = size_bytes / (1024 ** 2)
        self.title_label.setText(f"Your Worlds (Backup size: {size_mb:.1f} MB)")

    def set_game_status(self, active_names: set[str]):
        if active_names:
            preview = ", ".join(list(active_names)[:2])
            if len(active_names) > 2:
                preview += f" +{len(active_names)-2}"
            text = f"Game Active: {preview}"
            style = (
                "color: #0b8f5d; padding: 4px 10px; background: #d4edda; "
                "border-radius: 12px; font-weight: bold;"
            )
        else:
            text = "Game Inactive"
            style = (
                "color: #636e72; padding: 4px 10px; background: #dfe6e9; "
                "border-radius: 12px; font-weight: bold;"
            )

        self.game_status_label.setText(text)
        self.game_status_label.setStyleSheet(style)


class BackupsPanel(QWidget):
    """Handles backup list display and related buttons."""

    backup_selected = Signal(object)
    create_backup_clicked = Signal()
    restore_backup_clicked = Signal()
    delete_backup_clicked = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = QLabel("Backups")
        label.setProperty("class", "header")
        layout.addWidget(label)

        self.backups_list = QListWidget()
        self.backups_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.backups_list)

        self.info_label = QLabel("Select a backup to view details")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "background: white; border: 1px solid #dfe6e9; border-radius: 8px;"
            "padding: 16px; color: #636e72;"
        )
        self.info_label.setMinimumHeight(100)
        layout.addWidget(self.info_label)

    def set_world_available(self, has_world: bool):
        if not has_world:
            self.clear_backups(message="Select a world to view backups")

    def set_backups(self, backups: list[dict]):
        self.backups_list.clear()

        for backup in backups:
            metadata = backup['metadata']
            desc = metadata.get('description', 'No description')
            date_str = backup['date'].strftime("%Y-%m-%d %H:%M:%S")
            size_mb = backup['size'] / (1024 ** 2)
            item_text = f"{desc} - {date_str} ({size_mb:.1f} MB)"

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, backup)
            self.backups_list.addItem(item)

        if not backups:
            self.info_label.setText("No backups found for this world")
            self.backup_selected.emit(None)
        else:
            self.backups_list.setCurrentRow(0)

    def clear_backups(self, message: str = "No backup selected"):
        self.backups_list.clear()
        self.info_label.setText(message)
        self.backup_selected.emit(None)

    def selected_backup(self):
        items = self.backups_list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def _on_selection_changed(self):
        backup = self.selected_backup()
        has_backup = backup is not None

        if has_backup:
            metadata = backup['metadata']
            info = (
                "<b>Backup Info:</b><br>"
                f"World: {metadata.get('world_name', 'Unknown')}<br>"
                f"Description: {metadata.get('description', 'No description')}<br>"
                f"Created: {backup['date'].strftime('%Y-%m-%d %H:%M:%S')}<br>"
                f"Size: {backup['size'] / (1024**2):.2f} MB"
            )
            self.info_label.setText(info)
        else:
            self.info_label.setText("No backup selected")

        self.backup_selected.emit(backup)


class MainWindow(QMainWindow):
    """Main application window with world/backup management."""

    def __init__(self):
        super().__init__()

        self.settings = QSettings("PZSaveManager", "Simple")
        self.backup_manager = None
        self.tray_icon = None
        self.minimize_to_tray = self.settings.value("minimize_to_tray", True, bool)
        self.backup_limit_gb = float(self.settings.value("backup_limit_gb", 5.0, float))
        self.backup_limit_bytes = self.backup_limit_gb * (1024 ** 3)
        self.min_backups_per_world = max(1, self.settings.value("min_backups_per_world", 3, int))
        self.backup_warning_shown = False
        self._initialize_backup_manager()

        self.selected_world = None
        self.selected_backup = None

        self.setWindowTitle("ZomboidVault")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        # Load stylesheet
        self._load_stylesheet()

        self._create_menu_bar()
        self._create_toolbar()
        self._create_ui()
        self._setup_tray_icon()
        self._setup_autosave()
        self._load_worlds()

    def _create_menu_bar(self):
        """Set up simple application menu."""
        menu_bar = self.menuBar()
        settings_menu = menu_bar.addMenu("Settings")

        configure_action = QAction("Preferences...", self)
        configure_action.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(configure_action)

    def _create_toolbar(self):
        """Top toolbar exposing main actions with icons/hotkeys."""
        toolbar = QToolBar("Main actions")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self.refresh_action = QAction(QIcon.fromTheme("view-refresh"), "Refresh", self)
        self.refresh_action.setShortcut("F5")
        self.refresh_action.triggered.connect(self._load_worlds)
        toolbar.addAction(self.refresh_action)

        self.new_action = QAction(QIcon.fromTheme("document-save"), "New Backup", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self._create_backup)
        toolbar.addAction(self.new_action)

        self.restore_action = QAction(QIcon.fromTheme("document-revert"), "Restore", self)
        self.restore_action.setShortcut("Ctrl+R")
        self.restore_action.triggered.connect(self._restore_backup)
        toolbar.addAction(self.restore_action)

        self.delete_action = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        self.delete_action.setShortcut("Del")
        self.delete_action.triggered.connect(self._delete_backup)
        toolbar.addAction(self.delete_action)

        toolbar.addSeparator()

        self.explorer_action = QAction(QIcon.fromTheme("folder"), "Open Backups Folder", self)
        self.explorer_action.triggered.connect(self._open_backups_directory)
        toolbar.addAction(self.explorer_action)

        self._update_toolbar_state()

    def _open_backups_directory(self):
        path = self.backup_manager.backups_dir
        try:
            if sys.platform.startswith('darwin'):
                subprocess.check_call(['open', str(path)])
            elif sys.platform.startswith('win'):
                subprocess.check_call(['explorer', str(path)])
            else:
                subprocess.check_call(['xdg-open', str(path)])
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Open folder failed",
                f"Could not open the backups directory:\n{exc}"
            )

    def _update_toolbar_state(self):
        has_world = self.selected_world is not None
        has_backup = self.selected_backup is not None

        if hasattr(self, 'new_action'):
            self.new_action.setEnabled(has_world)
        if hasattr(self, 'restore_action'):
            self.restore_action.setEnabled(has_backup)
        if hasattr(self, 'delete_action'):
            self.delete_action.setEnabled(has_backup)

    def _open_settings_dialog(self):
        """Open configuration dialog for custom Zomboid path."""
        current_custom = self.settings.value("custom_zomboid_dir", "", str)
        current_path = Path(current_custom).expanduser() if current_custom else self.backup_manager.get_base_dir()
        minimize_pref = self.settings.value("minimize_to_tray", True, bool)

        autosave_interval = self.settings.value("autosave_interval", 10, int)

        dialog = SettingsDialog(
            current_path=current_path,
            default_path=BackupManager.detect_default_zomboid_path(),
            using_custom=bool(current_custom),
            minimize_to_tray=minimize_pref,
            backup_limit_gb=self.backup_limit_gb,
            min_backups_per_world=self.min_backups_per_world,
            autosave_interval=autosave_interval,
            parent=self
        )

        if dialog.exec() == QDialog.Accepted:
            selected_path = dialog.get_selected_path()
            if selected_path is None:
                self.settings.remove("custom_zomboid_dir")
            else:
                self.settings.setValue("custom_zomboid_dir", str(selected_path))

            self.minimize_to_tray = dialog.should_minimize_to_tray()
            self.settings.setValue("minimize_to_tray", self.minimize_to_tray)

            self.backup_limit_gb = dialog.get_backup_limit_gb()
            self.backup_limit_bytes = self.backup_limit_gb * (1024 ** 3)
            self.settings.setValue("backup_limit_gb", self.backup_limit_gb)

            self.min_backups_per_world = dialog.get_min_backups_per_world()
            self.settings.setValue("min_backups_per_world", self.min_backups_per_world)

            new_interval = dialog.get_autosave_interval()
            if new_interval != self.settings.value("autosave_interval", 10, int):
                self._update_autosave_interval(new_interval)

            self._initialize_backup_manager(show_errors=True)
            self._load_worlds()
            self._check_backup_usage(force=True)

    def _initialize_backup_manager(self, show_errors: bool = False):
        """Instantiate the backup manager using stored preferences."""
        custom_dir = self.settings.value("custom_zomboid_dir", "", str)
        custom_path = Path(custom_dir).expanduser() if custom_dir else None

        try:
            self.backup_manager = BackupManager(custom_path)
        except Exception as exc:
            if show_errors:
                QMessageBox.critical(
                    self,
                    "Zomboid Path Error",
                    f"Unable to use this folder:\n{exc}\n\nReverting to the auto-detected path."
                )
            else:
                print(f"Warning: could not use custom Zomboid directory: {exc}")

            self.settings.remove("custom_zomboid_dir")
            self.backup_manager = BackupManager()

        # Reset cached data if timers are already set up
        if hasattr(self, 'cached_worlds'):
            self.cached_worlds = []
        if hasattr(self, 'last_active_world'):
            self.last_active_world = None
        if hasattr(self, 'last_worlds_refresh'):
            self.last_worlds_refresh = datetime.now()

    def _check_backup_usage(self, force: bool = False):
        """Warn user if backup directory exceeds threshold."""
        total_size = self.backup_manager.get_total_backup_size()
        limit = self.backup_limit_bytes

        if total_size > limit:
            if self._enforce_backup_limit(total_size, limit):
                total_size = self.backup_manager.get_total_backup_size()

        if total_size >= limit:
            if force or not self.backup_warning_shown:
                self.backup_warning_shown = True
                total_gb = total_size / (1024 ** 3)
                limit_gb = limit / (1024 ** 3)
                QMessageBox.warning(
                    self,
                    "Backup folder is large",
                    "The backups directory currently uses "
                    f"{total_gb:.1f} GB (limit {limit_gb:.1f} GB).\n\n"
                    "Consider deleting older backups or raising the limit in Preferences."
                )
        else:
            self.backup_warning_shown = False

    def _enforce_backup_limit(self, total_size: int, limit: int) -> bool:
        """Delete oldest backups while keeping at least N per world."""
        backups = self.backup_manager.get_backups()
        if not backups:
            return False

        def resolve_world_name(backup_entry: dict) -> str:
            metadata = backup_entry['metadata']
            world_name = metadata.get('world_name')
            if world_name:
                return world_name
            return backup_entry['backup_dir'].name.split('_')[0]

        world_counts = Counter()
        for backup in backups:
            world_counts[resolve_world_name(backup)] += 1

        deletions = []
        for backup in sorted(backups, key=lambda b: b['date']):  # oldest first
            world_name = resolve_world_name(backup)
            if world_counts[world_name] <= self.min_backups_per_world:
                continue

            self.backup_manager.delete_backup(backup['backup_dir'])
            world_counts[world_name] -= 1
            total_size -= backup['size']
            deletions.append(backup)

            if total_size <= limit:
                break

        if deletions:
            freed_mb = sum(b['size'] for b in deletions) / (1024 ** 2)
            QMessageBox.information(
                self,
                "Old backups removed",
                "To stay under the configured limit, the app removed "
                f"{len(deletions)} older backups (freed {freed_mb:.1f} MB).\n"
                f"At least {self.min_backups_per_world} backups per world were kept."
            )
            if self.selected_world:
                self._load_backups(self.selected_world['name'])
            return True

        return False

    def _load_stylesheet(self):
        """Load and apply custom stylesheet."""
        style_file = Path(__file__).parent / "style.qss"
        if style_file.exists():
            with open(style_file, 'r') as f:
                self.setStyleSheet(f.read())

    def _create_ui(self):
        """Create the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: worlds list
        self.worlds_panel = WorldsPanel()
        self.worlds_panel.world_selected.connect(self._on_world_selected)
        self.worlds_panel.refresh_requested.connect(self._load_worlds)
        splitter.addWidget(self.worlds_panel)

        # Right panel: backups + autosave controls
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setSpacing(12)

        self.backups_panel = BackupsPanel()
        self.backups_panel.backup_selected.connect(self._on_backup_selected)
        self.backups_panel.create_backup_clicked.connect(self._create_backup)
        self.backups_panel.restore_backup_clicked.connect(self._restore_backup)
        self.backups_panel.delete_backup_clicked.connect(self._delete_backup)
        right_panel.addWidget(self.backups_panel)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _setup_tray_icon(self):
        """Set up system tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray not available")
            return

        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self)

        # Try to use a built-in icon or create a simple one
        # Using application icon or a default one
        icon = QIcon.fromTheme("document-save", QIcon.fromTheme("application-x-executable"))
        self.tray_icon.setIcon(icon)

        # Create tray menu
        tray_menu = QMenu()

        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        hide_action = QAction("Hide window (keep running)", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit app", self)
        quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("PZ Save Manager (window hides here when closed)")
        self.tray_icon.activated.connect(self._tray_icon_activated)

        self.tray_icon.show()

        # Show notification
        self.tray_icon.showMessage(
            "PZ Save Manager",
            "The app keeps running in the background",
            QSystemTrayIcon.Information,
            2000
        )

    def _tray_icon_activated(self, reason):
        """Handle tray icon click."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click - toggle visibility
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def _quit_application(self):
        """Quit the application completely."""
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """Override close event to minimize to tray instead of closing."""
        if self.minimize_to_tray and self.tray_icon and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "PZ Save Manager",
                "The app keeps running in the background.\nUse 'Quit' in the menu to exit.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            event.accept()

    def _setup_autosave(self):
        """Set up auto-save timer."""
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self._do_autosave)

        # Timer to update countdown display (every second)
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start(1000)  # Update every second

        # Separate timer for game status (less frequent to avoid slowdown)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_game_status)
        self.status_timer.start(3000)  # Update every 3 seconds

        # Cache for worlds list
        self.cached_worlds = []
        self.last_worlds_refresh = datetime.now()
        self.last_active_world = None  # Track active world changes

        # Get interval from settings
        interval_minutes = self.settings.value("autosave_interval", 10, int)
        self.autosave_interval_ms = interval_minutes * 60 * 1000
        self.autosave_start_time = datetime.now()
        self.autosave_timer.start(self.autosave_interval_ms)  # Convert to milliseconds

        print(f"Auto-save enabled: every {interval_minutes} minutes")
        print(
            "First auto-save will occur at: "
            f"{(self.autosave_start_time + __import__('datetime').timedelta(milliseconds=self.autosave_interval_ms)).strftime('%H:%M:%S')}"
        )

    def _update_autosave_interval(self, minutes: int):
        """Update auto-save interval."""
        self.settings.setValue("autosave_interval", minutes)
        self.autosave_interval_ms = minutes * 60 * 1000
        self.autosave_start_time = datetime.now()
        self.autosave_timer.start(self.autosave_interval_ms)
        print(f"Auto-save interval updated: {minutes} minutes")
        print(
            "Next auto-save at: "
            f"{(self.autosave_start_time + __import__('datetime').timedelta(milliseconds=self.autosave_interval_ms)).strftime('%H:%M:%S')}"
        )

    def _update_countdown(self):
        """Update countdown display for next auto-save."""
        # Countdown removed from UI - auto-save runs silently in background
        pass

    def _update_game_status(self):
        """Update game status indicator (optimized)."""
        # Refresh worlds list every 10 seconds
        now = datetime.now()
        if (now - self.last_worlds_refresh).total_seconds() > 10:
            self.cached_worlds = self.backup_manager.get_worlds()
            self.last_worlds_refresh = now

        if not self.cached_worlds:
            self.cached_worlds = self.backup_manager.get_worlds()

        # Single optimized call to check active worlds
        active_world_names = self.backup_manager.get_active_worlds(self.cached_worlds)

        # Check if active world changed - auto-select it
        if active_world_names and hasattr(self, 'last_active_world'):
            new_active = list(active_world_names)[0]  # Get first active world
            if new_active != self.last_active_world:
                # Active world changed, auto-select it
                if self.worlds_panel.select_world_by_name(new_active):
                    print(f"Auto-switched to active world: {new_active}")

        # Store current active world
        if active_world_names:
            self.last_active_world = list(active_world_names)[0]
        else:
            self.last_active_world = None

        if self.selected_world:
            self.selected_world['is_active'] = self.selected_world['name'] in active_world_names

        self.worlds_panel.set_game_status(active_world_names)

    def _test_autosave(self):
        """Manually trigger auto-save for testing."""
        print("\nManual auto-save test triggered")
        self._do_autosave()
        # Reset timer
        self.autosave_start_time = datetime.now()
        self.autosave_timer.start(self.autosave_interval_ms)

    def _do_autosave(self):
        """Perform auto-save for active world."""
        print(f"\nAuto-save triggered at {datetime.now().strftime('%H:%M:%S')}")

        worlds = self.backup_manager.get_worlds()
        print(f"Total worlds found: {len(worlds)}")

        # Use optimized method to get active worlds
        active_world_names = self.backup_manager.get_active_worlds(worlds)
        print(f"Active worlds (game running): {len(active_world_names)}")

        # Get the full world objects for active worlds
        active_worlds = [w for w in worlds if w['name'] in active_world_names]

        if active_worlds:
            for w in active_worlds:
                print(f"  - Active: {w['name']} ({w['gamemode']})")

            saved_count = 0
            for world in active_worlds:
                try:
                    self.backup_manager.create_backup(
                        world['path'],
                        description="Auto-save"
                    )
                    print(f"Auto-save created for: {world['name']}")
                    saved_count += 1

                    # Refresh backups if this world is selected
                    if self.selected_world and self.selected_world['name'] == world['name']:
                        self._load_backups(world['name'])

                except Exception as e:
                    print(f"Auto-save failed: {e}")
                    if hasattr(self, 'tray_icon') and self.tray_icon:
                        self.tray_icon.showMessage(
                            "Auto-save error",
                            f"Failed to back up {world['name']}",
                            QSystemTrayIcon.Critical,
                            3000
                        )

            # Show success notification
            if saved_count > 0 and hasattr(self, 'tray_icon') and self.tray_icon:
                world_names = ", ".join([w['name'] for w in active_worlds[:2]])
                if len(active_worlds) > 2:
                    world_names += f" +{len(active_worlds)-2}"
                self.tray_icon.showMessage(
                    "Auto-save complete",
                    f"Backups created for: {world_names}",
                    QSystemTrayIcon.Information,
                    2000
                )

            if saved_count > 0:
                self._check_backup_usage()

            # Reset timer
            self.autosave_start_time = datetime.now()
        else:
            print("No active worlds detected - auto-save skipped")
            print("Tip: Auto-save only runs when Project Zomboid is running with a loaded world")
            # Reset timer anyway
            self.autosave_start_time = datetime.now()

    def _load_worlds(self):
        """Load and display all worlds."""
        worlds = self.backup_manager.get_worlds()

        if not worlds:
            self.worlds_panel.clear()
            self.backups_panel.clear_backups("No backups to display")
            QMessageBox.warning(
                self,
                "No Worlds Found",
                "No Project Zomboid worlds found. Play the game to create a world first!"
            )
            return

        # Get active worlds
        active_world_names = self.backup_manager.get_active_worlds(worlds)

        self.worlds_panel.set_worlds(worlds, active_world_names)

        print(f"Loaded {len(worlds)} worlds")

        # Auto-select the active world, or the first world if none active
        if worlds:
            if active_world_names:
                # Select the first active world available
                active_world = next((w['name'] for w in worlds if w['name'] in active_world_names), None)
                if active_world and self.worlds_panel.select_world_by_name(active_world):
                    print(f"Auto-selected active world: {active_world}")
                else:
                    self.worlds_panel.select_first()
            else:
                # No active world, select the most recently modified world
                latest_world = max(worlds, key=lambda w: w.get('last_modified'), default=None)
                if latest_world and self.worlds_panel.select_world_by_name(latest_world['name']):
                    print(f"Auto-selected most recent world: {latest_world['name']}")
                else:
                    self.worlds_panel.select_first()

        self._check_backup_usage()

    def _on_world_selected(self, world):
        """Handle world selection change."""
        self.selected_world = world
        has_world = world is not None
        self.backups_panel.set_world_available(has_world)

        if has_world:
            self._load_backups(world['name'])
        else:
            self.backups_panel.clear_backups("Select a world to view backups")
            self.worlds_panel.update_backup_size(None)

        self._update_toolbar_state()

    def _load_backups(self, world_name: str):
        """Load backups for a world."""
        backups = self.backup_manager.get_backups(world_name)
        self.backups_panel.set_backups(backups)

        total_size = sum(b['size'] for b in backups)
        self.worlds_panel.update_backup_size(total_size if backups else 0)

        if backups:
            print(f"Loaded {len(backups)} backups for {world_name}")

    def _on_backup_selected(self, backup):
        """Track backup selection from the backups panel."""
        self.selected_backup = backup
        self._update_toolbar_state()

    def _create_backup(self):
        """Create a backup for selected world."""
        if not self.selected_world:
            return

        description, ok = QInputDialog.getText(
            self,
            "Create Backup",
            "Enter backup description:",
            text="Manual backup"
        )

        if not ok:
            return

        try:
            self.backup_manager.create_backup(
                self.selected_world['path'],
                description
            )

            QMessageBox.information(self, "Success", "Backup created successfully!")

            # Refresh backups list
            self._load_backups(self.selected_world['name'])
            self._check_backup_usage()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create backup:\n{e}")

    def _restore_backup(self):
        """Restore selected backup."""
        if not self.selected_backup or not self.selected_world:
            return

        # Check if world is active
        if self.selected_world['is_active']:
            QMessageBox.warning(
                self,
                "World Active",
                "Cannot restore backup while the world is active.\nPlease close the game first!"
            )
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            "Are you sure you want to restore this backup?\n\n"
            "This will OVERWRITE your current world!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.backup_manager.restore_backup(
                self.selected_backup['path'],
                self.selected_world['path']
            )

            QMessageBox.information(self, "Success", "Backup restored successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore backup:\n{e}")

    def _delete_backup(self):
        """Delete selected backup."""
        if not self.selected_backup:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this backup?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.backup_manager.delete_backup(self.selected_backup['backup_dir'])

            QMessageBox.information(self, "Success", "Backup deleted successfully!")

            # Refresh backups list
            if self.selected_world:
                self._load_backups(self.selected_world['name'])
            self._check_backup_usage()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete backup:\n{e}")


class SettingsDialog(QDialog):
    """Simple dialog to configure paths and storage preferences."""

    def __init__(
        self,
        current_path: Path,
        default_path: Path,
        using_custom: bool,
        minimize_to_tray: bool,
        backup_limit_gb: float,
        min_backups_per_world: int,
        autosave_interval: int,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Preferences")
        self.resize(520, 320)
        self.default_path = default_path
        self._last_custom_path = str(current_path) if using_custom else ""

        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Choose which Zomboid folder the app should use.\n"
            "Stick with the auto-detected path if you are unsure."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form_layout = QFormLayout()

        self.default_checkbox = QCheckBox("Use the auto-detected path")
        self.default_checkbox.setChecked(not using_custom)
        self.default_checkbox.toggled.connect(self._toggle_custom_path)
        form_layout.addRow("Mode:", self.default_checkbox)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(current_path))
        self.path_edit.setPlaceholderText("/path/to/Zomboid")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        form_layout.addRow("Zomboid folder:", path_row)

        self.tray_checkbox = QCheckBox("Keep app in system tray when closing the window")
        self.tray_checkbox.setChecked(minimize_to_tray)
        form_layout.addRow("Tray behavior:", self.tray_checkbox)

        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(1, 120)
        self.autosave_spin.setSuffix(" min")
        self.autosave_spin.setValue(autosave_interval)
        form_layout.addRow("Auto-save interval:", self.autosave_spin)

        self.limit_spin = QDoubleSpinBox()
        self.limit_spin.setRange(0.5, 1000.0)
        self.limit_spin.setSuffix(" GB")
        self.limit_spin.setSingleStep(0.5)
        self.limit_spin.setValue(backup_limit_gb)
        form_layout.addRow("Max backup size:", self.limit_spin)

        self.min_per_world_spin = QSpinBox()
        self.min_per_world_spin.setRange(1, 20)
        self.min_per_world_spin.setValue(min_backups_per_world)
        form_layout.addRow("Keep at least per world:", self.min_per_world_spin)

        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._toggle_custom_path(self.default_checkbox.isChecked())

    def _toggle_custom_path(self, use_default: bool):
        self.path_edit.setEnabled(not use_default)

        # When switching back to default, keep the last custom value in memory
        if use_default:
            if not self._last_custom_path:
                self._last_custom_path = self.path_edit.text().strip()
            self.path_edit.setText(str(self.default_path))
        else:
            self.path_edit.setText(self._last_custom_path or str(self.default_path))

    def _browse_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select the Zomboid folder", self.path_edit.text())
        if directory:
            self.path_edit.setText(directory)
            self._last_custom_path = directory

    def get_selected_path(self) -> Optional[Path]:
        if self.default_checkbox.isChecked():
            return None
        return Path(self.path_edit.text().strip()).expanduser()

    def should_minimize_to_tray(self) -> bool:
        return self.tray_checkbox.isChecked()

    def get_backup_limit_gb(self) -> float:
        return float(self.limit_spin.value())

    def get_min_backups_per_world(self) -> int:
        return int(self.min_per_world_spin.value())

    def get_autosave_interval(self) -> int:
        return int(self.autosave_spin.value())

    def accept(self):
        if not self.default_checkbox.isChecked():
            path_text = self.path_edit.text().strip()
            if not path_text:
                QMessageBox.warning(self, "Invalid path", "Please provide a valid folder.")
                return

            candidate = Path(path_text).expanduser()
            if not candidate.exists():
                QMessageBox.warning(self, "Folder not found", "This directory does not exist.")
                return

            if not (candidate / "Saves").exists():
                QMessageBox.warning(
                    self,
                    "Missing data",
                    "This directory does not contain a 'Saves' subfolder.\n"
                    "Please double-check the selected location."
                )
                return

            self._last_custom_path = str(candidate)

        super().accept()

def main():
    """Application entry point."""
    app = QApplication(sys.argv)

    app.setApplicationName("PZSaveManager")
    app.setOrganizationName("PZSaveManager")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
import subprocess
