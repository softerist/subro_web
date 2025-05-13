# backend/app/schemas/auth.py
from pydantic import BaseModel


class Token(BaseModel):
    """
    Represents the token response provided to the client upon successful authentication.
    """

    access_token: str
    token_type: str = "bearer"  # Default to "bearer" as it's standard for JWTs

    # Optional: If you ever decide to return the refresh token in the body
    # (generally not recommended if using HttpOnly cookies for refresh tokens)
    # refresh_token: str | None = None


class TokenData(BaseModel):
    """
    Represents the data encoded within a JWT token (e.g., user identifier).
    This is more for internal use when decoding tokens, not typically for API responses.
    """

    username: str | None = None  # Or user_id, email, etc., depending on your token's 'sub' claim
    # You might add other fields here if your tokens contain more claims you need to parse
    # e.g., scopes: list[str] = []
