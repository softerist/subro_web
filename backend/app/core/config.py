# /backend/app/core/config.py

import json
import logging
import os  # For default values
import sys  # For default PYTHON_EXECUTABLE_PATH
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
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",  # Added validation_alias
    )

    # --- Server Configuration ---
    SERVER_HOST: str = Field(default="0.0.0.0", validation_alias="SERVER_HOST")
    SERVER_PORT: int = Field(default=8000, validation_alias="SERVER_PORT")
    ROOT_PATH: str = Field(
        default="", description="Root path for the application if served under a subpath."
    )
    USE_HTTPS: bool = Field(default=False, validation_alias="USE_HTTPS_IN_CADDYFILE_SNIPPETS")

    # --- Core Application Settings ---
    APP_NAME: str = Field(default="Subtitle Downloader", validation_alias="APP_NAME")
    APP_VERSION: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    APP_DESCRIPTION: str = Field(
        default="API for managing subtitle download jobs and user authentication.",
        validation_alias="APP_DESCRIPTION",
    )
    API_V1_STR: str = Field(default="/api/v1", validation_alias="API_V1_STR")

    # --- JWT & Authentication Settings ---
    SECRET_KEY: str = Field(validation_alias="JWT_SECRET_KEY")
    JWT_REFRESH_SECRET_KEY: str = Field(validation_alias="JWT_REFRESH_SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", validation_alias="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, validation_alias="REFRESH_TOKEN_EXPIRE_DAYS")
    REFRESH_TOKEN_COOKIE_NAME: str = Field(
        default="subRefreshToken", validation_alias="REFRESH_TOKEN_COOKIE_NAME"
    )
    COOKIE_SECURE: bool = Field(default=True, validation_alias="COOKIE_SECURE")
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="lax", validation_alias="COOKIE_SAMESITE"
    )
    OPEN_SIGNUP: bool = Field(default=True, validation_alias="OPEN_SIGNUP")

    # --- Initial Superuser Settings ---
    FIRST_SUPERUSER_EMAIL: EmailStr = Field(validation_alias="FIRST_SUPERUSER_EMAIL")
    FIRST_SUPERUSER_PASSWORD: str = Field(validation_alias="FIRST_SUPERUSER_PASSWORD")

    # --- Database Settings ---
    PRIMARY_DATABASE_URL_ENV: PostgresDsn | None = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV: PostgresDsn | None = Field(
        default=None, validation_alias="ASYNC_SQLALCHEMY_DATABASE_URL_WORKER"
    )
    POSTGRES_SERVER: str = Field(default="db", validation_alias="POSTGRES_SERVER")
    POSTGRES_USER: str = Field(default="admin", validation_alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="Pa44w0rd", validation_alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="subappdb", validation_alias="POSTGRES_DB")
    POSTGRES_PORT: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    DB_ECHO: bool = Field(default=False, validation_alias="DB_ECHO")
    DB_ECHO_WORKER: bool = Field(
        default=False, validation_alias="DB_ECHO_WORKER"
    )  # For worker specific DB echo

    # --- Celery & Redis Settings ---
    REDIS_HOST: str = Field(default="redis", validation_alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, validation_alias="REDIS_PORT")
    CELERY_BROKER_URL_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND_ENV: RedisDsn | None = Field(
        default=None, validation_alias="CELERY_RESULT_BACKEND"
    )
    REDIS_PUBSUB_URL_ENV: RedisDsn | None = Field(default=None, validation_alias="REDIS_PUBSUB_URL")
    CELERY_SUBTITLE_TASK_NAME: str = Field(
        default="app.tasks.subtitle_jobs.execute_subtitle_downloader_task",
        validation_alias="CELERY_SUBTITLE_TASK_NAME",
    )
    TIMEZONE: str = Field(default="UTC", validation_alias="CELERY_TIMEZONE")
    CELERY_ACKS_LATE: bool = Field(default=True, validation_alias="CELERY_ACKS_LATE")
    CELERY_RESULT_EXPIRES: int = Field(
        default=3600, validation_alias="CELERY_RESULT_EXPIRES"
    )  # Default to 1 hour (in seconds)

    # --- Job Runner Settings ---
    PYTHON_EXECUTABLE_PATH: str = Field(
        default=sys.executable, validation_alias="PYTHON_EXECUTABLE_PATH"
    )
    SUBTITLE_DOWNLOADER_SCRIPT_PATH: str = Field(
        default="/app/scripts/sub_downloader.py",
        validation_alias="SUBTITLE_DOWNLOADER_SCRIPT_PATH",
    )
    JOB_TIMEOUT_SEC: int = int(os.getenv("JOB_TIMEOUT_SEC", "900"))  # Default 15 minutes
    JOB_MAX_RETRIES: int = Field(default=2, validation_alias="JOB_MAX_RETRIES")
    JOB_RESULT_MESSAGE_MAX_LEN: int = int(os.getenv("JOB_RESULT_MESSAGE_MAX_LEN", "500"))
    JOB_LOG_SNIPPET_MAX_LEN: int = int(os.getenv("JOB_LOG_SNIPPET_MAX_LEN", "5000"))
    DEFAULT_PAGINATION_LIMIT_MAX: int = Field(
        default=200, validation_alias="DEFAULT_PAGINATION_LIMIT_MAX"
    )

    LOG_SNIPPET_PREVIEW_LEN: int = int(os.getenv("LOG_SNIPPET_PREVIEW_LEN", "2048"))
    LOG_TRACEBACKS: bool = os.getenv("LOG_TRACEBACKS", "False").lower() in ("true", "1", "t")
    LOG_TRACEBACKS_CELERY_WRAPPER: bool = os.getenv(
        "LOG_TRACEBACKS_CELERY_WRAPPER", "True"
    ).lower() in ("true", "1", "t")  # Often good to see in wrapper
    LOG_TRACEBACKS_IN_JOB_LOGS: bool = os.getenv("LOG_TRACEBACKS_IN_JOB_LOGS", "False").lower() in (
        "true",
        "1",
        "t",
    )  # Control if full TB goes into job log snippet

    # --- Fields for complex parsing ---
    allowed_media_folders_env_str: str = Field(
        default='["/mnt/sata0/Media","/mnt/sata1/Media"]',
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
                    f"Input for {field_name_for_log} ('{input_str}') was valid JSON but not list/string. Trying comma separation."
                )
                parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]
        except json.JSONDecodeError:
            logger.debug(
                f"JSONDecodeError for {field_name_for_log}. Falling back to comma separation for: '{input_str}'"
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
            # If DB_ECHO_WORKER is False and DB_ECHO is True (due to debug override), set DB_ECHO_WORKER to True as well.
            if not self.DB_ECHO_WORKER and self.DB_ECHO:
                logger.info("DEBUG mode is ON & DB_ECHO is True. Setting DB_ECHO_WORKER to True.")
                self.DB_ECHO_WORKER = True
            if self.COOKIE_SECURE:
                logger.info("DEBUG mode is ON. Overriding COOKIE_SECURE to False.")
                self.COOKIE_SECURE = False
        elif self.ENVIRONMENT != "development" and not self.COOKIE_SECURE:
            if self.USE_HTTPS:
                self.COOKIE_SECURE = True
            else:
                logger.warning(
                    "Non-development environment with USE_HTTPS=False, COOKIE_SECURE remains False."
                )

        if self.ROOT_PATH:
            self.ROOT_PATH = self.ROOT_PATH.strip("/")
        return self

    # --- Convenience Properties for public access to parsed fields ---
    @property
    def ALLOWED_MEDIA_FOLDERS(self) -> list[str]:
        return self._parsed_allowed_media_folders

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._parsed_backend_cors_origins

    # --- Computed DSN Properties ---
    def _build_postgres_dsn(self, base_dsn: PostgresDsn | None, use_async: bool) -> PostgresDsn:
        driver_prefix = "postgresql+asyncpg://" if use_async else "postgresql://"
        alt_driver_prefix = "postgresql://" if use_async else "postgresql+asyncpg://"

        if base_dsn:
            db_url_str = str(base_dsn)
            if db_url_str.startswith(alt_driver_prefix):
                db_url_str = db_url_str.replace(alt_driver_prefix, driver_prefix, 1)
            elif not db_url_str.startswith(driver_prefix):
                if "://" in db_url_str:
                    db_url_str = driver_prefix + db_url_str.split("://", 1)[1]
                else:
                    raise ValueError(f"Malformed base DSN for DB: {db_url_str}")
            return PostgresDsn(db_url_str)
        return PostgresDsn(
            f"{driver_prefix}{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field(repr=False)
    @property
    def ASYNC_SQLALCHEMY_DATABASE_URL(self) -> PostgresDsn:
        return self._build_postgres_dsn(self.PRIMARY_DATABASE_URL_ENV, use_async=True)

    @computed_field(repr=False)
    @property
    def ASYNC_SQLALCHEMY_DATABASE_URL_WORKER(self) -> PostgresDsn:
        base_for_worker = (
            self.ASYNC_SQLALCHEMY_DATABASE_URL_WORKER_ENV or self.PRIMARY_DATABASE_URL_ENV
        )
        return self._build_postgres_dsn(base_for_worker, use_async=True)

    @computed_field(repr=False)
    @property
    def SYNC_SQLALCHEMY_DATABASE_URL(self) -> PostgresDsn:
        return self._build_postgres_dsn(self.PRIMARY_DATABASE_URL_ENV, use_async=False)

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
    print(f"JOB_MAX_RETRIES: {settings.JOB_MAX_RETRIES}")
    print(f"JOB_RESULT_MESSAGE_MAX_LEN: {settings.JOB_RESULT_MESSAGE_MAX_LEN}")
    print(f"JOB_LOG_SNIPPET_MAX_LEN: {settings.JOB_LOG_SNIPPET_MAX_LEN}")

    print("\n--- Paths & Lists ---")
    print(f"ALLOWED_MEDIA_FOLDERS: {settings.ALLOWED_MEDIA_FOLDERS}")
    print(f"BACKEND_CORS_ORIGINS: {settings.BACKEND_CORS_ORIGINS}")
    print(f"ROOT_PATH: '{settings.ROOT_PATH}'")
