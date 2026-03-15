"""Shared path-allowance helpers.

Centralizes the logic for checking whether a filesystem path falls under
one of the configured allowed media directories.  Used by both the jobs
router and the storage-paths browser endpoint.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_allowed_bases(allowed_paths_list: list[str]) -> list[Path]:
    """Resolve a list of allowed-path strings to ``Path`` objects.

    Paths that do not exist, cannot be resolved, or hit errors are
    silently skipped with a log message.
    """
    resolved: list[Path] = []
    for raw in allowed_paths_list:
        try:
            resolved.append(Path(raw).resolve(strict=True))
        except FileNotFoundError:
            logger.error(
                "Allowed base path '%s' does not exist or is a broken symlink. Skipping.", raw
            )
        except RuntimeError as exc:
            logger.error(
                "Resolution of allowed base path '%s' failed"
                " (e.g. symlink loop): %s",
                raw,
                exc,
            )
        except OSError as exc:
            logger.error(
                "Unexpected error resolving allowed base path '%s': %s",
                raw,
                exc,
            )
    return resolved


def is_path_allowed(resolved_path: Path, allowed_bases: list[Path]) -> bool:
    """Return ``True`` if *resolved_path* is one of the allowed bases or a descendant."""
    for base in allowed_bases:
        if resolved_path == base or base in resolved_path.parents:
            return True
    return False
