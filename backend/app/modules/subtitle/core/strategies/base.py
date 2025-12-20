# src/core/strategies/base.py
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Import the DI container type hint
from app.modules.subtitle.core.di import ServiceContainer

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """
    Holds the state and data passed between processing strategies.
    This object is mutable and updated by each strategy in the pipeline.
    """

    video_path: str
    video_info: dict[
        str, Any
    ]  # e.g., {'basename': '...', 'type': 'movie'/'episode', 'imdb_id': '...', 's': '01', 'e': '01'}
    options: dict[str, Any]  # e.g., {'skip_sync': False, 'skip_translation': False}
    di: ServiceContainer  # Dependency Injection container instance

    # --- Results accumulated by strategies ---
    # Preferred paths based on standard naming convention
    target_ro_path: str | None = None
    target_en_path: str | None = None

    # Status flags
    found_final_ro: bool = (
        False  # True if a RO subtitle (external file or embedded text) is finalized
    )
    # found_final_en: bool = False # REMOVE THIS or keep False until FinalSelector sets it

    # Candidate lists (populated by scanners/fetchers)
    local_candidates: list[dict[str, Any]] = field(default_factory=list)
    online_candidates: list[dict[str, Any]] = field(default_factory=list)
    embedded_candidates: list[dict[str, Any]] = field(default_factory=list)

    # --- Candidate Paths ---
    # These store potential EN sources until the final selection is made
    candidate_en_path_standard: str | None = None  # From StandardFileChecker
    candidate_en_path_online: str | None = None  # From OnlineFetcher
    candidate_en_path_embedded: str | None = None  # From EmbedScanner

    # Final selected/processed subtitle path(s) - could be the target path or an embedded marker
    final_ro_sub_path_or_status: str | None = None  # Path to file or 'embedded_text_ro'
    final_en_sub_path: str | None = None

    # Temp directories needing cleanup (managed by strategies, listed here for potential central cleanup)
    temp_dirs_to_clean: set[str] = field(default_factory=set)

    # Error tracking (optional)
    errors: list[str] = field(default_factory=list)

    def add_error(self, strategy_name: str, message: str):
        """Helper to add a formatted error message."""
        err_msg = f"[{strategy_name}] {message}"
        self.errors.append(err_msg)
        logger.error(err_msg)  # Also log immediately

    def add_temp_dir(self, dir_path: str | None):
        """Registers a temporary directory path that needs cleanup."""
        if dir_path and isinstance(dir_path, str):
            self.temp_dirs_to_clean.add(dir_path)
            logger.debug(f"Registered temp directory for cleanup: {dir_path}")


class ProcessingStrategy(ABC):
    """Abstract base class for all subtitle processing strategies."""

    @abstractmethod
    def execute(self, context: ProcessingContext) -> bool:
        """
        Executes the strategy's logic on the given context.

        Args:
            context (ProcessingContext): The mutable context object holding processing state.

        Returns:
            bool: True if the strategy executed successfully (even if no result was found),
                  False if a critical error occurred preventing further steps in its domain.
                  Note: The pipeline decides whether to continue based on this and context flags.
        """
        pass

    @property
    def name(self) -> str:
        """Returns the simple class name of the strategy for logging."""
        return self.__class__.__name__

    @property
    def logger(self) -> logging.Logger:
        """Returns a logger instance named after the strategy class."""
        return logging.getLogger(self.name)
