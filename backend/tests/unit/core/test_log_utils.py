# backend/tests/unit/core/test_log_utils.py
"""Unit tests for log_utils module - log sanitization utilities."""

from typing import Any

from app.core.log_utils import (
    safe_log_dict,
    safe_log_str,
    sanitize_for_log,
    sanitize_for_structured_log,
)


class TestSanitizeForLog:
    """Tests for the sanitize_for_log function."""

    # ==================== Basic Functionality ====================

    def test_basic_string_passthrough(self) -> None:
        """Normal strings should pass through unchanged."""
        assert sanitize_for_log("hello world") == "hello world"

    def test_none_handling(self) -> None:
        """None should return <None> marker."""
        assert sanitize_for_log(None) == "<None>"

    def test_non_string_conversion(self) -> None:
        """Non-strings should be converted to strings."""
        assert sanitize_for_log(123) == "123"
        assert sanitize_for_log(45.67) == "45.67"
        assert sanitize_for_log(True) == "True"
        assert sanitize_for_log(["a", "b"]) == "['a', 'b']"

    # ==================== Log Injection Prevention ====================

    def test_newline_escaping(self) -> None:
        """Newlines should be escaped to prevent log forging."""
        result = sanitize_for_log("line1\nline2")
        assert "\n" not in result
        assert "\\n" in result

    def test_carriage_return_escaping(self) -> None:
        """Carriage returns should be escaped."""
        result = sanitize_for_log("line1\rline2")
        assert "\r" not in result
        assert "\\r" in result

    def test_tab_escaping(self) -> None:
        """Tabs should be escaped."""
        result = sanitize_for_log("col1\tcol2")
        assert "\t" not in result
        assert "\\t" in result

    def test_log_injection_attack(self) -> None:
        """Classic log injection attack should be neutralized."""
        malicious = "admin\nFAKE LOG: [INFO] User deleted all data"
        result = sanitize_for_log(malicious)
        assert "\n" not in result
        assert "admin\\nFAKE LOG" in result

    def test_unicode_line_separators(self) -> None:
        """Unicode line separators should be escaped."""
        result = sanitize_for_log("line1\u2028line2\u2029line3")
        assert "\u2028" not in result
        assert "\u2029" not in result
        assert "\\u2028" in result
        assert "\\u2029" in result

    # ==================== ANSI Escape Sequence Removal ====================

    def test_ansi_color_removal(self) -> None:
        """ANSI color codes should be stripped."""
        result = sanitize_for_log("\x1b[31mRED TEXT\x1b[0m")
        assert "\x1b" not in result
        assert "RED TEXT" in result

    def test_ansi_cursor_movement(self) -> None:
        """ANSI cursor movement sequences should be stripped."""
        result = sanitize_for_log("\x1b[2J\x1b[HCleared screen")
        assert "\x1b" not in result
        assert "Cleared screen" in result

    def test_ansi_osc_sequences(self) -> None:
        """OSC (Operating System Command) sequences should be stripped."""
        result = sanitize_for_log("\x1b]0;Evil Title\x07Normal text")
        assert "\x1b" not in result
        assert "\x07" not in result
        assert "Normal text" in result

    # ==================== Control Character Removal ====================

    def test_null_byte_removal(self) -> None:
        """Null bytes should be removed."""
        result = sanitize_for_log("hello\x00world")
        assert "\x00" not in result
        assert "helloworld" in result

    def test_control_chars_removal(self) -> None:
        """Other control characters should be removed."""
        # Vertical tab, form feed, backspace
        result = sanitize_for_log("a\x0bb\x0cc\x08d")
        assert "\x0b" not in result
        assert "\x0c" not in result
        assert "\x08" not in result

    # ==================== Bidirectional Attack Prevention ====================

    def test_bidi_override_removal(self) -> None:
        """Bidirectional override characters should be stripped."""
        # RLO (Right-to-Left Override) - used in Trojan Source attacks
        result = sanitize_for_log("normal\u202edesrever")
        assert "\u202e" not in result

    def test_full_bidi_stripping(self) -> None:
        """All bidi control chars should be removed."""
        bidi_chars = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f"
        result = sanitize_for_log(f"text{bidi_chars}more")
        for char in bidi_chars:
            assert char not in result

    def test_bidi_optional_disable(self) -> None:
        """Bidi stripping can be disabled."""
        result = sanitize_for_log("a\u202eb", strip_bidi=False)
        assert "\u202e" in result

    # ==================== Invisible Character Removal ====================

    def test_zero_width_space_removal(self) -> None:
        """Zero-width spaces should be removed."""
        result = sanitize_for_log("admin\u200buser")
        assert "\u200b" not in result
        assert "adminuser" in result

    def test_invisible_chars_removal(self) -> None:
        """Various invisible characters should be removed."""
        # ZWSP, ZWJ, ZWNJ, Word Joiner, Soft Hyphen
        invisible = "\u200b\u200c\u200d\u2060\u00ad"
        result = sanitize_for_log(f"test{invisible}text")
        for char in invisible:
            assert char not in result

    def test_invisible_optional_disable(self) -> None:
        """Invisible char stripping can be disabled."""
        result = sanitize_for_log("a\u200bb", strip_invisible=False)
        assert "\u200b" in result

    # ==================== Length Limiting ====================

    def test_default_truncation(self) -> None:
        """Long strings should be truncated at 1000 chars by default."""
        long_text = "x" * 2000
        result = sanitize_for_log(long_text)
        assert len(result) <= 1000
        assert result.endswith("...[truncated]")

    def test_custom_max_length(self) -> None:
        """Custom max_length should be respected."""
        # Note: truncation adds "...[truncated]" suffix which is 14 chars
        # so max_length=20 on a 30 char string results in 20 char output
        result = sanitize_for_log("a" * 30, max_length=20)
        assert len(result) <= 20
        assert result.endswith("...[truncated]")

    def test_no_truncation_when_disabled(self) -> None:
        """No truncation when max_length is None."""
        long_text = "x" * 5000
        result = sanitize_for_log(long_text, max_length=None)
        assert len(result) == 5000

    # ==================== Backslash Handling ====================

    def test_existing_backslashes_escaped(self) -> None:
        """Existing backslashes should be escaped first."""
        result = sanitize_for_log("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_backslash_n_vs_newline(self) -> None:
        """Literal \\n should be distinguishable from escaped newline."""
        # Literal backslash-n in source
        result_literal = sanitize_for_log("line1\\nline2")
        # Actual newline character
        result_newline = sanitize_for_log("line1\nline2")
        # Both should show \\n but the literal had a backslash that got escaped
        assert "\\\\n" in result_literal  # \\n -> \\\\n
        assert "\\n" in result_newline  # \n -> \\n

    # ==================== Unicode Normalization ====================

    def test_unicode_normalization_optional(self) -> None:
        """Unicode normalization should be optional."""
        # Fullwidth 'A' (U+FF21) normalizes to 'A' under NFKC
        fullwidth_a = "\uff21"
        result_no_norm = sanitize_for_log(fullwidth_a, normalize_unicode=False)
        result_with_norm = sanitize_for_log(fullwidth_a, normalize_unicode=True)
        assert result_no_norm == fullwidth_a
        assert result_with_norm == "A"

    # ==================== Edge Cases ====================

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert sanitize_for_log("") == ""

    def test_only_control_chars(self) -> None:
        """String of only control chars should become empty."""
        result = sanitize_for_log("\x00\x01\x02")
        assert result == ""

    def test_escape_whitespace_false(self) -> None:
        """With escape_whitespace=False, newlines are preserved."""
        result = sanitize_for_log("line1\nline2", escape_whitespace=False)
        assert "\n" in result
        # But \r should still be removed
        result_cr = sanitize_for_log("line1\rline2", escape_whitespace=False)
        assert "\r" not in result_cr


class TestSanitizeForStructuredLog:
    """Tests for the sanitize_for_structured_log function."""

    # ==================== Basic Types ====================

    def test_primitives_unchanged(self) -> None:
        """Primitive types should pass through unchanged."""
        assert sanitize_for_structured_log(None) is None
        assert sanitize_for_structured_log(True) is True
        assert sanitize_for_structured_log(False) is False
        assert sanitize_for_structured_log(42) == 42
        assert sanitize_for_structured_log(3.14) == 3.14

    def test_string_sanitization(self) -> None:
        """Strings should be sanitized."""
        result = sanitize_for_structured_log("hello\nworld")
        assert "\n" not in result
        assert "\\n" in result

    def test_bytes_handling(self) -> None:
        """Bytes should be decoded and sanitized."""
        result = sanitize_for_structured_log(b"hello\nworld")
        assert isinstance(result, str)
        assert "\n" not in result

    # ==================== Dictionary Handling ====================

    def test_dict_value_sanitization(self) -> None:
        """Dict values should be sanitized."""
        result = sanitize_for_structured_log({"user": "admin\n", "count": 42})
        assert result["user"] == "admin\\n"
        assert result["count"] == 42

    def test_dict_key_sanitization(self) -> None:
        """Dict keys should be sanitized."""
        result = sanitize_for_structured_log({"key\nwith\nnewlines": "value"})
        assert "key\\nwith\\nnewlines" in result

    def test_nested_dict_sanitization(self) -> None:
        """Nested dicts should be recursively sanitized."""
        data = {"outer": {"inner": "value\n"}}
        result = sanitize_for_structured_log(data)
        assert result["outer"]["inner"] == "value\\n"

    # ==================== List/Sequence Handling ====================

    def test_list_sanitization(self) -> None:
        """List items should be sanitized."""
        result = sanitize_for_structured_log(["a\n", "b\r", 123])
        assert result == ["a\\n", "b\\r", 123]

    def test_tuple_preserved(self) -> None:
        """Tuples should be returned as tuples."""
        result = sanitize_for_structured_log(("a\n", "b"))
        assert isinstance(result, tuple)
        assert result == ("a\\n", "b")

    def test_set_sanitization(self) -> None:
        """Sets should be sanitized and converted to lists."""
        result = sanitize_for_structured_log({1, 2, 3})
        assert isinstance(result, list)
        assert sorted(result) == [1, 2, 3]

    # ==================== Circular Reference Detection ====================

    def test_circular_dict_reference(self) -> None:
        """Circular dict references should be detected."""
        circular: dict = {"a": None}
        circular["a"] = circular
        result = sanitize_for_structured_log(circular)
        assert result["a"] == "[circular]"

    def test_circular_list_reference(self) -> None:
        """Circular list references should be detected."""
        circular: list = [1, 2]
        circular.append(circular)
        result = sanitize_for_structured_log(circular)
        assert result[-1] == "[circular]"

    def test_diamond_pattern_allowed(self) -> None:
        """Diamond patterns (same object, different paths) should work."""
        shared = {"shared": "value"}
        data = {"a": shared, "b": shared}
        result = sanitize_for_structured_log(data)
        # Both should resolve correctly, not as circular
        assert result["a"]["shared"] == "value"
        assert result["b"]["shared"] == "value"

    # ==================== Depth Limiting ====================

    def test_max_depth_limiting(self) -> None:
        """Deep nesting should be limited."""
        deep: dict = {}
        current = deep
        for _ in range(20):
            current["next"] = {}
            current = current["next"]

        result = sanitize_for_structured_log(deep, max_depth=5)
        # Navigate down - should hit [max_depth] before bottom
        cursor: Any = result
        depth = 0
        while isinstance(cursor, dict) and "next" in cursor:
            cursor = cursor["next"]
            depth += 1
        assert cursor == "[max_depth]" or depth <= 10

    # ==================== Item Limiting ====================

    def test_dict_item_limiting(self) -> None:
        """Large dicts should be truncated."""
        large = {f"key{i}": i for i in range(300)}
        result = sanitize_for_structured_log(large, max_items=50)
        assert "[truncated_items]" in result
        assert len(result) <= 51  # 50 items + truncated marker

    def test_list_item_limiting(self) -> None:
        """Large lists should be truncated."""
        large = list(range(300))
        result = sanitize_for_structured_log(large, max_items=50)
        assert "[truncated_items]" in result
        assert len(result) <= 51

    # ==================== Key Collision Handling ====================

    def test_key_collision_handling(self) -> None:
        """Keys that collide after sanitization should get suffixes."""
        # After sanitization, "key\n" becomes "key\\n" which is different
        # from "key", so we need keys that truly become identical.
        # Use invisible characters that get stripped:
        data = {"key": 1, "key\u200b": 2}  # zero-width space gets stripped
        result = sanitize_for_structured_log(data)
        assert len(result) == 2
        assert "key" in result
        # Colliding keys get #1 suffix
        assert "key#1" in result

    # ==================== Edge Cases ====================

    def test_empty_dict(self) -> None:
        """Empty dict should return empty dict."""
        assert sanitize_for_structured_log({}) == {}

    def test_empty_list(self) -> None:
        """Empty list should return empty list."""
        assert sanitize_for_structured_log([]) == []

    def test_custom_object_fallback(self) -> None:
        """Custom objects should be stringified."""

        class CustomObj:
            def __str__(self) -> str:
                return "custom\nvalue"

        result = sanitize_for_structured_log(CustomObj())
        assert isinstance(result, str)
        assert "\n" not in result


class TestConvenienceFunctions:
    """Tests for safe_log_str and safe_log_dict."""

    def test_safe_log_str_basic(self) -> None:
        """safe_log_str should sanitize strings."""
        result = safe_log_str("user\nadmin")
        assert "\n" not in result
        assert "\\n" in result

    def test_safe_log_str_none(self) -> None:
        """safe_log_str should handle None."""
        assert safe_log_str(None) == "<None>"

    def test_safe_log_dict_basic(self) -> None:
        """safe_log_dict should sanitize dicts."""
        result = safe_log_dict({"user": "admin\n"})
        assert isinstance(result, dict)
        assert result["user"] == "admin\\n"

    def test_safe_log_dict_with_nested(self) -> None:
        """safe_log_dict should handle nested structures."""
        result = safe_log_dict({"outer": {"inner": "value\n"}})
        assert result["outer"]["inner"] == "value\\n"
