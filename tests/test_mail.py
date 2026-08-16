from agentic.mail import extract_otp, status


def test_extract_otp() -> None:
    assert extract_otp("O código é 847291") == "847291"
    assert extract_otp("sem codigo") is None


def test_status_does_not_include_api_key_value() -> None:
    payload = status()
    blob = str(payload)
    assert "am_" not in blob
    assert "api_key" not in payload
    assert isinstance(payload.get("api_key_present"), bool)
