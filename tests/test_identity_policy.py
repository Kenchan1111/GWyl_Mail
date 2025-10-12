"""
Test Identity Policy - Sprint 2
Reference: IDENTITY_POLICY_v0.md and identity_policy.py implementation
"""
import tempfile
from pathlib import Path

import pytest
import yaml

from gwyl_mail.identity_policy import IdentityPolicy


def test_exact_match_default():
    """
    Test exact match with default configuration (tolerance: exact)
    """
    policy = IdentityPolicy()

    result = policy.verify(
        from_email="alice@company.com",
        cert_subject="alice@company.com",
        cert_issuer="https://accounts.google.com"
    )

    assert result["valid"] is True
    assert result["from_cert"] is True


def test_exact_mismatch_default():
    """
    Test exact mismatch: from != certificate subject (no tolerance)
    """
    policy = IdentityPolicy()

    result = policy.verify(
        from_email="alice@company.com",
        cert_subject="mallory@evil.com",
        cert_issuer="https://accounts.google.com"
    )

    assert result["valid"] is False
    assert result["from_cert"] is False


def test_domain_tolerance():
    """
    Test domain tolerance: from and cert have same domain
    Reference: IDENTITY_POLICY_v0.md - Domain tolerance
    """
    policy_data = {
        "enforcement_mode": "strict",
        "validation_rules": [
            {"name": "from_matches_cert", "tolerance": "domain"}
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # noreply@company.com can be signed by alice@company.com (same domain)
        result = policy.verify(
            from_email="noreply@company.com",
            cert_subject="alice@company.com",
            cert_issuer="https://accounts.google.com"
        )

        assert result["valid"] is True
        assert result["from_cert"] is True

    finally:
        temp_path.unlink()


def test_domain_tolerance_fail_different_domain():
    """
    Test domain tolerance fails when domains differ
    """
    policy_data = {
        "enforcement_mode": "strict",
        "validation_rules": [
            {"name": "from_matches_cert", "tolerance": "domain"}
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # noreply@company.com cannot be signed by alice@otherdomain.com
        result = policy.verify(
            from_email="noreply@company.com",
            cert_subject="alice@otherdomain.com",
            cert_issuer="https://accounts.google.com"
        )

        assert result["valid"] is False
        assert result["from_cert"] is False

    finally:
        temp_path.unlink()


def test_alias_tolerance():
    """
    Test alias tolerance: from is in aliases list
    """
    policy_data = {
        "enforcement_mode": "strict",
        "validation_rules": [
            {"name": "from_matches_cert", "tolerance": "alias"}
        ],
        "aliases": {
            "robert@company.com": {
                "allowed_aliases": ["bob@company.com", "robert@company.com"]
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # bob@company.com can be signed by robert@company.com (alias)
        result = policy.verify(
            from_email="bob@company.com",
            cert_subject="robert@company.com",
            cert_issuer="https://any-issuer.com"
        )

        assert result["valid"] is True
        assert result["from_cert"] is True

    finally:
        temp_path.unlink()


def test_alias_tolerance_fail_not_in_list():
    """
    Test alias tolerance fails when from is not in aliases list
    """
    policy_data = {
        "enforcement_mode": "strict",
        "validation_rules": [
            {"name": "from_matches_cert", "tolerance": "alias"}
        ],
        "aliases": {
            "robert@company.com": {
                "allowed_aliases": ["bob@company.com"]
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # charlie@company.com is not an alias for robert@company.com
        result = policy.verify(
            from_email="charlie@company.com",
            cert_subject="robert@company.com",
            cert_issuer="https://any-issuer.com"
        )

        assert result["valid"] is False
        assert result["from_cert"] is False

    finally:
        temp_path.unlink()


def test_issuer_whitelist():
    """
    Test issuer whitelist enforcement
    """
    policy_data = {
        "enforcement_mode": "strict",
        "allowed_issuers": [
            "https://accounts.google.com",
            "https://github.com/login/oauth"
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Valid issuer
        result = policy.verify(
            from_email="alice@company.com",
            cert_subject="alice@company.com",
            cert_issuer="https://accounts.google.com"
        )
        assert result["valid"] is True
        assert result["issuer"] is True

        # Invalid issuer
        result = policy.verify(
            from_email="alice@company.com",
            cert_subject="alice@company.com",
            cert_issuer="https://evil-issuer.com"
        )
        assert result["valid"] is False
        assert result["issuer"] is False

    finally:
        temp_path.unlink()


def test_domain_whitelist():
    """
    Test domain whitelist enforcement
    """
    policy_data = {
        "enforcement_mode": "strict",
        "allowed_domains": ["company.com", "partner.com"]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Valid domain
        result = policy.verify(
            from_email="alice@company.com",
            cert_subject="alice@company.com",
            cert_issuer="https://any-issuer.com"
        )
        assert result["valid"] is True
        assert result["domain"] is True

        # Invalid domain
        result = policy.verify(
            from_email="mallory@evil.com",
            cert_subject="mallory@evil.com",
            cert_issuer="https://any-issuer.com"
        )
        assert result["valid"] is False
        assert result["domain"] is False

    finally:
        temp_path.unlink()


def test_warn_enforcement_mode():
    """
    Test that warn enforcement mode returns "warn" even on mismatch
    """
    policy_data = {
        "enforcement_mode": "warn"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Mismatch but enforcement is warn
        result = policy.verify(
            from_email="alice@company.com",
            cert_subject="bob@company.com",
            cert_issuer="https://any-issuer.com"
        )

        # Should return enforcement=warn
        assert result.get("enforcement") == "warn"

    finally:
        temp_path.unlink()


def test_strict_enforcement_mode():
    """
    Test that strict enforcement mode returns "strict" on mismatch
    """
    policy_data = {
        "enforcement_mode": "strict"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Mismatch with strict enforcement
        result = policy.verify(
            from_email="alice@company.com",
            cert_subject="bob@company.com",
            cert_issuer="https://any-issuer.com"
        )

        assert result["valid"] is False
        assert result["enforcement"] == "strict"

    finally:
        temp_path.unlink()


def test_case_insensitive_email_matching():
    """
    Test that email addresses are matched case-insensitively
    """
    policy = IdentityPolicy()

    # Different cases should match
    result = policy.verify(
        from_email="Alice@Company.COM",
        cert_subject="alice@company.com",
        cert_issuer="https://any-issuer.com"
    )

    assert result["valid"] is True
    assert result["from_cert"] is True


def test_same_domain_helper():
    """
    Test the _same_domain helper method
    """
    policy = IdentityPolicy()

    assert policy._same_domain("alice@company.com", "bob@company.com") is True
    assert policy._same_domain("alice@company.com", "bob@other.com") is False
    assert policy._same_domain("ALICE@COMPANY.COM", "bob@company.com") is True


def test_check_alias_helper():
    """
    Test the _check_alias helper method
    """
    policy_data = {
        "aliases": {
            "alice@company.com": {
                "allowed_aliases": ["noreply@company.com", "support@company.com"]
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Test exact match (always allowed)
        assert policy._check_alias("alice@company.com", "alice@company.com") is True

        # Test allowed alias
        assert policy._check_alias("noreply@company.com", "alice@company.com") is True

        # Test not allowed alias
        assert policy._check_alias("other@company.com", "alice@company.com") is False

    finally:
        temp_path.unlink()


def test_issuer_ok_helper():
    """
    Test the _issuer_ok helper method
    """
    policy_data = {
        "allowed_issuers": ["https://accounts.google.com", "https://github.com"]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Test allowed issuer (substring match)
        assert policy._issuer_ok("https://accounts.google.com") is True
        assert policy._issuer_ok("https://github.com/login/oauth") is True

        # Test not allowed issuer
        assert policy._issuer_ok("https://evil.com") is False

    finally:
        temp_path.unlink()


def test_domain_ok_helper():
    """
    Test the _domain_ok helper method
    """
    policy_data = {
        "allowed_domains": ["company.com", "partner.org"]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(policy_data, f)
        temp_path = Path(f.name)

    try:
        policy = IdentityPolicy(temp_path)

        # Test allowed domain
        assert policy._domain_ok("alice@company.com") is True
        assert policy._domain_ok("bob@partner.org") is True

        # Test not allowed domain
        assert policy._domain_ok("mallory@evil.com") is False

    finally:
        temp_path.unlink()
