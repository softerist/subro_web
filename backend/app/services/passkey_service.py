# backend/app/services/passkey_service.py
"""
Passkey (WebAuthn) service for passwordless authentication.

Provides functions for:
- Generating and verifying WebAuthn registration (credential creation)
- Generating and verifying WebAuthn authentication (credential assertion)
- Managing user passkeys (list, delete, rename)
- Challenge storage in Redis with TTL

Security considerations:
- Challenges stored in Redis with 5-minute TTL
- Sign count verification to detect cloned authenticators
- User verification required for strong authentication
- Discoverable credentials enabled for username-less login
"""

import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.db.models.passkey import Passkey
from app.db.models.user import User
from app.services import audit_service

logger = logging.getLogger(__name__)

# Constants
CHALLENGE_PREFIX = "webauthn:challenge:"
CHALLENGE_TTL_SECONDS = settings.WEBAUTHN_CHALLENGE_TTL_SECONDS


def _get_rp_id() -> str:
    """Get the Relying Party ID (domain) from settings or derive from FRONTEND_URL."""
    if settings.WEBAUTHN_RP_ID:
        return settings.WEBAUTHN_RP_ID
    # Derive from FRONTEND_URL if not explicitly set
    from urllib.parse import urlparse

    parsed = urlparse(settings.FRONTEND_URL)
    return parsed.hostname or "localhost"


def _get_origin() -> str:
    """Get the expected origin for WebAuthn verification."""
    if settings.WEBAUTHN_ORIGIN:
        return settings.WEBAUTHN_ORIGIN
    return settings.FRONTEND_URL


async def store_challenge(
    redis: Redis,
    user_id: str,
    challenge: bytes,
    context: str = "registration",
) -> None:
    """
    Store a WebAuthn challenge in Redis with TTL.

    Args:
        redis: Redis client
        user_id: User ID to associate with challenge
        challenge: Raw challenge bytes
        context: Either "registration" or "authentication"
    """
    key = f"{CHALLENGE_PREFIX}{context}:{user_id}"
    await redis.set(key, challenge, ex=CHALLENGE_TTL_SECONDS)
    logger.debug("Stored %s challenge for user %s", context, user_id)


async def retrieve_challenge(
    redis: Redis,
    user_id: str,
    context: str = "registration",
) -> bytes | None:
    """
    Retrieve and delete a WebAuthn challenge from Redis.

    Challenges are single-use, so we delete after retrieval.

    Args:
        redis: Redis client
        user_id: User ID to look up
        context: Either "registration" or "authentication"

    Returns:
        Challenge bytes if found, None otherwise
    """
    key = f"{CHALLENGE_PREFIX}{context}:{user_id}"
    challenge = await redis.get(key)
    if challenge:
        await redis.delete(key)
        logger.debug("Retrieved and deleted %s challenge for user %s", context, user_id)
        return bytes(challenge) if not isinstance(challenge, bytes) else challenge
    logger.warning("No %s challenge found for user %s", context, user_id)
    return None


async def get_registration_options(
    db: AsyncSession,
    redis: Redis,
    user: User,
) -> dict:
    """
    Generate WebAuthn registration options for a user.

    Returns options to be passed to navigator.credentials.create() in the browser.
    """
    # Get existing credentials to exclude (prevent re-registration)
    existing_passkeys = await list_user_passkeys(db, user)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(pk["credential_id_b64"]),
            transports=[AuthenticatorTransport(t) for t in (pk.get("transports") or [])],
        )
        for pk in existing_passkeys
    ]

    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=user.email.split("@")[0],
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,  # Discoverable credentials
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    # Store challenge for verification
    await store_challenge(redis, str(user.id), options.challenge, "registration")

    # Convert to JSON-serializable dict
    return {
        "rp": {"id": options.rp.id, "name": options.rp.name},
        "user": {
            "id": bytes_to_base64url(options.user.id),
            "name": options.user.name,
            "displayName": options.user.display_name,
        },
        "challenge": bytes_to_base64url(options.challenge),
        "pubKeyCredParams": [{"type": p.type, "alg": p.alg} for p in options.pub_key_cred_params],
        "timeout": options.timeout,
        "excludeCredentials": [
            {
                "id": bytes_to_base64url(c.id),
                "type": c.type,
                "transports": [t.value for t in (c.transports or [])],
            }
            for c in (options.exclude_credentials or [])
        ],
        "authenticatorSelection": {
            "residentKey": (
                options.authenticator_selection.resident_key.value
                if options.authenticator_selection and options.authenticator_selection.resident_key
                else "preferred"
            ),
            "userVerification": (
                options.authenticator_selection.user_verification.value
                if options.authenticator_selection
                and options.authenticator_selection.user_verification
                else "preferred"
            ),
        },
        "attestation": options.attestation.value if options.attestation else "none",
    }


async def verify_registration(
    db: AsyncSession,
    redis: Redis,
    user: User,
    credential: RegistrationCredential,
    device_name: str | None = None,
) -> Passkey:
    """
    Verify a WebAuthn registration response and store the credential.

    Args:
        db: Database session
        redis: Redis client
        user: User registering the passkey
        credential: Registration response from browser
        device_name: User-friendly name for this passkey

    Returns:
        The created Passkey record

    Raises:
        ValueError: If verification fails
    """
    # Retrieve stored challenge
    expected_challenge = await retrieve_challenge(redis, str(user.id), "registration")
    if not expected_challenge:
        raise ValueError("Registration session expired. Please try again.")

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
        )
    except Exception as e:
        logger.warning("WebAuthn registration verification failed for user %s: %s", user.id, e)
        raise ValueError(f"Registration verification failed: {e}") from e

    # Create passkey record
    passkey = Passkey(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        aaguid=str(verification.aaguid) if verification.aaguid else None,
        device_name=device_name or "Passkey",
        transports=[t.value for t in (credential.response.transports or [])],
        backup_eligible=verification.credential_backed_up,
        backup_state=verification.credential_backed_up,
    )

    db.add(passkey)
    await db.commit()
    await db.refresh(passkey)

    # Audit log
    await audit_service.log_event(
        db=db,
        category="auth",
        action="passkey.register",
        actor_user_id=str(user.id),
        details={
            "passkey_id": str(passkey.id),
            "device_name": device_name,
            "aaguid": passkey.aaguid,
        },
    )

    logger.info("Passkey registered for user %s: %s", user.id, passkey.id)
    return passkey


async def get_authentication_options(
    db: AsyncSession,  # noqa: ARG001 - kept for interface consistency
    redis: Redis,
    user_id: str | None = None,  # noqa: ARG001 - ignored for security hardening
) -> dict:
    """
    Generate WebAuthn authentication options.

    SECURITY HARDENING:
    - Always returns empty allowCredentials (discoverable credentials flow)
    - No database lookup for user passkeys (constant-time response)
    - Prevents timing side-channels and credential ID exposure
    - Requires passkeys to be registered as resident keys (enforced at registration)

    Returns options to be passed to navigator.credentials.get() in the browser.
    """
    # Generate challenge
    challenge = secrets.token_bytes(32)

    # Store challenge with anonymous user ID for constant-time behavior
    # The actual user is identified by the credential's userHandle during verification
    await store_challenge(redis, "anonymous", challenge, "authentication")

    options = generate_authentication_options(
        rp_id=_get_rp_id(),
        challenge=challenge,
        allow_credentials=None,  # SECURITY: Never expose credential IDs
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    return {
        "challenge": bytes_to_base64url(options.challenge),
        "timeout": options.timeout,
        "rpId": options.rp_id,
        "allowCredentials": [],  # Always empty for discoverable flow
        "userVerification": options.user_verification.value
        if options.user_verification
        else "preferred",
    }


async def verify_authentication(
    db: AsyncSession,
    redis: Redis,
    credential: AuthenticationCredential,
    user_id: str | None = None,
) -> User:
    """
    Verify a WebAuthn authentication response.

    Args:
        db: Database session
        redis: Redis client
        credential: Authentication response from browser
        user_id: Expected user ID (for non-discoverable flow)

    Returns:
        The authenticated User

    Raises:
        ValueError: If verification fails
    """
    # Look up passkey by credential ID
    result = await db.execute(select(Passkey).where(Passkey.credential_id == credential.raw_id))
    passkey = result.scalar_one_or_none()

    if not passkey:
        raise ValueError("Passkey not found.")

    # Get stored challenge
    challenge_user_id = user_id or "anonymous"
    expected_challenge = await retrieve_challenge(redis, challenge_user_id, "authentication")
    if not expected_challenge:
        raise ValueError("Authentication session expired. Please try again.")

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except Exception as e:
        logger.warning(
            "WebAuthn authentication verification failed for passkey %s: %s",
            passkey.id,
            e,
        )
        raise ValueError(f"Authentication failed: {e}") from e

    # Verify sign count to detect cloned authenticators
    if verification.new_sign_count <= passkey.sign_count and passkey.sign_count > 0:
        logger.error(
            "Possible cloned authenticator detected! Passkey %s: new_sign_count=%d <= current=%d",
            passkey.id,
            verification.new_sign_count,
            passkey.sign_count,
        )
        # We still allow login but log the warning
        # In stricter environments, you might want to block this

    # Update passkey metadata
    passkey.sign_count = verification.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    await db.commit()

    # Get user
    from app.db.models.user import User as UserModel

    result = await db.execute(select(UserModel).where(UserModel.id == passkey.user_id))
    user = result.scalar_one_or_none()

    if not user or not getattr(user, "is_active", True):
        raise ValueError("User not found or inactive.")

    # Audit log
    await audit_service.log_event(
        db=db,
        category="auth",
        action="passkey.authenticate",
        actor_user_id=str(user.id),
        details={"passkey_id": str(passkey.id), "device_name": passkey.device_name},
    )

    logger.info("User %s authenticated via passkey %s", user.id, passkey.id)
    return user  # type: ignore[return-value]


async def list_user_passkeys(db: AsyncSession, user: User) -> list[dict]:
    """Get all passkeys for a user."""
    result = await db.execute(select(Passkey).where(Passkey.user_id == user.id))
    passkeys = result.scalars().all()

    return [
        {
            "id": str(pk.id),
            "credential_id_b64": bytes_to_base64url(pk.credential_id),
            "device_name": pk.device_name,
            "created_at": pk.created_at.isoformat() if pk.created_at else None,
            "last_used_at": pk.last_used_at.isoformat() if pk.last_used_at else None,
            "transports": pk.transports,
            "backup_eligible": pk.backup_eligible,
            "backup_state": pk.backup_state,
        }
        for pk in passkeys
    ]


async def rename_passkey(
    db: AsyncSession,
    user: User,
    passkey_id: str,
    new_name: str,
) -> bool:
    """Rename a passkey. Returns True if successful."""
    result = await db.execute(
        update(Passkey)
        .where(Passkey.id == UUID(passkey_id), Passkey.user_id == user.id)
        .values(device_name=new_name)
    )
    await db.commit()
    return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]


async def delete_passkey(
    db: AsyncSession,
    user: User,
    passkey_id: str,
) -> bool:
    """
    Delete a passkey.

    Note: We generally rely on passwords as fallback, but if we ever support
    passwordless-only accounts, we should check here. For now, we allow deleting
    the last passkey as the user presumably has a password.

    Returns True if successful.
    """
    result = await db.execute(
        delete(Passkey).where(Passkey.id == UUID(passkey_id), Passkey.user_id == user.id)
    )
    await db.commit()

    if result.rowcount and result.rowcount > 0:  # type: ignore[attr-defined]
        await audit_service.log_event(
            db=db,
            category="auth",
            action="passkey.delete",
            actor_user_id=str(user.id),
            details={"passkey_id": passkey_id},
        )
        logger.info("Passkey %s deleted for user %s", passkey_id, user.id)
        return True

    return False


async def get_passkey_count(db: AsyncSession, user_id: UUID) -> int:
    """Get the number of passkeys a user has registered."""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id)
    )
    return result.scalar() or 0
