# backend/app/api/routers/webhook_keys.py
"""Webhook key management endpoints for qBittorrent integration."""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

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

    # env_file_exists field removed/deprecated as we don't use files anymore

    # Keeping it for backward compatibility if frontend expects it, but always False

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
        env_file_exists=False,  # No longer using files
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
    """Generate a new webhook key."""

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

    # Note: We don't write to file anymore.

    # The user/admin is responsible for configuring qBittorrent with this key,

    # OR using the auto-configure endpoint which handles it.

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

    2. Connects to qBittorrent and sets autorun_enabled + autorun_program with the key.

    """

    from app.crud.crud_app_settings import crud_app_settings
    from app.modules.subtitle.services.torrent_client import (
        configure_webhook_autorun,
        disable_webhook_autorun,
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
            },
        )

    # Configure autorun WITH key

    script_path = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh"

    configured = configure_webhook_autorun(client, script_path, api_key=raw_key)

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
            "autorun_command": f'/usr/bin/bash {script_path} "%F" --api-key="***"',
        },
    )

    @router.delete(
        "/configure-qbittorrent",
        status_code=status.HTTP_200_OK,
        summary="Remove qBittorrent integration",
        description="Revokes the webhook key and disables the autorun script in qBittorrent.",
    )
    async def remove_qbittorrent_configuration(
        db: AsyncSession = Depends(get_async_session),
        current_user: User = Depends(get_current_active_admin_user),
    ) -> dict[str, Any]:
        """Remove qBittorrent integration."""

        from app.modules.subtitle.services.torrent_client import (
            login_to_qbittorrent,
        )

        logger.info(f"Removing qBittorrent integration requested by: {current_user.email}")

        # 1. Revoke keys

        result = await db.execute(
            select(WebhookKey).where(WebhookKey.is_active == True)  # noqa: E712
        )

        keys = result.scalars().all()

        for key in keys:
            key.is_active = False

            db.add(key)

        await db.commit()

        # 2. Disable in qBittorrent

        qb_status = "not_connected"

        client = login_to_qbittorrent()

        if client:
            if disable_webhook_autorun(client):
                qb_status = "disabled"

            else:
                qb_status = "failed_to_disable"

        else:
            qb_status = "connection_failed"

        return {
            "success": True,
            "message": "Integration removed.",
            "details": {"keys_revoked": len(keys), "qbittorrent_status": qb_status},
        }


async def ensure_default_webhook_key(db: AsyncSession) -> None:
    """

    Ensure a webhook key exists and qBittorrent is configured.

    Run this on startup.

    """

    from app.modules.subtitle.services.torrent_client import (
        configure_webhook_autorun,
        login_to_qbittorrent,
    )

    # 1. Check if we have ANY active key in DB

    result = await db.execute(select(WebhookKey).where(WebhookKey.is_active == True).limit(1))  # noqa: E712

    existing_key = result.scalar_one_or_none()

    raw_key = None

    if existing_key:
        logger.info("Active webhook key found in DB. Skipping generation.")

        # If key exists, we can't configure qBittorrent with it as we don't have raw_key.

        # We assume configuration persists in qBittorrent.

        return

    else:
        logger.info("No webhook key configured. Generating default key...")

        raw_key = secrets.token_urlsafe(32)

        hashed_key = _hash_webhook_key(raw_key)

        new_key = WebhookKey(
            name="Auto-Generated (Startup)",
            description="Generated automatically on startup",
            prefix=raw_key[:8],
            last4=raw_key[-4:],
            hashed_key=hashed_key,
            scopes=["jobs:create"],
            is_active=True,
        )

        db.add(new_key)

        await db.commit()

        logger.info(f"Default webhook key generated: {new_key.preview}")

    # 2. Try to configure qBittorrent if we generated a new key

    if raw_key:
        try:
            client = login_to_qbittorrent()

            if client:
                logger.info("Connecting to qBittorrent to configure webhook...")

                script_path = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh"

                if configure_webhook_autorun(client, script_path, api_key=raw_key):
                    logger.info("qBittorrent successfully auto-configured with new webhook key.")

                else:
                    logger.warning("Failed to configure qBittorrent webhook settings.")

            else:
                # This is common if qBittorrent credentials aren't set in env/settings yet

                logger.info("Skipping qBittorrent configuration (client not connected/configured).")

        except Exception as e:
            logger.warning(f"Error attempting to configure qBittorrent on startup: {e}")
