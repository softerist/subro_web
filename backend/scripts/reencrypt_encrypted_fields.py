#!/usr/bin/env python3
"""
Re-encrypt all encrypted fields using the current DATA_ENCRYPTION_KEYS.

Usage:
  poetry run python backend/scripts/reencrypt_encrypted_fields.py
  poetry run python backend/scripts/reencrypt_encrypted_fields.py --dry-run
  poetry run python backend/scripts/reencrypt_encrypted_fields.py --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure we can import from 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("/app")  # Fallback for Docker environment

from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.crud.crud_app_settings import ENCRYPTED_FIELDS
from app.db.base import Base  # noqa: F401  # ensure model registry is populated
from app.db.models.app_settings import AppSettings
from app.db.models.user import User
from app.db.session import SyncSessionLocal

logger = logging.getLogger(__name__)


def _reencrypt(raw_value: str | None, field_name: str) -> str | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        decrypted = decrypt_value(raw_value)
    except ValueError:
        logger.warning("Skipping %s: unable to decrypt with current keyring.", field_name)
        return None
    try:
        return encrypt_value(decrypted)
    except ValueError:
        logger.error("Failed to re-encrypt %s.", field_name)
        return None


def reencrypt_app_settings(session, dry_run: bool) -> int:
    changed = 0
    settings = session.query(AppSettings).filter(AppSettings.id == 1).first()
    if not settings:
        logger.warning("AppSettings row not found.")
        return 0

    for field in ENCRYPTED_FIELDS:
        raw_value = getattr(settings, field, None)
        if raw_value is None or raw_value == "":
            continue
        new_value = _reencrypt(raw_value, f"app_settings.{field}")
        if new_value and new_value != raw_value:
            setattr(settings, field, new_value)
            changed += 1

    if changed and not dry_run:
        session.add(settings)
    return changed


def reencrypt_user_fields(session, dry_run: bool) -> int:
    changed = 0
    fields = ["mfa_secret", "mfa_backup_codes"]
    users = session.query(User).all()

    for user in users:
        user_changed = False
        for field in fields:
            raw_value = getattr(user, field, None)
            if raw_value is None or raw_value == "":
                continue
            new_value = _reencrypt(raw_value, f"users.{field}")
            if new_value and new_value != raw_value:
                setattr(user, field, new_value)
                changed += 1
                user_changed = True
        if user_changed and not dry_run:
            session.add(user)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-encrypt encrypted database fields.")
    parser.add_argument("--dry-run", action="store_true", help="Scan only; do not write.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-encrypt even if DATA_ENCRYPTION_KEYS has only one entry.",
    )
    args = parser.parse_args()

    key_count = len([key for key in settings.DATA_ENCRYPTION_KEYS if key])
    if key_count < 2 and not args.force:
        logger.info(
            "Skipping re-encryption; DATA_ENCRYPTION_KEYS has %s entry. Use --force to override.",
            key_count,
        )
        print("skip_no_rotation")
        return 0

    session = SyncSessionLocal()
    try:
        changed_settings = reencrypt_app_settings(session, args.dry_run)
        changed_users = reencrypt_user_fields(session, args.dry_run)
        total = changed_settings + changed_users
        if args.dry_run:
            session.rollback()
            print(f"dry_run_changes={total}")
        elif total:
            session.commit()
            print(f"updated_fields={total}")
        else:
            session.rollback()
            print("no_changes")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
