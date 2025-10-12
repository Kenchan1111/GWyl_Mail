"""
Test Robust Sigstore Identity Extraction - Sprint 3

Tests the new sigstore_identity module that properly extracts
certificate identity using cryptography X.509 parsing.
"""
import json
import tempfile
from pathlib import Path

import pytest

from gwyl_mail.sigstore_identity import (
    extract_identity_from_bundle,
    verify_identity_against_policy,
    SignatureIdentity,
)


def test_signature_identity_dataclass():
    """Test SignatureIdentity dataclass initialization"""
    identity = SignatureIdentity()
    assert identity.email is None
    assert identity.issuer is None
    assert identity.rekor_log_index is None
    assert identity.rekor_timestamp is None
    assert identity.san_emails == []

    identity2 = SignatureIdentity(
        email="alice@example.com",
        issuer="https://accounts.google.com",
        rekor_log_index=12345,
        rekor_timestamp=1704931200,
        san_emails=["alice@example.com"]
    )
    assert identity2.email == "alice@example.com"
    assert identity2.issuer == "https://accounts.google.com"


def test_extract_identity_missing_file():
    """Test that missing bundle file raises ValueError"""
    with pytest.raises(ValueError, match="Bundle file not found"):
        extract_identity_from_bundle(Path("/nonexistent/bundle.json"))


def test_extract_identity_invalid_json():
    """Test that invalid JSON raises ValueError"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("invalid json{{{")
        temp_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="Failed to parse"):
            extract_identity_from_bundle(temp_path)
    finally:
        temp_path.unlink()


def test_extract_identity_empty_bundle():
    """Test extraction from minimal/empty bundle"""
    bundle_data = {
        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.1",
        "verificationMaterial": {},
        "messageSignature": {"signature": ""}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(bundle_data, f)
        temp_path = Path(f.name)

    try:
        identity = extract_identity_from_bundle(temp_path)
        # Should not crash, but may have no data
        assert isinstance(identity, SignatureIdentity)
    finally:
        temp_path.unlink()


def test_verify_identity_no_email():
    """Test verification fails when identity has no email"""
    identity = SignatureIdentity()
    valid, reason = verify_identity_against_policy(identity, "alice@example.com")

    assert valid is False
    assert "No email found" in reason


def test_verify_identity_email_match():
    """Test verification succeeds on email match"""
    identity = SignatureIdentity(email="alice@example.com")
    valid, reason = verify_identity_against_policy(identity, "alice@example.com")

    assert valid is True
    assert reason == "Identity verified"


def test_verify_identity_email_mismatch():
    """Test verification fails on email mismatch"""
    identity = SignatureIdentity(email="alice@example.com")
    valid, reason = verify_identity_against_policy(identity, "bob@example.com")

    assert valid is False
    assert "mismatch" in reason.lower()


def test_verify_identity_case_insensitive():
    """Test email verification is case-insensitive"""
    identity = SignatureIdentity(email="Alice@Example.COM")
    valid, reason = verify_identity_against_policy(identity, "alice@example.com")

    assert valid is True
    assert reason == "Identity verified"


def test_verify_identity_issuer_whitelist_allowed():
    """Test issuer whitelist allows matching issuer"""
    identity = SignatureIdentity(
        email="alice@example.com",
        issuer="https://accounts.google.com"
    )
    valid, reason = verify_identity_against_policy(
        identity,
        "alice@example.com",
        allowed_issuers=["https://accounts.google.com", "https://github.com"]
    )

    assert valid is True


def test_verify_identity_issuer_whitelist_blocked():
    """Test issuer whitelist blocks non-matching issuer"""
    identity = SignatureIdentity(
        email="alice@example.com",
        issuer="https://evil-issuer.com"
    )
    valid, reason = verify_identity_against_policy(
        identity,
        "alice@example.com",
        allowed_issuers=["https://accounts.google.com", "https://github.com"]
    )

    assert valid is False
    assert "Issuer not allowed" in reason


def test_verify_identity_issuer_substring_match():
    """Test issuer whitelist uses substring matching"""
    identity = SignatureIdentity(
        email="alice@example.com",
        issuer="https://accounts.google.com/oauth"
    )
    valid, reason = verify_identity_against_policy(
        identity,
        "alice@example.com",
        allowed_issuers=["https://accounts.google.com"]
    )

    # Should match because "https://accounts.google.com" is in the issuer
    assert valid is True


def test_extract_identity_fallback_json_parsing():
    """
    Test fallback JSON parsing when sigstore models fail

    This creates a minimal bundle structure to test the _extract_from_raw_json
    fallback path.
    """
    # Create a bundle with basic structure but without full sigstore format
    bundle_data = {
        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.1",
        "verificationMaterial": {
            "tlogEntries": [{
                "logIndex": 12345,
                "integratedTime": 1704931200
            }]
        },
        "messageSignature": {"signature": "dummysig"}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(bundle_data, f)
        temp_path = Path(f.name)

    try:
        identity = extract_identity_from_bundle(temp_path)
        # Should extract Rekor data even without certificate
        assert identity.rekor_log_index == 12345
        assert identity.rekor_timestamp == 1704931200
    finally:
        temp_path.unlink()


def test_signature_identity_with_multiple_san_emails():
    """Test SignatureIdentity can store multiple SAN emails"""
    identity = SignatureIdentity(
        email="alice@example.com",
        san_emails=["alice@example.com", "alice@company.com"]
    )

    assert len(identity.san_emails) == 2
    assert "alice@example.com" in identity.san_emails
    assert "alice@company.com" in identity.san_emails
    assert identity.email == "alice@example.com"  # Primary


def test_verify_identity_no_issuer_with_whitelist():
    """Test verification when issuer is None but whitelist is provided"""
    identity = SignatureIdentity(
        email="alice@example.com",
        issuer=None
    )
    # Should succeed because issuer check is skipped when identity.issuer is None
    valid, reason = verify_identity_against_policy(
        identity,
        "alice@example.com",
        allowed_issuers=["https://accounts.google.com"]
    )

    # Current implementation only checks issuer if identity.issuer is truthy
    assert valid is True
