# SPDX-License-Identifier: GPL-3.0-only
"""Embed and extract proofs inside EML messages (SPRINT 9).

The proof travels WITH the email: 'sign' attaches the DSSE envelope
(gwylproof.json), the OpenTimestamps stamp (gwylproof.ots) and the Sigstore
bundle (gwylbundle.json) to the message and marks it with an X-GWyl-Proof
header. 'check' extracts everything from the received message alone — the
recipient never needs a side-channel file.

Canonical-hash invariant: the proof is computed on the message WITHOUT the
proof attachments, so 'check' strips them before hashing. Adding and removing
the attachments does not change the canonical hash: Content-Type/MIME headers
are not canonical headers, the body is found via get_body(), and the proof
parts are never counted as regular attachments.

Portable references: in a traveling proof, sigstore.bundle_path and
opentimestamps.proof_file hold the ATTACHMENT FILENAMES (not local paths),
resolved by the verifier against a lookup directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any, Dict, Optional, cast

PROOF_HEADER = "X-GWyl-Proof"
PROOF_VERSION = "v1"
PROOF_JSON_FILENAME = "gwylproof.json"
OTS_FILENAME = "gwylproof.ots"
BUNDLE_FILENAME = "gwylbundle.json"
PROOF_FILENAMES = {PROOF_JSON_FILENAME, OTS_FILENAME, BUNDLE_FILENAME}


@dataclass
class ExtractedProof:
    """Proof artifacts extracted from a received message."""

    envelope: Dict[str, Any]  # DSSE envelope (or plain proof dict)
    ots_bytes: Optional[bytes] = None
    bundle_bytes: Optional[bytes] = None


def _parse(eml_bytes: bytes) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(eml_bytes)


def inject_proof(
    eml_bytes: bytes,
    envelope: Dict[str, Any],
    ots_bytes: Optional[bytes] = None,
    bundle_bytes: Optional[bytes] = None,
) -> bytes:
    """Return the EML with proof artifacts attached and the marker header set.

    The canonical hash of the stripped result equals the hash of the original
    input: proof parts are filtered out by filename at extraction/stripping
    time.
    """
    msg = _parse(eml_bytes)

    proof_json = json.dumps(envelope, ensure_ascii=False, indent=2)
    msg.add_attachment(
        proof_json.encode("utf-8"),
        maintype="application",
        subtype="json",
        filename=PROOF_JSON_FILENAME,
    )
    if ots_bytes:
        msg.add_attachment(
            ots_bytes, maintype="application", subtype="octet-stream", filename=OTS_FILENAME
        )
    if bundle_bytes:
        msg.add_attachment(
            bundle_bytes, maintype="application", subtype="json", filename=BUNDLE_FILENAME
        )

    del msg[PROOF_HEADER]  # idempotent re-sign
    msg[PROOF_HEADER] = PROOF_VERSION
    out = msg.as_bytes()
    return out if isinstance(out, bytes) else out.encode()


def _find_part_by_filename(msg: EmailMessage, filename: str) -> Optional[Any]:
    for part in msg.walk():
        if part.get_filename() == filename:
            return part
    return None


def extract_proof(eml_bytes: bytes) -> Optional[ExtractedProof]:
    """Extract proof artifacts from a message, or None if absent.

    Detection is based on the gwylproof.json attachment itself: the
    X-GWyl-Proof marker header is advisory, because MTAs may strip unknown
    X- headers in transit.
    """
    msg = _parse(eml_bytes)

    proof_part = _find_part_by_filename(msg, PROOF_JSON_FILENAME)
    if proof_part is None:
        return None
    payload = proof_part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return None
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    ots_bytes: Optional[bytes] = None
    ots_part = _find_part_by_filename(msg, OTS_FILENAME)
    if ots_part is not None:
        raw = ots_part.get_payload(decode=True)
        if isinstance(raw, bytes):
            ots_bytes = raw

    bundle_bytes: Optional[bytes] = None
    bundle_part = _find_part_by_filename(msg, BUNDLE_FILENAME)
    if bundle_part is not None:
        raw = bundle_part.get_payload(decode=True)
        if isinstance(raw, bytes):
            bundle_bytes = raw

    return ExtractedProof(envelope=envelope, ots_bytes=ots_bytes, bundle_bytes=bundle_bytes)


def strip_proof(eml_bytes: bytes) -> bytes:
    """Remove proof attachments and the marker header from a message.

    Returns the input unchanged when neither the marker header nor any proof
    attachment is present. Proof attachments are removed by filename even
    when the marker header was stripped by an MTA.
    """
    msg = _parse(eml_bytes)
    has_marker = msg.get(PROOF_HEADER) is not None

    changed = False
    if msg.is_multipart():
        payload = msg.get_payload()
        if isinstance(payload, list):
            parts = cast(Any, payload)  # Message objects at runtime
            kept = [part for part in parts if part.get_filename() not in PROOF_FILENAMES]
            if len(kept) != len(parts):
                msg.set_payload(kept)
                changed = True
    if has_marker:
        del msg[PROOF_HEADER]
        changed = True
    if not changed:
        return eml_bytes
    out = msg.as_bytes()
    return out if isinstance(out, bytes) else out.encode()
