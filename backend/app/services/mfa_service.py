# backend/app/services/mfa_service.py
"""
MFA (Multi-Factor Authentication) service using TOTP.

Provides functions for:
- Generating and verifying TOTP codes
- Managing trusted devices
- Generating QR codes for authenticator apps
"""

import base64
import hashlib
import io
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.db.models.trusted_device import TrustedDevice
from app.db.models.user import User

logger = logging.getLogger(__name__)

# Constants
TRUSTED_DEVICE_EXPIRY_DAYS = 30
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8
APP_NAME = "SubroWeb"  # Shown in authenticator apps


def generate_totp_secret() -> str:
    """Generate a new TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Generate the TOTP provisioning URI for QR code."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=APP_NAME)


def generate_qr_code_base64(uri: str) -> str:
    """Generate a QR code as base64 PNG for the given URI."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify a TOTP code against the secret.

    Allows for 1 window of tolerance (30 seconds before/after).
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes() -> list[str]:
    """Generate a list of backup codes for recovery."""
    return [secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper() for _ in range(BACKUP_CODE_COUNT)]


def hash_backup_code(code: str) -> str:
    """Hash a backup code for storage."""
    return hashlib.sha256(code.encode()).hexdigest()


def hash_device_token(token: str) -> str:
    """Hash a device trust token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_device_token() -> str:
    """Generate a secure random token for device trust."""
    return secrets.token_urlsafe(32)


async def setup_mfa(
    db: AsyncSession,
    user: User,
) -> dict:
    """
    Initialize MFA setup for a user.

    Returns the secret, QR code, and backup codes.
    The caller should store these temporarily until verified.
    """
    # Generate new secret
    secret = generate_totp_secret()

    # Generate provisioning URI and QR code
    uri = get_totp_uri(secret, user.email)
    qr_code_base64 = generate_qr_code_base64(uri)

    # Generate backup codes
    backup_codes = generate_backup_codes()

    logger.info(f"MFA setup initiated for user {user.email}")

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_code_base64}",
        "backup_codes": backup_codes,
        "uri": uri,  # For manual entry
    }


async def enable_mfa(
    db: AsyncSession,
    user: User,
    secret: str,
    code: str,
    backup_codes: list[str],
) -> bool:
    """
    Enable MFA after verifying the initial code.

    Returns True if successful, False if code invalid.
    """
    if not verify_totp_code(secret, code):
        logger.warning(f"Invalid TOTP code during MFA setup for {user.email}")
        return False

    # Encrypt and store the secret
    encrypted_secret = encrypt_value(secret)

    # Hash and encrypt backup codes
    hashed_codes = [hash_backup_code(code) for code in backup_codes]
    encrypted_codes = encrypt_value(json.dumps(hashed_codes))

    # Update user
    user.mfa_secret = encrypted_secret
    user.mfa_enabled = True
    user.mfa_backup_codes = encrypted_codes

    db.add(user)
    await db.commit()

    logger.info(f"MFA enabled for user {user.email}")
    return True


async def verify_mfa(
    db: AsyncSession,
    user: User,
    code: str,
) -> bool:
    """
    Verify a TOTP code for login.

    Also checks backup codes if TOTP fails.
    """
    if not user.mfa_enabled or not user.mfa_secret:
        return True  # MFA not enabled, always pass

    # Decrypt the secret
    try:
        secret = decrypt_value(user.mfa_secret)
    except Exception as e:
        logger.error(f"Failed to decrypt MFA secret for {user.email}: {e}")
        return False

    # Try TOTP verification first
    if verify_totp_code(secret, code):
        return True

    # Try backup codes
    if user.mfa_backup_codes:
        try:
            hashed_codes = json.loads(decrypt_value(user.mfa_backup_codes))
            code_hash = hash_backup_code(code.upper().replace("-", "").replace(" ", ""))

            if code_hash in hashed_codes:
                # Remove used backup code
                hashed_codes.remove(code_hash)
                user.mfa_backup_codes = encrypt_value(json.dumps(hashed_codes))
                db.add(user)
                await db.commit()

                logger.info(f"Backup code used for {user.email}, {len(hashed_codes)} remaining")
                return True
        except Exception as e:
            logger.error(f"Error checking backup codes for {user.email}: {e}")

    return False


async def disable_mfa(
    db: AsyncSession,
    user: User,
) -> None:
    """Disable MFA for a user."""
    user.mfa_secret = None
    user.mfa_enabled = False
    user.mfa_backup_codes = None

    # Also remove all trusted devices
    await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))

    db.add(user)
    await db.commit()

    logger.info(f"MFA disabled for user {user.email}")


async def trust_device(
    db: AsyncSession,
    user: User,
    device_name: str | None,
    ip_address: str | None,
) -> str:
    """
    Create a trusted device entry and return the token.

    The raw token should be stored in a cookie.
    """
    token = generate_device_token()
    token_hash = hash_device_token(token)

    trusted = TrustedDevice(
        user_id=user.id,
        token_hash=token_hash,
        device_name=device_name,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=TRUSTED_DEVICE_EXPIRY_DAYS),
    )

    db.add(trusted)
    await db.commit()

    logger.info(f"Trusted device added for {user.email}: {device_name}")
    return token


async def verify_trusted_device(
    db: AsyncSession,
    user_id: str,
    token: str,
) -> bool:
    """
    Check if a device token is valid and not expired.

    Updates last_used_at if valid.
    """
    if not token:
        return False

    token_hash = hash_device_token(token)
    now = datetime.now(UTC)

    stmt = select(TrustedDevice).where(
        TrustedDevice.user_id == user_id,
        TrustedDevice.token_hash == token_hash,
        TrustedDevice.expires_at > now,
    )

    result = await db.execute(stmt)
    trusted = result.scalar_one_or_none()

    if trusted:
        trusted.last_used_at = now
        db.add(trusted)
        await db.commit()
        return True

    return False


async def revoke_trusted_device(
    db: AsyncSession,
    user: User,
    device_id: str,
) -> bool:
    """Revoke a specific trusted device."""
    result = await db.execute(
        delete(TrustedDevice).where(
            TrustedDevice.id == device_id,
            TrustedDevice.user_id == user.id,
        )
    )
    await db.commit()

    return result.rowcount > 0


async def get_user_trusted_devices(
    db: AsyncSession,
    user: User,
) -> list[dict]:
    """Get all trusted devices for a user."""
    stmt = (
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user.id)
        .order_by(TrustedDevice.created_at.desc())
    )

    result = await db.execute(stmt)
    devices = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "device_name": d.device_name,
            "ip_address": d.ip_address,
            "created_at": d.created_at.isoformat(),
            "last_used_at": d.last_used_at.isoformat() if d.last_used_at else None,
            "expires_at": d.expires_at.isoformat(),
            "is_expired": d.is_expired(),
        }
        for d in devices
    ]
