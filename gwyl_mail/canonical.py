from __future__ import annotations

import hashlib
import re
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser, Parser
from email.utils import getaddresses
from typing import List


CANONICAL_HEADERS = ["from", "to", "subject", "date", "message-id"]


def _unfold(value: str) -> str:
    return re.sub(r"\r?\n[\t ]+", " ", value).strip()


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


def canonicalize_headers(msg: EmailMessage) -> bytes:
    lines: List[str] = []
    for key in CANONICAL_HEADERS:
        raw = msg.get(key, "")
        if not raw:
            continue
        v = _unfold(str(raw))
        v = _decode_rfc2047(v)
        v = " ".join(v.split())
        if key in ("from", "to"):
            v = _normalize_addresses(v)
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


def canonicalize(msg: EmailMessage) -> bytes:
    headers = canonicalize_headers(msg)
    body = canonicalize_body(msg)
    atts = canonicalize_attachments(msg)
    parts: List[bytes] = [headers, b"\n", body]
    parts.extend([a + b"\n" for a in atts])
    return b"".join(parts)


def compute_hash(msg: EmailMessage) -> str:
    return hashlib.sha256(canonicalize(msg)).hexdigest()


class GWylCanonical:
    @staticmethod
    def hash(message: EmailMessage | str) -> str:
        if isinstance(message, EmailMessage):
            return compute_hash(message)
        # If raw string provided, parse to EmailMessage
        if isinstance(message, bytes):
            m = BytesParser(policy=policy.default).parsebytes(message)
        else:
            m = Parser(policy=policy.default).parsestr(message)
        return compute_hash(m)

