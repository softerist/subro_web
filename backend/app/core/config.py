import json
import logging
from typing import Literal

from pydantic import (
    EmailStr,
    Field,
    PostgresDsn,
    RedisDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Environment & Debug ---
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )
    DEBUG: bool = Field(default=False, validation_alias="DEBUG_MODE")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Server Configuration ---
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    USE_HTTPS: bool = Field(
        default=False, validation_alias="USE_HTTPS_IN_CADDYFILE_SNIPPETS"
    )  # Or just USE_HTTPS if it's purely app logic

    # --- Core Application Settings ---
    APP_NAME: str = "Subtitle Downloader"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "API for managing subtitle download jobs and user authentication."
    API_V1_STR: str = "/api/v1"

    # --- JWT & Authentication Settings ---
    SECRET_KEY: str = Field(validation_alias="JWT_SECRET_KEY")
    JWT_REFRESH_SECRET_KEY: str = Field(validation_alias="JWT_REFRESH_SECRET_KEY")  # Added alias
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_COOKIE_NAME: str = "subRefreshToken"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    OPEN_SIGNUP: bool = Field(default=True, validation_alias="OPEN_SIGNUP")

    # --- Initial Superuser Settings ---
    FIRST_SUPERUSER_EMAIL: EmailStr = Field(validation_alias="FIRST_SUPERUSER_EMAIL")
    FIRST_SUPERUSER_PASSWORD: str = Field(validation_alias="FIRST_SUPERUSER_PASSWORD")

    # --- Database Settings ---
    DATABASE_URL_ENV: PostgresDsn | None = Field(default=None, validation_alias="DATABASE_URL")
    POSTGRES_SERVER: str = "db"
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "Pa44w0rd"
    POSTGRES_DB: str = "subappdb"
    POSTGRES_PORT: int = 5432
    DB_ECHO: bool = False

    # --- Celery & Redis Settings ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CELERY_BROKER_URL_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_RESULT_BACKEND"
    )
    REDIS_PUBSUB_URL_ENV: RedisDsn | None = Field(default=None, validation_alias="REDIS_PUBSUB_URL")
    CELERY_SUBTITLE_TASK_NAME: str = Field(  # <<<< ADDED THIS
        default="app.tasks.subtitle_jobs.execute_subtitle_downloader_task",  # Default value matches plan
        validation_alias="CELERY_SUBTITLE_TASK_NAME",
    )

    # --- Job Runner Settings ---
    DOWNLOAD_SCRIPT_PATH: str = "/app/scripts/sub_downloader.py"  # placeholder for now
    JOB_TIMEOUT_SEC: int = 900
    JOB_MAX_RETRIES: int = 2
    DEFAULT_PAGINATION_LIMIT_MAX: int = 200

    # --- Fields for complex parsing ---
    allowed_media_folders_env_str: str = Field(
        default='["/mnt/sata0/Media","/mnt/sata1/Media"]',  # Default example, often overridden
        validation_alias="ALLOWED_MEDIA_FOLDERS",
    )
    backend_cors_origins_env_str: str | None = Field(
        default='["http://localhost:5173","http://localhost:8000","https://localhost"]',
        validation_alias="BACKEND_CORS_ORIGINS",
    )

    # --- Private storage for parsed values ---
    _parsed_allowed_media_folders: list[str] = []
    _parsed_backend_cors_origins: list[str] = []

    def _parse_string_list_input_helper(
        self, input_str: str | None, field_name_for_log: str
    ) -> list[str]:
        # ... (your existing helper implementation is good) ...
        parsed_list: list[str] = []
        if not input_str or not input_str.strip():
            return parsed_list
        try:
            loaded_items = json.loads(input_str)
            if isinstance(loaded_items, list):
                parsed_list = [str(item).strip() for item in loaded_items if str(item).strip()]
            elif isinstance(loaded_items, str) and loaded_items.strip():
                parsed_list = [item.strip() for item in loaded_items.split(",") if item.strip()]
            else:
                logger.debug(
                    f"Input for {field_name_for_log} was valid JSON but not list/string. Trying comma separation."
                )
                parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]
        except json.JSONDecodeError:
            logger.debug(
                f"JSONDecodeError for {field_name_for_log}. Falling back to comma separation for: {input_str}"
            )
            parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]

        if not parsed_list and input_str and input_str.strip():
            logger.warning(
                f"Env var {field_name_for_log} (value: '{input_str}') resulted in an empty parsed list."
            )
        return parsed_list

    @model_validator(mode="after")
    def _process_complex_fields_and_debug_overrides(self) -> "Settings":
        self._parsed_allowed_media_folders = self._parse_string_list_input_helper(
            self.allowed_media_folders_env_str, "ALLOWED_MEDIA_FOLDERS"
        )
        self._parsed_backend_cors_origins = self._parse_string_list_input_helper(
            self.backend_cors_origins_env_str, "BACKEND_CORS_ORIGINS"
        )

        if self.DEBUG:
            if self.LOG_LEVEL != "DEBUG":
                logger.info("DEBUG mode is ON. Overriding LOG_LEVEL to DEBUG.")
                self.LOG_LEVEL = "DEBUG"
            if not self.DB_ECHO:
                logger.info("DEBUG mode is ON. Overriding DB_ECHO to True.")
                self.DB_ECHO = True
            if self.COOKIE_SECURE:  # Only make insecure if DEBUG is on
                logger.info("DEBUG mode is ON. Overriding COOKIE_SECURE to False.")
                self.COOKIE_SECURE = False
        elif self.ENVIRONMENT != "development" and not self.COOKIE_SECURE:
            # Ensure cookies are secure in staging/production if not explicitly overridden by USE_HTTPS=false
            # This is a bit more complex if USE_HTTPS is meant to control Caddy side.
            # For app-set cookies, COOKIE_SECURE should ideally be True for non-dev unless USE_HTTPS is False.
            if self.USE_HTTPS:  # If we expect HTTPS, cookies should be secure
                self.COOKIE_SECURE = True
            else:  # If USE_HTTPS is false even in prod (e.g. behind another trusted proxy), then they can be insecure
                logger.warning(
                    "Non-development environment with USE_HTTPS=False, COOKIE_SECURE remains False."
                )

        return self

    # --- Convenience Properties for public access to parsed fields ---
    @property
    def ALLOWED_MEDIA_FOLDERS(self) -> list[str]:
        return self._parsed_allowed_media_folders

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._parsed_backend_cors_origins

    # --- Computed DSN Properties ---
    @computed_field(repr=False)  # Hide from default repr to avoid showing password
    @property
    def ASYNC_DATABASE_URI(self) -> PostgresDsn:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if not db_url_str.startswith("postgresql+asyncpg://"):
                db_url_str = db_url_str.replace("postgresql://", "postgresql+asyncpg://", 1)
            return PostgresDsn(db_url_str)
        return PostgresDsn(
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field(repr=False)  # Hide from default repr
    @property
    def SYNC_DATABASE_URI(self) -> PostgresDsn | None:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if db_url_str.startswith("postgresql+asyncpg://"):
                db_url_str = db_url_str.replace("postgresql+asyncpg://", "postgresql://", 1)
            try:
                return PostgresDsn(db_url_str)
            except Exception as e:
                logger.error(f"Failed to parse DATABASE_URL_ENV for SYNC_DATABASE_URI: {e}")
                return None
        if all(
            [self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_SERVER, self.POSTGRES_DB]
        ):
            try:
                return PostgresDsn(
                    f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
                )
            except Exception as e:
                logger.error(f"Failed to build SYNC_DATABASE_URI from components: {e}")
                return None
        logger.error(
            "SYNC_DATABASE_URI could not be determined from components or DATABASE_URL_ENV."
        )
        return None

    @property
    def CELERY_BROKER_URL(self) -> RedisDsn | None:
        if self.CELERY_BROKER_URL_ENV:
            return self.CELERY_BROKER_URL_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn(f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0")
            except Exception as e:
                logger.error(f"Failed to build CELERY_BROKER_URL: {e}")
                return None
        return None

    @property
    def CELERY_RESULT_BACKEND(self) -> RedisDsn | None:
        if self.CELERY_RESULT_BACKEND_ENV:
            return self.CELERY_RESULT_BACKEND_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn(f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1")
            except Exception as e:
                logger.error(f"Failed to build CELERY_RESULT_BACKEND: {e}")
                return None
        return None

    @property
    def REDIS_PUBSUB_URL(self) -> RedisDsn | None:
        if self.REDIS_PUBSUB_URL_ENV:
            return self.REDIS_PUBSUB_URL_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn(f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/2")
            except Exception as e:
                logger.error(f"Failed to build REDIS_PUBSUB_URL: {e}")
                return None
        return None


settings = Settings()

# --- Debug prints for verification when running file directly ---
if __name__ == "__main__":
    print("--- Loaded Settings (Debug from config.py) ---")
    print(f"APP_NAME: {settings.APP_NAME}")
    print(f"ENVIRONMENT: {settings.ENVIRONMENT}")
    print(f"DEBUG: {settings.DEBUG}")
    print(f"DB_ECHO: {settings.DB_ECHO}")  # Reflects override if DEBUG is true
    print(f"LOG_LEVEL: {settings.LOG_LEVEL}")  # Reflects override if DEBUG is true
    print(f"COOKIE_SECURE: {settings.COOKIE_SECURE}")  # Reflects override if DEBUG is true
    print(f"USE_HTTPS: {settings.USE_HTTPS}")

    print("\n--- Database ---")
    print(f"DATABASE_URL_ENV (raw from .env): {settings.DATABASE_URL_ENV}")
    print(f"ASYNC_DATABASE_URI (for app): {settings.ASYNC_DATABASE_URI}")
    print(f"SYNC_DATABASE_URI (for Alembic/sync): {settings.SYNC_DATABASE_URI}")

    print("\n--- Celery & Redis ---")
    print(f"CELERY_BROKER_URL (for Celery app): {settings.CELERY_BROKER_URL}")
    print(f"CELERY_RESULT_BACKEND (for Celery app): {settings.CELERY_RESULT_BACKEND}")
    print(f"REDIS_PUBSUB_URL (for WebSockets): {settings.REDIS_PUBSUB_URL}")
    print(
        f"CELERY_SUBTITLE_TASK_NAME: {settings.CELERY_SUBTITLE_TASK_NAME}"
    )  # Verify this new setting

    print("\n--- Paths & Lists ---")
    print(f"DOWNLOAD_SCRIPT_PATH: {settings.DOWNLOAD_SCRIPT_PATH}")
    print(
        f"allowed_media_folders_env_str (raw from .env): {settings.allowed_media_folders_env_str}"
    )
    print(f"ALLOWED_MEDIA_FOLDERS (parsed property): {settings.ALLOWED_MEDIA_FOLDERS}")
    print(f"backend_cors_origins_env_str (raw from .env): {settings.backend_cors_origins_env_str}")
    print(f"BACKEND_CORS_ORIGINS (parsed property): {settings.BACKEND_CORS_ORIGINS}")

    print("\n--- Auth & Secrets (values masked) ---")
    print(f"API_V1_STR: {settings.API_V1_STR}")
    print(f"SECRET_KEY: {'*' * len(settings.SECRET_KEY) if settings.SECRET_KEY else 'Not Set'}")
    print(
        f"JWT_REFRESH_SECRET_KEY: {'*' * len(settings.JWT_REFRESH_SECRET_KEY) if settings.JWT_REFRESH_SECRET_KEY else 'Not Set'}"
    )
    print(f"FIRST_SUPERUSER_EMAIL: {settings.FIRST_SUPERUSER_EMAIL}")
    print(
        f"FIRST_SUPERUSER_PASSWORD: {'*' * len(settings.FIRST_SUPERUSER_PASSWORD) if settings.FIRST_SUPERUSER_PASSWORD else 'Not Set'}"
    )
    print(f"OPEN_SIGNUP: {settings.OPEN_SIGNUP}")
