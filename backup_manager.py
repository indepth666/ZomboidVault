"""
Simple backup manager for Project Zomboid worlds.
All core functionality in ~150 lines of straightforward code.
"""
import shutil
import zipfile
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import platform


class BackupManager:
    """Manages Project Zomboid world backups with minimal complexity."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize backup manager using default or custom Zomboid directory."""
        self.zomboid_dir = self._resolve_base_dir(base_dir)
        self.saves_dir = self.zomboid_dir / "Saves"
        self.backups_dir = self.zomboid_dir / "Backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def detect_default_zomboid_path() -> Path:
        """Best-effort detection of the Project Zomboid data directory."""
        system = platform.system()
        home = Path.home()

        if system == "Windows":
            return home / "Zomboid"

        if system == "Darwin":  # macOS
            mac_path = home / "Library" / "Application Support" / "Zomboid"
            return mac_path if mac_path.exists() else home / "Zomboid"

        # Linux: prefer ~/.local/share/Zomboid but fall back to ~/Zomboid
        linux_path = home / ".local" / "share" / "Zomboid"
        return linux_path if linux_path.exists() else home / "Zomboid"

    def _resolve_base_dir(self, custom_dir: Optional[Path]) -> Path:
        if custom_dir:
            return Path(custom_dir).expanduser()
        return self.detect_default_zomboid_path()

    def get_base_dir(self) -> Path:
        """Expose the currently used Zomboid directory."""
        return self.zomboid_dir

    def get_worlds(self) -> list[dict]:
        """
        Get all Project Zomboid worlds.

        Returns:
            List of dicts with 'name', 'path', 'gamemode', 'is_active', 'last_modified'
        """
        if not self.saves_dir.exists():
            return []

        worlds = []

        # Iterate through gamemodes (Survival, Sandbox, etc.)
        for gamemode_dir in self.saves_dir.iterdir():
            if not gamemode_dir.is_dir():
                continue

            # Iterate through worlds in this gamemode
            for world_dir in gamemode_dir.iterdir():
                if not world_dir.is_dir():
                    continue

                # Skip backup directories (they contain Save.zip or Save.tar)
                if (world_dir / "Save.zip").exists() or (world_dir / "Save.tar").exists():
                    continue

                worlds.append({
                    'name': world_dir.name,
                    'path': world_dir,
                    'gamemode': gamemode_dir.name,
                    'is_active': False,  # Will be updated by get_active_worlds()
                    'last_modified': datetime.fromtimestamp(world_dir.stat().st_mtime)
                })

        return worlds

    def get_active_worlds(self, worlds: list[dict]) -> set[str]:
        """
        Get set of active world names (using file modification time).

        A world is considered active if any of its files have been modified
        in the last 60 seconds. This is fast and cross-platform.

        Args:
            worlds: List of world dicts from get_worlds()

        Returns:
            Set of world directory names that are currently active
        """
        active_worlds = set()
        now = datetime.now().timestamp()
        threshold = 60  # seconds - consider world active if modified in last minute

        for world in worlds:
            world_path = world['path']

            # Check key files that get updated during gameplay
            key_files = [
                world_path / "players.db",
                world_path / "map_meta.bin",
                world_path / "reanimated.bin",
            ]

            # Check if any key file was modified recently
            for key_file in key_files:
                if key_file.exists():
                    mtime = key_file.stat().st_mtime
                    if (now - mtime) < threshold:
                        active_worlds.add(world['name'])
                        break  # Found one, no need to check other files

        return active_worlds

    def _is_world_active(self, world_path: Path) -> bool:
        """
        Check if world is currently being played (using file modification time).

        Fast and cross-platform alternative to file locking.
        """
        now = datetime.now().timestamp()
        threshold = 60  # seconds

        # Check key files that get updated during gameplay
        key_files = [
            world_path / "players.db",
            world_path / "map_meta.bin",
            world_path / "reanimated.bin",
        ]

        for key_file in key_files:
            if key_file.exists():
                mtime = key_file.stat().st_mtime
                if (now - mtime) < threshold:
                    return True

        return False

    def create_backup(self, world_path: Path, description: str = "Manual backup") -> Path:
        """
        Create a backup of a world.

        Args:
            world_path: Path to world directory
            description: Backup description

        Returns:
            Path to created backup ZIP file
        """
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        world_name = world_path.name
        backup_name = f"{world_name}_{timestamp}"
        backup_path = self.backups_dir / backup_name

        # Create backup directory
        backup_path.mkdir(exist_ok=True)

        # Create ZIP archive
        zip_file = backup_path / "save.zip"

        print(f"Creating backup: {zip_file}")

        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in world_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(world_path.parent)
                    zf.write(file_path, arcname)

        # Save metadata
        metadata = {
            'world_name': world_name,
            'description': description,
            'created': datetime.now().isoformat(),
            'gamemode': world_path.parent.name
        }

        metadata_file = backup_path / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        print(f"Backup created: {backup_name}")
        return zip_file

    def get_backups(self, world_name: Optional[str] = None) -> list[dict]:
        """
        Get all backups, optionally filtered by world name.

        Args:
            world_name: Optional world name to filter by

        Returns:
            List of dicts with 'path', 'metadata', 'size', 'date'
        """
        if not self.backups_dir.exists():
            return []

        backups = []

        for backup_dir in self.backups_dir.iterdir():
            if not backup_dir.is_dir():
                continue

            zip_file = backup_dir / "save.zip"
            metadata_file = backup_dir / "metadata.json"

            if not zip_file.exists():
                continue

            # Load metadata
            metadata = {}
            if metadata_file.exists():
                try:
                    metadata = json.loads(metadata_file.read_text())
                except:
                    pass

            # Try to extract world name from backup folder name if not in metadata
            # Format: {world_name}_{timestamp} or {world_name}_{timestamp}_{timestamp}
            backup_world_name = metadata.get('world_name')
            if not backup_world_name:
                # Extract from folder name: split by _ and remove timestamp parts
                folder_parts = backup_dir.name.split('_')
                if len(folder_parts) >= 3:
                    # Remove timestamp parts (YYYY-MM-DD and HH-MM-SS)
                    # Keep everything before the first timestamp
                    timestamp_pattern = folder_parts[-2] + '_' + folder_parts[-1]
                    backup_world_name = backup_dir.name.replace('_' + timestamp_pattern, '')

            # If still no world name, use folder name
            if not backup_world_name:
                backup_world_name = backup_dir.name

            # Filter by world name if specified
            # Match against the world name, handling both exact matches and prefix matches
            if world_name:
                # Check if backup belongs to this world
                # Try exact match, prefix match, or if world name is in backup name
                if not (backup_world_name == world_name or
                        backup_world_name.startswith(world_name + '_') or
                        world_name in backup_world_name):
                    continue

            # Get creation date
            if 'created' in metadata:
                try:
                    date = datetime.fromisoformat(metadata['created'])
                except:
                    date = datetime.fromtimestamp(zip_file.stat().st_mtime)
            else:
                date = datetime.fromtimestamp(zip_file.stat().st_mtime)

            backups.append({
                'path': zip_file,
                'backup_dir': backup_dir,
                'metadata': metadata,
                'size': zip_file.stat().st_size,
                'date': date
            })

        # Sort by date (newest first)
        backups.sort(key=lambda b: b['date'], reverse=True)

        return backups

    def restore_backup(self, backup_path: Path, world_path: Path) -> bool:
        """
        Restore a backup to a world directory.

        Args:
            backup_path: Path to backup ZIP file
            world_path: Path where to restore the world

        Returns:
            True if successful, False otherwise
        """
        if self._is_world_active(world_path):
            raise RuntimeError("Cannot restore: world is currently active. Close the game first!")

        print(f"Restoring backup to: {world_path}")

        # Remove existing world files
        if world_path.exists():
            shutil.rmtree(world_path)

        # Extract backup
        with zipfile.ZipFile(backup_path, 'r') as zf:
            zf.extractall(world_path.parent)

        print("Backup restored successfully")
        return True

    def delete_backup(self, backup_dir: Path):
        """Delete a backup directory."""
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
            print(f"Backup deleted: {backup_dir.name}")

    def get_total_backup_size(self) -> int:
        """Return total size of the backups directory in bytes."""
        if not self.backups_dir.exists():
            return 0

        total = 0
        for path in self.backups_dir.rglob('*'):
            if path.is_file():
                total += path.stat().st_size
        return total
