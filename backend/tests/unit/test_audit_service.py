from app.services.audit_service import compute_event_hash, get_severity, sanitize_details


def test_sanitize_details_allowed_keys():
    details = {"changed_fields": ["status"], "secret_token": "hidden"}
    sanitized = sanitize_details(details)
    assert "changed_fields" in sanitized
    assert "secret_token" not in sanitized


def test_sanitize_details_size_cap():
    # Large value that exceeds MAX_DETAILS_SIZE (32KB)
    large_details = {"reason": "a" * 100000}
    sanitized = sanitize_details(large_details)
    assert sanitized["_truncated"] is True
    # 'reason' might be deleted to get under the limit
    assert "reason" not in sanitized


def test_compute_event_hash_consistency():
    params = {
        "event_id": "uuid-123",
        "timestamp": "2024-01-01T00:00:00Z",
        "action": "auth.login",
        "actor_user_id": "user-456",
        "target_user_id": None,
        "resource_type": None,
        "resource_id": None,
        "success": True,
        "http_status": 200,
        "details": {"method": "password"},
        "prev_hash": "hash-abc",
    }
    hash1 = compute_event_hash(**params)
    hash2 = compute_event_hash(**params)
    assert hash1 == hash2


def test_get_severity_mapping():
    assert get_severity("auth.login", True) == "info"
    assert get_severity("auth.login", False) == "warning"
    assert get_severity("auth.mfa.disable", True) == "critical"
    assert get_severity("security.suspicious_token", False) == "critical"
