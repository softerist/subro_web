# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, validator
from typing import Optional

class Settings(BaseSettings):
    # Define where to load settings from (environment variables and .env file)
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # --- Core Application Settings ---
    APP_NAME: str = "Subtitle Downloader"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(False, validation_alias='DEBUG') # Use alias for compatibility

    # --- Database Settings ---
    # Use validation_alias to allow either DATABASE_URL or POSTGRES_URL
    DATABASE_URL: Optional[PostgresDsn] = Field(None, validation_alias='DATABASE_URL')
    POSTGRES_SERVER: Optional[str] = Field(None, validation_alias='POSTGRES_SERVER')
    POSTGRES_USER: Optional[str] = Field(None, validation_alias='POSTGRES_USER')
    POSTGRES_PASSWORD: Optional[str] = Field(None, validation_alias='POSTGRES_PASSWORD')
    POSTGRES_DB: Optional[str] = Field(None, validation_alias='POSTGRES_DB')
    POSTGRES_PORT: Optional[int] = Field(5432, validation_alias='POSTGRES_PORT')

    # --- Calculated Database URL ---
    # Combine individual DB parts if DATABASE_URL is not provided
    # Use property for calculated value
    @property
    def ASYNC_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            # Ensure the DSN uses the asyncpg driver
            return str(self.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://")

        if all([self.POSTGRES_SERVER, self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_DB]):
             return (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
                f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        raise ValueError("Database configuration is incomplete. Set DATABASE_URL or individual POSTGRES_* variables.")

    # --- JWT Settings (required by fastapi-users) ---
    # Generate a secret key using: openssl rand -hex 32
    SECRET_KEY: str = Field(..., validation_alias='JWT_SECRET_KEY') # Use alias
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- User Registration Settings ---
    OPEN_SIGNUP: bool = Field(True, validation_alias='OPEN_SIGNUP')

    # --- CORS Settings ---
    # Example: http://localhost:5173,https://yourdomain.com
    BACKEND_CORS_ORIGINS: list[str] = Field(default=[], validation_alias='BACKEND_CORS_ORIGINS')


# Create a single instance of the settings
settings = Settings()

# Example usage (optional, just for understanding):
# print(f"Database URI: {settings.ASYNC_DATABASE_URI}")
# print(f"Secret Key: {settings.SECRET_KEY}")
