# backend/app/core/custom_jwt_strategy.py
"""
Custom JWT strategy that adds auth_time claim for step-up authentication.
"""

from datetime import UTC, datetime

from fastapi_users import models
from fastapi_users.authentication.strategy import JWTStrategy
from fastapi_users.jwt import decode_jwt, generate_jwt


class AuthTimeJWTStrategy(JWTStrategy):
    """
    Extended JWT strategy that includes auth_time claim.

    The auth_time claim records when the user last performed interactive authentication
    (not token refresh). This enables step-up authentication for sensitive operations.
    """

    async def write_token(self, user: models.UP) -> str:
        """
        Generate JWT token with auth_time claim.

        Override to add auth_time to the token payload when user logs in interactively.
        """
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "auth_time": int(datetime.now(UTC).timestamp()),  # Record login time
        }

        # Add any custom user data
        if hasattr(user, "get_jwt_data"):
            data.update(user.get_jwt_data())

        return generate_jwt(data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm)

    async def refresh_token(self, token: str) -> str:
        """
        Refresh token while preserving auth_time.

        CRITICAL: This ensures token refresh does NOT update auth_time,
        preventing step-up auth bypass.
        """
        try:
            # Decode the old token to extract auth_time
            payload = decode_jwt(
                token, self.decode_key, self.token_audience, algorithms=[self.algorithm]
            )

            # Preserve the original auth_time
            original_auth_time = payload.get("auth_time")

            # Generate new token with same auth_time
            data = {
                "sub": payload["sub"],
                "aud": self.token_audience,
                "auth_time": original_auth_time,  # PRESERVE original login time
            }

            return generate_jwt(
                data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm
            )
        except Exception:
            # If refresh fails, require new login
            raise
