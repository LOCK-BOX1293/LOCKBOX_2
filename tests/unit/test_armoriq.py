from src.security.armoriq import ArmorIQClient, ArmorIQConfig


def test_armoriq_prefers_sanitized_text():
    client = ArmorIQClient(
        ArmorIQConfig(
            api_key="k",
            base_url="https://example.com",
            scan_path="/scan",
            timeout_seconds=5.0,
            fail_closed=True,
            app_name="hackbite2",
        )
    )

    resolved = client._resolve_text(
        {"allowed": True, "sanitized_text": "cleaned"}, original_text="raw"
    )

    assert resolved == "cleaned"


def test_armoriq_raises_on_blocked_payload():
    client = ArmorIQClient(
        ArmorIQConfig(
            api_key="k",
            base_url="https://example.com",
            scan_path="/scan",
            timeout_seconds=5.0,
            fail_closed=True,
            app_name="hackbite2",
        )
    )

    try:
        client._resolve_text(
            {"blocked": True, "message": "blocked by policy"}, original_text="raw"
        )
    except RuntimeError as exc:
        assert "blocked by policy" in str(exc)
    else:
        raise AssertionError("Expected blocked ArmorIQ payload to raise.")
