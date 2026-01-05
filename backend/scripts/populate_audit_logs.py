#!/usr/bin/env python3
"""
Script to populate audit logs with test data.
Run: poetry run python scripts/populate_audit_logs.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import async_sessionmaker
from app.services import audit_service


async def populate_test_logs():
    """Create test audit log entries."""
    session = async_sessionmaker()
    async with session.begin() as db:
        print("Creating test audit log entries...")

        # Test 1: User login
        await audit_service.log_event(
            db,
            category="auth",
            action="auth.login",
            severity="info",
            success=True,
            details={
                "method": "password",
                "device_name": "Chrome on Linux",
                "trusted_device": True,
            },
        )
        print("✓ Created auth.login entry")

        # Test 2: Failed login
        await audit_service.log_event(
            db,
            category="auth",
            action="auth.login",
            severity="warning",
            success=False,
            details={
                "method": "password",
                "reason": "Invalid credentials",
                "attempts": 3,
            },
        )
        print("✓ Created failed auth.login entry")

        # Test 3: API key validation (like the system events)
        await audit_service.log_event(
            db,
            category="security",
            action="security.api_validation",
            severity="info",
            details={
                "tmdb_valid": True,
                "omdb_valid": True,
                "opensubtitles_valid": True,
                "google_cloud_valid": None,
                "validation_count": 3,
                "apis_validated": "TMDB, OMDB, OpenSubtitles",
            },
        )
        print("✓ Created security.api_validation entry")

        # Test 4: User action - settings update
        await audit_service.log_event(
            db,
            category="settings",
            action="settings.update",
            severity="info",
            details={
                "changed_fields": ["tmdb_api_key", "omdb_api_key"],
                "count": 2,
            },
        )
        print("✓ Created settings.update entry")

        # Test 5: Admin action
        await audit_service.log_event(
            db,
            category="admin",
            action="admin.user.create",
            severity="info",
            details={
                "email": "newuser@example.com",
                "role": "user",
            },
        )
        print("✓ Created admin.user.create entry")

        await db.commit()
        print("\n✅ Successfully created 5 test audit log entries!")
        print("Refresh the audit log page to see them.")


if __name__ == "__main__":
    asyncio.run(populate_test_logs())
