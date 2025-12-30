import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- Configuration Constants within this module ---
DEFAULT_CONSOLE_LOG_LEVEL = logging.INFO
DEFAULT_FILE_LOG_LEVEL = logging.INFO
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_FILE_BACKUP_COUNT = 2  # Keep 2 backup logs


def _clear_existing_handlers(logger):
    """Removes all existing handlers from the logger."""
    existing_handlers = logger.handlers[:]
    if existing_handlers:
        logging.debug(f"Removing {len(existing_handlers)} existing root logger handlers.")
        for handler in existing_handlers:
            try:
                handler.flush()
                handler.close()
            except Exception as e:
                # Use print here as logging might not be working yet
                print(f"Warning: Error closing existing log handler: {e}", file=sys.stderr)
            logger.removeHandler(handler)


def _setup_console_handler(logger, console_log_level, include_timestamp=True):
    """Configures and adds the console handler."""
    try:
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setLevel(console_log_level)

        # Choose format based on verbosity
        timestamp_format = "%(asctime)s " if include_timestamp else ""
        if console_log_level <= logging.DEBUG:
            c_format_str = f"{timestamp_format}%(levelname)s: [%(name)s:%(lineno)d] %(message)s"
        else:
            c_format_str = f"{timestamp_format}%(levelname)s: %(message)s"

        c_format = logging.Formatter(c_format_str, datefmt="%Y-%m-%d %H:%M:%S")
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        if console_log_level <= logging.DEBUG:
            logging.debug("Console logging handler added.")
    except Exception as e:
        print(f"CRITICAL: Failed to configure console logging: {e}", file=sys.stderr)


def _setup_file_handler(logger, log_file_path):
    """Configures and adds the rotating file handler."""
    try:
        log_dir = Path(log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        f_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        f_handler.setLevel(DEFAULT_FILE_LOG_LEVEL)  # File log defaults to INFO
        f_format = logging.Formatter(
            "%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        f_handler.setFormatter(f_format)
        logger.addHandler(f_handler)
        logging.debug("Rotating file logging handler added.")

    except Exception as e:
        logging.error(f"Failed to configure file logging to {log_file_path}: {e}", exc_info=True)


def setup_logging(log_file_path=None, console_level_override=None, include_timestamp=True):
    """
    Configures the root logger with console and optional rotating file handlers.

    Args:
        log_file_path (str, optional): The full path to the log file. If None, file logging is skipped.
        console_level_override (str, optional): String name of the logging level
                                                 (e.g., 'DEBUG', 'INFO') to override
                                                 the default console level. Defaults to None.
        include_timestamp (bool, optional): Whether to include timestamp in console logs. Defaults to True.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Root level always lowest

    _clear_existing_handlers(logger)

    # --- Determine Console Level ---
    console_log_level = DEFAULT_CONSOLE_LOG_LEVEL
    if console_level_override:
        level_override_name = console_level_override.upper()
        level_override_val = getattr(logging, level_override_name, None)
        if isinstance(level_override_val, int):
            console_log_level = level_override_val
            print(f"Note: Console log level overridden to {level_override_name}", file=sys.stderr)
        else:
            print(
                f"Warning: Invalid console log level override '{console_level_override}'. Using default {logging.getLevelName(DEFAULT_CONSOLE_LOG_LEVEL)}.",
                file=sys.stderr,
            )

    _setup_console_handler(logger, console_log_level, include_timestamp=include_timestamp)

    if log_file_path:
        _setup_file_handler(logger, log_file_path)

    # --- Initial Log Messages ---
    logging.info(
        f"Logging initialized. Console Level: {logging.getLevelName(console_log_level)}, File Level: {logging.getLevelName(DEFAULT_FILE_LOG_LEVEL) if log_file_path else 'N/A'}"
    )
    if log_file_path:
        logging.info(f"Log file path: {log_file_path}")
    logging.debug("Root logger setup complete.")


# --- Get Logger Function ---
def get_logger(module_name):
    """Gets a logger instance specific to a module."""
    # This ensures log messages from different modules can be identified
    # by checking the logger name (`%(name)s` in the file format).
    return logging.getLogger(module_name)


# --- Explicit Exports ---
__all__ = ["get_logger", "setup_logging"]
