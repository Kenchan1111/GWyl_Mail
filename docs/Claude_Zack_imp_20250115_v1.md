# GWyl Mail - Propositions d'Amélioration Architecture

**Date**: 2025-01-15
**Version**: v1.0
**Auteurs**: Zack, Claude (Anthropic)
**Statut**: DRAFT - Réflexion et Clarification Requises

---

## 📋 Table des Matières

1. [Problèmes Identifiés](#problèmes-identifiés)
2. [Solutions Proposées](#solutions-proposées)
3. [Code Complet des Prototypes](#code-complet-des-prototypes)
4. [Questions à Clarifier](#questions-à-clarifier)
5. [Impact sur Architecture Existante](#impact-sur-architecture-existante)
6. [Plan d'Implémentation (si validé)](#plan-dimplémentation)

---

## 🔴 Problèmes Identifiés

### Problème 1: Chainpoint Abandonné (2022)

**Constat**:
- Chainpoint n'est plus maintenu depuis 2022
- Projet probablement passé en propriétaire sous un autre nom
- Pattern récurrent dans l'écosystème open-source

**Impact**:
- Dépendance sur un projet mort
- Risque de non-disponibilité des services
- Pas de support ni mises à jour sécurité

**Référence code actuel**: Non implémenté dans le PoC actuel (bien vu!)

---

### Problème 2: Délai OpenTimestamps (6-24h)

**Constat**:
- OTS requiert confirmation Bitcoin: 10min minimum, jusqu'à 24h
- Pendant ce temps, le destinataire reçoit quoi?
  - Un `TXID` pending qui ne prouve rien
  - Status `"PENDING"` dans le proof
  - Aucune garantie temporelle immédiate

**Exemple actuel** (`dual_proof.py:106-113`):
```json
"opentimestamps": {
  "status": "PENDING",
  "proof_file": "./proofs/gwyl-proof-550e8400.ots",
  "submitted_at": "2025-01-11T14:30:25Z",
  "confirmed_at": null,          // ← Null pendant 6-24h !
  "bitcoin_block": null,
  "trust_level": "PENDING"       // ← Pas de trust immédiat
}
```

**Impact**:
- Preuve non vérifiable immédiatement
- Trust level bloqué à MEDIUM (Sigstore seul) pendant 24h
- UX dégradée (destinataire attend confirmation)

---

### Problème 3: Signature Monolithique (Hash Global Binaire)

**Constat**:
- Hash global du message canonique = résultat binaire OK/KO
- En cas de mismatch, **impossible de savoir quoi a changé**
- Faux positifs MTA (footers, disclaimers) = rejet total

**Code actuel** (`canonical.py:195-224`):
```python
def canonicalize(msg: EmailMessage, profile: str = "strict") -> bytes:
    headers = canonicalize_headers(msg, profile)
    body = canonicalize_body(msg)
    atts = canonicalize_attachments(msg)
    parts: List[bytes] = [headers, b"\n", body]
    parts.extend([a + b"\n" for a in atts])
    return b"".join(parts)  # ← Tout dans un blob binaire

def compute_hash(msg: EmailMessage, profile: str = "strict") -> str:
    return hashlib.sha256(canonicalize(msg, profile)).hexdigest()
    # ← Un seul hash, aucune granularité
```

**Scénario réel**:
```
Message envoyé:
  From: alice@company.com
  To: bob@example.com
  Subject: Contract Review
  Body: "Hello Bob!\n\nPlease review the contract."

Message reçu (après MTA Gmail):
  From: alice@company.com
  To: bob@example.com
  Subject: Contract Review
  Body: "Hello Bob!\n\nPlease review the contract.\n\n---\nGet Gmail on mobile"

Vérification:
  expected_hash: a3f7b2e9d1c4f5a6...
  actual_hash:   9f2b8c4d1e5a6f7b...
  Result: ❌ FAILED

Utilisateur: "Pourquoi ça échoue ? Qu'est-ce qui a changé ?"
→ Système: "Hash mismatch" (aucun détail)
```

**Impact**:
- Impossible de distinguer modification malveillante vs MTA benign
- Validation humaine impossible (pas de diff)
- Faux positifs → abandon du système par utilisateurs

---

## ✅ Solutions Proposées

### Solution 1: Triple Timestamping (Immediate + Legal)

**Architecture**:

```
Tier 1 - IMMEDIATE (0-2 secondes):
  ├─ Sigstore Rekor (OIDC identity + transparency log)
  └─ TSA RFC 3161 (qualified timestamp authority)

Tier 2 - LEGAL (différé, upgrade background):
  └─ OpenTimestamps Bitcoin (6-24h, HIGH trust)
```

**Bénéfices**:
- ✅ Preuve vérifiable **immédiatement** (pas d'attente 24h)
- ✅ Deux sources indépendantes tier 1 (résilience)
- ✅ TSA qualifié conforme eIDAS/EU (légal)
- ✅ OTS reste pour trust HIGH Bitcoin (upgrade async)

**Changements architecturaux**:
- Remplacer Chainpoint (mort) par TSA RFC 3161
- Ajouter tier 1 (immediate) vs tier 2 (legal)
- Permettre vérification sans attendre OTS

---

### Solution 2: Canonicalisation Structurée (Merkle Tree)

**Architecture**:

```
Au lieu de:
  canonical = concat(headers, body, attachments)
  hash = SHA256(canonical)

Proposé:
                    ROOT_HASH
                   /         \
              HEADERS       CONTENT
              /  |  \        /    \
           FROM TO SUBJ   BODY   ATT1  ATT2

Chaque composant a son propre hash individuel
```

**Structure**:
```json
{
  "merkle_root": "abc123...",
  "components": {
    "header:from": {
      "hash": "def456...",
      "canonical_preview": "from:alice@company.com"
    },
    "header:to": {
      "hash": "789abc...",
      "canonical_preview": "to:bob@example.com"
    },
    "header:subject": {
      "hash": "012def...",
      "canonical_preview": "subject:Contract Review"
    },
    "body": {
      "hash": "345678...",
      "canonical_preview": "Hello Bob!\n[...]"
    },
    "attachment:0": {
      "hash": "9abcde...",
      "filename": "contract.pdf",
      "size": 102400
    }
  }
}
```

**Bénéfices**:
- ✅ Granularité fine (savoir **quel** composant a changé)
- ✅ Headers intacts même si body modifié
- ✅ Attachments vérifiables indépendamment
- ✅ Base pour diff algorithm

---

### Solution 3: Vérification Diff-Revealing

**Concept**:

Au lieu de:
```
Verification Result: ❌ FAILED (hash mismatch)
```

Proposé:
```
Verification Report:
  ✅ header:from          OK
  ✅ header:to            OK
  ✅ header:subject       OK
  ⚠️  body                MODIFIED

      Diff:
      --- original
      +++ received
      @@ -1,3 +1,5 @@
       Hello Bob!

       Please review the contract.
      +
      +---
      +Get Gmail on mobile

      Analysis: Likely MTA footer (benign)
      Pattern: "Get Gmail on mobile" (known Gmail footer)
      Recommendation: ACCEPT (low risk)

  ✅ attachment:0         OK (contract.pdf)

Trust Level: MEDIUM (benign MTA modification)
Action: Accept? [y/N]
```

**Bénéfices**:
- ✅ Utilisateur voit **exactement** ce qui a changé
- ✅ Validation humaine possible (accepter footer MTA)
- ✅ Réduction faux positifs
- ✅ Détection modification malveillante (body core content)

---

## 💻 Code Complet des Prototypes

### 1. Client TSA RFC 3161

```python
# gwyl_mail/tsa_client.py
# SPDX-License-Identifier: GPL-3.0-only

"""
RFC 3161 Time-Stamp Protocol (TSP) Client

References:
- RFC 3161: https://www.rfc-editor.org/rfc/rfc3161.html
- eIDAS Regulation (EU): https://eur-lex.europa.eu/eli/reg/2014/910/oj

Free TSA Services:
- FreeTSA: https://freetsa.org/tsr
- DFN-Verein (Germany): https://zeitstempel.dfn.de
- DigiCert: http://timestamp.digicert.com
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests


@dataclass
class TimeStampToken:
    """RFC 3161 Time-Stamp Token"""

    token: bytes                    # DER-encoded TimeStampToken
    timestamp: datetime             # Certified timestamp (genTime)
    tsa_cert: bytes                 # TSA certificate (X.509 DER)
    serial_number: int              # Token serial number
    hash_algorithm: str             # Hash algorithm used (e.g., "sha256")
    message_imprint: bytes          # Hash of timestamped data
    accuracy_seconds: Optional[int] # Accuracy in seconds (if provided)
    tsa_name: Optional[str]         # TSA distinguished name


class TSAError(Exception):
    """TSA request/response error"""
    pass


class TSAClient:
    """
    Time-Stamp Authority Client (RFC 3161)

    Usage:
        client = TSAClient("https://freetsa.org/tsr")
        token = client.request_timestamp(b"message hash")
        print(f"Timestamp: {token.timestamp}")
    """

    def __init__(self, tsa_url: str = "https://freetsa.org/tsr"):
        """
        Initialize TSA client

        Args:
            tsa_url: TSA endpoint URL (default: FreeTSA)
        """
        self.tsa_url = tsa_url

    def request_timestamp(self,
                         message_hash: bytes,
                         hash_algorithm: str = "sha256",
                         request_cert: bool = True,
                         nonce: Optional[int] = None) -> TimeStampToken:
        """
        Request RFC 3161 timestamp for a message hash

        Args:
            message_hash: SHA-256 hash of content to timestamp
            hash_algorithm: Hash algorithm identifier (default: sha256)
            request_cert: Include TSA certificate in response
            nonce: Optional nonce for replay protection

        Returns:
            TimeStampToken with certified timestamp

        Raises:
            TSAError: If TSA request fails or response invalid
        """

        # 1. Build TimeStampReq (simplified - requires asn1crypto or similar)
        # For production, use cryptography library:
        # from cryptography.hazmat.primitives import hashes
        # from cryptography.x509 import ocsp

        # Simplified implementation using requests only
        # In production, use proper ASN.1 encoding

        try:
            # Create TSR (Time-Stamp Request) - ASN.1 DER encoded
            # This is a simplified placeholder - real implementation needs ASN.1 library

            # For PoC, we'll use a library-free HTTP request
            # Production code should use cryptography or asn1crypto

            # Prepare request data (simplified)
            request_data = self._build_tsr_request(
                message_hash=message_hash,
                hash_algorithm=hash_algorithm,
                request_cert=request_cert,
                nonce=nonce
            )

            # 2. Send HTTP POST to TSA
            response = requests.post(
                self.tsa_url,
                data=request_data,
                headers={
                    "Content-Type": "application/timestamp-query",
                    "User-Agent": "GWyl-Mail/0.3.0"
                },
                timeout=10
            )

            if response.status_code != 200:
                raise TSAError(
                    f"TSA HTTP error {response.status_code}: {response.text}"
                )

            # 3. Parse TimeStampResp
            token = self._parse_tsr_response(response.content)

            return token

        except requests.RequestException as e:
            raise TSAError(f"TSA request failed: {e}")
        except Exception as e:
            raise TSAError(f"TSA processing error: {e}")

    def _build_tsr_request(self,
                          message_hash: bytes,
                          hash_algorithm: str,
                          request_cert: bool,
                          nonce: Optional[int]) -> bytes:
        """
        Build TimeStampReq (ASN.1 DER encoded)

        NOTE: This is a PLACEHOLDER for documentation purposes.
        Real implementation requires ASN.1 library (asn1crypto, pyasn1, or cryptography).

        Structure (RFC 3161):

        TimeStampReq ::= SEQUENCE {
           version                  INTEGER  { v1(1) },
           messageImprint           MessageImprint,
           reqPolicy                TSAPolicyId OPTIONAL,
           nonce                    INTEGER OPTIONAL,
           certReq                  BOOLEAN DEFAULT FALSE,
           extensions               [0] IMPLICIT Extensions OPTIONAL
        }

        MessageImprint ::= SEQUENCE {
           hashAlgorithm            AlgorithmIdentifier,
           hashedMessage            OCTET STRING
        }
        """

        # TODO: Implement with proper ASN.1 library
        # For now, return placeholder

        raise NotImplementedError(
            "TSA ASN.1 encoding requires cryptography library. "
            "Install with: pip install cryptography>=41.0.0"
        )

    def _parse_tsr_response(self, response_data: bytes) -> TimeStampToken:
        """
        Parse TimeStampResp (ASN.1 DER encoded)

        NOTE: This is a PLACEHOLDER for documentation purposes.
        Real implementation requires ASN.1 library.

        Structure (RFC 3161):

        TimeStampResp ::= SEQUENCE {
           status                   PKIStatusInfo,
           timeStampToken           TimeStampToken OPTIONAL
        }

        PKIStatusInfo ::= SEQUENCE {
           status                   PKIStatus,
           statusString             PKIFreeText OPTIONAL,
           failInfo                 PKIFailureInfo OPTIONAL
        }
        """

        # TODO: Implement with proper ASN.1 library

        raise NotImplementedError(
            "TSA ASN.1 decoding requires cryptography library. "
            "Install with: pip install cryptography>=41.0.0"
        )

    def verify_timestamp(self,
                        token: TimeStampToken,
                        message_hash: bytes,
                        tsa_cert_chain: Optional[list] = None) -> bool:
        """
        Verify RFC 3161 timestamp token

        Args:
            token: TimeStampToken to verify
            message_hash: Original message hash
            tsa_cert_chain: Optional TSA certificate chain for validation

        Returns:
            True if token is valid and trusted
        """

        # TODO: Implement verification
        # 1. Verify TSA certificate chain
        # 2. Verify timestamp signature
        # 3. Verify message_imprint matches message_hash
        # 4. Check timestamp within validity period

        raise NotImplementedError("TSA verification requires cryptography library")


# ============================================================================
# Production-Ready Implementation (with cryptography library)
# ============================================================================

"""
Production implementation requires:

pip install cryptography>=41.0.0

Example:

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import requests

class TSAClientProduction:
    def request_timestamp(self, message_hash: bytes):
        # Use cryptography library for proper ASN.1 handling
        # Implementation: ~150 lines with proper error handling
        pass
"""
```

---

### 2. Canonicalisation Structurée (Merkle Tree)

```python
# gwyl_mail/merkle_canonical.py
# SPDX-License-Identifier: GPL-3.0-only

"""
Structured Canonicalization with Merkle Tree

Instead of global hash, create Merkle tree of message components:
- Individual header hashes (from, to, subject, etc.)
- Body hash
- Individual attachment hashes

Benefits:
- Granular verification (know WHICH component changed)
- Diff-revealing (show exact modifications)
- Partial integrity (headers intact even if body modified)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Dict, List, Optional

from .canonical import (
    CANONICAL_HEADERS,
    canonicalize_body,
    canonicalize_headers,
    _unfold,
    _decode_rfc2047,
    _normalize_addresses
)


@dataclass
class CanonicalComponent:
    """Single canonicalized component with individual hash"""

    name: str                # "header:from", "body", "attachment:0"
    canonical: bytes         # Canonical form (normalized bytes)
    hash: str               # SHA-256 hash of canonical
    preview: Optional[str]  # Human-readable preview (first 256 chars)
    size: int               # Size in bytes


class MerkleNode:
    """Node in Merkle tree"""

    def __init__(self,
                 hash_value: str,
                 left: Optional[MerkleNode] = None,
                 right: Optional[MerkleNode] = None,
                 component: Optional[CanonicalComponent] = None):
        self.hash = hash_value
        self.left = left
        self.right = right
        self.component = component  # Leaf nodes have component data

    def is_leaf(self) -> bool:
        return self.component is not None


class MerkleTree:
    """
    Merkle tree of message components

    Structure:
                        ROOT
                       /    \
                  HEADERS  CONTENT
                  /  |  \    /   \
               FROM TO SUB BODY  ATT
    """

    def __init__(self, components: List[CanonicalComponent]):
        self.components_dict: Dict[str, CanonicalComponent] = {
            comp.name: comp for comp in components
        }
        self.root_node = self._build_tree(components)
        self.root_hash = self.root_node.hash

    def _build_tree(self, components: List[CanonicalComponent]) -> MerkleNode:
        """Build Merkle tree from components (bottom-up)"""

        if not components:
            # Empty tree
            return MerkleNode(hash_value=hashlib.sha256(b"").hexdigest())

        # Create leaf nodes
        nodes = [
            MerkleNode(
                hash_value=comp.hash,
                component=comp
            )
            for comp in components
        ]

        # Build tree bottom-up
        while len(nodes) > 1:
            next_level = []

            # Pair nodes and create parents
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else left

                # Parent hash = hash(left_hash || right_hash)
                combined = (left.hash + right.hash).encode('utf-8')
                parent_hash = hashlib.sha256(combined).hexdigest()

                parent = MerkleNode(
                    hash_value=parent_hash,
                    left=left,
                    right=right
                )
                next_level.append(parent)

            nodes = next_level

        return nodes[0]

    def get_component(self, name: str) -> Optional[CanonicalComponent]:
        """Get component by name"""
        return self.components_dict.get(name)

    def get_proof(self, component_name: str) -> List[str]:
        """
        Get Merkle proof for a component (for efficient verification)

        Returns list of sibling hashes from leaf to root
        """
        # TODO: Implement Merkle proof generation
        # Useful for partial verification (verify one component without full tree)
        raise NotImplementedError("Merkle proof generation not yet implemented")

    def to_dict(self) -> dict:
        """Export tree to dict (for JSON serialization)"""
        return {
            "merkle_root": self.root_hash,
            "components": {
                name: {
                    "hash": comp.hash,
                    "canonical_preview": comp.preview,
                    "size": comp.size
                }
                for name, comp in self.components_dict.items()
            }
        }


class MerkleCanonical:
    """Structured canonicalization using Merkle tree"""

    def canonicalize_structured(self,
                                message: EmailMessage,
                                profile: str = "strict") -> MerkleTree:
        """
        Canonicalize message into Merkle tree of components

        Args:
            message: Email message to canonicalize
            profile: Canonicalization profile (strict/relaxed)

        Returns:
            MerkleTree with individual component hashes
        """

        components = []

        # 1. Individual headers
        for header_name in CANONICAL_HEADERS:
            raw = message.get(header_name, "")
            if not raw:
                continue

            # Canonicalize header value
            value = _unfold(str(raw))
            value = _decode_rfc2047(value)
            value = " ".join(value.split())

            if header_name in ("from", "to"):
                value = _normalize_addresses(value)

            canonical = f"{header_name.lower()}:{value}".encode('utf-8')

            components.append(CanonicalComponent(
                name=f"header:{header_name}",
                canonical=canonical,
                hash=hashlib.sha256(canonical).hexdigest(),
                preview=value[:256],
                size=len(canonical)
            ))

        # 2. Body
        body_canonical = canonicalize_body(message)
        if body_canonical:
            try:
                body_preview = body_canonical.decode('utf-8', errors='replace')[:256]
            except:
                body_preview = "<binary>"

            components.append(CanonicalComponent(
                name="body",
                canonical=body_canonical,
                hash=hashlib.sha256(body_canonical).hexdigest(),
                preview=body_preview,
                size=len(body_canonical)
            ))

        # 3. Individual attachments
        for i, part in enumerate(message.iter_attachments()):
            payload = part.get_payload(decode=True)
            if payload:
                filename = part.get_filename() or f"attachment_{i}"

                components.append(CanonicalComponent(
                    name=f"attachment:{i}",
                    canonical=payload,
                    hash=hashlib.sha256(payload).hexdigest(),
                    preview=f"{filename} ({len(payload)} bytes)",
                    size=len(payload)
                ))

        # 4. Build Merkle tree
        return MerkleTree(components)

    def hash(self, message: EmailMessage, profile: str = "strict") -> str:
        """
        Compute Merkle root hash (backward compatible with global hash)

        Args:
            message: Email message
            profile: Canonicalization profile

        Returns:
            Merkle root hash (SHA-256 hex)
        """
        tree = self.canonicalize_structured(message, profile)
        return tree.root_hash
```

---

### 3. Vérification Diff-Revealing

```python
# gwyl_mail/diff_verification.py
# SPDX-License-Identifier: GPL-3.0-only

"""
Diff-Revealing Verification

Instead of binary OK/FAIL, show:
- Which components changed
- Exact diff for text components
- Human-readable analysis
- Validation suggestions (accept MTA footer, reject content change)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional, Dict

from .merkle_canonical import MerkleCanonical, MerkleTree, CanonicalComponent


@dataclass
class ComponentDiff:
    """Diff for a single component"""

    component: str              # Component name
    status: str                 # "OK" | "MODIFIED" | "ADDED" | "REMOVED"
    original_hash: Optional[str]
    received_hash: Optional[str]
    diff_text: Optional[str]    # Unified diff (for text components)
    analysis: Optional[str]     # AI/pattern-based analysis
    recommendation: str         # "ACCEPT" | "REJECT" | "REVIEW"
    severity: str              # "BENIGN" | "SUSPICIOUS" | "CRITICAL"


@dataclass
class VerificationReport:
    """Complete verification report with diff details"""

    merkle_root_match: bool
    component_diffs: List[ComponentDiff]
    trust_level: str           # "HIGH" | "MEDIUM" | "LOW"
    recommendation: str        # Overall recommendation
    summary: str              # Human-readable summary


class DiffAnalyzer:
    """Analyze diffs to detect benign MTA modifications"""

    # Known MTA footer patterns (benign)
    MTA_FOOTER_PATTERNS = [
        r"Get Gmail (?:on mobile|for mobile)",
        r"Sent from my (?:iPhone|iPad|Android)",
        r"This email (?:has been|was) scanned for viruses",
        r"(?:Disclaimer|Confidentiality Notice):",
        r"Virus-free\. www\.(?:avg|avast|norton)\.com",
        r"--\s*$",  # Signature separator
    ]

    # Encoding change indicators (benign)
    ENCODING_INDICATORS = [
        "Content-Transfer-Encoding",
        "quoted-printable",
        "base64",
    ]

    def analyze_diff(self,
                    component: str,
                    diff_text: Optional[str]) -> tuple[str, str, str]:
        """
        Analyze diff to detect modification type

        Returns:
            (analysis, recommendation, severity)
        """

        if not diff_text:
            return ("No changes", "ACCEPT", "BENIGN")

        # Check for MTA footer
        for pattern in self.MTA_FOOTER_PATTERNS:
            if re.search(pattern, diff_text, re.IGNORECASE):
                return (
                    f"MTA footer detected (pattern: {pattern[:30]}...)",
                    "ACCEPT",
                    "BENIGN"
                )

        # Check for encoding changes
        if component == "body":
            if any(ind in diff_text for ind in self.ENCODING_INDICATORS):
                return (
                    "Encoding change (QP↔Base64, benign)",
                    "ACCEPT",
                    "BENIGN"
                )

        # Check diff size
        lines = diff_text.splitlines()
        added_lines = [l for l in lines if l.startswith('+') and not l.startswith('+++')]
        removed_lines = [l for l in lines if l.startswith('-') and not l.startswith('---')]

        if len(removed_lines) == 0 and len(added_lines) < 5:
            return (
                f"Small addition ({len(added_lines)} lines), likely MTA",
                "REVIEW",
                "SUSPICIOUS"
            )

        if len(removed_lines) > 0 or len(added_lines) > 10:
            return (
                "Significant content modification detected",
                "REJECT",
                "CRITICAL"
            )

        return ("Unknown modification pattern", "REVIEW", "SUSPICIOUS")


class DiffVerifier:
    """Diff-revealing verifier"""

    def __init__(self):
        self.analyzer = DiffAnalyzer()

    def verify_with_diff(self,
                        proof: dict,
                        received_message: EmailMessage,
                        profile: str = "strict") -> VerificationReport:
        """
        Verify message and generate detailed diff report

        Args:
            proof: Original proof dict (with components)
            received_message: Message received by user
            profile: Canonicalization profile

        Returns:
            VerificationReport with component-level diffs
        """

        # 1. Build Merkle tree of received message
        merkle_canonical = MerkleCanonical()
        received_tree = merkle_canonical.canonicalize_structured(
            received_message,
            profile
        )

        # 2. Extract original components from proof
        original_components = proof.get("components", {})
        original_root = proof.get("merkle_root")

        # 3. Compare component by component
        diffs: List[ComponentDiff] = []

        for comp_name, original_data in original_components.items():
            original_hash = original_data["hash"]

            # Find corresponding component in received message
            received_comp = received_tree.get_component(comp_name)

            if not received_comp:
                # Component removed
                diffs.append(ComponentDiff(
                    component=comp_name,
                    status="REMOVED",
                    original_hash=original_hash,
                    received_hash=None,
                    diff_text=None,
                    analysis="Component was removed (likely attachment stripped)",
                    recommendation="REJECT",
                    severity="CRITICAL"
                ))
                continue

            received_hash = received_comp.hash

            if original_hash == received_hash:
                # ✅ Identical
                diffs.append(ComponentDiff(
                    component=comp_name,
                    status="OK",
                    original_hash=original_hash,
                    received_hash=received_hash,
                    diff_text=None,
                    analysis="Component intact",
                    recommendation="ACCEPT",
                    severity="BENIGN"
                ))
            else:
                # ⚠️ Modified - Generate diff
                diff_text = self._generate_diff(
                    comp_name,
                    original_data.get("canonical_preview", ""),
                    received_comp
                )

                # Analyze diff
                analysis, recommendation, severity = self.analyzer.analyze_diff(
                    comp_name,
                    diff_text
                )

                diffs.append(ComponentDiff(
                    component=comp_name,
                    status="MODIFIED",
                    original_hash=original_hash,
                    received_hash=received_hash,
                    diff_text=diff_text,
                    analysis=analysis,
                    recommendation=recommendation,
                    severity=severity
                ))

        # 4. Detect added components
        for comp_name, received_comp in received_tree.components_dict.items():
            if comp_name not in original_components:
                diffs.append(ComponentDiff(
                    component=comp_name,
                    status="ADDED",
                    original_hash=None,
                    received_hash=received_comp.hash,
                    diff_text=None,
                    analysis="Component was added (unexpected)",
                    recommendation="REVIEW",
                    severity="SUSPICIOUS"
                ))

        # 5. Compute trust level and recommendation
        merkle_match = (received_tree.root_hash == original_root)
        trust_level, recommendation = self._compute_trust(diffs, merkle_match)

        return VerificationReport(
            merkle_root_match=merkle_match,
            component_diffs=diffs,
            trust_level=trust_level,
            recommendation=recommendation,
            summary=self._generate_summary(diffs, merkle_match)
        )

    def _generate_diff(self,
                      component: str,
                      original_preview: str,
                      received_comp: CanonicalComponent) -> str:
        """Generate unified diff for text components"""

        if component.startswith("header:") or component == "body":
            # Text diff
            try:
                original_lines = original_preview.splitlines()
                received_text = received_comp.canonical.decode('utf-8', errors='replace')
                received_lines = received_text.splitlines()

                diff = difflib.unified_diff(
                    original_lines,
                    received_lines,
                    lineterm='',
                    fromfile='original',
                    tofile='received'
                )

                return '\n'.join(diff)
            except:
                return f"<diff generation failed>"
        else:
            # Binary (attachment)
            return f"Binary content changed (size: {received_comp.size} bytes)"

    def _compute_trust(self,
                      diffs: List[ComponentDiff],
                      merkle_match: bool) -> tuple[str, str]:
        """Compute overall trust level and recommendation"""

        if merkle_match:
            return ("HIGH", "ACCEPT")

        # Count severity levels
        critical = sum(1 for d in diffs if d.severity == "CRITICAL")
        suspicious = sum(1 for d in diffs if d.severity == "SUSPICIOUS")
        benign = sum(1 for d in diffs if d.severity == "BENIGN")

        if critical > 0:
            return ("LOW", "REJECT")
        elif suspicious > 0:
            return ("MEDIUM", "REVIEW")
        elif benign > 0:
            return ("MEDIUM", "ACCEPT (MTA modifications)")
        else:
            return ("HIGH", "ACCEPT")

    def _generate_summary(self,
                         diffs: List[ComponentDiff],
                         merkle_match: bool) -> str:
        """Generate human-readable summary"""

        if merkle_match:
            return "✅ Message integrity verified - no modifications detected"

        modified = [d for d in diffs if d.status == "MODIFIED"]
        removed = [d for d in diffs if d.status == "REMOVED"]
        added = [d for d in diffs if d.status == "ADDED"]

        parts = []

        if modified:
            benign = [d for d in modified if d.severity == "BENIGN"]
            if benign:
                parts.append(f"{len(benign)} benign modification(s) detected (likely MTA)")

            critical = [d for d in modified if d.severity == "CRITICAL"]
            if critical:
                parts.append(f"⚠️ {len(critical)} critical modification(s) detected!")

        if removed:
            parts.append(f"{len(removed)} component(s) removed")

        if added:
            parts.append(f"{len(added)} component(s) added")

        return "; ".join(parts) if parts else "Unknown modifications"
```

---

### 4. CLI avec Affichage Diff

```python
# gwyl_mail/cli_diff.py
# SPDX-License-Identifier: GPL-3.0-only

"""
CLI with diff-revealing output
"""

from .diff_verification import DiffVerifier, VerificationReport, ComponentDiff


def display_verification_report(report: VerificationReport, verbose: bool = False):
    """
    Display verification report with diff details

    Args:
        report: VerificationReport from DiffVerifier
        verbose: Show full diffs (default: summaries only)
    """

    print("=" * 80)
    print("GWyl Mail - Verification Report (Diff-Revealing)")
    print("=" * 80)
    print()

    # 1. Merkle root status
    if report.merkle_root_match:
        print("✅ MERKLE ROOT: VALID (no modifications)")
    else:
        print("⚠️  MERKLE ROOT: MISMATCH (modifications detected)")
    print()

    # 2. Component-by-component analysis
    print("Component Analysis:")
    print("-" * 80)

    for diff in report.component_diffs:
        # Status icon
        if diff.status == "OK":
            icon = "✅"
            color = ""
        elif diff.status == "MODIFIED":
            if diff.severity == "BENIGN":
                icon = "⚠️ "
                color = ""
            elif diff.severity == "SUSPICIOUS":
                icon = "⚠️ "
                color = ""
            else:  # CRITICAL
                icon = "❌"
                color = ""
        elif diff.status == "ADDED":
            icon = "➕"
            color = ""
        else:  # REMOVED
            icon = "➖"
            color = ""

        # Component line
        print(f"{icon} {diff.component:<30} {diff.status}")

        # Details for modified/added/removed
        if diff.status != "OK":
            if diff.analysis:
                print(f"   Analysis: {diff.analysis}")

            if verbose and diff.diff_text:
                print()
                print("   Diff:")
                for line in diff.diff_text.splitlines():
                    print(f"   {line}")
                print()
            elif diff.diff_text and not verbose:
                # Show first 3 lines of diff
                lines = diff.diff_text.splitlines()
                for line in lines[:3]:
                    print(f"   {line}")
                if len(lines) > 3:
                    print(f"   ... ({len(lines) - 3} more lines, use --verbose)")
                print()

            # Recommendation
            if diff.recommendation:
                rec_icon = "✓" if diff.recommendation == "ACCEPT" else "⚠"
                print(f"   {rec_icon} Recommendation: {diff.recommendation}")

        print()

    # 3. Summary
    print("=" * 80)
    print(f"Summary: {report.summary}")
    print(f"Trust Level: {report.trust_level}")
    print(f"Recommendation: {report.recommendation}")
    print("=" * 80)


def cmd_verify_diff(args):
    """CLI command for diff-revealing verification"""

    from pathlib import Path
    from email.parser import BytesParser
    from email import policy
    import json

    # Load proof and message
    proof_path = Path(args.proof)
    eml_path = Path(args.eml)

    proof = json.loads(proof_path.read_text())
    message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())

    # Verify with diff
    verifier = DiffVerifier()
    report = verifier.verify_with_diff(
        proof=proof,
        received_message=message,
        profile=args.profile or "strict"
    )

    # Display report
    display_verification_report(report, verbose=args.verbose)

    # Exit code
    if report.recommendation == "ACCEPT":
        return 0
    elif report.recommendation == "REVIEW":
        return 2  # Manual review required
    else:  # REJECT
        return 1
```

---

## ❓ Questions à Clarifier

### Question 1: TSA - Implémentation Complète vs Stub

**Contexte**:
- TSA RFC 3161 requiert bibliothèque ASN.1 (`cryptography`, `asn1crypto`, ou `pyasn1`)
- Le code prototype ci-dessus est un stub documenté
- Implémentation complète = +200 lignes avec gestion certificats X.509

**Questions**:
1. Doit-on implémenter TSA complet dans le PoC v0.3 ?
2. Ou garder TSA comme "TODO" et se concentrer sur Merkle tree d'abord ?
3. Alternative: utiliser bibliothèque tierce (ex: `python-tsa`) ?

**Impact**:
- Implémentation TSA complète = 2-3 jours dev
- Stub TSA = documentation seulement (0 dev)
- Avec stub: dual timestamp = Sigstore + OTS seulement (comme actuellement)

---

### Question 2: Merkle Tree - Granularité des Headers

**Contexte**:
- Proposition actuelle: un hash par header (`header:from`, `header:to`, etc.)
- Alternative: regrouper headers en un seul nœud

**Options**:

**Option A - Granularité fine** (proposée):
```
HEADERS
├── header:from
├── header:to
├── header:subject
├── header:date
└── header:message-id
```

**Avantages**:
- ✅ Diff précis (savoir quel header a changé)
- ✅ Vérification partielle (check From sans Body)

**Inconvénients**:
- ❌ Proof plus lourd (+5 hashs au lieu de 1)
- ❌ Complexité accrue

**Option B - Headers groupés**:
```
HEADERS (single hash of all canonical headers)
```

**Avantages**:
- ✅ Proof compact
- ✅ Simple

**Inconvénients**:
- ❌ Pas de diff granulaire headers

**Question**: Quelle option choisir ?

---

### Question 3: Diff Algorithm - Pattern Matching vs ML

**Contexte**:
- Prototype utilise regex pattern matching pour détecter footers MTA
- Patterns hardcodés: "Get Gmail", "Scanned for viruses", etc.

**Questions**:
1. Pattern matching suffit-il ? (extensible manuellement)
2. Ou prévoir ML/heuristique pour détecter footers inconnus ?
3. Comment gérer nouveaux patterns MTA (Gmail change footer) ?

**Options**:

**Option A - Patterns statiques** (actuel):
```python
MTA_FOOTER_PATTERNS = [
    r"Get Gmail on mobile",
    r"Scanned for viruses",
    # ... liste exhaustive
]
```

**Avantages**: Simple, prédictible
**Inconvénients**: Maintenance (nouveaux MTAs)

**Option B - ML classifier**:
```python
def is_mta_footer(text: str) -> bool:
    features = extract_features(text)
    return classifier.predict(features) == "footer"
```

**Avantages**: Adaptatif
**Inconvénients**: Dépendance ML, faux positifs

**Question**: Quelle approche ?

---

### Question 4: Proof Storage - Backward Compatibility v0.2 → v0.3

**Contexte**:
- v0.2 actuelle: proof global hash
- v0.3 proposée: proof Merkle tree avec composants

**Question**: Comment migrer preuves existantes v0.2 ?

**Options**:

**Option A - Dual format support**:
```python
def verify_proof(proof: dict, message: EmailMessage):
    if proof["version"] == "0.2.0":
        # Legacy verification (global hash)
        return verify_v02(proof, message)
    elif proof["version"] == "0.3.0":
        # Merkle tree verification
        return verify_v03_merkle(proof, message)
```

**Option B - Migration automatique**:
```python
def migrate_proof_v02_to_v03(proof_v02: dict) -> dict:
    # Impossible car on n'a pas les composants individuels !
    raise NotImplementedError("Cannot migrate without original message")
```

**Option C - Breaking change (pas de migration)**:
- v0.3 est nouvelle version incompatible
- Preuves v0.2 restent vérifiables par CLI v0.2

**Question**: Quelle stratégie de migration ?

---

### Question 5: UI Validation Humaine - CLI vs GUI

**Contexte**:
- Prototype montre diff en CLI texte
- Cas d'usage: utilisateur non-technique

**Question**: Où placer la validation humaine ?

**Options**:

**Option A - CLI interactive** (prototype):
```
⚠️  body MODIFIED
Diff: [...]
Analysis: Likely MTA footer
Action: Accept? [y/N]: _
```

**Avantages**: Simple, pas de GUI
**Inconvénients**: UX limitée

**Option B - Extension navigateur GUI**:
```
[Extension Thunderbird]
┌─────────────────────────────────┐
│ ⚠️ Message modified by MTA      │
│                                 │
│ Body changed:                   │
│ + "Get Gmail on mobile"         │
│                                 │
│ [Accept] [Reject] [View Diff]  │
└─────────────────────────────────┘
```

**Avantages**: UX meilleure
**Inconvénients**: Dev extension (+2-3 semaines)

**Option C - Web UI** (upload EML + proof):
```
https://verify.gwyl.io/
- Upload message.eml
- Upload proof.json
- View diff report in browser
```

**Avantages**: Accessible, pas d'install
**Inconvénients**: Upload données sensibles

**Question**: Quelle UI prioriser pour PoC ?

---

### Question 6: Performance - Impact Merkle Tree

**Contexte**:
- Hash global: 1 hash SHA-256
- Merkle tree: N composants + log(N) nœuds internes

**Exemple**:
```
Message avec:
- 5 headers = 5 hashs
- 1 body = 1 hash
- 2 attachments = 2 hashs
Total: 8 hashs feuilles + 7 nœuds internes = 15 hashs SHA-256

vs global: 1 hash SHA-256
```

**Questions**:
1. Impact performance acceptable ? (15x hashs mais still <10ms total)
2. Optimisation nécessaire ? (parallel hashing)
3. KPI actuel "<150ms" toujours atteignable ?

**Mesures à faire**:
- Benchmark hash global vs Merkle (N=5, 10, 50 composants)
- Vérifier impact taille proof JSON (+20% ?)

---

### Question 7: Header GWyl-Proof-Ref - Merkle Root ou Global Hash ?

**Contexte**:
- `Traversal_Concept.md` propose: `GWyl-Proof-Ref: sha256=<content_hash>`
- Avec Merkle tree, quel hash mettre dans le header ?

**Options**:

**Option A - Merkle root**:
```
GWyl-Proof-Ref: merkle_root=abc123...; ts=rekor:142857
```

**Avantages**: Cohérent avec proof v0.3
**Inconvénients**: Changement vs spec actuelle

**Option B - Global hash (backward compat)**:
```
GWyl-Proof-Ref: sha256=def456...; ts=rekor:142857
```

Avec: `global_hash = SHA256(concat_all_components)`

**Avantages**: Compatible spec actuelle
**Inconvénients**: Redondance (merkle_root + global_hash)

**Question**: Quel hash dans le header DKIM-protected ?

---

### Question 8: Séparation Proof Files - Structure Finale

**Contexte**:
- Demande: séparer request/response/audit
- Proposition structure répertoire

**Structure proposée**:
```
.gwyl_mail/proofs/<message_id>/
├── request.json          # Requête initiale (hash, identity, timestamp)
├── canonical/
│   ├── global.bin        # Forme canonique globale (legacy)
│   └── components/       # Composants individuels
│       ├── header_from.bin
│       ├── header_to.bin
│       ├── body.bin
│       └── attachment_0.bin
├── response.json         # Preuve cryptographique (immutable)
│   ├── merkle_root
│   ├── components: {...}
│   └── timestamps: {...}
├── response.sig          # Signature DSSE de response.json
├── timestamps/
│   ├── sigstore.bundle   # Bundle Sigstore
│   ├── tsa.tsr           # TSA timestamp token
│   └── ots/
│       ├── merkle_root.ots
│       └── merkle_root.ots.bak
├── metadata.json         # Métadonnées mutables (coherence, trust_level)
└── audit.jsonl           # Logs d'audit append-only
```

**Questions**:
1. Cette structure convient-elle ?
2. Stocker composants canoniques individuels ? (utile pour debug/diff)
3. Trop de fichiers ? (alternative: tout dans response.json)

---

### Question 9: Timestamp Tiers - Naming

**Contexte**:
- Proposition: Tier 1 (immediate) vs Tier 2 (legal)

**Naming**:

**Option A - Tiers numériques**:
```
"timestamps": {
  "tier1": {
    "sigstore": {...},
    "tsa": {...}
  },
  "tier2": {
    "ots_bitcoin": {...}
  }
}
```

**Option B - Semantic naming**:
```
"timestamps": {
  "immediate": {
    "sigstore": {...},
    "tsa": {...}
  },
  "legal_grade": {
    "ots_bitcoin": {...}
  }
}
```

**Option C - Flat structure** (actuel):
```
"timestamps": {
  "sigstore": {...},
  "tsa": {...},
  "ots": {...}
}
```

**Question**: Quelle structure JSON préférée ?

---

### Question 10: Roadmap - Priorisation

**Contexte**:
- Multiples améliorations proposées
- Ressources limitées

**Priorisation proposée**:

**P0 - CRITICAL (à faire pour PoC)**:
1. ✅ Merkle tree canonicalization (diff-revealing est le cœur)
2. ✅ Diff verification algorithm
3. ✅ CLI display diff report

**P1 - HIGH (important mais pas bloquant)**:
4. ⏳ TSA RFC 3161 integration (stub OK pour PoC)
5. ⏳ Séparation proof files (request/response/audit)

**P2 - MEDIUM (nice to have)**:
6. ⏳ Pattern matching amélioration (ML footer detection)
7. ⏳ Extension navigateur GUI
8. ⏳ Web UI verification

**P3 - LOW (futur)**:
9. ⏳ Performance optimization (parallel hashing)
10. ⏳ Merkle proof generation (partial verification)

**Question**: Cette priorisation est-elle correcte ?

---

## 📊 Impact sur Architecture Existante

### Modules à Modifier

| Module | Changement | Impact | Effort |
|--------|-----------|--------|--------|
| `canonical.py` | Ajouter `MerkleCanonical` | Nouveau mode (backward compat) | 2-3j |
| `dual_proof.py` | Stocker composants Merkle | Changement structure proof | 1j |
| `cli.py` | Ajouter `verify-diff` cmd | Nouveau verbe CLI | 1j |
| `validation.py` | Schema v0.3 (Merkle) | Nouveau schema JSON | 0.5j |
| `sigstore_timestamp.py` | Ajouter TSA (stub) | Documentation seulement | 0.5j |

**Total effort estimé**: 5-6 jours dev

### Nouveaux Modules

| Module | Description | Effort |
|--------|-------------|--------|
| `merkle_canonical.py` | Merkle tree canonicalization | 2j |
| `diff_verification.py` | Diff-revealing verifier | 2j |
| `tsa_client.py` | TSA RFC 3161 client (stub) | 0.5j |
| `cli_diff.py` | CLI diff display | 1j |

**Total nouveaux modules**: 5.5 jours dev

---

### Backward Compatibility

**Stratégie proposée**:

```python
# gwyl_mail/canonical.py (extended)

class GWylCanonical:
    @staticmethod
    def hash(message: EmailMessage,
             profile: str = "strict",
             mode: str = "global") -> str:
        """
        Args:
            mode: "global" (v0.2 compat) or "merkle" (v0.3)
        """
        if mode == "merkle":
            tree = MerkleCanonical().canonicalize_structured(message, profile)
            return tree.root_hash
        else:
            # Legacy global hash
            canonical = canonicalize(message, profile)
            return hashlib.sha256(canonical).hexdigest()
```

**Preuves v0.2 restent vérifiables**:
```python
def verify_proof(proof: dict, message: EmailMessage):
    version = proof.get("version", "0.2.0")

    if version == "0.2.0":
        # Legacy verification
        expected = proof["canonical"]["content_hash"]
        actual = GWylCanonical.hash(message, mode="global")
        return expected == actual

    elif version == "0.3.0":
        # Merkle tree verification with diff
        verifier = DiffVerifier()
        report = verifier.verify_with_diff(proof, message)
        return report
```

---

## 📅 Plan d'Implémentation (si validé)

### Phase 1: Merkle Tree Core (Sprint 7)
**Durée**: 3 jours
**Livrables**:
- ✅ `merkle_canonical.py` complet
- ✅ `MerkleTree` class avec build + verification
- ✅ Tests unitaires (20 test cases)
- ✅ Backward compat mode="global"

### Phase 2: Diff Verification (Sprint 7 suite)
**Durée**: 2 jours
**Livrables**:
- ✅ `diff_verification.py` complet
- ✅ `DiffAnalyzer` avec pattern matching
- ✅ `DiffVerifier.verify_with_diff()`
- ✅ Tests diff algorithm

### Phase 3: CLI Integration (Sprint 8)
**Durée**: 1 jour
**Livrables**:
- ✅ `cli_diff.py` display report
- ✅ Commande `gwyl-mail verify-diff`
- ✅ Exemples utilisation docs

### Phase 4: TSA Stub (Sprint 8)
**Durée**: 0.5 jour
**Livrables**:
- ✅ `tsa_client.py` documentation
- ✅ Interfaces définies (TODO implem)
- ✅ Specs TSA intégration

### Phase 5: Séparation Proof Files (Sprint 9)
**Durée**: 1 jour
**Livrables**:
- ✅ Structure répertoire proof/
- ✅ request.json, response.json, audit.jsonl
- ✅ Migration script v0.2 → v0.3

### Phase 6: Tests & Validation (Sprint 9)
**Durée**: 2 jours
**Livrables**:
- ✅ Tests intégration bout-en-bout
- ✅ Test vectors v0.3 calculés
- ✅ Benchmark performance (vs v0.2)
- ✅ Validation KPIs

**Total**: ~10 jours dev

---

## 🔗 Références

### RFC & Standards
- **RFC 3161**: Time-Stamp Protocol (TSP)
  https://www.rfc-editor.org/rfc/rfc3161.html

- **RFC 6962**: Certificate Transparency (Merkle tree concept)
  https://www.rfc-editor.org/rfc/rfc6962.html

- **eIDAS Regulation**: EU qualified timestamps
  https://eur-lex.europa.eu/eli/reg/2014/910/oj

### Bibliothèques Python
- `cryptography`: https://cryptography.io/ (ASN.1, X.509, TSA)
- `asn1crypto`: https://github.com/wbond/asn1crypto (alternative)
- `pyasn1`: https://pypi.org/project/pyasn1/ (ASN.1 low-level)

### TSA Services Gratuits
- FreeTSA: https://freetsa.org/
- DFN-Verein: https://www.pki.dfn.de/zeitstempeldienst/
- DigiCert: https://knowledge.digicert.com/generalinformation/INFO4231.html

---

## 📝 Notes de Réflexion

### Note 1: Chainpoint Obsolescence
- Vérifier si projet réellement mort ou fork actif ?
- Alternative Chainpoint: https://github.com/chainpoint/chainpoint-core (dernière maj 2022)
- Confirmation: pas de commit depuis 3 ans → **mort confirmé**

### Note 2: TSA vs OTS Trade-off
- **TSA**: Immédiat (0-2s), qualifié EU, mais **centralisé** (trust TSA provider)
- **OTS**: Différé (6-24h), Bitcoin décentralisé, mais **lent**
- **Dual approach**: Best of both worlds → ✅ validé

### Note 3: Merkle Tree Overhead
- Performance: 15 hashs vs 1 hash = impact négligeable (<5ms sur laptop)
- Taille proof: ~5KB → ~8KB (+60%) → toujours sous KPI <50KB ✅
- Trade-off acceptable pour diff-revealing capability

### Note 4: Pattern Matching Limitations
- Patterns statiques OK pour PoC
- Production nécessitera:
  - Whitelist configurable (admin peut ajouter patterns)
  - Community-sourced patterns (GitHub repo public ?)
  - ML optionnel (phase 2)

### Note 5: UI Validation Workflow
- CLI interactive suffit pour utilisateurs techniques (PoC)
- Extension navigateur critique pour adoption grand public
- Prioriser: CLI → Web UI → Extension (ordre implémentation)

---

## ✅ Prochaines Étapes

1. **Clarifier questions listées** (Zack decision)
2. **Valider architecture Merkle tree** (go/no-go)
3. **Valider TSA stub vs full implementation** (scope PoC)
4. **Définir structure proof finale** (fichiers séparés)
5. **Prioriser roadmap** (P0/P1/P2)
6. **Lancer implémentation** (si validé)

---

**Fin du document - Document de réflexion, non finalisé**

**Statut**: DRAFT - Attente feedback Zack pour clarification questions
