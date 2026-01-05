#!/usr/bin/env python3
"""
Production-Grade Custom Version Bumper with Rollover Rules + Database Sync

This script safely increments version numbers with file locking,
proper TOML handling, atomic writes, and updates the database.
"""

import argparse
import logging
import platform
import re
import shutil
import sys
import tempfile
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# Platform-specific imports for file locking
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import msvcrt
else:
    import fcntl

# Validate dependencies
try:
    import tomlkit
except ImportError:
    print("Error: This script requires 'tomlkit' for safe TOML editing.")
    print("Install it with: pip install tomlkit")
    sys.exit(1)

# Ensure backend path is in sys.path for app imports
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@contextmanager
def file_lock(file_path: Path, timeout: int = 30):
    """Cross-platform file locking context manager."""
    lock_path = file_path.with_suffix(file_path.suffix + ".lock")
    lock_file = None
    start_time = time.time()

    try:
        while True:
            try:
                lock_file = lock_path.open("x")
                if IS_WINDOWS:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.debug(f"Acquired lock: {lock_path}")
                break
            except (FileExistsError, OSError) as err:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock on {file_path}") from err
                time.sleep(0.1)
        yield
    finally:
        if lock_file:
            try:
                if IS_WINDOWS:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass


@dataclass
class Version:
    """Represents a semantic version number."""

    major: int
    minor: int
    patch: int
    suffix: str | None = None

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.suffix}" if self.suffix else base

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            return False
        return (self.major, self.minor, self.patch, self.suffix) == (
            other.major,
            other.minor,
            other.patch,
            other.suffix,
        )

    @classmethod
    def from_string(cls, version_str: str) -> "Version":
        # Handle suffix matching (e.g., 0.1.0-PROD)
        # Regex captures: (major).(minor).(patch)(optional -suffix)
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9]+))?", version_str)
        if not match:
            raise ValueError(f"Invalid version format: {version_str}")

        major, minor, patch = map(int, match.groups()[:3])
        suffix = match.group(4) if match.group(4) else None
        return cls(major, minor, patch, suffix)

    def bump(self) -> "Version":
        patch = self.patch + 1
        minor = self.minor
        major = self.major
        if patch >= 20:
            patch = 0
            minor += 1
        if minor >= 10:
            minor = 0
            major += 1

        # Note: bump() does NOT preserve suffix by default, because it's re-applied by environment context
        # But we could default to None here and let the caller set it.
        return Version(major, minor, patch, suffix=None)


class FileUpdater:
    """Handles safe file updates with atomic writes and rollback."""

    def __init__(self, file_path: Path, dry_run: bool = False):
        self.file_path = file_path
        self.dry_run = dry_run
        self.backup_path: Path | None = None
        self.temp_path: Path | None = None
        self.original_content: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_path and self.temp_path.exists():
            try:
                self.temp_path.unlink()
            except Exception:
                pass
        return False

    def update(self, content: str) -> bool:
        if self.dry_run:
            return True
        try:
            self.original_content = self.file_path.read_text()
            self.backup_path = self.file_path.with_suffix(self.file_path.suffix + ".bak")
            shutil.copy2(self.file_path, self.backup_path)

            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.file_path.parent,
                delete=False,
                prefix=f".{self.file_path.name}.",
                suffix=".tmp",
                encoding="utf-8",
            ) as tmp:
                tmp.write(content)
                self.temp_path = Path(tmp.name)

            self.temp_path.replace(self.file_path)
            self.temp_path = None
            return True
        except Exception as e:
            logger.error(f"Failed to update {self.file_path}: {e}")
            return False

    def rollback(self) -> bool:
        if not self.original_content:
            return False
        try:
            self.file_path.write_text(self.original_content)
            return True
        except Exception:
            if self.backup_path and self.backup_path.exists():
                try:
                    shutil.copy2(self.backup_path, self.file_path)
                    return True
                except Exception:
                    pass
            return False

    def cleanup_backup(self):
        if self.backup_path and self.backup_path.exists():
            try:
                self.backup_path.unlink()
            except Exception:
                pass


class VersionBumper:
    """Main version bumping orchestrator."""

    def __init__(self, backend_dir: Path, dry_run: bool = False):
        self.backend_dir = backend_dir
        self.dry_run = dry_run
        self.pyproject_path = backend_dir / "pyproject.toml"
        self.config_path = backend_dir / "app/core/config.py"
        self.updaters: list[FileUpdater] = []
        self.env_suffix: str | None = None

    def read_current_version(self) -> Version:
        if not self.pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {self.pyproject_path}")
        try:
            with self.pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            version_str = data.get("tool", {}).get("poetry", {}).get("version") or data.get(
                "project", {}
            ).get("version")
            if not version_str:
                raise ValueError("Version not found in [tool.poetry] or [project]")
            return Version.from_string(version_str)
        except (ValueError, IndexError) as err:
            logger.warning(f"Could not parse version from {self.pyproject_path}: {err}")
            raise ValueError(f"Invalid version format in {self.pyproject_path}") from err
        except Exception as e:
            logger.error(f"Failed to read version from {self.pyproject_path}: {e}")
            raise

    def update_pyproject(self, new_version: Version) -> bool:
        try:
            with self.pyproject_path.open("r", encoding="utf-8") as f:
                doc = tomlkit.load(f)

            updated = False
            if "tool" in doc and "poetry" in doc["tool"] and "version" in doc["tool"]["poetry"]:
                doc["tool"]["poetry"]["version"] = str(new_version)
                updated = True
            if "project" in doc and "version" in doc["project"]:
                doc["project"]["version"] = str(new_version)
                updated = True

            if not updated:
                logger.error("Could not find version field")
                return False

            if self.dry_run:
                logger.info(f"[DRY-RUN] Update pyproject.toml to {new_version}")
                return True

            new_content = tomlkit.dumps(doc)
            updater = FileUpdater(self.pyproject_path, self.dry_run)
            self.updaters.append(updater)
            with updater:
                if updater.update(new_content):
                    logger.info(f"✓ Updated pyproject.toml to {new_version}")
                    return True
        except Exception as e:
            logger.error(f"Failed to update pyproject.toml: {e}")
            return False
        return False

    def update_config(self, new_version: Version) -> bool:
        if not self.config_path.exists():
            return True
        try:
            content = self.config_path.read_text()
            pattern = r'(APP_VERSION\s*:\s*str\s*=\s*Field\s*\(\s*default\s*=\s*)"[^"]+"'
            if not re.search(pattern, content):
                logger.warning("APP_VERSION not found in config.py")
                return True

            if self.dry_run:
                logger.info(f"[DRY-RUN] Update config.py to {new_version}")
                return True

            new_content = re.sub(pattern, f'\\1"{new_version}"', content)

            try:
                compile(new_content, str(self.config_path), "exec")
            except SyntaxError as e:
                logger.error(f"Syntax error in new config.py: {e}")
                return False

            updater = FileUpdater(self.config_path, self.dry_run)
            self.updaters.append(updater)
            with updater:
                if updater.update(new_content):
                    logger.info(f"✓ Updated config.py to {new_version}")
                    return True
        except Exception as e:
            logger.error(f"Failed to update config.py: {e}")
            return False
        return False

    def update_database(self, new_version: Version) -> bool:
        """Update app_version in the database."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Update DB app_settings to {new_version}")
            return True

        try:
            # Lazy import to avoid import errors if not in correct venv
            from sqlalchemy import create_engine, text

            from app.core.config import settings

            # Use sync engine for script
            db_url = (
                str(settings.PRIMARY_DATABASE_URL_ENV or "")
                .replace("+asyncpg", "")
                .replace("postgresql://", "postgresql+psycopg2://")
            )
            if not db_url or "None" in db_url:
                # Fallback to reconstructed URL if env var is missing
                db_url = f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            if "+psycopg2" not in db_url and "postgresql" in db_url:
                # If it was just postgresql:// (libpq), fine.
                # But usually asyncpg is specified. Ensure we have a sync driver or default.
                if "postgresql://" in db_url and "+asyncpg" not in db_url:
                    pass  # Assume default driver (psycopg2)

            # Create a localized sync engine
            engine = create_engine(db_url)

            with engine.connect() as conn:
                # Update the singleton row (id=1)
                sql = text("UPDATE app_settings SET app_version = :ver WHERE id = 1")
                result = conn.execute(sql, {"ver": str(new_version)})
                conn.commit()
                if result.rowcount == 0:
                    # Row might not exist yet if init_db hasn't run, but usually it does.
                    logger.warning("No row found in app_settings (id=1). Version not saved to DB.")
                else:
                    logger.info(f"✓ Updated Database app_version to {new_version}")
            return True

        except ImportError as e:
            logger.warning(f"Database update skipped: Missing dependencies ({e})")
            return False  # Non-critical if running outside full env, but user asked for it.
        except Exception as e:
            logger.error(f"Database update failed: {e}")
            return False

    def bump_version(self) -> bool:
        try:
            with file_lock(self.pyproject_path):
                current = self.read_current_version()
                logger.info(f"Current version: {current}")
                new_version = current.bump()

                # Apply Environment Suffix
                if self.env_suffix:
                    new_version.suffix = self.env_suffix

                logger.info(f"New version:     {new_version}")

                if self.update_pyproject(new_version) and self.update_config(new_version):
                    # DB sync is "best effort" via script but important.
                    # We don't rollback files if DB fails (since DB might differ in envs)
                    self.update_database(new_version)

                    if not self.dry_run:
                        for u in self.updaters:
                            u.cleanup_backup()
                    return True
                else:
                    logger.error("Update failed, rolling back...")
                    for u in reversed(self.updaters):
                        u.rollback()
                    return False
        except TimeoutError as e:
            logger.error(str(e))
            return False
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            for u in reversed(self.updaters):
                u.rollback()
            return False


def main():
    parser = argparse.ArgumentParser(description="Version Bumper")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend-dir", type=Path)
    args = parser.parse_args()

    # Check dependencies (tomlkit already checked)
    # Check sqlalchemy presence if we want to warn early? No, fail gracefully.

    backend_dir = args.backend_dir or BACKEND_DIR

    # Auto-detect Environment Suffix
    env_suffix = None
    import os

    branch_name = os.environ.get("CI_COMMIT_BRANCH", "")
    if branch_name == "main":
        env_suffix = "PROD"
    elif branch_name == "develop":
        env_suffix = "DEV"

    bumper = VersionBumper(backend_dir, dry_run=args.dry_run)
    bumper.env_suffix = env_suffix

    success = bumper.bump_version()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
