# backend/tests/utils/test_encryption_keyring.py
import importlib.util
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core import security
from app.core.config import settings


def _load_reencrypt_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "reencrypt_encrypted_fields.py"
    spec = importlib.util.spec_from_file_location("reencrypt_encrypted_fields", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load reencrypt script module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REENCRYPT_MODULE = _load_reencrypt_module()


def _set_keyring(keys: list[str]) -> None:
    settings._parsed_data_encryption_keys = list(keys)
    security._get_fernet.cache_clear()


def _restore_keyring(original_keys: list[str]) -> None:
    settings._parsed_data_encryption_keys = list(original_keys)
    security._get_fernet.cache_clear()


def test_encrypt_uses_primary_key() -> None:
    original_keys = list(settings.DATA_ENCRYPTION_KEYS)
    try:
        _set_keyring(["primary-key", "secondary-key"])
        token = security.encrypt_value("payload")
        assert security.decrypt_value(token) == "payload"

        primary = Fernet(security._derive_fernet_key("primary-key"))
        assert primary.decrypt(token.encode()).decode() == "payload"

        secondary = Fernet(security._derive_fernet_key("secondary-key"))
        with pytest.raises(InvalidToken):
            secondary.decrypt(token.encode())
    finally:
        _restore_keyring(original_keys)


def test_decrypt_accepts_secondary_key() -> None:
    original_keys = list(settings.DATA_ENCRYPTION_KEYS)
    try:
        _set_keyring(["new-key", "old-key"])
        old_fernet = Fernet(security._derive_fernet_key("old-key"))
        token = old_fernet.encrypt(b"payload").decode()
        assert security.decrypt_value(token) == "payload"
    finally:
        _restore_keyring(original_keys)


def test_reencrypt_uses_primary_key() -> None:
    original_keys = list(settings.DATA_ENCRYPTION_KEYS)
    try:
        _set_keyring(["new-key", "old-key"])
        old_fernet = Fernet(security._derive_fernet_key("old-key"))
        old_token = old_fernet.encrypt(b"payload").decode()

        new_token = REENCRYPT_MODULE._reencrypt(old_token, "test.field")
        assert new_token is not None
        assert new_token != old_token

        primary = Fernet(security._derive_fernet_key("new-key"))
        assert primary.decrypt(new_token.encode()).decode() == "payload"
    finally:
        _restore_keyring(original_keys)


def test_reencrypt_script_skips_without_rotation(capsys) -> None:
    original_keys = list(settings.DATA_ENCRYPTION_KEYS)
    original_argv = list(sys.argv)
    try:
        _set_keyring(["only-key"])
        sys.argv = ["reencrypt_encrypted_fields.py"]
        result = REENCRYPT_MODULE.main()
        captured = capsys.readouterr()
        assert result == 0
        assert "skip_no_rotation" in captured.out
    finally:
        sys.argv = original_argv
        _restore_keyring(original_keys)
