import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def bump_version_module():
    sys.modules.setdefault("tomlkit", types.ModuleType("tomlkit"))
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"
    spec = importlib.util.spec_from_file_location("bump_version", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_base_and_suffix_parsing(bump_version_module) -> None:
    Version = bump_version_module.Version
    version = Version.from_string("0.1.3-PROD")
    assert version.base() == "0.1.3"
    assert str(version) == "0.1.3-PROD"


def test_version_parses_local_suffix(bump_version_module) -> None:
    Version = bump_version_module.Version
    version = Version.from_string("0.1.3+prod")
    assert version.base() == "0.1.3"
    assert version.suffix == "prod"


def test_version_bump_drops_suffix(bump_version_module) -> None:
    Version = bump_version_module.Version
    version = Version.from_string("0.1.3-PROD")
    bumped = version.bump()
    assert bumped.base() == "0.1.4"
    assert bumped.suffix is None


def test_update_package_lock_json_updates_root_versions(
    tmp_path: Path, bump_version_module
) -> None:
    backend_dir = tmp_path / "backend"
    frontend_dir = tmp_path / "frontend"
    backend_dir.mkdir()
    frontend_dir.mkdir()

    package_lock_path = frontend_dir / "package-lock.json"
    package_lock_path.write_text(
        json.dumps(
            {
                "name": "subtitle-downloader-frontend",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "subtitle-downloader-frontend",
                        "version": "1.0.0",
                    }
                },
            },
            indent=2,
        )
        + "\n"
    )

    bumper = bump_version_module.VersionBumper(backend_dir, dry_run=False)
    new_version = bump_version_module.Version.from_string("2.3.4")

    assert bumper.update_package_lock_json(new_version) is True

    updated = json.loads(package_lock_path.read_text())
    assert updated["version"] == "2.3.4"
    assert updated["packages"][""]["version"] == "2.3.4"


def test_update_root_package_json_updates_version(tmp_path: Path, bump_version_module) -> None:
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    package_json_path = tmp_path / "package.json"
    package_json_path.write_text(
        json.dumps({"name": "subro-web", "version": "0.0.0"}, indent=2) + "\n"
    )

    bumper = bump_version_module.VersionBumper(backend_dir, dry_run=False)
    new_version = bump_version_module.Version.from_string("2.3.4")

    assert bumper.update_root_package_json(new_version) is True

    updated = json.loads(package_json_path.read_text())
    assert updated["version"] == "2.3.4"


def test_update_root_package_lock_json_updates_root_versions(
    tmp_path: Path, bump_version_module
) -> None:
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    package_lock_path = tmp_path / "package-lock.json"
    package_lock_path.write_text(
        json.dumps(
            {
                "name": "subro-web",
                "version": "0.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "subro-web",
                        "version": "0.0.0",
                    }
                },
            },
            indent=2,
        )
        + "\n"
    )

    bumper = bump_version_module.VersionBumper(backend_dir, dry_run=False)
    new_version = bump_version_module.Version.from_string("2.3.4")

    assert bumper.update_root_package_lock_json(new_version) is True

    updated = json.loads(package_lock_path.read_text())
    assert updated["version"] == "2.3.4"
    assert updated["packages"][""]["version"] == "2.3.4"
