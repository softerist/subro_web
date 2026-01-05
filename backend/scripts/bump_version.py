#!/usr/bin/env python3
import re
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = BACKEND_DIR / "pyproject.toml"
CONFIG_PATH = BACKEND_DIR / "app/core/config.py"


def read_version_from_pyproject():
    content = PYPROJECT_PATH.read_text()
    match = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', content)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def update_pyproject(major, minor, patch):
    content = PYPROJECT_PATH.read_text()
    new_version = f"{major}.{minor}.{patch}"
    new_content = re.sub(
        r'version = "\d+\.\d+\.\d+"', f'version = "{new_version}"', content, count=1
    )
    PYPROJECT_PATH.write_text(new_content)
    print(f"Updated pyproject.toml to {new_version}")


def update_config(major, minor, patch):
    content = CONFIG_PATH.read_text()
    new_version = f"{major}.{minor}.{patch}"
    # Look for: APP_VERSION: str = Field(default="0.1.0"
    new_content = re.sub(
        r'APP_VERSION: str = Field\(default="\d+\.\d+\.\d+"',
        f'APP_VERSION: str = Field(default="{new_version}"',
        content,
    )
    CONFIG_PATH.write_text(new_content)
    print(f"Updated config.py to {new_version}")


def calculate_new_version(major, minor, patch):
    # Rule 1: Always increment sub-minor (patch)
    patch += 1

    # Rule 2: If sub-minor >= 20, increment minor and reset sub-minor
    if patch >= 20:
        patch = 0
        minor += 1

    # Rule 3: If minor >= 10, increment major and reset minor
    if minor >= 10:
        minor = 0
        major += 1

    return major, minor, patch


def main():
    print("--- Custom Version Bumper ---")
    try:
        major, minor, patch = read_version_from_pyproject()
        print(f"Current version: {major}.{minor}.{patch}")

        new_major, new_minor, new_patch = calculate_new_version(major, minor, patch)
        print(f"New version:     {new_major}.{new_minor}.{new_patch}")

        update_pyproject(new_major, new_minor, new_patch)
        update_config(new_major, new_minor, new_patch)

    except Exception as e:
        print(f"Error bumping version: {e}")
        exit(1)


if __name__ == "__main__":
    main()
