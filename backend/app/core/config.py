import json
import logging

from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Core Application Settings ---
    APP_NAME: str = "Subtitle Downloader"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "API for managing subtitle download jobs and user authentication."
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = Field(default=False, validation_alias="DEBUG_MODE")

    # --- JWT & Authentication Settings ---
    SECRET_KEY: str = Field(validation_alias="JWT_SECRET_KEY")
    JWT_REFRESH_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_COOKIE_NAME: str = "subRefreshToken"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    OPEN_SIGNUP: bool = Field(default=True, validation_alias="OPEN_SIGNUP")

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

    # --- Job Runner Settings ---
    DOWNLOAD_SCRIPT_PATH: str = "/app/scripts/sub_downloader.py"
    JOB_TIMEOUT_SEC: int = 900
    JOB_MAX_RETRIES: int = 2
    DEFAULT_PAGINATION_LIMIT_MAX: int = 200

    # --- Fields for complex parsing ---
    # These are "input" fields from the environment. The parsed versions will be properties.
    allowed_media_folders_env_str: str = Field(
        default='["/mnt/sata0/Media","/media/usb_drive"]',
        validation_alias="ALLOWED_MEDIA_FOLDERS",
    )
    backend_cors_origins_env_str: str | None = Field(
        default='["http://localhost:5173","http://localhost:8000"]',
        validation_alias="BACKEND_CORS_ORIGINS",
    )

    # --- Server Settings ---
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # --- Private storage for parsed values (not model fields, but instance attributes)
    # These will be set in the model_validator. They don't use Field() so Pydantic won't treat them as model fields.
    # Pydantic v2 is generally okay with instance attributes starting with an underscore if they aren't Fields.
    _parsed_allowed_media_folders: list[str] = []
    _parsed_backend_cors_origins: list[str] = []

    # --- Helper method (not a model field validator, but a utility) ---
    # Using an underscore for the helper method name is fine.
    def _parse_string_list_input_helper(
        self, input_str: str | None, field_name_for_log: str
    ) -> list[str]:
        """Helper to parse a string that could be a JSON list or comma-separated."""
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
                    f"Input for {field_name_for_log} was valid JSON but not a list or simple string. Trying comma separation."
                )
                parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]
        except json.JSONDecodeError:
            logger.debug(
                f"JSONDecodeError for {field_name_for_log}. Falling back to comma separation for: {input_str}"
            )
            parsed_list = [item.strip() for item in input_str.split(",") if item.strip()]

        if not parsed_list and input_str and input_str.strip():
            logger.warning(
                f"Environment variable {field_name_for_log} (value: '{input_str}') "
                "resulted in an empty list of parsed items."
            )
        return parsed_list

    @model_validator(mode="after")
    def _process_complex_fields_and_debug_overrides(self) -> "Settings":
        # Parse complex fields and store them in the private instance attributes
        self._parsed_allowed_media_folders = self._parse_string_list_input_helper(
            self.allowed_media_folders_env_str, "ALLOWED_MEDIA_FOLDERS"
        )
        self._parsed_backend_cors_origins = self._parse_string_list_input_helper(
            self.backend_cors_origins_env_str, "BACKEND_CORS_ORIGINS"
        )

        # --- Auto-configure based on DEBUG mode ---
        if self.DEBUG:
            if self.LOG_LEVEL.upper() != "DEBUG":
                logger.info("DEBUG mode is ON. Overriding LOG_LEVEL to DEBUG.")
                self.LOG_LEVEL = "DEBUG"  # Modifying LOG_LEVEL directly
            if not self.DB_ECHO:
                logger.info("DEBUG mode is ON. Overriding DB_ECHO to True.")
                self.DB_ECHO = True  # Modifying DB_ECHO directly
            if self.COOKIE_SECURE:
                logger.info("DEBUG mode is ON. Overriding COOKIE_SECURE to False.")
                self.COOKIE_SECURE = False  # Modifying COOKIE_SECURE directly
        return self

    # --- Convenience Properties for public access to parsed fields ---
    @property
    def ALLOWED_MEDIA_FOLDERS(self) -> list[str]:
        return self._parsed_allowed_media_folders

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._parsed_backend_cors_origins

    # --- Properties for DSNs and URLs ---
    @property
    def ASYNC_DATABASE_URI(self) -> PostgresDsn | None:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if not db_url_str.startswith("postgresql+asyncpg://"):
                if db_url_str.startswith("postgresql://"):
                    db_url_str = db_url_str.replace("postgresql://", "postgresql+asyncpg://", 1)
                else:
                    logger.warning(
                        f"ASYNC_DATABASE_URI: DATABASE_URL_ENV scheme ('{db_url_str.split('://')[0]}') "
                        "is not 'postgresql' or 'postgresql+asyncpg'. Attempting to proceed."
                    )
            try:
                return PostgresDsn(db_url_str)
            except Exception as e:
                logger.error(
                    f"ASYNC_DATABASE_URI: Failed to parse DATABASE_URL_ENV '{db_url_str}': {e}",
                    exc_info=True,
                )
                raise
        elif all(
            [self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_SERVER, self.POSTGRES_DB]
        ):
            try:
                return PostgresDsn.build(
                    scheme="postgresql+asyncpg",
                    username=self.POSTGRES_USER,
                    password=self.POSTGRES_PASSWORD,
                    host=self.POSTGRES_SERVER,
                    port=self.POSTGRES_PORT,
                    path=f"/{self.POSTGRES_DB}",
                )
            except Exception as e:
                logger.error(
                    f"ASYNC_DATABASE_URI: Failed to build DSN from components: {e}", exc_info=True
                )
                raise
        logger.critical(
            "ASYNC_DATABASE_URI could not be determined. Essential for application function."
        )
        return None

    @property
    def SYNC_DATABASE_URI(self) -> PostgresDsn | None:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if db_url_str.startswith("postgresql+asyncpg://"):
                db_url_str = db_url_str.replace("postgresql+asyncpg://", "postgresql://", 1)
            elif not db_url_str.startswith("postgresql://"):
                logger.warning(
                    f"SYNC_DATABASE_URI: DATABASE_URL_ENV scheme ('{db_url_str.split('://')[0]}') "
                    "is not 'postgresql'. Attempting to proceed."
                )
            try:
                return PostgresDsn(db_url_str)
            except Exception as e:
                logger.error(
                    f"SYNC_DATABASE_URI: Failed to parse DATABASE_URL_ENV '{db_url_str}': {e}",
                    exc_info=True,
                )
                raise
        elif all(
            [self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_SERVER, self.POSTGRES_DB]
        ):
            try:
                return PostgresDsn.build(
                    scheme="postgresql",
                    username=self.POSTGRES_USER,
                    password=self.POSTGRES_PASSWORD,
                    host=self.POSTGRES_SERVER,
                    port=self.POSTGRES_PORT,
                    path=f"/{self.POSTGRES_DB}",
                )
            except Exception as e:
                logger.error(
                    f"SYNC_DATABASE_URI: Failed to build DSN from components: {e}", exc_info=True
                )
                raise
        logger.error("SYNC_DATABASE_URI could not be determined.")
        return None

    @property
    def CELERY_BROKER_URL(self) -> RedisDsn | None:
        if self.CELERY_BROKER_URL_ENV:
            return self.CELERY_BROKER_URL_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn.build(
                    scheme="redis", host=self.REDIS_HOST, port=self.REDIS_PORT, path="/0"
                )
            except Exception as e:
                logger.error(
                    f"Failed to build CELERY_BROKER_URL from components: {e}", exc_info=True
                )
                return None
        logger.warning("CELERY_BROKER_URL could not be determined.")
        return None

    @property
    def CELERY_RESULT_BACKEND(self) -> RedisDsn | None:
        if self.CELERY_RESULT_BACKEND_ENV:
            return self.CELERY_RESULT_BACKEND_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn.build(
                    scheme="redis", host=self.REDIS_HOST, port=self.REDIS_PORT, path="/1"
                )
            except Exception as e:
                logger.error(
                    f"Failed to build CELERY_RESULT_BACKEND from components: {e}", exc_info=True
                )
                return None
        logger.warning("CELERY_RESULT_BACKEND could not be determined.")
        return None

    @property
    def REDIS_PUBSUB_URL(self) -> RedisDsn | None:
        if self.REDIS_PUBSUB_URL_ENV:
            return self.REDIS_PUBSUB_URL_ENV
        if self.REDIS_HOST:
            try:
                return RedisDsn.build(
                    scheme="redis", host=self.REDIS_HOST, port=self.REDIS_PORT, path="/2"
                )
            except Exception as e:
                logger.error(
                    f"Failed to build REDIS_PUBSUB_URL from components: {e}", exc_info=True
                )
                return None
        logger.warning("REDIS_PUBSUB_URL could not be determined.")
        return None


settings = Settings()

if __name__ == "__main__":
    print("--- Loaded Settings (Debug from config.py) ---")
    print(f"APP_NAME: {settings.APP_NAME}")
    print(f"DEBUG: {settings.DEBUG}")
    print(f"DB_ECHO: {settings.DB_ECHO}")
    print(f"LOG_LEVEL: {settings.LOG_LEVEL}")
    print(f"COOKIE_SECURE: {settings.COOKIE_SECURE}")
    print(f"DATABASE_URL_ENV (from env): {settings.DATABASE_URL_ENV}")
    print(f"ASYNC_DATABASE_URI (computed): {settings.ASYNC_DATABASE_URI}")
    print(f"SYNC_DATABASE_URI (computed): {settings.SYNC_DATABASE_URI}")
    print(f"CELERY_BROKER_URL (computed): {settings.CELERY_BROKER_URL}")
    print(f"CELERY_RESULT_BACKEND (computed): {settings.CELERY_RESULT_BACKEND}")
    print(f"REDIS_PUBSUB_URL (computed): {settings.REDIS_PUBSUB_URL}")
    print(f"allowed_media_folders_env_str: {settings.allowed_media_folders_env_str}")  # Renamed
    print(f"ALLOWED_MEDIA_FOLDERS (parsed property): {settings.ALLOWED_MEDIA_FOLDERS}")
    print(f"backend_cors_origins_env_str: {settings.backend_cors_origins_env_str}")  # Renamed
    print(f"BACKEND_CORS_ORIGINS (parsed property): {settings.BACKEND_CORS_ORIGINS}")
    print(f"API_V1_STR: {settings.API_V1_STR}")
