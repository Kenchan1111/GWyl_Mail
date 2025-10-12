"""
Robust Sigstore Identity Extraction

Uses sigstore-python library to properly parse bundle and extract:
- Certificate subject (email from SAN)
- Certificate issuer (OIDC provider)
- Rekor log entry timestamp

Reference: Sprint 3 - ChatGPT critical security issue #1
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from sigstore.models import Bundle, InvalidBundle
    from sigstore._internal.rekor.client import RekorClient
    from cryptography import x509
    from cryptography.x509.oid import ExtensionOID, NameOID
except ImportError:
    Bundle = None  # type: ignore
    InvalidBundle = None  # type: ignore
    RekorClient = None
    x509 = None
    ExtensionOID = None
    NameOID = None


@dataclass
class SignatureIdentity:
    """Extracted identity from Sigstore bundle"""
    email: Optional[str] = None
    issuer: Optional[str] = None
    rekor_log_index: Optional[int] = None
    rekor_timestamp: Optional[int] = None
    san_emails: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.san_emails is None:
            self.san_emails = []


def extract_identity_from_bundle(bundle_path: Path) -> SignatureIdentity:
    """
    Extract identity from Sigstore bundle using proper X.509 parsing

    Args:
        bundle_path: Path to the cosign bundle JSON file

    Returns:
        SignatureIdentity with email, issuer, and Rekor data

    Raises:
        ValueError: If bundle is invalid or cannot be parsed
        ImportError: If sigstore-python is not installed
    """
    if Bundle is None or x509 is None:
        raise ImportError(
            "sigstore-python not installed. "
            "Install with: pip install sigstore"
        )

    if not bundle_path.exists():
        raise ValueError(f"Bundle file not found: {bundle_path}")

    try:
        # Load bundle JSON
        bundle_data = json.loads(bundle_path.read_text())

        identity = SignatureIdentity()

        # Try to parse using sigstore-python Bundle model
        # If it fails, fall back to raw JSON parsing
        bundle = None
        try:
            bundle = Bundle.from_json(bundle_path.read_text())
        except (InvalidBundle, Exception):
            # Bundle format not valid for sigstore-python, use fallback
            return _extract_from_raw_json(bundle_data, identity)

        # Extract certificate from bundle
        cert_pem = None
        if hasattr(bundle, 'verification_material'):
            vm = bundle.verification_material
            if hasattr(vm, 'certificate'):
                cert_pem = vm.certificate

        if cert_pem:
            # Parse X.509 certificate
            from cryptography.hazmat.backends import default_backend
            cert = x509.load_pem_x509_certificate(
                cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
                default_backend()
            )

            # Extract SAN (Subject Alternative Name) emails
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                san_emails = [
                    email.value
                    for email in san_ext.value
                    if isinstance(email, x509.RFC822Name)
                ]
                identity.san_emails = san_emails
                if san_emails:
                    identity.email = san_emails[0]  # Primary email
            except x509.ExtensionNotFound:
                pass

            # Extract issuer from X.509 Issuer field
            try:
                issuer_attrs = cert.issuer.get_attributes_for_oid(
                    NameOID.COMMON_NAME
                )
                if issuer_attrs:
                    identity.issuer = issuer_attrs[0].value
            except Exception:
                pass

            # Also check for OIDC issuer in certificate extensions
            # Sigstore embeds OIDC issuer in custom OID 1.3.6.1.4.1.57264.1.1
            try:
                for ext in cert.extensions:
                    # Check for Fulcio OIDC Issuer extension
                    if ext.oid.dotted_string == "1.3.6.1.4.1.57264.1.1":
                        identity.issuer = ext.value.value.decode('utf-8')
                        break
            except Exception:
                pass

        # Extract Rekor log entry data
        if hasattr(bundle, 'verification_material'):
            vm = bundle.verification_material
            if hasattr(vm, 'transparency_entries') and vm.transparency_entries:
                entry = vm.transparency_entries[0]

                # Extract log index
                if hasattr(entry, 'log_index'):
                    identity.rekor_log_index = entry.log_index

                # Extract timestamp from integrated time
                if hasattr(entry, 'integrated_time'):
                    identity.rekor_timestamp = entry.integrated_time

        # Fallback: try to extract from raw JSON if sigstore models didn't work
        if not identity.email or not identity.issuer:
            identity = _extract_from_raw_json(bundle_data, identity)

        return identity

    except Exception as e:
        raise ValueError(f"Failed to parse Sigstore bundle: {e}")


def _extract_from_raw_json(bundle_data: dict, identity: SignatureIdentity) -> SignatureIdentity:
    """
    Fallback: extract identity from raw bundle JSON structure

    This is less robust but provides compatibility if sigstore-python
    models don't work with the bundle format.
    """
    # Try to find certificate in various locations
    cert_pem = None

    # Check verification material
    vm = bundle_data.get('verificationMaterial', {})
    if 'x509CertificateChain' in vm:
        certs = vm['x509CertificateChain'].get('certificates', [])
        if certs:
            cert_pem = certs[0].get('rawBytes')

    if cert_pem and not identity.email:
        try:
            from cryptography.hazmat.backends import default_backend
            import base64

            # Decode base64 certificate
            cert_der = base64.b64decode(cert_pem)
            cert = x509.load_der_x509_certificate(cert_der, default_backend())

            # Extract SAN emails
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                san_emails = [
                    email.value
                    for email in san_ext.value
                    if isinstance(email, x509.RFC822Name)
                ]
                if san_emails:
                    identity.email = san_emails[0]
                    identity.san_emails = san_emails
            except Exception:
                pass

            # Extract OIDC issuer
            try:
                for ext in cert.extensions:
                    if ext.oid.dotted_string == "1.3.6.1.4.1.57264.1.1":
                        identity.issuer = ext.value.value.decode('utf-8')
                        break
            except Exception:
                pass
        except Exception:
            pass

    # Extract Rekor data
    if not identity.rekor_timestamp:
        if 'verificationMaterial' in bundle_data:
            vm = bundle_data['verificationMaterial']
            if 'tlogEntries' in vm and vm['tlogEntries']:
                entry = vm['tlogEntries'][0]
                identity.rekor_log_index = entry.get('logIndex')
                identity.rekor_timestamp = entry.get('integratedTime')

    return identity


def verify_identity_against_policy(
    identity: SignatureIdentity,
    expected_email: str,
    allowed_issuers: Optional[list[str]] = None
) -> tuple[bool, str]:
    """
    Verify extracted identity against policy constraints

    Args:
        identity: Extracted SignatureIdentity
        expected_email: Expected email address (case-insensitive)
        allowed_issuers: Optional list of allowed OIDC issuers

    Returns:
        (valid, reason) tuple
    """
    if not identity.email:
        return False, "No email found in certificate"

    # Case-insensitive email match
    if identity.email.lower() != expected_email.lower():
        return False, f"Email mismatch: {identity.email} != {expected_email}"

    # Check issuer whitelist if provided
    if allowed_issuers and identity.issuer:
        if not any(allowed in identity.issuer for allowed in allowed_issuers):
            return False, f"Issuer not allowed: {identity.issuer}"

    return True, "Identity verified"
