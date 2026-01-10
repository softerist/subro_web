import importlib.util
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
