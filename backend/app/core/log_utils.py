# backend/app/core/log_utils.py
"""Utilities for safe logging to prevent log injection attacks.

This module provides comprehensive sanitization for logging:
- ANSI escape sequence removal (terminal manipulation)
- Control character neutralization (log injection/forging)
- Unicode normalization (reduces some confusables, optional)
- Bidirectional control stripping (visual spoofing/Trojan Source)
- Invisible character removal (zero-width spoofing, optional)
- Circular reference detection (crash prevention)
- Length/depth/item limits (DoS prevention)

WARNING: This sanitizer does NOT prevent format-string injection.
Always use: logger.info("%s", user_input) NOT logger.info(user_input)
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

# ============================================================================
# Pre-compiled regex patterns for performance
# ============================================================================

# Complete ANSI escape handling: CSI, OSC, and single-char ESC sequences
_ANSI_RE = re.compile(
    r"""
    \x1B
    (?:
        [@-Z\\-_]                          # 7-bit C1 control (Fe)
      | \[ [0-?]* [ -/]* [@-~]             # CSI ... Cmd (ECMA-48)
      | \] (?: [^\x07\x1B]* (?:\x07|\x1B\\))  # OSC ... BEL or ST
    )
    """,
    re.VERBOSE,
)

# Control characters EXCLUDING standard whitespace (\t=0x09, \n=0x0A, \r=0x0D)
# We handle whitespace separately via escape_whitespace logic.
# Matches:
# - \x00-\x08 (Null -> Backspace)
# - \x0b-\x0c (Vertical Tab, Form Feed)
# - \x0e-\x1f (Shift Out -> Unit Separator)
# - \x7f-\x9f (DEL + C1 controls)
_UNSAFE_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Bidirectional control characters (prevents "Trojan Source" visual tricks)
_BIDI_RE = re.compile(r"[\u202A-\u202E\u2066-\u2069\u200E\u200F]")

# Invisible/zero-width characters (log viewer spoofing)
# Zero Width Space, Zero Width Joiner/Non-Joiner, Word Joiner, Soft Hyphen
# NOTE: Removing ZWJ/ZWNJ can affect some languages. Set strip_invisible=False if needed.
_INVISIBLE_RE = re.compile(r"[\u200B-\u200D\u2060\u00AD]")


# ============================================================================
# Main sanitization functions
# ============================================================================


def sanitize_for_log(
    value: Any,
    max_length: int | None = 1000,
    *,
    escape_whitespace: bool = True,
    strip_bidi: bool = True,
    strip_invisible: bool = True,
    normalize_unicode: bool = False,
) -> str:
    """Sanitize user-controlled values for safe logging.

    Protects against:
    - Log injection/forging (newlines, control chars)
    - Terminal manipulation (ANSI escape sequences)
    - Visual spoofing (bidirectional controls, invisible chars)
    - Log flooding (length limits)

    Args:
        value: Any value to sanitize (will be converted to string)
        max_length: Maximum output length. None for no limit.
        escape_whitespace: If True (RECOMMENDED), converts \\n, \\r, \\t to visible literals
                           for safe line-oriented logging. If False (UNSAFE MODE), preserves
                           raw newlines but still removes \\r to prevent terminal overwrites.
                           Only set to False if using structured/JSON logging where the
                           encoder handles escaping. Note: escape_whitespace=False can enable
                           log forging in line-oriented logs.
        strip_bidi: If True, remove bidirectional control characters.
        strip_invisible: If True, remove zero-width and other invisible characters.
                        Note: This can affect rendering in some languages (Arabic, Devanagari).
        normalize_unicode: If True, apply NFKC normalization to reduce some compatibility
                          variants (ligatures, fullwidth forms). Does NOT prevent all
                          homograph attacks (e.g., cross-script confusables like Latin 'a'
                          vs Cyrillic 'a'-lookalike). Use with caution as it modifies content.

    Returns:
        Sanitized string safe for logging (with caveats for escape_whitespace=False)

    Examples:
        >>> sanitize_for_log("Hello\\nWorld")
        'Hello\\\\nWorld'
        >>> sanitize_for_log("User: \\x1b[31mRED\\x1b[0m")
        'User: RED'
        >>> sanitize_for_log(None)
        '<None>'
        >>> sanitize_for_log("Line 1\\nLine 2", escape_whitespace=False)
        'Line 1\\nLine 2'  # Raw newline preserved (UNSAFE for line-oriented logs)
    """
    # Handle None explicitly for better debugging
    if value is None:
        return "<None>"

    # 1. Safe string conversion (handles buggy __str__ implementations)
    try:
        text = str(value)
    except Exception:
        try:
            text = repr(value)
        except Exception:
            return f"<Error converting to string: {type(value).__name__}>"

    # 2. Unicode normalization (NFKC) - reduces some confusables
    # NOTE: This changes original content and doesn't prevent all homograph attacks
    if normalize_unicode:
        try:
            text = unicodedata.normalize("NFKC", text)
        except Exception:
            # Continue without normalization if it fails
            pass

    # 3. Remove ANSI escape sequences (terminal manipulation attacks)
    text = _ANSI_RE.sub("", text)

    # 4. Handle standard whitespace and Unicode line separators
    if escape_whitespace:
        # Order matters: escape backslashes first to avoid double-escaping!
        text = (
            text.replace("\\", "\\\\")  # \ → \\
            .replace("\r", "\\r")  # CR → \r (visible)
            .replace("\n", "\\n")  # LF → \n (visible)
            .replace("\t", "\\t")  # Tab → \t (visible)
            .replace("\u2028", "\\u2028")  # Line Separator → escaped
            .replace("\u2029", "\\u2029")  # Paragraph Separator → escaped
        )
    else:
        # UNSAFE MODE: Even when preserving newlines, remove \r to prevent
        # carriage-return overwrites in terminals/viewers
        text = text.replace("\r", "")
        # Also neutralize Unicode line separators (break JS/JSON parsers)
        text = text.replace("\u2028", "").replace("\u2029", "")

    # 5. Remove unsafe control characters (null bytes, vertical tabs, etc.)
    # This regex excludes \t, \n, \r so they're preserved if escape_whitespace=False
    text = _UNSAFE_CTRL_RE.sub("", text)

    # 6. Strip bidirectional override characters (Trojan Source protection)
    if strip_bidi:
        text = _BIDI_RE.sub("", text)

    # 7. Strip invisible/zero-width characters (log viewer spoofing)
    if strip_invisible:
        text = _INVISIBLE_RE.sub("", text)

    # 8. Truncate to prevent log flooding/DoS
    if max_length is not None and len(text) > max_length:
        suffix = "...[truncated]"
        # Ensure keep is non-negative even if max_length is very small
        keep = max(0, max_length - len(suffix))
        text = text[:keep] + suffix

    return text


def sanitize_for_structured_log(  # noqa: C901
    value: Any,
    *,
    max_str_len: int = 1000,
    max_depth: int = 10,
    max_items: int = 200,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> Any:
    """Sanitize values for structured logging (e.g., JSON logs).

    Recursively sanitizes data structures while:
    - Sanitizing all strings (including dict keys)
    - Detecting and breaking circular references
    - Limiting recursion depth
    - Limiting collection sizes
    - Preserving primitive types
    - Handling key collisions in dictionaries
    - Converting bytes to safe strings

    Args:
        value: Value to sanitize (any type)
        max_str_len: Maximum length for string values
        max_depth: Maximum recursion depth
        max_items: Maximum items in collections (lists/dicts/sets)
        _depth: Internal recursion depth counter
        _seen: Internal set for cycle detection (current recursion stack)

    Returns:
        Sanitized value safe for JSON serialization

    Examples:
        >>> sanitize_for_structured_log({"user": "admin\\n", "count": 42})
        {'user': 'admin\\\\n', 'count': 42}
        >>> circular = {"a": None}
        >>> circular["a"] = circular
        >>> sanitize_for_structured_log(circular)
        {'a': '[circular]'}
        >>> sanitize_for_structured_log({"key": 1, "key\\u200b": 2})  # collision
        {'key': 1, 'key#1': 2}
    """
    # Check recursion depth limit
    if _depth > max_depth:
        return "[max_depth]"

    # Initialize cycle detection set on first call
    if _seen is None:
        _seen = set()

    # Pass through primitives unchanged
    if value is None or isinstance(value, (bool, int, float)):
        return value

    # Sanitize strings
    if isinstance(value, str):
        return sanitize_for_log(value, max_length=max_str_len)

    # Handle bytes/bytearray - decode safely with replacement for invalid sequences
    if isinstance(value, (bytes, bytearray)):
        try:
            decoded = value.decode("utf-8", errors="backslashreplace")
            return sanitize_for_log(decoded, max_length=max_str_len)
        except Exception:
            # Fallback if decode fails somehow
            return sanitize_for_log(repr(value), max_length=max_str_len)

    # Cycle detection for reference types
    # Tracks objects on current recursion stack only (allows diamond patterns)
    obj_id = id(value)
    if obj_id in _seen:
        return "[circular]"
    _seen.add(obj_id)

    try:
        # Handle dictionaries and mappings
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for i, (k, v) in enumerate(value.items()):
                # Limit number of items to prevent DoS
                if i >= max_items:
                    out["[truncated_items]"] = True
                    break

                # Sanitize key with EXPLICIT escape_whitespace=True
                # This prevents multiline keys even if default changes
                safe_key = sanitize_for_log(k, max_length=200, escape_whitespace=True)

                # Handle key collisions robustly
                # Loop until we find a unique key (handles pre-existing "#1" suffixes)
                base_key = safe_key
                suffix_n = 1
                while safe_key in out:
                    safe_key = f"{base_key}#{suffix_n}"
                    suffix_n += 1

                # Ensure key length doesn't exceed limit after suffix addition
                if len(safe_key) > 200:
                    safe_key = safe_key[:200]

                # Recursively sanitize values
                out[safe_key] = sanitize_for_structured_log(
                    v,
                    max_str_len=max_str_len,
                    max_depth=max_depth,
                    max_items=max_items,
                    _depth=_depth + 1,
                    _seen=_seen,
                )
            return out

        # Handle sequences (lists, tuples, sets, frozensets)
        if isinstance(value, (list, tuple, set, frozenset)):
            # For sets/frozensets, try to sort for stable, deterministic output
            # Falls back to unsorted if items aren't comparable (e.g., mixed types)
            if isinstance(value, (set, frozenset)):
                try:
                    iterable: list[Any] | tuple[Any, ...] = sorted(value)
                except Exception:
                    # Can't sort mixed types in Python 3 - use insertion order
                    iterable = list(value)
            else:
                iterable = value

            out_list = []
            for i, item in enumerate(iterable):
                if i >= max_items:
                    out_list.append("[truncated_items]")
                    break

                out_list.append(
                    sanitize_for_structured_log(
                        item,
                        max_str_len=max_str_len,
                        max_depth=max_depth,
                        max_items=max_items,
                        _depth=_depth + 1,
                        _seen=_seen,
                    )
                )

            # Preserve tuple type (JSON will still serialize as array,
            # but Python processors may care)
            return tuple(out_list) if isinstance(value, tuple) else out_list

        # Fallback for custom objects: sanitize their string representation
        return sanitize_for_log(value, max_length=max_str_len)

    finally:
        # Clean up cycle detection for this branch
        # Allows the same object to appear in different branches (diamond pattern)
        _seen.discard(obj_id)


# ============================================================================
# Convenience aliases and helpers
# ============================================================================


def safe_log_str(value: Any) -> str:
    """Convenience alias for sanitize_for_log with defaults.

    Usage:
        logger.info(f"User {safe_log_str(username)} logged in")
    """
    return sanitize_for_log(value)


def safe_log_dict(data: Mapping[Any, Any]) -> dict[str, Any]:
    """Convenience alias for sanitizing dictionaries and mappings.

    Accepts any Mapping type (dict, UserDict, OrderedDict, etc.) and returns
    a sanitized dict with string keys safe for JSON serialization.

    Usage:
        logger.info("User data", extra=safe_log_dict(user_data))
    """
    result = sanitize_for_structured_log(data)
    # Ensure we return a dict (sanitize_for_structured_log should return dict for Mapping)
    if isinstance(result, dict):
        return result
    return {"value": result}
