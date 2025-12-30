# backend/tests/auth/test_token_secrets.py
from app.core.config import settings
from app.core.security import UserManager


def test_token_secrets_fallback_to_secret_key():
    expected_reset = str(settings.RESET_PASSWORD_TOKEN_SECRET or settings.SECRET_KEY)
    expected_verify = str(settings.VERIFICATION_TOKEN_SECRET or settings.SECRET_KEY)
    assert UserManager.reset_password_token_secret == expected_reset
    assert UserManager.verification_token_secret == expected_verify
