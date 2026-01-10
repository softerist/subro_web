# backend/app/api/routers/webhook_keys.py
"""Webhook key management endpoints for qBittorrent integration."""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.users import get_current_active_admin_user
from app.db.models.user import User
from app.db.models.webhook_key import WebhookKey
from app.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/webhook-key", tags=["Webhook Key"])

# File path for webhook key (inside Docker, mapped to host via volume)
WEBHOOK_ENV_FILE = Path("/app/secrets/.env.webhook")


class WebhookKeyResponse(BaseModel):
    """Response when a webhook key is generated."""

    id: str
    name: str
    preview: str
    raw_key: str | None = None  # Only returned on creation
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    use_count: int
    is_active: bool


class WebhookKeyStatus(BaseModel):
    """Status of webhook key configuration."""

    configured: bool
    preview: str | None = None
    last_used_at: datetime | None = None
    use_count: int = 0
    env_file_exists: bool = False


def _hash_webhook_key(raw_key: str) -> str:
    """Hash a webhook key using HMAC-SHA256 with pepper."""
    if not settings.API_KEY_PEPPER:
        raise RuntimeError("API_KEY_PEPPER is not configured.")
    return hmac.new(
        settings.API_KEY_PEPPER.encode(),
        raw_key.encode(),
        hashlib.sha256,
    ).hexdigest()


def _write_key_to_env_file(raw_key: str) -> bool:
    """Write the webhook key to the env file for external scripts."""
    try:
        WEBHOOK_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        WEBHOOK_ENV_FILE.write_text(f"SUBRO_API_KEY={raw_key}\n")
        WEBHOOK_ENV_FILE.chmod(0o600)
        logger.info(f"Wrote webhook key to {WEBHOOK_ENV_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to write webhook key to env file: {e}")
        return False


@router.get(
    "/status",
    response_model=WebhookKeyStatus,
    summary="Get webhook key status",
    description="Check if a webhook key is configured and its status.",
)
async def get_webhook_key_status(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_admin_user),
) -> WebhookKeyStatus:
    """Get the current status of webhook key configuration."""
    logger.debug(f"Webhook key status checked by: {current_user.email}")

    result = await db.execute(
        select(WebhookKey).where(WebhookKey.is_active == True).limit(1)  # noqa: E712
    )
    key = result.scalar_one_or_none()

    return WebhookKeyStatus(
        configured=key is not None,
        preview=key.preview if key else None,
        last_used_at=key.last_used_at if key else None,
        use_count=key.use_count if key else 0,
        env_file_exists=WEBHOOK_ENV_FILE.exists(),
    )


@router.post(
    "",
    response_model=WebhookKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate webhook key",
    description="Generate a new webhook key for qBittorrent integration. Revokes any existing key.",
)
async def generate_webhook_key(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_admin_user),
) -> WebhookKeyResponse:
    """Generate a new webhook key and write it to the env file."""
    logger.info(f"Generating webhook key requested by: {current_user.email}")

    # Revoke any existing active keys
    result = await db.execute(
        select(WebhookKey).where(WebhookKey.is_active == True)  # noqa: E712
    )
    existing_keys = result.scalars().all()
    for key in existing_keys:
        key.is_active = False
        db.add(key)
    if existing_keys:
        logger.info(f"Revoked {len(existing_keys)} existing webhook key(s)")

    # Generate new key
    raw_key = secrets.token_urlsafe(32)
    hashed_key = _hash_webhook_key(raw_key)

    new_key = WebhookKey(
        name="qBittorrent Webhook",
        description="Auto-generated for qBittorrent integration",
        prefix=raw_key[:8],
        last4=raw_key[-4:],
        hashed_key=hashed_key,
        scopes=["jobs:create"],
        is_active=True,
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    # Write to env file
    if not _write_key_to_env_file(raw_key):
        logger.warning("Key created but failed to write to env file")

    logger.info(f"Webhook key generated: {new_key.preview}")

    return WebhookKeyResponse(
        id=str(new_key.id),
        name=new_key.name,
        preview=new_key.preview,
        raw_key=raw_key,  # Only returned on creation
        scopes=new_key.scopes,
        created_at=new_key.created_at,
        last_used_at=new_key.last_used_at,
        use_count=new_key.use_count,
        is_active=new_key.is_active,
    )


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="Revoke webhook key",
    description="Revoke the current webhook key.",
)
async def revoke_webhook_key(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_admin_user),
) -> dict:
    """Revoke any active webhook keys."""
    logger.info(f"Revoking webhook key requested by: {current_user.email}")

    result = await db.execute(
        select(WebhookKey).where(WebhookKey.is_active == True)  # noqa: E712
    )
    keys = result.scalars().all()

    if not keys:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active webhook key found",
        )

    for key in keys:
        key.is_active = False
        db.add(key)

    await db.commit()

    # Remove env file
    try:
        if WEBHOOK_ENV_FILE.exists():
            WEBHOOK_ENV_FILE.unlink()
            logger.info("Removed webhook env file")
    except Exception as e:
        logger.warning(f"Failed to remove webhook env file: {e}")

    return {"revoked": True, "count": len(keys)}


async def validate_webhook_key(
    raw_key: str,
    db: AsyncSession,
    required_scope: str = "jobs:create",
) -> WebhookKey | None:
    """
    Validate a webhook key and check scope.

    Returns the WebhookKey if valid, None otherwise.
    Updates last_used_at and use_count on success.
    """
    if not raw_key or not settings.API_KEY_PEPPER:
        return None

    prefix = raw_key[:8]
    hashed = _hash_webhook_key(raw_key)

    result = await db.execute(
        select(WebhookKey).where(
            WebhookKey.prefix == prefix,
            WebhookKey.is_active == True,  # noqa: E712
        )
    )
    candidates = result.scalars().all()

    for key in candidates:
        if hmac.compare_digest(key.hashed_key, hashed):
            # Check scope
            if required_scope not in key.scopes:
                logger.warning(f"Webhook key {key.preview} missing scope: {required_scope}")
                return None

            # Update usage stats
            key.last_used_at = datetime.now(UTC)
            key.use_count = (key.use_count or 0) + 1
            db.add(key)
            await db.commit()
            return key

    return None


class QBittorrentConfigureResponse(BaseModel):
    """Response from qBittorrent auto-configure."""

    success: bool
    message: str
    webhook_key_generated: bool = False
    qbittorrent_configured: bool = False
    details: dict | None = None


@router.post(
    "/configure-qbittorrent",
    response_model=QBittorrentConfigureResponse,
    summary="Auto-configure qBittorrent webhook",
    description=(
        "Generates a webhook key and configures qBittorrent to run the webhook script "
        "on torrent completion. Requires qBittorrent credentials to be configured."
    ),
)
async def configure_qbittorrent_webhook(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_admin_user),
) -> QBittorrentConfigureResponse:
    """
    Auto-configure qBittorrent webhook integration.

    This endpoint:
    1. Generates a new webhook key (revoking any existing one)
    2. Writes the key to /app/secrets/.env.webhook
    3. Connects to qBittorrent and sets autorun_enabled + autorun_program
    """
    from app.crud.crud_app_settings import crud_app_settings
    from app.modules.subtitle.services.torrent_client import (
        configure_webhook_autorun,
        login_to_qbittorrent,
    )

    logger.info(f"Auto-configure qBittorrent requested by: {current_user.email}")

    # Step 1: Check qBittorrent credentials
    app_settings = await crud_app_settings.get(db)
    if not app_settings.qbittorrent_host:
        return QBittorrentConfigureResponse(
            success=False,
            message="qBittorrent host not configured. Please fill in the qBittorrent connection details first.",
            details={"step": "validate_credentials"},
        )

    # Step 2: Generate webhook key
    # Revoke existing keys
    result = await db.execute(
        select(WebhookKey).where(WebhookKey.is_active == True)  # noqa: E712
    )
    existing_keys = result.scalars().all()
    for key in existing_keys:
        key.is_active = False
        db.add(key)

    # Generate new key
    raw_key = secrets.token_urlsafe(32)
    hashed_key = _hash_webhook_key(raw_key)

    new_key = WebhookKey(
        name="qBittorrent Webhook",
        description="Auto-generated by configure-qbittorrent endpoint",
        prefix=raw_key[:8],
        last4=raw_key[-4:],
        hashed_key=hashed_key,
        scopes=["jobs:create"],
        is_active=True,
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    # Write to env file
    key_written = _write_key_to_env_file(raw_key)
    logger.info(f"Webhook key generated: {new_key.preview}, written to file: {key_written}")

    # Step 3: Connect to qBittorrent and configure
    client = login_to_qbittorrent()
    if not client:
        return QBittorrentConfigureResponse(
            success=False,
            message="Failed to connect to qBittorrent. Check your credentials and ensure qBittorrent is running.",
            webhook_key_generated=True,
            qbittorrent_configured=False,
            details={
                "step": "connect_qbittorrent",
                "key_preview": new_key.preview,
                "key_written_to_file": key_written,
            },
        )

    # Configure autorun
    script_path = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh"
    configured = configure_webhook_autorun(client, script_path)

    if not configured:
        return QBittorrentConfigureResponse(
            success=False,
            message="Connected to qBittorrent but failed to configure autorun. Check qBittorrent logs.",
            webhook_key_generated=True,
            qbittorrent_configured=False,
            details={
                "step": "configure_autorun",
                "key_preview": new_key.preview,
            },
        )

    return QBittorrentConfigureResponse(
        success=True,
        message="qBittorrent webhook configured successfully! Subtitles will be downloaded automatically when torrents complete.",
        webhook_key_generated=True,
        qbittorrent_configured=True,
        details={
            "key_preview": new_key.preview,
            "script_path": script_path,
            "autorun_command": f'/usr/bin/bash {script_path} "%F"',
        },
    )
