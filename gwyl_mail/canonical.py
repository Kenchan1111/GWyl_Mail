# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import hashlib
import re
import unicodedata
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser, Parser
from email.utils import getaddresses
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


# Default canonical headers (strict profile)
CANONICAL_HEADERS = ["from", "to", "subject", "date", "message-id"]

# MTA headers to exclude in relaxed profile (Sprint 6.2.1, extended per ChatGPT)
RELAXED_EXCLUDED_HEADERS = [
    # Routing headers
    "received", "return-path", "delivered-to", "x-original-to",
    # Authentication headers
    "dkim-signature", "arc-seal", "arc-message-signature", "arc-authentication-results",
    "authentication-results", "received-spf", "domainkey-signature",
    # Spam/virus filtering
    "x-spam-status", "x-spam-score", "x-spam-flag", "x-spam-level", "x-spam-report",
    "x-virus-scanned", "x-spam-checker-version",
    # MTA-specific headers
    "x-mailer", "x-originating-ip", "x-received", "x-priority", "x-msmail-priority",
    "importance", "x-google-smtp-source", "x-gm-message-state",
    # Microsoft Exchange headers
    "x-ms-exchange-organization-authas", "x-ms-exchange-organization-authsource",
    "x-ms-exchange-organization-authmechanism", "x-ms-has-attach", "x-ms-tnef-correlator",
    # AWS SES headers
    "x-ses-outgoing", "x-ses-receipt-id", "x-ses-configuration-set",
    # Feedback/security vendor headers
    "x-feedback-id", "x-proofpoint-virus-version", "x-proofpoint-spam-details",
    "x-barracuda-envelope-from", "x-barracuda-apparent-source-ip",
    # List management
    "list-id", "list-unsubscribe", "list-subscribe", "list-post",
    # Auto-reply
    "auto-submitted", "x-auto-response-suppress",
    # MIME version (can be added by MTA)
    "mime-version"
]


def _load_profile_config(profile: str = "strict") -> Dict[str, Any]:
    """Load canonicalization profile configuration (Sprint 6.2.1).

    Args:
        profile: Profile name ("strict" or "relaxed")

    Returns:
        Profile configuration dict
    """
    # Try to load from YAML config file
    config_path = Path(__file__).parent / "canonical_profiles.yml"
    if yaml and config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text())
            return config["profiles"].get(profile, config["profiles"]["strict"])
        except Exception:
            pass

    # Fallback to hardcoded configs
    if profile == "relaxed":
        return {
            "canonical_headers": CANONICAL_HEADERS,
            "excluded_headers": RELAXED_EXCLUDED_HEADERS,
            "whitespace": {"normalize": True, "trim": True, "normalize_tabs": True},
            "line_endings": {"normalize": True, "tolerate_wrapping": True},
            "addresses": {"lowercase_domain": True, "preserve_local": True}
        }
    else:  # strict
        return {
            "canonical_headers": CANONICAL_HEADERS,
            "excluded_headers": [],
            "whitespace": {"normalize": True, "trim": True},
            "line_endings": {"normalize": True},
            "addresses": {"lowercase_domain": True, "preserve_local": True}
        }


def _unfold(value: str, profile_config: Optional[Dict[str, Any]] = None) -> str:
    """Unfold header value, optionally with profile-specific rules."""
    result = re.sub(r"\r?\n[\t ]+", " ", value).strip()

    # Apply profile-specific whitespace normalization
    if profile_config and profile_config.get("whitespace", {}).get("normalize_tabs"):
        result = result.replace("\t", " ")

    return result


def _decode_rfc2047(value: str) -> str:
    parts = decode_header(value)
    out: List[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _normalize_addresses(value: str) -> str:
    # Lowercase only the domain part; preserve local-part and display name
    addrs = getaddresses([value])
    if not addrs:
        return value
    normalized = []
    for name, addr in addrs:
        if addr and "@" in addr:
            local, domain = addr.split("@", 1)
            addr = f"{local}@{domain.lower()}"
        if name:
            normalized.append(f"{name} <{addr}>")
        else:
            normalized.append(addr)
    return ", ".join(normalized)


def canonicalize_headers(msg: EmailMessage, profile: str = "strict") -> bytes:
    """Canonicalize email headers with profile support (Sprint 6.2.1).

    Args:
        msg: Email message
        profile: Canonicalization profile ("strict" or "relaxed")

    Returns:
        Canonicalized headers as bytes
    """
    profile_config = _load_profile_config(profile)
    canonical_headers = profile_config.get("canonical_headers", CANONICAL_HEADERS)
    excluded_headers = [h.lower() for h in profile_config.get("excluded_headers", [])]

    lines: List[str] = []
    for key in canonical_headers:
        # Skip if this header is excluded in the profile
        if key.lower() in excluded_headers:
            continue

        raw = msg.get(key, "")
        if not raw:
            continue
        v = _unfold(str(raw), profile_config)
        v = _decode_rfc2047(v)
        v = " ".join(v.split())
        if key in ("from", "to"):
            v = _normalize_addresses(v)
        # Unicode NFC normalization
        v = unicodedata.normalize('NFC', v)
        lines.append(f"{key}:{v}")
    return "\n".join(lines).encode("utf-8")


def canonicalize_body(msg: EmailMessage) -> bytes:
    # Prefer text/plain, else text/html as-is (V0 strict)
    if isinstance(msg, EmailMessage):
        body = msg.get_body(preferencelist=("plain", "html"))
        if not body:
            return b""
        content = body.get_content()
    else:
        return b""

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in content.split("\n")]
    normalized = "\n".join(lines)
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    # Unicode NFC normalization
    normalized = unicodedata.normalize('NFC', normalized)
    return normalized.encode("utf-8")


def canonicalize_attachments(msg: EmailMessage) -> List[bytes]:
    hashes: List[str] = []
    for part in msg.iter_attachments():
        payload = part.get_payload(decode=True)
        if payload:
            h = hashlib.sha256(payload).hexdigest()
            hashes.append(h)
    hashes.sort()
    return [f"attachment:sha256:{h}".encode("utf-8") for h in hashes]


def canonicalize(msg: EmailMessage, profile: str = "strict") -> bytes:
    """Canonicalize email message with profile support (Sprint 6.2.1).

    Args:
        msg: Email message
        profile: Canonicalization profile ("strict" or "relaxed")

    Returns:
        Canonicalized message as bytes
    """
    headers = canonicalize_headers(msg, profile)
    body = canonicalize_body(msg)
    atts = canonicalize_attachments(msg)
    parts: List[bytes] = [headers, b"\n", body]
    parts.extend([a + b"\n" for a in atts])
    return b"".join(parts)


def compute_hash(msg: EmailMessage, profile: str = "strict") -> str:
    """Compute hash of canonicalized message.

    Args:
        msg: Email message
        profile: Canonicalization profile ("strict" or "relaxed")

    Returns:
        SHA256 hex digest
    """
    return hashlib.sha256(canonicalize(msg, profile)).hexdigest()


class GWylCanonical:
    @staticmethod
    def hash(message: EmailMessage | bytes | str, profile: str = "strict") -> str:
        """Compute canonical hash of email message (Sprint 6.2.1: profile support).

        Args:
            message: Email message (EmailMessage, bytes, or string)
            profile: Canonicalization profile ("strict" or "relaxed")

        Returns:
            SHA256 hex digest of canonical form

        Examples:
            >>> GWylCanonical.hash(msg, profile="strict")   # Original behavior
            'abc123...'
            >>> GWylCanonical.hash(msg, profile="relaxed")  # Tolerates MTA mods
            'def456...'
        """
        if isinstance(message, EmailMessage):
            return compute_hash(message, profile)
        # If raw bytes/string provided, parse to EmailMessage
        if isinstance(message, bytes):
            m = BytesParser(policy=policy.default).parsebytes(message)
        else:
            m = Parser(policy=policy.default).parsestr(message)
        return compute_hash(m, profile)
