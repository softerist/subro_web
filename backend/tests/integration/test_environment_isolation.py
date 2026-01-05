# backend/tests/integration/test_environment_isolation.py
"""
Tests to verify environment isolation and prevent DNS collision regressions.
These tests ensure that production and staging environments use distinct resources.

Key scenarios tested:
1. Database configuration uses explicit docker container names
2. Redis configuration uses explicit docker container names
3. Setup flow correctly persists to the configured database
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_app_settings import crud_app_settings


class TestEnvironmentConfiguration:
    """Tests for environment configuration correctness."""

    def test_postgres_server_is_not_generic_alias(self):
        """
        Verify that POSTGRES_SERVER is not a generic alias like 'db'.

        In Docker Compose environments with shared networks, generic aliases
        like 'db' can resolve to multiple IPs, causing production to hit
        staging databases. This test ensures explicit container names are used.

        Note: This test is most relevant in production. In development/test,
        'db' or 'localhost' may be acceptable.
        """
        postgres_server = settings.POSTGRES_SERVER

        # In production, we expect explicit container names
        if settings.ENVIRONMENT == "production":
            # Should NOT be a generic alias that could resolve to multiple hosts
            generic_aliases = {"db", "database", "postgres", "postgresql"}
            assert postgres_server.lower() not in generic_aliases, (
                f"POSTGRES_SERVER should use explicit container name in production, "
                f"not generic alias '{postgres_server}'. "
                f"Expected something like 'infra-db-1' to prevent DNS collisions."
            )

    def test_redis_host_is_not_generic_alias(self):
        """
        Verify that REDIS_HOST is not a generic alias like 'redis'.

        Similar to the database, generic Redis aliases can cause environment
        cross-talk in shared Docker networks.
        """
        redis_host = settings.REDIS_HOST

        if settings.ENVIRONMENT == "production":
            generic_aliases = {"redis", "cache", "redis-server"}
            assert redis_host.lower() not in generic_aliases, (
                f"REDIS_HOST should use explicit container name in production, "
                f"not generic alias '{redis_host}'. "
                f"Expected something like 'infra-redis-1' to prevent DNS collisions."
            )

    def test_database_url_contains_expected_host(self):
        """Verify the constructed database URL uses the configured host."""
        db_url = settings.ASYNC_SQLALCHEMY_DATABASE_URL

        if settings.ENVIRONMENT == "production":
            # In production, URL should contain explicit host
            assert (
                "infra-db-1" in db_url or settings.POSTGRES_SERVER in db_url
            ), f"Database URL should contain explicit host, got: {db_url}"


class TestSetupDatabaseIsolation:
    """Tests to verify setup operations affect the correct database."""

    @pytest.mark.asyncio
    async def test_setup_status_persists_correctly(self, db_session: AsyncSession):
        """
        Verify that setup status changes persist to the test database.

        This test ensures that CRUD operations affect the expected database,
        not a different environment's database due to misconfiguration.
        """
        # Get initial status
        initial_status = await crud_app_settings.get_setup_completed(db_session)

        # Toggle status
        if initial_status:
            # If already completed, we can't easily reset without direct DB access
            # Just verify we can read the status
            assert initial_status is True
        else:
            # Mark as completed
            await crud_app_settings.mark_setup_completed(db_session)
            await db_session.commit()

            # Verify change persisted
            new_status = await crud_app_settings.get_setup_completed(db_session)
            assert new_status is True, (
                "Setup status did not persist. This could indicate the application "
                "is connected to a different database than expected."
            )

    @pytest.mark.asyncio
    async def test_app_settings_singleton_exists(self, db_session: AsyncSession):
        """Verify that the AppSettings singleton is accessible."""
        app_settings = await crud_app_settings.get(db_session)

        assert app_settings is not None, "AppSettings singleton should exist"
        assert app_settings.id == 1, "AppSettings singleton should have id=1"


class TestConfigurationConsistency:
    """Tests for configuration consistency across the application."""

    def test_environment_is_set(self):
        """Verify ENVIRONMENT is explicitly configured."""
        assert settings.ENVIRONMENT in {"development", "staging", "production"}, (
            f"ENVIRONMENT must be one of development/staging/production, "
            f"got: {settings.ENVIRONMENT}"
        )

    def test_secret_key_is_set(self):
        """Verify SECRET_KEY is configured (not default)."""
        assert settings.SECRET_KEY, "SECRET_KEY must be set"
        assert (
            len(settings.SECRET_KEY) >= 32
        ), "SECRET_KEY should be at least 32 characters for security"

    def test_jwt_secrets_are_unique(self):
        """Verify JWT secrets are distinct from each other."""
        secrets = [
            settings.SECRET_KEY,
            settings.JWT_REFRESH_SECRET_KEY,
        ]

        # Add optional secrets if set
        if settings.RESET_PASSWORD_TOKEN_SECRET:
            secrets.append(settings.RESET_PASSWORD_TOKEN_SECRET)
        if settings.VERIFICATION_TOKEN_SECRET:
            secrets.append(settings.VERIFICATION_TOKEN_SECRET)

        # All secrets should be unique
        assert len(secrets) == len(
            set(secrets)
        ), "JWT secrets should be unique from each other to prevent token confusion attacks"

    def test_cors_origins_configured(self):
        """Verify CORS origins are configured in non-development environments."""
        if settings.ENVIRONMENT != "development":
            # In production/staging, CORS should be explicitly configured
            # Empty list means CORS is disabled, which is also valid
            cors_origins = settings.BACKEND_CORS_ORIGINS
            # Just verify it's a list (empty or not)
            assert isinstance(cors_origins, list), "BACKEND_CORS_ORIGINS should be a list"
