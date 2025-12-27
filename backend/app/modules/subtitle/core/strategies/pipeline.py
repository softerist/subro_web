import logging
import time
from pathlib import Path

from app.modules.subtitle.utils import file_utils  # For cleanup

from .base import ProcessingContext, ProcessingStrategy

logger = logging.getLogger(__name__)


class SubtitlePipeline:
    """
    Orchestrates the execution of a series of subtitle processing strategies.
    Manages the processing context and handles final cleanup.
    """

    def __init__(self, strategies: list[type[ProcessingStrategy]]):
        """
        Initializes the pipeline with a list of strategy *classes*.

        Args:
            strategies: A list of ProcessingStrategy subclasses (the classes themselves).
        """
        if not strategies:
            raise ValueError("SubtitlePipeline requires at least one strategy.")
        self._strategy_classes = strategies
        # Instantiate strategies - they are stateful only for the duration of one pipeline run
        self._strategies = [cls() for cls in self._strategy_classes]
        logger.info(f"Pipeline initialized with strategies: {[s.name for s in self._strategies]}")

    def run(self, context: ProcessingContext) -> bool:  # noqa: C901
        """
        Executes the configured strategies sequentially on the context.

        Args:
            context (ProcessingContext): The processing context, which will be mutated
                                         by the strategies.

        Returns:
            bool: True if a final subtitle (RO or EN) was successfully
                  identified/processed and exists, False otherwise.
        """
        start_time = time.monotonic()
        video_basename = context.video_info.get("basename", "Unknown Video")
        logger.info(f"Starting Pipeline for: {video_basename}")

        overall_success = False
        try:
            # --- Execute Strategies Sequentially ---
            for strategy in self._strategies:
                strategy_start_time = time.monotonic()
                logger.info(f"Executing Strategy: {strategy.name}...")

                # --- Early Exit Condition Check ---
                # If the primary goal (finding a definitive RO subtitle) is already met,
                # skip strategies that primarily search for subtitles (e.g., scanners, fetchers).
                # We might still run Translator (won't do anything if RO found) and Synchronizer.
                # Customize this logic if finer control is needed.
                if context.found_final_ro and strategy.name in [
                    "LocalScanner",
                    "OnlineFetcher",
                    "FinalSelector",
                ]:
                    logger.info(
                        f"Skipping strategy '{strategy.name}': Final RO subtitle already found."
                    )
                    continue
                # Add more sophisticated skip conditions if needed (e.g., skip translation if skip flag set)

                # --- Execute Strategy ---
                try:
                    strategy_success = strategy.execute(context)
                except Exception as strategy_exec_err:
                    # Catch unexpected errors *within* a strategy's execute method
                    logger.error(
                        f"Strategy '{strategy.name}' execution failed with unexpected error: {strategy_exec_err}",
                        exc_info=True,
                    )
                    context.add_error(strategy.name, f"Execution failed: {strategy_exec_err}")
                    strategy_success = False  # Treat unexpected error as failure

                strategy_duration = time.monotonic() - strategy_start_time
                logger.info(
                    f"Strategy {strategy.name} finished in {strategy_duration:.3f}s. Success reported: {strategy_success}"
                )

                # --- Handle Strategy Failure Reporting ---
                if not strategy_success:
                    # Log that the strategy reported failure.
                    if strategy.is_critical:
                        logger.error(
                            f"CRITICAL failure in mandatory strategy '{strategy.name}'. "
                            "Aborting pipeline execution to report failure."
                        )
                        # Ensure we don't accidentally report success if a critical step failed
                        overall_success = False
                        break  # Stop the pipeline
                    else:
                        logger.warning(
                            f"Strategy '{strategy.name}' reported failure or encountered an error. "
                            "Pipeline continuing (Non-critical)..."
                        )

                # --- Log RO Goal Achievement ---
                # Check if the primary goal (RO sub) was achieved by *this* strategy
                if context.found_final_ro and not hasattr(strategy, "_ro_goal_logged"):
                    logger.info(
                        f"Pipeline goal (RO subtitle) achieved or confirmed by strategy '{strategy.name}'."
                    )
                    # Mark that we've logged this to avoid repeat messages
                    strategy._ro_goal_logged = True
                    # Pipeline continues to allow subsequent steps like synchronization.

            # --- Final Status Determination (After all strategies run) ---
            if context.found_final_ro:
                # Check if the RO result is valid (path exists or it's embedded text)
                ro_path = context.final_ro_sub_path_or_status
                if ro_path == "embedded_text_ro":
                    logger.info(
                        f"Pipeline Result: Final RO subtitle confirmed (Embedded Text) for {video_basename}."
                    )
                    overall_success = True
                elif ro_path and Path(ro_path).exists():
                    logger.info(
                        f"Pipeline Result: Final RO subtitle identified/processed (File: {Path(ro_path).name}) for {video_basename}."
                    )
                    overall_success = True
                else:
                    logger.error(
                        f"Pipeline Result: RO flag set, but final path '{ro_path}' is invalid or missing for {video_basename}."
                    )
                    overall_success = False  # RO flag set, but result is bad

            elif context.final_en_sub_path and Path(context.final_en_sub_path).exists():
                # RO goal wasn't met, check if a valid EN subtitle was finalized
                logger.info(
                    f"Pipeline Result: Final EN subtitle selected (File: {Path(context.final_en_sub_path).name}) for {video_basename} (RO not found/processed)."
                )
                overall_success = (
                    True  # Count finding a valid EN file as success if RO wasn't found
                )
            else:
                # No RO and no valid final EN path found
                logger.warning(
                    f"Pipeline Result: No suitable final subtitle (RO or EN) found or processed for {video_basename}."
                )
                overall_success = False

        except Exception as e:
            # Catch unexpected errors during pipeline orchestration itself
            logger.critical(
                f"Pipeline execution interrupted by unexpected error: {e}", exc_info=True
            )
            context.add_error("Pipeline", f"Unexpected critical error: {e}")
            overall_success = False
        finally:
            # --- Cleanup Temporary Directories ---
            if context.temp_dirs_to_clean:
                logger.info(
                    f"Cleaning up {len(context.temp_dirs_to_clean)} temporary director{'y' if len(context.temp_dirs_to_clean) == 1 else 'ies'}..."
                )
                # Iterate over a copy in case the set is modified during cleanup (unlikely but safe)
                for temp_dir in list(context.temp_dirs_to_clean):
                    file_utils.clean_temp_directory(temp_dir)
                context.temp_dirs_to_clean.clear()  # Clear the set in the context

            # --- Shutdown Services (e.g., logout) ---
            # This calls the shutdown method on the DI container instance passed in the context
            if context.di:
                logger.info("Shutting down services via DI container...")
                context.di.shutdown()
            else:
                logger.warning(
                    "DI container not found in context. Cannot perform service shutdown."
                )

            # --- Final Logging ---
            pipeline_duration = time.monotonic() - start_time
            log_level = logging.INFO if overall_success else logging.WARNING
            logger.log(
                log_level,
                f"Pipeline Finished for: {video_basename} in {pipeline_duration:.2f}s. Overall Success: {overall_success}",
            )
            if context.errors:
                logger.warning(
                    f"Errors encountered during pipeline execution ({len(context.errors)}):"
                )
                for err in context.errors:
                    logger.warning(f"  - {err}")

        return overall_success
