import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import (
    AliasChoices,
    EmailStr,
    Field,
    PostgresDsn,
    RedisDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _default_app_state_dir() -> str:
    xdg_state_home = os.getenv("XDG_STATE_HOME")
    if xdg_state_home:
        base_dir = Path(xdg_state_home)
    else:
        home_dir = os.getenv("HOME")
        if home_dir:
            base_dir = Path(home_dir) / ".local" / "state"
        else:
            base_dir = Path(tempfile.gettempdir())
    return str(base_dir / "subro-web")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Environment & Debug ---
    ENVIRONMENT: Literal["development", "staging", "test", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )
    DEBUG: bool = Field(default=False, validation_alias=AliasChoices("DEBUG_MODE", "DEBUG"))
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )

    # --- Server Configuration ---
    SERVER_HOST: str = Field(default="0.0.0.0", validation_alias="SERVER_HOST")  # nosec B104 - intentional for Docker
    SERVER_PORT: int = Field(default=8000, validation_alias="SERVER_PORT")
    ROOT_PATH: str = Field(
        default="", description="Root path for the application if served under a subpath."
    )
    USE_HTTPS: bool = Field(default=False, validation_alias="USE_HTTPS_IN_CADDYFILE_SNIPPETS")
    FRONTEND_URL: str = Field(
        default="https://localhost:8443",
        description="Frontend URL for email links (password reset, etc.)",
        validation_alias="FRONTEND_URL",
    )

    # --- Core Application Settings ---
    APP_NAME: str = Field(default="Subtitle Downloader", validation_alias="APP_NAME")
    APP_VERSION: str = Field(default="1.0.0", validation_alias="APP_VERSION")
    APP_DESCRIPTION: str = Field(
        default="API for managing subtitle download jobs and user authentication.",
        validation_alias="APP_DESCRIPTION",
    )

    # --- Runtime State Paths ---
    APP_STATE_DIR: str = Field(
        default_factory=_default_app_state_dir, validation_alias="APP_STATE_DIR"
    )
    API_V1_STR: str = Field(default="/api/v1", validation_alias="API_V1_STR")
    OPENAPI_URL: str | None = Field(default=None, validation_alias="OPENAPI_URL")
    DOCS_URL: str | None = Field(default=None, validation_alias="DOCS_URL")
    REDOC_URL: str | None = Field(default=None, validation_alias="REDOC_URL")
    HEALTHZ_URL: str | None = Field(default=None, validation_alias="HEALTHZ_URL")

    # --- JWT & Authentication Settings ---
    SECRET_KEY: str = Field(
        default="CHANGEME_SECRET_KEY",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "SECRET_KEY"),
    )
    JWT_REFRESH_SECRET_KEY: str = Field(
        default="CHANGEME_REFRESH_SECRET_KEY", validation_alias="JWT_REFRESH_SECRET_KEY"
    )
    API_KEY_PEPPER: str | None = Field(default=None, validation_alias="API_KEY_PEPPER")
    ALGORITHM: str = Field(default="HS256", validation_alias="ALGORITHM")
    DATA_ENCRYPTION_KEYS_ENV_STR: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATA_ENCRYPTION_KEYS", "DATA_ENCRYPTION_KEY"),
    )
    RESET_PASSWORD_TOKEN_SECRET: str | None = Field(
        default=None, validation_alias="RESET_PASSWORD_TOKEN_SECRET"
    )
    VERIFICATION_TOKEN_SECRET: str | None = Field(
        default=None, validation_alias="VERIFICATION_TOKEN_SECRET"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, validation_alias="REFRESH_TOKEN_EXPIRE_DAYS")
    REFRESH_TOKEN_COOKIE_NAME: str = Field(
        default="subRefreshToken", validation_alias="REFRESH_TOKEN_COOKIE_NAME"
    )
    COOKIE_SECURE: bool = Field(default=True, validation_alias="COOKIE_SECURE")
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="strict", validation_alias="COOKIE_SAMESITE"
    )
    OPEN_SIGNUP: bool = Field(default=False, validation_alias="OPEN_SIGNUP")

    # --- Account Lockout Settings ---
    LOGIN_MAX_ATTEMPTS: int = Field(
        default=5,
        description="Max failed login attempts before lockout",
        validation_alias="LOGIN_MAX_ATTEMPTS",
    )
    LOGIN_LOCKOUT_MINUTES: int = Field(
        default=15,
        description="Lockout duration in minutes after max failed attempts",
        validation_alias="LOGIN_LOCKOUT_MINUTES",
    )
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = Field(
        default=30,
        description="Time window (minutes) to count failed attempts",
        validation_alias="LOGIN_ATTEMPT_WINDOW_MINUTES",
    )

    # --- Mailgun Email Settings ---
    MAILGUN_API_KEY: str | None = Field(default=None, validation_alias="MAILGUN_API_KEY")
    MAILGUN_DOMAIN: str | None = Field(default=None, validation_alias="MAILGUN_DOMAIN")
    MAILGUN_FROM_EMAIL: str | None = Field(default=None, validation_alias="MAILGUN_FROM_EMAIL")
    MAILGUN_FROM_NAME: str = Field(default="Subro Web", validation_alias="MAILGUN_FROM_NAME")

    # --- Initial Superuser Settings ---
    FIRST_SUPERUSER_EMAIL: EmailStr | None = Field(
        default=None, validation_alias="FIRST_SUPERUSER_EMAIL"
    )
    FIRST_SUPERUSER_PASSWORD: str | None = Field(
        default=None, validation_alias="FIRST_SUPERUSER_PASSWORD"
    )
    ONBOARDING_TOKEN: str | None = Field(default=None, validation_alias="ONBOARDING_TOKEN")
    FORCE_INITIAL_SETUP: bool = Field(
        default=False,
        description="When true, the setup wizard is required regardless of setup_completed status.",
        validation_alias="FORCE_INITIAL_SETUP",
    )

    # --- External API Keys (optional, can be overridden via Settings UI) ---
    TMDB_API_KEY: str | None = Field(default=None, validation_alias="TMDB_API_KEY")
    OMDB_API_KEY: str | None = Field(default=None, validation_alias="OMDB_API_KEY")
    OPENSUBTITLES_API_KEY: str | None = Field(
        default=None, validation_alias="OPENSUBTITLES_API_KEY"
    )
    OPENSUBTITLES_USERNAME: str | None = Field(
        default=None, validation_alias="OPENSUBTITLES_USERNAME"
    )
    OPENSUBTITLES_PASSWORD: str | None = Field(
        default=None, validation_alias="OPENSUBTITLES_PASSWORD"
    )
    # --- qBittorrent Settings (optional, for torrent monitoring) ---
    QBITTORRENT_HOST: str | None = Field(default=None, validation_alias="QBITTORRENT_HOST")
    QBITTORRENT_PORT: int | None = Field(default=None, validation_alias="QBITTORRENT_PORT")
    QBITTORRENT_USERNAME: str | None = Field(default=None, validation_alias="QBITTORRENT_USERNAME")
    QBITTORRENT_PASSWORD: str | None = Field(default=None, validation_alias="QBITTORRENT_PASSWORD")

    # --- Database Settings ---
    PRIMARY_DATABASE_URL_ENV: PostgresDsn | None = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV: PostgresDsn | None = Field(
        default=None, validation_alias="ASYNC_SQLALCHEMY_DATABASE_URL_WORKER"
    )
    POSTGRES_SERVER: str = Field(
        default="db", validation_alias=AliasChoices("POSTGRES_SERVER", "DB_TEST_SERVER")
    )
    POSTGRES_USER: str = Field(
        default="admin", validation_alias=AliasChoices("POSTGRES_USER", "DB_TEST_USER")
    )
    POSTGRES_PASSWORD: str = Field(
        validation_alias=AliasChoices("POSTGRES_PASSWORD", "DB_TEST_PASSWORD")
    )
    POSTGRES_DB: str = Field(
        default="subappdb", validation_alias=AliasChoices("POSTGRES_DB", "DB_TEST_DB")
    )
    POSTGRES_PORT: int = Field(
        default=5432, validation_alias=AliasChoices("POSTGRES_PORT", "DB_TEST_PORT")
    )
    DB_ECHO: bool = Field(default=False, validation_alias="DB_ECHO")
    DB_ECHO_WORKER: bool = Field(default=False, validation_alias="DB_ECHO_WORKER")

    # --- Celery & Redis Settings ---
    REDIS_HOST: str = Field(default="redis", validation_alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, validation_alias="REDIS_PORT")
    CELERY_BROKER_URL_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_RESULT_BACKEND"
    )
    CELERY_BEAT_SCHEDULE_FILENAME_ENV: str | None = Field(
        default=None, validation_alias="CELERY_BEAT_SCHEDULE_FILENAME"
    )
    REDIS_PUBSUB_URL_ENV: RedisDsn | None = Field(default=None, validation_alias="REDIS_PUBSUB_URL")
    CELERY_SUBTITLE_TASK_NAME: str = Field(
        default="app.tasks.subtitle_jobs.execute_subtitle_downloader_task",
        validation_alias="CELERY_SUBTITLE_TASK_NAME",
    )
    TIMEZONE: str = Field(default="UTC", validation_alias="CELERY_TIMEZONE")
    CELERY_ACKS_LATE: bool = Field(default=True, validation_alias="CELERY_ACKS_LATE")
    CELERY_RESULT_EXPIRES: int = Field(default=3600, validation_alias="CELERY_RESULT_EXPIRES")
    CELERY_TASK_CREATE_MISSING_QUEUES: bool = Field(
        default=True, validation_alias="CELERY_TASK_CREATE_MISSING_QUEUES"
    )
    CELERY_TASK_CREATE_MISSING_QUEUE_TYPE: bool = Field(
        default=True, validation_alias="CELERY_TASK_CREATE_MISSING_QUEUE_TYPE"
    )
    CELERY_TASK_CREATE_MISSING_QUEUE_EXCHANGE_TYPE: bool = Field(
        default=True, validation_alias="CELERY_TASK_CREATE_MISSING_QUEUE_EXCHANGE_TYPE"
    )
    CELERY_ENABLE_UTC: bool = Field(default=True, validation_alias="CELERY_ENABLE_UTC")
    CELERY_TASK_SERIALIZER: str = Field(default="json", validation_alias="CELERY_TASK_SERIALIZER")
    CELERY_ACCEPT_CONTENT: list[str] = Field(
        default=["json"], validation_alias="CELERY_ACCEPT_CONTENT"
    )
    CELERY_RESULT_SERIALIZER: str = Field(
        default="json", validation_alias="CELERY_RESULT_SERIALIZER"
    )
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: bool = Field(
        default=True, validation_alias="CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP"
    )
    CELERY_TASK_TRACK_STARTED: bool = Field(
        default=True, validation_alias="CELERY_TASK_TRACK_STARTED"
    )

    # --- Job Runner Settings ---
    PYTHON_EXECUTABLE_PATH: str = Field(
        default=sys.executable, validation_alias="PYTHON_EXECUTABLE_PATH"
    )
    SUBTITLE_DOWNLOADER_SCRIPT_PATH: str = Field(
        default="/app/scripts/sub_downloader.py",
        validation_alias="SUBTITLE_DOWNLOADER_SCRIPT_PATH",
    )
    JOB_TIMEOUT_SEC: int = int(os.getenv("JOB_TIMEOUT_SEC", "900"))
    PROCESS_TERMINATE_GRACE_PERIOD_S: int = int(
        os.getenv("PROCESS_TERMINATE_GRACE_PERIOD_S", "5")
    )  # Added this, was missing from your new version
    JOB_MAX_RETRIES: int = Field(default=2, validation_alias="JOB_MAX_RETRIES")
    JOB_RESULT_MESSAGE_MAX_LEN: int = int(os.getenv("JOB_RESULT_MESSAGE_MAX_LEN", "500"))
    JOB_LOG_SNIPPET_MAX_LEN: int = int(os.getenv("JOB_LOG_SNIPPET_MAX_LEN", "50000"))
    DEFAULT_PAGINATION_LIMIT_MAX: int = Field(
        default=200, validation_alias="DEFAULT_PAGINATION_LIMIT_MAX"
    )

    # --- Logging & Debugging Specifics ---
    LOG_SNIPPET_PREVIEW_LEN: int = int(
        os.getenv("LOG_SNIPPET_PREVIEW_LEN", "200")
    )  # Changed default from 2048 to 200
    LOG_TRACEBACKS: bool = os.getenv("LOG_TRACEBACKS", "True").lower() in (
        "true",
        "1",
        "t",
    )  # Default to True
    LOG_TRACEBACKS_CELERY_WRAPPER: bool = os.getenv(
        "LOG_TRACEBACKS_CELERY_WRAPPER", "True"
    ).lower() in ("true", "1", "t")
    LOG_TRACEBACKS_IN_JOB_LOGS: bool = os.getenv(
        "LOG_TRACEBACKS_IN_JOB_LOGS", "True"
    ).lower() in (  # Default to True
        "true",
        "1",
        "t",
    )
    DEBUG_TASK_CANCELLATION_DELAY_S: int = int(
        os.getenv("DEBUG_TASK_CANCELLATION_DELAY_S", "10")
    )  # Default 10 seconds

    DEEPL_API_KEYS_ENV_STR: str | None = Field(
        default=None, validation_alias="DEEPL_API_KEYS"
    )  # JSON list of keys

    # Google Cloud Translate Settings
    GOOGLE_PROJECT_ID: str | None = Field(default=None, validation_alias="GOOGLE_PROJECT_ID")
    GOOGLE_CREDENTIALS_PATH: str | None = Field(
        default=None, validation_alias="GOOGLE_CREDENTIALS_PATH"
    )

    # Translation Settings
    DEEPL_CHARACTER_QUOTA: int = Field(default=500000, validation_alias="DEEPL_CHARACTER_QUOTA")
    GOOGLE_CHARACTER_QUOTA: int = Field(default=500000, validation_alias="GOOGLE_CHARACTER_QUOTA")

    # Application Settings (Subtitle Tool Specific)
    USER_AGENT_APP_NAME: str = Field(
        default="SubtitleDownloader", validation_alias="USER_AGENT_APP_NAME"
    )
    USER_AGENT_APP_VERSION: str | None = Field(
        default=None, validation_alias="USER_AGENT_APP_VERSION"
    )
    LOG_FILE_NAME_PATTERN: str = Field(
        default="{base_name}.log", validation_alias="LOG_FILE_NAME_PATTERN"
    )

    # Sync Tool Paths
    FFSUBSYNC_PATH: str = Field(default="ffsubsync", validation_alias="FFSUBSYNC_PATH")
    ALASS_CLI_PATH: str = Field(default="alass-cli", validation_alias="ALASS_CLI_PATH")
    SUP2SRT_PATH: str = Field(default="sup2srt", validation_alias="SUP2SRT_PATH")

    # Other Subtitle Settings
    NETWORK_MAX_RETRIES: int = Field(default=5, validation_alias="NETWORK_MAX_RETRIES")
    NETWORK_BACKOFF_FACTOR: int = Field(default=1, validation_alias="NETWORK_BACKOFF_FACTOR")
    FUZZY_MATCH_THRESHOLD: int = Field(default=80, validation_alias="FUZZY_MATCH_THRESHOLD")
    SUBTITLE_SYNC_OFFSET_THRESHOLD: int = Field(
        default=1, validation_alias="SUBTITLE_SYNC_OFFSET_THRESHOLD"
    )
    FFSUBSYNC_CHECK_TIMEOUT: int = Field(default=90, validation_alias="FFSUBSYNC_CHECK_TIMEOUT")
    FFSUBSYNC_TIMEOUT: int = Field(default=600, validation_alias="FFSUBSYNC_TIMEOUT")
    ALASS_TIMEOUT: int = Field(default=600, validation_alias="ALASS_TIMEOUT")

    # --- Fields for complex parsing ---
    allowed_media_folders_env_str: str = Field(
        default='["/mnt/sata0/Media","/mnt/sata1/Media"]',
        validation_alias=AliasChoices("ALLOWED_MEDIA_FOLDERS", "ALLOWED_MEDIA_FOLDERS_ENV"),
    )
    backend_cors_origins_env_str: str | None = Field(
        default='["http://localhost:5173","http://localhost:8000","https://localhost"]',
        validation_alias=AliasChoices("BACKEND_CORS_ORIGINS", "BACKEND_CORS_ORIGINS_ENV"),
    )

    # --- Private storage for parsed values ---
    _parsed_allowed_media_folders: list[str] = []
    _parsed_backend_cors_origins: list[str] = []
    _parsed_deepl_api_keys: list[str] = []
    _parsed_data_encryption_keys: list[str] = []

    @property
    def DATA_ENCRYPTION_KEYS(self) -> list[str]:
        return self._parsed_data_encryption_keys

    @property
    def DEEPL_API_KEYS(self) -> list[str]:
        return self._parsed_deepl_api_keys

    def _parse_string_list_input_helper(
        self, input_str: str | None, field_name_for_log: str
    ) -> list[str]:
        parsed_list: list[str] = []
        if not input_str or not input_str.strip():
            return parsed_list
        try:
            loaded_items = json.loads(input_str)
            if isinstance(loaded_items, list):
                parsed_list = [str(item).strip() for item in loaded_items if str(item).strip()]
            elif isinstance(loaded_items, str) and loaded_items.strip():
                # This case is less likely if default is JSON list, but good fallback
                parsed_list = [item.strip() for item in loaded_items.split(",") if item.strip()]
            else:  # Not a list or a parsable string, try comma separation as last resort
                logger.debug(
                    f"Input for {field_name_for_log} ('{input_str}') was valid JSON but not list/string. Trying comma separation."
                )
                parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]
        except json.JSONDecodeError:
            logger.debug(
                f"JSONDecodeError for {field_name_for_log}. Falling back to comma separation for: '{input_str}'"
            )
            parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]

        if (
            not parsed_list and input_str and input_str.strip()
        ):  # Log if input was non-empty but parsing yielded empty
            logger.warning(
                f"Env var {field_name_for_log} (value: '{input_str}') resulted in an empty parsed list."
            )
        return parsed_list

    @model_validator(mode="after")
    def _run_post_init_logic(self) -> "Settings":
        """Orchestrates post-initialization logic to reduce complexity."""
        self._normalize_state_dir()
        self._parse_complex_fields()
        self._apply_debug_overrides()
        self._configure_docs()

        # Default User-Agent version to App version if not specified
        if not self.USER_AGENT_APP_VERSION:
            self.USER_AGENT_APP_VERSION = self.APP_VERSION

        if self.ROOT_PATH and self.ROOT_PATH != "/":
            self.ROOT_PATH = self.ROOT_PATH.strip("/")
        return self

    def _normalize_state_dir(self) -> None:
        raw_state_dir = str(self.APP_STATE_DIR).strip()
        if not raw_state_dir:
            raw_state_dir = _default_app_state_dir()
        state_dir = Path(os.path.expandvars(raw_state_dir)).expanduser()
        self.APP_STATE_DIR = str(state_dir)

    def _parse_complex_fields(self) -> None:
        """Parses JSON list strings from environment variables."""
        self._parsed_allowed_media_folders = self._parse_string_list_input_helper(
            self.allowed_media_folders_env_str, "ALLOWED_MEDIA_FOLDERS"
        )
        self._parsed_backend_cors_origins = self._parse_string_list_input_helper(
            self.backend_cors_origins_env_str, "BACKEND_CORS_ORIGINS"
        )
        self._parsed_deepl_api_keys = self._parse_string_list_input_helper(
            self.DEEPL_API_KEYS_ENV_STR, "DEEPL_API_KEYS"
        )
        self._parsed_data_encryption_keys = self._parse_string_list_input_helper(
            self.DATA_ENCRYPTION_KEYS_ENV_STR, "DATA_ENCRYPTION_KEYS"
        )

    def _apply_debug_overrides(self) -> None:
        """Applies configuration overrides when DEBUG mode is enabled."""
        if not self.DEBUG:
            # Handle non-development environment security defaults
            if self.ENVIRONMENT != "development" and not self.COOKIE_SECURE and self.USE_HTTPS:
                self.COOKIE_SECURE = True
            elif self.ENVIRONMENT != "development" and not self.COOKIE_SECURE:
                logger.warning(
                    "Non-development environment with USE_HTTPS=False, COOKIE_SECURE remains False."
                )
            return

        if self.LOG_LEVEL != "DEBUG":
            logger.info("DEBUG mode is ON. Overriding LOG_LEVEL to DEBUG.")
            self.LOG_LEVEL = "DEBUG"
        if not self.DB_ECHO:
            logger.info("DEBUG mode is ON. Overriding DB_ECHO to True.")
            self.DB_ECHO = True
        if not self.DB_ECHO_WORKER and self.DB_ECHO:
            logger.info("DEBUG mode is ON & DB_ECHO is True. Setting DB_ECHO_WORKER to True.")
            self.DB_ECHO_WORKER = True
        if self.COOKIE_SECURE:
            logger.info("DEBUG mode is ON. Overriding COOKIE_SECURE to False.")
            self.COOKIE_SECURE = False

    def _configure_docs(self) -> None:
        """Configures API documentation URLs based on environment."""
        if self.ENVIRONMENT == "development":
            if self.OPENAPI_URL is None:
                self.OPENAPI_URL = f"{self.API_V1_STR}/openapi.json"
            if self.DOCS_URL is None:
                self.DOCS_URL = f"{self.API_V1_STR}/docs"
            if self.REDOC_URL is None:
                self.REDOC_URL = f"{self.API_V1_STR}/redoc"
            if self.HEALTHZ_URL is None:
                self.HEALTHZ_URL = f"{self.API_V1_STR}/healthz"
        else:
            # In other environments, docs are None (disabled) unless explicitly set.
            pass  # HEALTHZ_URL remains None if not explicitly set

    @property
    def ALLOWED_MEDIA_FOLDERS(self) -> list[str]:
        return self._parsed_allowed_media_folders

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._parsed_backend_cors_origins

    def _build_postgres_dsn(self, base_dsn: PostgresDsn | None, use_async: bool) -> PostgresDsn:
        driver_prefix = "postgresql+asyncpg://" if use_async else "postgresql://"
        alt_driver_prefix = (
            "postgresql://" if use_async else "postgresql+asyncpg://"
        )  # The opposite driver

        if base_dsn:
            db_url_str = str(base_dsn)
            # If base_dsn already has the correct driver, use it
            if db_url_str.startswith(driver_prefix):
                return base_dsn
            # If base_dsn has the alternate driver, swap it
            elif db_url_str.startswith(alt_driver_prefix):
                return PostgresDsn(db_url_str.replace(alt_driver_prefix, driver_prefix, 1))
            # If base_dsn has a scheme but not the one we want (e.g. just 'postgres://')
            elif "://" in db_url_str:
                # Rebuild with correct prefix and rest of URL
                return PostgresDsn(driver_prefix + db_url_str.split("://", 1)[1])
            else:
                # This case implies a malformed DSN without a scheme.
                # It's unlikely Pydantic would allow this for PostgresDsn, but defensive.
                raise ValueError(f"Malformed base DSN for DB (missing scheme?): {db_url_str}")
        # If no base_dsn, construct from components
        return PostgresDsn(
            f"{driver_prefix}{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def ASYNC_SQLALCHEMY_DATABASE_URL(self) -> str:
        return str(self._build_postgres_dsn(self.PRIMARY_DATABASE_URL_ENV, use_async=True))

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def ASYNC_SQLALCHEMY_DATABASE_URL_WORKER(self) -> str:
        base_for_worker = (
            self.ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV or self.PRIMARY_DATABASE_URL_ENV
        )
        return str(self._build_postgres_dsn(base_for_worker, use_async=True))

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def SYNC_SQLALCHEMY_DATABASE_URL(self) -> str:
        return str(self._build_postgres_dsn(self.PRIMARY_DATABASE_URL_ENV, use_async=False))

    @property
    def CELERY_BROKER_URL(self) -> str | None:
        if self.CELERY_BROKER_URL_ENV:
            return str(self.CELERY_BROKER_URL_ENV)
        if self.REDIS_HOST:  # Construct if not provided explicitly
            try:
                return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
            except Exception as e:  # Catch Pydantic validation error or others
                logger.error(f"Failed to build CELERY_BROKER_URL from components: {e}")
                return None
        return None  # No explicit URL and no components to build from

    @property
    def CELERY_RESULT_BACKEND(self) -> str | None:
        if self.CELERY_RESULT_BACKEND_ENV:
            return str(self.CELERY_RESULT_BACKEND_ENV)
        if self.REDIS_HOST:
            try:
                return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"  # Different DB for results
            except Exception as e:
                logger.error(f"Failed to build CELERY_RESULT_BACKEND from components: {e}")
                return None
        return None

    @property
    def CELERY_BEAT_SCHEDULE_FILENAME(self) -> str:
        if self.CELERY_BEAT_SCHEDULE_FILENAME_ENV:
            return str(
                Path(os.path.expandvars(str(self.CELERY_BEAT_SCHEDULE_FILENAME_ENV))).expanduser()
            )
        return str(Path(self.APP_STATE_DIR) / "celerybeat-schedule.db")

    @property
    def REDIS_PUBSUB_URL(self) -> str | None:
        if self.REDIS_PUBSUB_URL_ENV:
            return str(self.REDIS_PUBSUB_URL_ENV)
        if self.REDIS_HOST:
            try:
                return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/2"  # Different DB for pubsub
            except Exception as e:
                logger.error(f"Failed to build REDIS_PUBSUB_URL from components: {e}")
                return None
        return None


settings = Settings()

if __name__ == "__main__":
    print("--- Loaded Settings (Debug from config.py) ---")
    print(
        f"ENVIRONMENT: {settings.ENVIRONMENT}, DEBUG: {settings.DEBUG}, LOG_LEVEL: {settings.LOG_LEVEL}"
    )
    print(
        f"DB_ECHO: {settings.DB_ECHO}, DB_ECHO_WORKER: {settings.DB_ECHO_WORKER}, COOKIE_SECURE: {settings.COOKIE_SECURE}"
    )

    print("\n--- Database ---")
    print(f"PRIMARY_DATABASE_URL_ENV: {settings.PRIMARY_DATABASE_URL_ENV}")
    print(
        f"ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV: {settings.ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV}"
    )
    print(f"ASYNC_SQLALCHEMY_DATABASE_URL (for FastAPI): {settings.ASYNC_SQLALCHEMY_DATABASE_URL}")
    print(
        f"ASYNC_SQLALCHEMY_DATABASE_URL_WORKER (for Celery): {settings.ASYNC_SQLALCHEMY_DATABASE_URL_WORKER}"
    )
    print(f"SYNC_SQLALCHEMY_DATABASE_URL (for Alembic): {settings.SYNC_SQLALCHEMY_DATABASE_URL}")

    print("\n--- Celery & Redis ---")
    print(f"TIMEZONE: {settings.TIMEZONE}")
    print(f"CELERY_ACKS_LATE: {settings.CELERY_ACKS_LATE}")
    print(f"CELERY_RESULT_EXPIRES: {settings.CELERY_RESULT_EXPIRES}")
    print(f"CELERY_BROKER_URL: {settings.CELERY_BROKER_URL}")
    print(f"CELERY_RESULT_BACKEND: {settings.CELERY_RESULT_BACKEND}")
    print(f"REDIS_PUBSUB_URL: {settings.REDIS_PUBSUB_URL}")
    print(f"CELERY_SUBTITLE_TASK_NAME: {settings.CELERY_SUBTITLE_TASK_NAME}")

    print("\n--- Job Runner ---")
    print(f"PYTHON_EXECUTABLE_PATH: {settings.PYTHON_EXECUTABLE_PATH}")
    print(f"SUBTITLE_DOWNLOADER_SCRIPT_PATH: {settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH}")
    print(f"JOB_TIMEOUT_SEC: {settings.JOB_TIMEOUT_SEC}")
    print(f"PROCESS_TERMINATE_GRACE_PERIOD_S: {settings.PROCESS_TERMINATE_GRACE_PERIOD_S}")  # Added
    print(f"JOB_MAX_RETRIES: {settings.JOB_MAX_RETRIES}")
    print(f"JOB_RESULT_MESSAGE_MAX_LEN: {settings.JOB_RESULT_MESSAGE_MAX_LEN}")
    print(f"JOB_LOG_SNIPPET_MAX_LEN: {settings.JOB_LOG_SNIPPET_MAX_LEN}")
    print(f"DEBUG_TASK_CANCELLATION_DELAY_S: {settings.DEBUG_TASK_CANCELLATION_DELAY_S}")  # Added

    print("\n--- Logging & Debugging Specifics ---")
    print(f"LOG_SNIPPET_PREVIEW_LEN: {settings.LOG_SNIPPET_PREVIEW_LEN}")
    print(f"LOG_TRACEBACKS: {settings.LOG_TRACEBACKS}")
    print(f"LOG_TRACEBACKS_CELERY_WRAPPER: {settings.LOG_TRACEBACKS_CELERY_WRAPPER}")
    print(f"LOG_TRACEBACKS_IN_JOB_LOGS: {settings.LOG_TRACEBACKS_IN_JOB_LOGS}")

    print("\n--- Paths & Lists ---")
    print(f"ALLOWED_MEDIA_FOLDERS: {settings.ALLOWED_MEDIA_FOLDERS}")
    print(f"BACKEND_CORS_ORIGINS: {settings.BACKEND_CORS_ORIGINS}")
    print(f"ROOT_PATH: '{settings.ROOT_PATH}'")
