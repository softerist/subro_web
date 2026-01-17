# backend/app/api/routers/webhook_keys.py
"""Webhook key management endpoints for qBittorrent integration."""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.log_utils import sanitize_for_log as _sanitize_for_log
from app.core.security import decrypt_value, encrypt_value
from app.core.users import get_current_active_admin_user
from app.db.models.user import User
from app.db.models.webhook_key import WebhookKey
from app.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/webhook-key", tags=["Webhook Key"])

# Allowed IPs for localhost-only endpoint
LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost"}
DOCKER_GATEWAY_PREFIXES = ("172.17.", "172.18.", "172.19.", "172.20.", "172.21.")


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


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header first (for reverse proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    return "unknown"


def _is_localhost_request(client_ip: str) -> bool:
    """Check if request is from localhost or Docker gateway."""
    if client_ip in LOCALHOST_IPS:
        return True
    # Check Docker gateway IPs (172.17.x.x - 172.21.x.x)
    if any(client_ip.startswith(prefix) for prefix in DOCKER_GATEWAY_PREFIXES):
        return True
    return False


@router.get(
    "/current-key",
    include_in_schema=False,  # Hide from OpenAPI docs for security
    summary="Get current webhook key (localhost only)",
)
async def get_current_webhook_key(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    """
    Retrieve the current qBittorrent webhook key.

    Security:
    - Only accessible from localhost (127.0.0.1, ::1) or Docker gateway
    - Used by the webhook script to authenticate with the API
    - Audit logged for security monitoring
    """
    from app.crud.crud_app_settings import crud_app_settings

    # 1. Validate client IP - localhost only
    client_ip = _get_client_ip(request)

    if not _is_localhost_request(client_ip):
        logger.warning(
            "Rejected webhook key retrieval from non-localhost IP: %s", _sanitize_for_log(client_ip)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible from localhost",
        )

    # 2. Get encrypted key from database
    app_settings = await crud_app_settings.get(db)

    if not app_settings.qbittorrent_webhook_key_encrypted:
        logger.info(
            "Webhook key retrieval attempted but no key configured (from %s)",
            _sanitize_for_log(client_ip),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No webhook key is configured. Use the Settings page to configure qBittorrent.",
        )

    # 3. Decrypt the key
    try:
        raw_key = decrypt_value(app_settings.qbittorrent_webhook_key_encrypted)
    except Exception as e:
        logger.error("Failed to decrypt webhook key: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt webhook key",
        ) from None

    # 4. Audit log successful retrieval
    logger.info("Webhook key retrieved successfully from %s", _sanitize_for_log(client_ip))

    return {"key": raw_key}


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

    logger.debug("Webhook key status checked by: %s", _sanitize_for_log(current_user.email))

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

    logger.info("Generating webhook key requested by: %s", _sanitize_for_log(current_user.email))

    # Revoke any existing active keys

    result = await db.execute(
        select(WebhookKey).where(WebhookKey.is_active == True)  # noqa: E712
    )

    existing_keys = result.scalars().all()

    for key in existing_keys:
        key.is_active = False

        db.add(key)

    if existing_keys:
        logger.info("Revoked %d existing webhook key(s)", len(existing_keys))

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

    logger.info("Webhook key generated: %s", new_key.preview)

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

    logger.info("Revoking webhook key requested by: %s", _sanitize_for_log(current_user.email))

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
                logger.warning("Webhook key %s missing scope: %s", key.preview, required_scope)

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
        login_to_qbittorrent_with_settings,
    )

    logger.info(
        "Auto-configure qBittorrent requested by: %s", _sanitize_for_log(current_user.email)
    )

    # Step 1: Check qBittorrent credentials

    app_settings = await crud_app_settings.get(db)

    if not app_settings.qbittorrent_host:
        return QBittorrentConfigureResponse(
            success=False,
            message="qBittorrent host not configured. Please fill in the qBittorrent connection details first.",
            details={"step": "validate_credentials"},
        )

    # Get effective settings from database (decrypt password)
    effective_host = app_settings.qbittorrent_host
    effective_port = app_settings.qbittorrent_port or 8080
    effective_username = app_settings.qbittorrent_username or ""

    # Decrypt password if present
    effective_password = ""
    if app_settings.qbittorrent_password:
        from app.core.security import decrypt_value

        try:
            effective_password = decrypt_value(app_settings.qbittorrent_password)
        except Exception as e:
            # nosemgrep: python-logger-credential-disclosure - logs error, not actual password
            logger.warning("Failed to decrypt qBittorrent password: %s", e)
            effective_password = ""

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

    # Step 2b: Store encrypted key in app_settings for secure script retrieval
    app_settings.qbittorrent_webhook_key_encrypted = encrypt_value(raw_key)
    await db.commit()
    logger.info("Stored encrypted webhook key in app_settings")

    # Step 3: Connect to qBittorrent using DB settings

    client = login_to_qbittorrent_with_settings(
        host=effective_host,
        port=effective_port,
        username=effective_username,
        password=effective_password,
    )

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

    # Configure autorun WITHOUT api_key - script fetches key from /current-key endpoint

    script_path = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh"

    configured = configure_webhook_autorun(client, script_path)  # No api_key parameter

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

    # Step 4: Update /opt/subro_web/.env with required settings
    env_updated = _update_webhook_env_config()

    return QBittorrentConfigureResponse(
        success=True,
        message="qBittorrent webhook configured successfully! Subtitles will be downloaded automatically when torrents complete.",
        webhook_key_generated=True,
        qbittorrent_configured=True,
        details={
            "key_preview": new_key.preview,
            "script_path": script_path,
            "autorun_command": f'/usr/bin/bash {script_path} "%F"',
            "env_file_updated": env_updated,
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
        disable_webhook_autorun,
        login_to_qbittorrent,
    )

    logger.info(
        "Removing qBittorrent integration requested by: %s", _sanitize_for_log(current_user.email)
    )

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

        logger.info("Default webhook key generated: %s", new_key.preview)

    # 2. Try to configure qBittorrent if we generated a new key

    if raw_key:
        try:
            client = login_to_qbittorrent()

            if client:
                logger.info("Connecting to qBittorrent to configure webhook...")

                script_path = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh"

                if configure_webhook_autorun(client, script_path):
                    logger.info("qBittorrent successfully auto-configured with new webhook key.")

                else:
                    logger.warning("Failed to configure qBittorrent webhook settings.")

            else:
                # This is common if qBittorrent credentials aren't set in env/settings yet

                logger.info("Skipping qBittorrent configuration (client not connected/configured).")

        except Exception as e:
            logger.warning("Error attempting to configure qBittorrent on startup: %s", e)


def _update_webhook_env_config() -> bool:
    """
    Updates the /opt/subro_web/.env file with path mapping and API URL.
    Returns True if updated successfully, False otherwise.
    """
    env_file_path = "/opt/subro_web/.env"
    try:
        import os
        from pathlib import Path

        env_path = Path(env_file_path)

        # Get the API base URL from env or use default
        api_base_url = f"http://localhost:{os.environ.get('APP_PORT', '8001')}/api/v1"

        # Read existing env or start fresh
        existing_content = ""
        if env_path.exists():
            existing_content = env_path.read_text()

        # Variables to update/add
        env_updates = {
            "SUBRO_API_BASE_URL": api_base_url,
            "PATH_MAP_SRC": "/root/Downloads",
            "PATH_MAP_DST": "/data/downloads",
        }

        # Parse existing and update
        lines = existing_content.strip().split("\n") if existing_content.strip() else []
        updated_keys = set()

        for i, line in enumerate(lines):
            for key, value in env_updates.items():
                if line.startswith(f"{key}="):
                    lines[i] = f'{key}="{value}"'
                    updated_keys.add(key)
                    break

        # Add missing keys
        for key, value in env_updates.items():
            if key not in updated_keys:
                lines.append(f'{key}="{value}"')

        # Write back
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(lines) + "\n")
        logger.info("Updated %s with webhook settings", env_file_path)
        return True

    except Exception as e:
        logger.warning("Failed to update %s: %s", env_file_path, e)
        return False
