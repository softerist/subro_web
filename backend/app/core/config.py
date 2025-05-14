import json
import logging
from typing import Literal

from pydantic import (
    EmailStr,
    Field,
    PostgresDsn,
    RedisDsn,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict  # <<<< THIS IS THE IMPORTANT IMPORT

# from pydantic_core.core_schema import FieldValidationInfo # Not directly used, ValidationInfo is preferred for Pydantic v2
# from pydantic import PostgresDsn, field_validator # Duplicate import

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DEBUG: bool = Field(default=False, validation_alias="DEBUG_MODE")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Environment & Debug ---
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",  # Use a distinct alias if needed
    )
    DEBUG: bool = Field(default=False, validation_alias="DEBUG_MODE")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Server Configuration ---
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    USE_HTTPS: bool = False

    # --- Core Application Settings ---
    APP_NAME: str = "Subtitle Downloader"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "API for managing subtitle download jobs and user authentication."
    API_V1_STR: str = "/api/v1"

    # --- JWT & Authentication Settings ---
    SECRET_KEY: str = Field(validation_alias="JWT_SECRET_KEY")
    JWT_REFRESH_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_COOKIE_NAME: str = "subRefreshToken"
    COOKIE_SECURE: bool = True  # Will be overridden by DEBUG mode if True
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    OPEN_SIGNUP: bool = Field(default=True)  # validation_alias="OPEN_SIGNUP" if needed

    # --- Initial Superuser Settings ---
    FIRST_SUPERUSER_EMAIL: EmailStr
    FIRST_SUPERUSER_PASSWORD: str
    # FIRST_SUPERUSER_USERNAME: str | None = None # Or str if it's required
    # --- Database Settings ---
    # Primary environment variable for full DSN (optional)
    DATABASE_URL_ENV: PostgresDsn | None = Field(default=None, validation_alias="DATABASE_URL")

    # Components for building DSN if DATABASE_URL_ENV is not provided
    POSTGRES_SERVER: str = "db"
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "Pa44w0rd"
    POSTGRES_DB: str = "subappdb"
    POSTGRES_PORT: int = 5432
    DB_ECHO: bool = False  # Will be overridden by DEBUG mode if True

    # SQLALCHEMY_DATABASE_URI: Intended as the primary DSN used by SQLAlchemy,
    # often the sync one for Alembic, or could be async if app only uses async.
    # Here, we'll make its validator construct an ASYNC DSN for potential direct use,
    # but ASYNC_DATABASE_URI (computed_field) is preferred for clarity for the app's async engine.
    # The validator is kept to show the fix, but you might simplify further.
    SQLALCHEMY_DATABASE_URI: PostgresDsn | None = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(
        cls, v: str | None, info: ValidationInfo
    ) -> str | PostgresDsn | None:
        if isinstance(v, str):  # Allows setting SQLALCHEMY_DATABASE_URI directly in .env
            return v

        # If DATABASE_URL_ENV is set, prefer that for SQLALCHEMY_DATABASE_URI
        # This part depends on how you want SQLALCHEMY_DATABASE_URI to behave relative to DATABASE_URL_ENV
        # For now, if SQLALCHEMY_DATABASE_URI is not explicitly set, we build from components.
        # if info.data.get("DATABASE_URL_ENV"):
        #     return str(info.data.get("DATABASE_URL_ENV")).replace("postgresql://", "postgresql+asyncpg://")

        # Build from components if SQLALCHEMY_DATABASE_URI (v) is None
        # and DATABASE_URL_ENV is not being used to populate this specific field.
        if v is None:
            db_data = info.data  # data from other fields
            required_keys = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_SERVER", "POSTGRES_DB"]
            if not all(db_data.get(key) for key in required_keys):
                # Optionally log a warning, returning None as the field is Optional.
                # logger.warning("Not all Postgres components set, SQLALCHEMY_DATABASE_URI will be None.")
                return None

            try:
                return PostgresDsn.build(
                    scheme="postgresql+asyncpg",
                    username=db_data.get("POSTGRES_USER"),
                    password=db_data.get("POSTGRES_PASSWORD"),
                    host=db_data.get("POSTGRES_SERVER"),
                    port=int(db_data.get("POSTGRES_PORT", 5432)),
                    # CORRECTED PATH: Use only the database name for the 'path' argument in build()
                    path=db_data.get("POSTGRES_DB"),
                )
            except Exception as e:
                logger.error(f"Error building SQLALCHEMY_DATABASE_URI from components: {e}")
                return None
        return v

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
    allowed_media_folders_env_str: str = Field(
        default='["/mnt/sata0/Media","/mnt/sata1/Media"]',
        validation_alias="ALLOWED_MEDIA_FOLDERS",
    )
    backend_cors_origins_env_str: str | None = Field(
        default='["http://localhost:5173","http://localhost:8000","https://localhost"]',  # <<< ADD THIS
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
            elif (
                isinstance(loaded_items, str) and loaded_items.strip()
            ):  # if json is just a string "item1,item2"
                parsed_list = [item.strip() for item in loaded_items.split(",") if item.strip()]
            else:  # Not a list, not a string. Try direct comma separation on original input_str
                logger.debug(
                    f"Input for {field_name_for_log} was valid JSON but not a list or simple string. Trying comma separation on original input."
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
            if self.COOKIE_SECURE:
                logger.info("DEBUG mode is ON. Overriding COOKIE_SECURE to False.")
                self.COOKIE_SECURE = False
        return self

    # --- Convenience Properties for public access to parsed fields ---
    @property
    def ALLOWED_MEDIA_FOLDERS(self) -> list[str]:
        return self._parsed_allowed_media_folders

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._parsed_backend_cors_origins

    # --- Computed DSN Properties ---

    # ASYNC_DATABASE_URI: Primary DSN for the application's asynchronous engine.
    # This version directly constructs the string, which Pydantic then validates.
    # It ensures components are used if DATABASE_URL_ENV is not set for this specific purpose.
    @computed_field
    @property
    def ASYNC_DATABASE_URI(self) -> PostgresDsn:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if not db_url_str.startswith("postgresql+asyncpg://"):
                if db_url_str.startswith("postgresql://"):
                    db_url_str = db_url_str.replace("postgresql://", "postgresql+asyncpg://", 1)
                else:  # If scheme is unexpected, Pydantic validation will catch it
                    logger.warning(
                        f"DATABASE_URL_ENV ('{db_url_str}') is not 'postgresql' or 'postgresql+asyncpg'. Will attempt to use as is for async."
                    )
            return PostgresDsn(db_url_str)  # Let Pydantic validate the final string

        # Build from components if DATABASE_URL_ENV is not available
        # All components have defaults, so this should always succeed in building a string.
        # Pydantic's PostgresDsn will validate the built string.
        return PostgresDsn(
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # SYNC_DATABASE_URI: For synchronous operations (e.g., Alembic migrations).
    @property
    def SYNC_DATABASE_URI(self) -> PostgresDsn | None:
        if self.DATABASE_URL_ENV:
            db_url_str = str(self.DATABASE_URL_ENV)
            if db_url_str.startswith("postgresql+asyncpg://"):
                db_url_str = db_url_str.replace("postgresql+asyncpg://", "postgresql://", 1)
            elif not db_url_str.startswith("postgresql://"):
                logger.warning(
                    f"DATABASE_URL_ENV ('{db_url_str}') is not 'postgresql'. Will attempt to use as is for sync."
                )
            try:
                return PostgresDsn(db_url_str)
            except Exception as e:
                logger.error(f"Failed to parse DATABASE_URL_ENV for SYNC_DATABASE_URI: {e}")
                return None  # Or raise, depending on desired strictness

        if all(
            [self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_SERVER, self.POSTGRES_DB]
        ):
            try:
                return PostgresDsn.build(
                    scheme="postgresql",
                    username=self.POSTGRES_USER,
                    password=self.POSTGRES_PASSWORD,
                    host=self.POSTGRES_SERVER,
                    port=self.POSTGRES_PORT,
                    path=self.POSTGRES_DB,  # Correct: use database name directly
                )
            except Exception as e:
                logger.error(f"Failed to build SYNC_DATABASE_URI from components: {e}")
                return None
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
                logger.error(f"Failed to build CELERY_BROKER_URL from components: {e}")
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
                logger.error(f"Failed to build CELERY_RESULT_BACKEND from components: {e}")
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
                logger.error(f"Failed to build REDIS_PUBSUB_URL from components: {e}")
                return None
        logger.warning("REDIS_PUBSUB_URL could not be determined.")
        return None


settings = Settings()
# Debug print: SQLALCHEMY_DATABASE_URI is now the one from the validator (which makes an async DSN)
# Or None if components are missing and it's not set in env.
# The app should primarily use settings.ASYNC_DATABASE_URI for its async engine.
print(
    f"DEBUG [config.py]: SQLALCHEMY_DATABASE_URI (validator processed) = {settings.SQLALCHEMY_DATABASE_URI}"
)
print(f"DEBUG [config.py]: ASYNC_DATABASE_URI (computed field) = {settings.ASYNC_DATABASE_URI}")
print(f"DEBUG [config.py]: SYNC_DATABASE_URI (property) = {settings.SYNC_DATABASE_URI}")
print(
    f"DEBUG [config.py]: FIRST_SUPERUSER_EMAIL from settings object = {settings.FIRST_SUPERUSER_EMAIL}"
)  # For debugging
print(
    f"DEBUG [config.py]: FIRST_SUPERUSER_PASSWORD from settings object = {settings.FIRST_SUPERUSER_PASSWORD}"
)  # For debugging
print(
    f"DEBUG [config.py]: FIRST_SUPERUSER_PASSWORD = {'*' * len(settings.FIRST_SUPERUSER_PASSWORD) if settings.FIRST_SUPERUSER_PASSWORD else None}"
)
print(f"BACKEND_CORS_ORIGINS (parsed property): {settings.BACKEND_CORS_ORIGINS}")


if __name__ == "__main__":
    print("--- Loaded Settings (Debug from config.py) ---")
    print(f"APP_NAME: {settings.APP_NAME}")
    print(f"DEBUG: {settings.DEBUG}")
    print(f"DB_ECHO: {settings.DB_ECHO}")
    print(f"LOG_LEVEL: {settings.LOG_LEVEL}")
    print(f"COOKIE_SECURE: {settings.COOKIE_SECURE}")
    print(f"DATABASE_URL_ENV (from env): {settings.DATABASE_URL_ENV}")
    print(f"SQLALCHEMY_DATABASE_URI (validator processed): {settings.SQLALCHEMY_DATABASE_URI}")
    print(f"ASYNC_DATABASE_URI (computed for app): {settings.ASYNC_DATABASE_URI}")
    print(f"SYNC_DATABASE_URI (computed for Alembic/sync): {settings.SYNC_DATABASE_URI}")
    print(f"CELERY_BROKER_URL (computed): {settings.CELERY_BROKER_URL}")
    print(f"CELERY_RESULT_BACKEND (computed): {settings.CELERY_RESULT_BACKEND}")
    print(f"REDIS_PUBSUB_URL (computed): {settings.REDIS_PUBSUB_URL}")
    print(f"allowed_media_folders_env_str: {settings.allowed_media_folders_env_str}")
    print(f"ALLOWED_MEDIA_FOLDERS (parsed property): {settings.ALLOWED_MEDIA_FOLDERS}")
    print(f"backend_cors_origins_env_str: {settings.backend_cors_origins_env_str}")
    print(f"BACKEND_CORS_ORIGINS (parsed property): {settings.BACKEND_CORS_ORIGINS}")
    print(f"API_V1_STR: {settings.API_V1_STR}")
    print(f"FIRST_SUPERUSER_EMAIL: {settings.FIRST_SUPERUSER_EMAIL}")
    print(
        f"FIRST_SUPERUSER_PASSWORD: {'*' * len(settings.FIRST_SUPERUSER_PASSWORD) if settings.FIRST_SUPERUSER_PASSWORD else None}"
    )
