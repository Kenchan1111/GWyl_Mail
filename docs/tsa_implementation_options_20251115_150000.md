# TSA (Time Stamping Authority) RFC 3161 - Analyse et Options d'Implémentation

**Date**: 2025-11-15 15:00:00
**Auteur**: Claude (Anthropic)
**Version**: 1.0
**Statut**: Analyse technique - Décision requise

---

## Résumé Exécutif

### Verdict: TSA est INDISPENSABLE (pas optionnel)

L'implémentation actuelle du TSA dans GWyl Mail est un **stub non fonctionnel** (évaluation: 3/10). Cette analyse propose trois options d'implémentation pour remédier à ce blocage critique.

**Criticité**: 🔴 **BLOQUANT CRITIQUE** - TSA est requis pour:
- ✅ **Conformité eIDAS** (horodatage qualifié obligatoire)
- ✅ **Preuve cryptographique de l'heure d'envoi** (indépendante SMTP)
- ✅ **Intégrité de la chaîne de traitement** (chaining des mails)
- ✅ **État immuable 1** (timestamp du hash au moment précis de l'envoi)
- ✅ **Tier 1 timestamping** (immédiat, 0-2 secondes)

**Impact sur l'architecture**:
```
Sans TSA:
├── ❌ Pas de conformité légale (eIDAS)
├── ❌ Pas de preuve d'heure d'envoi indépendante
├── ❌ Pas de chaining fonctionnel
└── ❌ Triple timestamping devient Dual (Sigstore + OTS seulement)

Avec TSA:
├── ✅ Conformité eIDAS complète
├── ✅ Proof-of-send cryptographique
├── ✅ Chaining de fil de discussion
└── ✅ Triple timestamping (Sigstore + TSA + OTS)
```

---

## 1. État Actuel - Stub Non Fonctionnel

### 1.1 Code Actuel (gwyl_mail/tsa_client.py)

**Situation**: Le fichier `tsa_client.py` proposé dans `docs/Claude_Zack_imp_20250115_v1.md` est un **stub documentation** (NotImplementedError).

```python
# Code actuel (NON FONCTIONNEL)
class TSAClient:
    def __init__(self, tsa_url: str, ...):
        self.tsa_url = tsa_url
        # ... pas d'implémentation réelle

    def timestamp(self, data: bytes) -> TSATimestamp:
        raise NotImplementedError(
            "TSA client requires ASN.1 library (asn1crypto) "
            "and ~500 lines of RFC 3161 implementation"
        )
```

**Évaluation**: 3/10
- ✅ Interface définie (signature correcte)
- ✅ Documentation du problème
- ❌ Aucune fonctionnalité
- ❌ Bloque triple timestamping
- ❌ Bloque conformité eIDAS

### 1.2 Complexité Technique du TSA

**Pourquoi un stub ne suffit pas**:

#### a) Encodage ASN.1 DER Complexe
```python
# Exemple de structure ASN.1 à encoder/décoder
TimeStampReq ::= SEQUENCE {
    version           INTEGER  { v1(1) },
    messageImprint    MessageImprint,
    reqPolicy         TSAPolicyId              OPTIONAL,
    nonce             INTEGER                  OPTIONAL,
    certReq           BOOLEAN                  DEFAULT FALSE,
    extensions        [0] IMPLICIT Extensions  OPTIONAL
}

MessageImprint ::= SEQUENCE {
    hashAlgorithm     AlgorithmIdentifier,
    hashedMessage     OCTET STRING
}

# Réponse encore plus complexe
TimeStampResp ::= SEQUENCE {
    status            PKIStatusInfo,
    timeStampToken    TimeStampToken  OPTIONAL
}

TimeStampToken ::= ContentInfo
    -- contentType is id-signedData
    -- content is SignedData
```

**Problème**: Nécessite bibliothèque ASN.1 (`asn1crypto` ou `pyasn1`)

#### b) Parsing CMS SignedData
```python
# Structure CMS SignedData à parser
SignedData ::= SEQUENCE {
    version           CMSVersion,
    digestAlgorithms  DigestAlgorithmIdentifiers,
    encapContentInfo  EncapsulatedContentInfo,
    certificates      [0] IMPLICIT CertificateSet      OPTIONAL,
    crls              [1] IMPLICIT RevocationInfoChoices OPTIONAL,
    signerInfos       SignerInfos
}

# Extraction du TSTInfo (TST Info)
TSTInfo ::= SEQUENCE {
    version           INTEGER  { v1(1) },
    policy            TSAPolicyId,
    messageImprint    MessageImprint,
    serialNumber      INTEGER,
    genTime           GeneralizedTime,   # ← HORODATAGE CRITIQUE
    accuracy          Accuracy           OPTIONAL,
    ordering          BOOLEAN            DEFAULT FALSE,
    nonce             INTEGER            OPTIONAL,
    tsa               [0] GeneralName    OPTIONAL,
    extensions        [1] IMPLICIT Extensions OPTIONAL
}
```

**Problème**: ~300 lignes de code pour parser correctement SignedData + TSTInfo

#### c) Validation Chaîne de Certificats
```python
# Validation X.509 complète requise
def verify_tsa_certificate(tsa_cert: x509.Certificate, trusted_roots: List[x509.Certificate]) -> bool:
    """
    Vérifier:
    1. Chaîne de certificats valide jusqu'à root CA
    2. Certificate policy pour timestamping (OID 1.3.6.1.5.5.7.3.8)
    3. Pas de révocation (OCSP ou CRL)
    4. Validité temporelle
    5. Extensions critiques
    """
    # ~100 lignes de validation
```

#### d) Services TSA Publics Limités
```python
# Seule option gratuite: FreeTSA (INSTABLE)
FREE_TSA_SERVERS = {
    "freetsa": "https://freetsa.org/tsr",  # ⚠️ Uptime ~85%, rate limits
}

# Options payantes/qualifiées (eIDAS)
QUALIFIED_TSA_SERVERS = {
    "digicert": "https://timestamp.digicert.com",  # $$$
    "globalsign": "https://timestamp.globalsign.com",  # $$$
    "entrust": "https://timestamp.entrust.net",  # $$$
}
```

**Problème**: Infrastructure externe requise (coût ou fiabilité)

---

## 2. Importance Critique du TSA (Rappel)

### 2.1 Explication Technique de l'Horodatage TSA

Citation de l'utilisateur:

> "L'algorithme de horodatage d'une autorité de horodatage (TSA) repose sur un processus cryptographique en plusieurs étapes:
>
> 1. **Hachage du document** : Le client calcule un hash du document à horodater (SHA-256).
> 2. **Création de la requête** : Le client envoie le hash (pas le document) au TSA avec optionnellement un nonce (anti-replay).
> 3. **Signature par le TSA** :
>    - Le TSA ajoute un timestamp précis (UTC avec précision milliseconde)
>    - Encapsule hash + timestamp + nonce dans une structure TSTInfo
>    - Signe cryptographiquement le tout avec sa clé privée qualifiée
>    - Retourne un token TimeStampToken (CMS SignedData)
> 4. **Vérification** :
>    - Vérifier signature TSA avec certificat public
>    - Vérifier chaîne de certificats jusqu'à root CA de confiance
>    - Extraire le timestamp signé
>    - Vérifier que le hash correspond
>
> **Ca se passe de commentaires.**"

### 2.2 Gains Pratiques pour GWyl Mail

> "En gros le TSA nous donne **l'heure du hachage** donc en gros **l'heure à laquelle le mail a été envoyé** car il est haché juste avant envoi.
>
> Donc en gros on a une info qui va **au-delà de celle du serveur SMTP** ou du protocole qui horodate de manière cryptée le mail, le courrier.
>
> Bref la poste mais on sait **quand le courrier est parti**, on sait normalement quand est-ce qu'il va arriver car on a l'assurance de l'heure à laquelle il a été délivré...
>
> Un autre élément c'est qu'il assure aussi une **forme d'intégrité pour la chaîne de traitement**, il assure une **cohérence de tout le fil des mails envoyés**, on peut lier une **fonctionnalité de chaining**.
>
> Bref je crois que **ça offre beaucoup de perspectives**."

### 2.3 Rôle dans Triple Timestamping

```
Architecture Triple Timestamping:

Message → Hash SHA-256 → Tier 1 (IMMÉDIAT 0-2s)
                           ├── Sigstore Rekor (OIDC identity, MEDIUM trust)
                           └── TSA RFC 3161 (eIDAS qualifié, HIGH trust) ← INDISPENSABLE

                         Tier 2 (LÉGAL DIFFÉRÉ 6-24h)
                           └── OpenTimestamps Bitcoin (blockchain, HIGH trust)

État Immuable 1 (t0):
├── Sigstore: log_index, integrated_time
├── TSA: genTime (timestamp qualifié signé) ← PROOF-OF-SEND
└── OTS: pending (attestation Bitcoin différée)

Chaining:
Mail N → TSA timestamp → Mail N+1 → TSA timestamp
         (t_N)                       (t_N+1, ref hash_N)

         Assure: t_N+1 > t_N ET intégrité du fil
```

---

## 3. Trois Options d'Implémentation

### Option A: Implémentation Complète Native Python

**Description**: Implémenter RFC 3161 complet avec `asn1crypto` ou `pyasn1`.

#### Architecture
```python
# gwyl_mail/tsa/client.py (~300 lignes)
class TSAClient:
    def __init__(self, tsa_url: str, hash_algo: str = "sha256", timeout: int = 10):
        self.tsa_url = tsa_url
        self.hash_algo = hash_algo
        self.timeout = timeout

    def timestamp(self, data: bytes, nonce: Optional[int] = None) -> TSATimestamp:
        """
        1. Créer TimeStampReq (ASN.1 DER)
        2. POST → TSA server
        3. Parser TimeStampResp (ASN.1 DER)
        4. Extraire et valider TimeStampToken (CMS SignedData)
        5. Retourner TSATimestamp structuré
        """
        # Hash du data
        hasher = hashlib.sha256()
        hasher.update(data)
        digest = hasher.digest()

        # Créer requête ASN.1
        req = self._build_timestamp_request(digest, nonce)
        req_der = req.dump()  # asn1crypto

        # Envoyer au TSA
        response = requests.post(
            self.tsa_url,
            data=req_der,
            headers={"Content-Type": "application/timestamp-query"},
            timeout=self.timeout
        )

        # Parser réponse
        resp = asn1_parse_timestamp_response(response.content)

        # Valider status
        if resp.status != PKIStatus.granted:
            raise TSAError(f"TSA rejected: {resp.status}")

        # Extraire token
        token = resp.time_stamp_token
        tst_info = self._extract_tst_info(token)

        # Valider hash
        if tst_info.message_imprint.hashed_message != digest:
            raise TSAError("Hash mismatch in TSA response")

        return TSATimestamp(
            timestamp=tst_info.gen_time,
            tsa_policy=tst_info.policy,
            serial_number=tst_info.serial_number,
            token_der=token.dump(),
            certificates=self._extract_certificates(token)
        )

# gwyl_mail/tsa/asn1_structures.py (~200 lignes)
# Définitions ASN.1 complètes avec asn1crypto

from asn1crypto.core import Sequence, Integer, OctetString, Boolean
from asn1crypto.algos import DigestAlgorithm
from asn1crypto.cms import ContentInfo, SignedData

class MessageImprint(Sequence):
    _fields = [
        ('hash_algorithm', DigestAlgorithm),
        ('hashed_message', OctetString),
    ]

class TimeStampReq(Sequence):
    _fields = [
        ('version', Integer),
        ('message_imprint', MessageImprint),
        ('req_policy', ObjectIdentifier, {'optional': True}),
        ('nonce', Integer, {'optional': True}),
        ('cert_req', Boolean, {'default': False}),
        ('extensions', Extensions, {'optional': True, 'implicit': 0}),
    ]

# ... 15+ structures ASN.1 supplémentaires

# gwyl_mail/tsa/verification.py (~150 lignes)
class TSAVerifier:
    def __init__(self, trusted_roots: List[Path]):
        self.trusted_roots = self._load_roots(trusted_roots)

    def verify(self, tsa_timestamp: TSATimestamp, original_data: bytes) -> VerificationResult:
        """
        Vérification complète:
        1. Valider signature CMS
        2. Valider chaîne de certificats
        3. Vérifier hash correspond
        4. Vérifier policy TSA
        5. Vérifier nonce (si présent)
        """
        # Parse CMS SignedData
        signed_data = cms.ContentInfo.load(tsa_timestamp.token_der)

        # Vérifier signature
        signer_info = signed_data['content']['signer_infos'][0]
        signature = signer_info['signature'].native

        # Reconstruire signed attributes
        signed_attrs = signer_info['signed_attrs']
        signed_attrs_der = signed_attrs.dump()

        # Vérifier avec certificat TSA
        tsa_cert = self._extract_tsa_certificate(signed_data)
        public_key = tsa_cert.public_key()

        try:
            public_key.verify(
                signature,
                signed_attrs_der,
                padding.PKCS1v15(),
                tsa_cert.signature_hash_algorithm
            )
        except InvalidSignature:
            return VerificationResult(valid=False, error="Invalid TSA signature")

        # Vérifier chaîne de certificats
        chain_valid = self._verify_certificate_chain(tsa_cert, self.trusted_roots)
        if not chain_valid:
            return VerificationResult(valid=False, error="Invalid certificate chain")

        # Vérifier hash
        hasher = hashlib.sha256()
        hasher.update(original_data)
        expected_hash = hasher.digest()

        tst_info = self._extract_tst_info(signed_data)
        actual_hash = tst_info.message_imprint.hashed_message

        if expected_hash != actual_hash:
            return VerificationResult(valid=False, error="Hash mismatch")

        return VerificationResult(
            valid=True,
            timestamp=tst_info.gen_time,
            tsa_name=self._extract_tsa_name(tsa_cert),
            accuracy=tst_info.accuracy
        )
```

#### Dépendances
```python
# requirements.txt ajouts
asn1crypto>=1.5.1  # ASN.1 encoding/decoding
requests>=2.31.0   # HTTP pour TSA requests
cryptography>=41.0.0  # X.509 validation (déjà présent)
```

#### Avantages
- ✅ **Contrôle total** sur implémentation
- ✅ **Pas de dépendance externe fragile** (bibliothèque)
- ✅ **Optimisable** (caching, retry logic personnalisé)
- ✅ **Éducatif** (compréhension profonde RFC 3161)
- ✅ **Maintenabilité** (code sous notre contrôle)

#### Inconvénients
- ❌ **Effort important**: ~500 lignes code + tests (~3-5 jours)
- ❌ **Complexité ASN.1**: Courbe d'apprentissage raide
- ❌ **Risque bugs**: Validation cryptographique critique
- ❌ **Maintenance**: Évolution RFC, nouvelles attaques

#### Effort Estimé
- **Développement**: 3-5 jours (24-40h)
  - Jour 1: ASN.1 structures + build request (8h)
  - Jour 2: Parse response + extract TSTInfo (8h)
  - Jour 3: Verification + certificate chain (8h)
  - Jour 4-5: Tests + edge cases + documentation (8-16h)
- **Tests**: 2 jours (16h)
  - Tests unitaires (mock TSA responses)
  - Tests intégration (FreeTSA réel)
  - Tests erreurs (invalid signatures, expired certs)
- **Documentation**: 0.5 jour (4h)

**Total**: 5.5-7.5 jours (44-60h)

---

### Option B: Utiliser Bibliothèque `rfc3161ng`

**Description**: Utiliser bibliothèque Python existante pour RFC 3161.

#### Bibliothèque Recommandée: rfc3161ng
```bash
pip install rfc3161ng
```

**GitHub**: https://github.com/trbs/rfc3161ng
**Statut**: Actif (dernière release 2023), 200+ stars
**Dépendances**: `pyasn1`, `pyasn1-modules`, `requests`, `cryptography`

#### Implémentation avec rfc3161ng
```python
# gwyl_mail/tsa/client.py (~100 lignes avec rfc3161ng)

from rfc3161ng import RemoteTimestamper, TimestampingError
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import hashlib

@dataclass
class TSATimestamp:
    """Timestamp TSA structuré."""
    timestamp: datetime  # genTime du TSTInfo
    tsa_policy: str  # OID de la politique TSA
    serial_number: int  # Numéro de série unique
    token_der: bytes  # Token complet (pour archivage)
    hash_algorithm: str  # Algorithme utilisé (sha256)
    nonce: Optional[int] = None

class TSAClient:
    """Client TSA utilisant rfc3161ng."""

    def __init__(
        self,
        tsa_url: str = "https://freetsa.org/tsr",
        hash_algo: str = "sha256",
        timeout: int = 10,
        certificate: Optional[Path] = None
    ):
        self.tsa_url = tsa_url
        self.hash_algo = hash_algo
        self.timeout = timeout

        # Créer timestamper
        self.timestamper = RemoteTimestamper(
            tsa_url,
            certificate=str(certificate) if certificate else None,
            hashname=hash_algo
        )

    def timestamp(self, data: bytes, nonce: Optional[int] = None) -> TSATimestamp:
        """
        Créer timestamp TSA pour data.

        Args:
            data: Données à horodater (généralement hash d'un message)
            nonce: Nonce optionnel anti-replay

        Returns:
            TSATimestamp avec token signé

        Raises:
            TSAError: Si TSA refuse ou timeout
        """
        # Hash du data
        hasher = hashlib.new(self.hash_algo)
        hasher.update(data)
        digest = hasher.digest()

        try:
            # Appel rfc3161ng
            tsr = self.timestamper(
                data=digest,
                nonce=nonce,
                return_tsr=True
            )

            # Extraire TSTInfo
            tst_info = tsr.tst_info

            return TSATimestamp(
                timestamp=tst_info['gen_time'].asDateTime,
                tsa_policy=str(tst_info['policy']),
                serial_number=int(tst_info['serial_number']),
                token_der=tsr.token,
                hash_algorithm=self.hash_algo,
                nonce=nonce
            )

        except TimestampingError as e:
            raise TSAError(f"TSA timestamping failed: {e}")
        except Exception as e:
            raise TSAError(f"Unexpected error: {e}")

class TSAVerifier:
    """Vérificateur de timestamps TSA."""

    def __init__(self, trusted_roots: Optional[List[Path]] = None):
        self.trusted_roots = trusted_roots or []

    def verify(
        self,
        tsa_timestamp: TSATimestamp,
        original_data: bytes
    ) -> tuple[bool, Optional[str]]:
        """
        Vérifier timestamp TSA.

        Returns:
            (valid, error_message)
        """
        # Hash de l'original
        hasher = hashlib.new(tsa_timestamp.hash_algorithm)
        hasher.update(original_data)
        expected_digest = hasher.digest()

        try:
            # Vérifier avec rfc3161ng
            from rfc3161ng import check_timestamp

            # check_timestamp vérifie:
            # - Signature CMS
            # - Chaîne de certificats
            # - Hash match
            # - Nonce (si présent)
            result = check_timestamp(
                tsa_timestamp.token_der,
                digest=expected_digest,
                hashname=tsa_timestamp.hash_algorithm,
                nonce=tsa_timestamp.nonce
            )

            if result:
                return True, None
            else:
                return False, "Timestamp verification failed"

        except Exception as e:
            return False, f"Verification error: {e}"

# Intégration dans dual_proof.py
def create_proof_with_tsa(
    message: EmailMessage,
    identity: str,
    tsa_url: str = "https://freetsa.org/tsr",
    profile: str = "strict"
) -> Dict[str, Any]:
    """Créer preuve avec triple timestamping incluant TSA."""

    # 1. Canonicalisation
    content_hash = GWylCanonical.hash(message, profile=profile)

    # 2. Tier 1 - Sigstore (immédiat)
    sigstore_proof = sign_and_timestamp(content_hash.encode(), identity)

    # 3. Tier 1 - TSA RFC 3161 (immédiat)
    tsa_client = TSAClient(tsa_url=tsa_url)
    try:
        tsa_timestamp = tsa_client.timestamp(content_hash.encode())
        tsa_proof = {
            "timestamp": tsa_timestamp.timestamp.isoformat(),
            "tsa_policy": tsa_timestamp.tsa_policy,
            "serial_number": tsa_timestamp.serial_number,
            "token": base64.b64encode(tsa_timestamp.token_der).decode(),
            "hash_algorithm": tsa_timestamp.hash_algorithm
        }
    except TSAError as e:
        # Fallback graceful: continuer sans TSA
        tsa_proof = {"error": str(e), "status": "failed"}

    # 4. Tier 2 - OTS (différé)
    ots_proof_file = OTSManager.submit(content_hash.encode(), Path(".gwyl_mail/proofs/ots"))

    # Construire proof JSON complet
    proof = {
        "version": "0.3.0",  # Version avec TSA
        "content_hash": content_hash,
        "canonicalization": {"profile": profile},
        "timestamps": {
            "tier1_sigstore": sigstore_proof,
            "tier1_tsa": tsa_proof,  # ← NOUVEAU
            "tier2_ots": {"file": str(ots_proof_file), "status": "pending"}
        },
        # ... reste du proof
    }

    return proof
```

#### Avantages
- ✅ **Rapide à implémenter**: ~100 lignes wrapper (1-2 jours)
- ✅ **Bibliothèque mature**: testée, utilisée en production
- ✅ **Complexité ASN.1 cachée**: abstraction propre
- ✅ **Maintenance réduite**: bugs fixes upstream
- ✅ **Tests existants**: rfc3161ng a sa propre suite de tests

#### Inconvénients
- ❌ **Dépendance externe**: risque abandon projet (dernière release 2023)
- ❌ **Moins de contrôle**: debugging difficile si problème interne
- ❌ **API limitée**: fonctionnalités avancées peut-être absentes
- ❌ **Dépendances transitives**: `pyasn1` + `pyasn1-modules` (lourd)

#### Effort Estimé
- **Développement**: 1-2 jours (8-16h)
  - Jour 1: Wrapper TSAClient/TSAVerifier + intégration dual_proof.py (8h)
  - Jour 2: Tests + documentation (8h optionnel)
- **Tests**: 1 jour (8h)
  - Tests unitaires (mock)
  - Tests intégration FreeTSA
- **Documentation**: 0.5 jour (4h)

**Total**: 2.5-3.5 jours (20-28h)

---

### Option C: Hybride (Client Python + Service TSA Externe Dédié)

**Description**: Implémenter client léger + déployer service TSA dédié (FreeTSA local ou service payant).

#### Architecture
```
GWyl Mail (Python)
    ↓ HTTP POST (TimeStampReq)
    ↓
FreeTSA Local (Docker)
    ├── freetsa/freetsa:latest
    ├── Config: /etc/freetsa/freetsa.conf
    ├── Certificats: Let's Encrypt ou auto-signé
    └── Port: 2020
    ↓
Retourne: TimeStampResp
```

#### Implémentation Client Léger
```python
# gwyl_mail/tsa/simple_client.py (~50 lignes)

import requests
from dataclasses import dataclass
from typing import Optional
import hashlib
import base64

@dataclass
class TSATimestamp:
    """Timestamp TSA minimal."""
    timestamp_token: bytes  # Token complet (opaque)
    timestamp_iso: Optional[str] = None  # Timestamp extrait (si parsé)

class SimpleTSAClient:
    """Client TSA ultra-simple (pas de parsing ASN.1)."""

    def __init__(self, tsa_url: str, timeout: int = 10):
        self.tsa_url = tsa_url
        self.timeout = timeout

    def timestamp(self, data: bytes) -> TSATimestamp:
        """
        Envoyer hash au TSA, retourner token opaque.
        AUCUN PARSING - juste stockage du token.
        """
        # Hash
        digest = hashlib.sha256(data).digest()

        # Requête minimale (hardcoded DER)
        req_der = self._build_minimal_request(digest)

        # POST au TSA
        response = requests.post(
            self.tsa_url,
            data=req_der,
            headers={"Content-Type": "application/timestamp-query"},
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise TSAError(f"TSA HTTP error: {response.status_code}")

        # Retourner token OPAQUE (pas de parsing)
        return TSATimestamp(
            timestamp_token=response.content,
            timestamp_iso=None  # Parsing fait par service externe
        )

    def _build_minimal_request(self, digest: bytes) -> bytes:
        """Construire TimeStampReq minimal (hardcoded DER)."""
        # Template DER pour SHA-256 (structure fixe)
        # Version 1 + MessageImprint(SHA-256, digest) + certReq=True
        # ... 20 lignes de bytes hardcodés ...
        pass  # Simplifié ici

# Vérification externalisée
class TSAVerifier:
    """Vérification déléguée à outil externe."""

    def verify(self, token: bytes, original_data: bytes) -> tuple[bool, Optional[str]]:
        """
        Option 1: Appeler openssl CLI
        Option 2: Appeler endpoint vérification du service TSA
        Option 3: Utiliser rfc3161ng juste pour verify
        """
        # Exemple avec openssl
        import subprocess

        # Sauver token temporairement
        with tempfile.NamedTemporaryFile(suffix=".tsr") as token_file:
            token_file.write(token)
            token_file.flush()

            # Sauver data
            with tempfile.NamedTemporaryFile(suffix=".dat") as data_file:
                data_file.write(original_data)
                data_file.flush()

                # Vérifier avec openssl
                cmd = [
                    "openssl", "ts", "-verify",
                    "-data", data_file.name,
                    "-in", token_file.name,
                    "-CAfile", "/path/to/tsa_ca.pem"
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    return True, None
                else:
                    return False, result.stderr
```

#### Déploiement FreeTSA Local (Docker)
```yaml
# docker-compose.yml
version: '3.8'

services:
  freetsa:
    image: freetsa/freetsa:latest
    container_name: gwyl_tsa
    ports:
      - "2020:2020"
    volumes:
      - ./tsa_config:/etc/freetsa
      - ./tsa_certs:/opt/freetsa/certs
    environment:
      - TSA_POLICY_OID=1.2.3.4.5.6.7.8.9
    restart: unless-stopped

# Lancer:
# docker-compose up -d
# Client Python → http://localhost:2020/tsr
```

#### Avantages
- ✅ **Client ultra-simple**: ~50 lignes Python
- ✅ **Parsing ASN.1 externalisé**: openssl ou service dédié
- ✅ **Contrôle infrastructure**: TSA local (uptime 99%+)
- ✅ **Pas de dépendance Python lourde**: requests seulement

#### Inconvénients
- ❌ **Infrastructure supplémentaire**: Docker, maintenance service
- ❌ **Complexité opérationnelle**: monitoring, certificats, backup
- ❌ **Pas portable**: nécessite service externe (tests CI/CD compliqués)
- ❌ **Vérification subprocess**: fragile (comme Sigstore actuel)

#### Effort Estimé
- **Développement client**: 1 jour (8h)
- **Setup infrastructure**: 2 jours (16h)
  - Docker FreeTSA
  - Certificats Let's Encrypt
  - Configuration firewall
  - Tests uptime
- **Vérification openssl**: 1 jour (8h)
- **Documentation**: 0.5 jour (4h)

**Total**: 4.5 jours (36h) + maintenance infrastructure continue

---

## 4. Analyse Comparative

### 4.1 Tableau de Décision

| Critère | Option A (Native) | Option B (rfc3161ng) | Option C (Hybride) |
|---------|-------------------|----------------------|-------------------|
| **Effort initial** | 🔴 44-60h | 🟢 20-28h | 🟡 36h |
| **Complexité code** | 🔴 Haute (~500 LOC) | 🟢 Basse (~100 LOC) | 🟢 Basse (~50 LOC) |
| **Dépendances** | 🟡 asn1crypto | 🔴 rfc3161ng + pyasn1 | 🟢 requests only |
| **Contrôle** | 🟢 Total | 🟡 Partiel | 🟡 Partiel |
| **Maintenabilité** | 🔴 Interne (effort) | 🟢 Upstream | 🔴 Infrastructure |
| **Portabilité** | 🟢 Pure Python | 🟢 Pure Python | 🔴 Nécessite service |
| **Fiabilité** | 🟡 À tester | 🟢 Éprouvée | 🟡 Dépend infra |
| **Conformité eIDAS** | 🟢 Full control | 🟢 Via library | 🟢 Via service |
| **Performance** | 🟢 Optimisable | 🟡 Dépend lib | 🟢 Réseau local |
| **Tests CI/CD** | 🟢 Mock facile | 🟢 Mock facile | 🔴 Service externe |
| **Debugging** | 🟢 Code visible | 🔴 Boîte noire | 🟡 Logs service |
| **Courbe apprentissage** | 🔴 ASN.1 complexe | 🟢 API simple | 🟢 API simple |

**Légende**: 🟢 Bon | 🟡 Moyen | 🔴 Problématique

### 4.2 Recommandation par Contexte

#### Si **Timeline court** (PoC dans 1-2 semaines):
→ **Option B (rfc3161ng)** - Implémentation rapide, fonctionnel immédiatement

#### Si **Projet à long terme** (production 6+ mois):
→ **Option A (Native)** - Contrôle total, maintenance interne, pas de dette technique

#### Si **Infrastructure existante** (déjà Docker, Kubernetes):
→ **Option C (Hybride)** - Service TSA dédié, client simple

#### Si **Conformité eIDAS critique** (audit légal):
→ **Option B ou C** - Bibliothèque/service éprouvé plutôt que code maison

### 4.3 Recommandation Finale

**RECOMMANDATION: Option B (rfc3161ng) pour Phase 1, puis Option A pour Phase 2+**

**Rationale**:
1. **Phase 1 (PoC - 2-4 semaines)**:
   - Utiliser `rfc3161ng` pour débloquer triple timestamping rapidement
   - Valider architecture globale avec TSA fonctionnel
   - Tester interopérabilité avec FreeTSA
   - Mesurer KPIs (latence, fiabilité)

2. **Phase 2 (Production - 3-6 mois)**:
   - Réimplémenter en natif (Option A) si:
     - `rfc3161ng` montre limitations
     - Besoins optimisation performance
     - Volonté indépendance totale
   - Garder `rfc3161ng` si:
     - Fonctionnalités suffisantes
     - Maintenance upstream active
     - Pas de bugs critiques

**Avantages approche hybride**:
- ✅ Déblocage immédiat (20-28h vs 44-60h)
- ✅ Validation architecture TSA sans sur-investment
- ✅ Option migration native reste ouverte
- ✅ Réduction risque (bibliothèque testée vs code maison non testé)

---

## 5. Plan d'Implémentation Option B (Recommandée)

### Sprint 1: Setup + Client TSA (2 jours / 16h)

#### Tâches
1. **Installer rfc3161ng** (1h)
   ```bash
   pip install rfc3161ng
   # Tester CLI
   rfc3161ng --url https://freetsa.org/tsr --data test.txt
   ```

2. **Créer gwyl_mail/tsa/client.py** (4h)
   - Classe `TSAClient` avec `timestamp()`
   - Classe `TSATimestamp` (dataclass)
   - Gestion erreurs (`TSAError`)
   - Configuration TSA URL (env var ou config)

3. **Créer gwyl_mail/tsa/verification.py** (3h)
   - Classe `TSAVerifier` avec `verify()`
   - Validation hash + signature
   - Extraction timestamp

4. **Tests unitaires** (4h)
   - Mock réponses TSA
   - Tests erreurs (timeout, invalid response)
   - Tests hash mismatch

5. **Tests intégration FreeTSA** (2h)
   - Tests réels avec https://freetsa.org/tsr
   - Mesure latence (KPI: <2s)
   - Tests retry logic

6. **Documentation** (2h)
   - Docstrings
   - README TSA usage
   - Exemples

### Sprint 2: Intégration Triple Timestamping (1.5 jours / 12h)

#### Tâches
1. **Modifier dual_proof.py → triple_proof.py** (3h)
   - Ajouter appel TSA client
   - Gérer fallback graceful si TSA down
   - Logging événements TSA

2. **Mettre à jour schéma proof JSON** (2h)
   - Ajouter section `tier1_tsa` dans timestamps
   - Versionner à 0.3.0
   - Migrer schémas existants

3. **Modifier verify.py** (3h)
   - Ajouter vérification TSA timestamp
   - Valider cohérence temporelle (Sigstore ≈ TSA ± 5s)
   - Rapport détaillé (quel tier a échoué)

4. **Tests end-to-end** (3h)
   - Email → canonicalisation → triple timestamp → vérification
   - Tests scénarios (TSA success, TSA failure)
   - Validation KPIs

5. **Documentation** (1h)
   - Mettre à jour PROOF_SCHEMA_v0.md → v0.3.0
   - Diagrammes triple timestamping

### Sprint 3: Production Ready (1 jour / 8h)

#### Tâches
1. **Retry logic + circuit breaker** (2h)
   - Retry avec backoff exponentiel (FreeTSA instable)
   - Circuit breaker si TSA down >3 fois

2. **Monitoring + observabilité** (2h)
   - Métriques: latence TSA, taux succès, erreurs
   - Logs structurés (JSON)

3. **Configuration flexible** (1h)
   - Support multi-TSA (fallback FreeTSA → DigiCert)
   - Config par environnement (dev/staging/prod)

4. **Certificats trusted roots** (1h)
   - Embarquer CA roots pour validation
   - Update process (certifi-like)

5. **Tests performance** (1h)
   - Benchmark: 100 timestamps sequentiels
   - KPI: <2s par timestamp (moyenne)

6. **Documentation finale** (1h)
   - Guide opérationnel
   - Troubleshooting TSA

### Timeline Total
- **Sprint 1**: 2 jours (16h)
- **Sprint 2**: 1.5 jours (12h)
- **Sprint 3**: 1 jour (8h)
- **Buffer**: 0.5 jour (4h)

**Total: 5 jours (40h)** pour TSA production-ready avec Option B

---

## 6. Intégration avec Architecture Existante

### 6.1 Modification Proof Schema (v0.2 → v0.3)

```json
{
  "version": "0.3.0",
  "content_hash": "abc123...",
  "canonicalization": {
    "profile": "strict",
    "algorithm": "gwyl_v0"
  },
  "timestamps": {
    "tier1_sigstore": {
      "bundle_path": ".gwyl_mail/proofs/sigstore/bundle_msg123.json",
      "log_index": 98765432,
      "integrated_time": 1700000000,
      "certificate_identity": "user@example.com",
      "certificate_issuer": "https://accounts.google.com"
    },
    "tier1_tsa": {
      "timestamp": "2025-11-15T15:23:45.123456Z",
      "tsa_policy": "1.3.6.1.4.1.4146.2.3",
      "serial_number": 4567890123,
      "token_path": ".gwyl_mail/proofs/tsa/token_msg123.tsr",
      "hash_algorithm": "sha256",
      "accuracy": {
        "seconds": 1,
        "millis": 0,
        "micros": 0
      },
      "tsa_name": "FreeTSA"
    },
    "tier2_ots": {
      "file": ".gwyl_mail/proofs/ots/msg123.ots",
      "status": "pending",
      "submitted_at": "2025-11-15T15:23:46Z"
    }
  },
  "identity": {
    "from_hash": "sha256:def456...",
    "policy_hash": "sha256:789abc..."
  },
  "metadata": {
    "message_id": "msg123",
    "created_at": "2025-11-15T15:23:44Z",
    "gwyl_version": "0.3.0"
  }
}
```

### 6.2 Workflow Triple Timestamping

```python
# gwyl_mail/triple_proof.py (évolution de dual_proof.py)

def create_triple_proof(
    message: EmailMessage,
    identity: str,
    tsa_url: str = "https://freetsa.org/tsr",
    policy_path: Optional[Path] = None,
    profile: str = "strict"
) -> Dict[str, Any]:
    """
    Créer preuve cryptographique avec triple timestamping.

    Architecture:
        Tier 1 (Immédiat 0-2s):
            - Sigstore Rekor (OIDC identity, transparency log)
            - TSA RFC 3161 (horodatage qualifié eIDAS)

        Tier 2 (Différé 6-24h):
            - OpenTimestamps (ancrage blockchain Bitcoin)

    Returns:
        Proof JSON v0.3.0 avec 3 timestamps
    """
    from gwyl_mail.tsa.client import TSAClient, TSAError

    # 1. Canonicalisation
    content_hash = GWylCanonical.hash(message, profile=profile)
    logger.info(f"Content hash: {content_hash}")

    # 2. Tier 1a - Sigstore (immédiat, OIDC identity)
    try:
        sigstore_proof = sign_and_timestamp(content_hash.encode(), identity)
        logger.info(f"Sigstore: log_index={sigstore_proof['log_index']}")
    except Exception as e:
        logger.error(f"Sigstore failed: {e}")
        raise ProofError("Sigstore timestamping failed (critical)")

    # 3. Tier 1b - TSA (immédiat, horodatage qualifié)
    tsa_proof = {}
    try:
        tsa_client = TSAClient(tsa_url=tsa_url, timeout=10)
        tsa_timestamp = tsa_client.timestamp(content_hash.encode())

        # Sauvegarder token TSA
        token_dir = Path(".gwyl_mail/proofs/tsa")
        token_dir.mkdir(parents=True, exist_ok=True)

        message_id = extract_message_id(message) or "unknown"
        token_path = token_dir / f"token_{message_id}.tsr"
        token_path.write_bytes(tsa_timestamp.token_der)

        tsa_proof = {
            "timestamp": tsa_timestamp.timestamp.isoformat(),
            "tsa_policy": tsa_timestamp.tsa_policy,
            "serial_number": tsa_timestamp.serial_number,
            "token_path": str(token_path),
            "hash_algorithm": tsa_timestamp.hash_algorithm,
            "tsa_name": "FreeTSA"  # Ou extraire du certificat
        }

        logger.info(f"TSA: timestamp={tsa_timestamp.timestamp}")

        # Vérifier cohérence temporelle (Sigstore ≈ TSA)
        sigstore_time = datetime.fromtimestamp(sigstore_proof['integrated_time'])
        tsa_time = tsa_timestamp.timestamp
        delta = abs((sigstore_time - tsa_time).total_seconds())

        if delta > 60:  # Alerte si >1 minute d'écart
            logger.warning(f"Time delta Sigstore-TSA: {delta}s (>60s)")

    except TSAError as e:
        logger.error(f"TSA failed: {e}")
        # Fallback graceful: continuer sans TSA (backward compat)
        tsa_proof = {
            "status": "failed",
            "error": str(e),
            "timestamp": None
        }

    # 4. Tier 2 - OTS (différé, blockchain)
    ots_dir = Path(".gwyl_mail/proofs/ots")
    ots_file = OTSManager.submit(content_hash.encode(), ots_dir)
    logger.info(f"OTS submitted: {ots_file}")

    # 5. Charger politique identité
    policy_hash = None
    if policy_path and policy_path.exists():
        policy_content = policy_path.read_text()
        policy_hash = hashlib.sha256(policy_content.encode()).hexdigest()

    # 6. Construire proof JSON complet
    proof = {
        "version": "0.3.0",
        "content_hash": content_hash,
        "canonicalization": {
            "profile": profile,
            "algorithm": "gwyl_v0"
        },
        "timestamps": {
            "tier1_sigstore": sigstore_proof,
            "tier1_tsa": tsa_proof,  # ← NOUVEAU
            "tier2_ots": {
                "file": str(ots_file),
                "status": "pending",
                "submitted_at": datetime.utcnow().isoformat() + "Z"
            }
        },
        "identity": {
            "from_hash": hashlib.sha256(
                extract_from_address(message).encode()
            ).hexdigest(),
            "policy_hash": policy_hash
        },
        "metadata": {
            "message_id": extract_message_id(message),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "gwyl_version": "0.3.0"
        }
    }

    return proof
```

### 6.3 Vérification Triple Proof

```python
# gwyl_mail/verify.py (ajout vérification TSA)

def verify_triple_proof(
    message: EmailMessage,
    proof: Dict[str, Any]
) -> VerificationResult:
    """
    Vérifier preuve triple timestamping.

    Vérifie:
    1. Content hash (canonicalisation)
    2. Sigstore signature + Rekor transparency
    3. TSA timestamp signature + chain
    4. OTS blockchain anchor (si disponible)
    5. Cohérence temporelle entre tiers
    """
    results = {
        "content_hash": False,
        "sigstore": False,
        "tsa": False,
        "ots": False,
        "temporal_consistency": False
    }

    # 1. Vérifier content hash
    expected_hash = proof["content_hash"]
    actual_hash = GWylCanonical.hash(message, profile=proof["canonicalization"]["profile"])

    if actual_hash != expected_hash:
        return VerificationResult(
            valid=False,
            error="Content hash mismatch",
            details=results
        )

    results["content_hash"] = True

    # 2. Vérifier Sigstore
    sigstore_proof = proof["timestamps"]["tier1_sigstore"]
    # ... vérification existante ...
    results["sigstore"] = True

    # 3. Vérifier TSA
    tsa_proof = proof["timestamps"].get("tier1_tsa", {})

    if tsa_proof.get("status") == "failed":
        # TSA a échoué lors de création (backward compat)
        logger.warning("TSA timestamp not available (proof creation failed)")
        results["tsa"] = None  # Ni succès ni échec
    elif "token_path" in tsa_proof:
        from gwyl_mail.tsa.verification import TSAVerifier

        token_path = Path(tsa_proof["token_path"])
        if not token_path.exists():
            return VerificationResult(
                valid=False,
                error=f"TSA token not found: {token_path}",
                details=results
            )

        token_der = token_path.read_bytes()

        verifier = TSAVerifier()
        tsa_valid, tsa_error = verifier.verify(
            TSATimestamp(
                timestamp_token=token_der,
                timestamp_iso=tsa_proof["timestamp"],
                hash_algorithm=tsa_proof.get("hash_algorithm", "sha256")
            ),
            actual_hash.encode()
        )

        if not tsa_valid:
            return VerificationResult(
                valid=False,
                error=f"TSA verification failed: {tsa_error}",
                details=results
            )

        results["tsa"] = True

    # 4. Vérifier OTS (si confirmé)
    ots_proof = proof["timestamps"]["tier2_ots"]
    ots_file = Path(ots_proof["file"])

    if ots_file.exists():
        ots_valid, ots_timestamp = OTSManager.verify(ots_file, actual_hash.encode())
        results["ots"] = ots_valid
    else:
        results["ots"] = None  # Fichier manquant

    # 5. Vérifier cohérence temporelle
    timestamps = []

    # Sigstore
    if "integrated_time" in sigstore_proof:
        timestamps.append(("Sigstore", datetime.fromtimestamp(sigstore_proof["integrated_time"])))

    # TSA
    if results["tsa"] and "timestamp" in tsa_proof:
        timestamps.append(("TSA", datetime.fromisoformat(tsa_proof["timestamp"].replace("Z", ""))))

    # OTS (si confirmé)
    if results["ots"] and ots_timestamp:
        timestamps.append(("OTS", datetime.fromtimestamp(ots_timestamp)))

    # Vérifier que tous les timestamps sont cohérents (±5 minutes pour Tier 1)
    if len(timestamps) >= 2:
        tier1_times = [t for name, t in timestamps if name in ["Sigstore", "TSA"]]

        if len(tier1_times) == 2:
            delta = abs((tier1_times[0] - tier1_times[1]).total_seconds())

            if delta > 300:  # >5 minutes
                logger.warning(f"Tier 1 time delta: {delta}s (>300s)")
                # Pas bloquant, juste warning

            results["temporal_consistency"] = (delta <= 300)
        else:
            results["temporal_consistency"] = True  # Pas assez de données

    # Verdict final
    critical_checks = [results["content_hash"], results["sigstore"]]

    # TSA optionnel mais recommandé
    if results["tsa"] is False:  # False = échec, None = absent
        logger.warning("TSA verification failed (not critical)")

    if not all(critical_checks):
        return VerificationResult(
            valid=False,
            error="Critical verification failed",
            details=results
        )

    return VerificationResult(
        valid=True,
        error=None,
        details=results,
        timestamps=timestamps
    )
```

---

## 7. Services TSA Disponibles

### 7.1 Gratuits (Limités)

| Service | URL | Uptime | Limites | eIDAS |
|---------|-----|--------|---------|-------|
| FreeTSA | https://freetsa.org/tsr | ~85% | 100 req/jour | ❌ Non qualifié |
| DigiCert Free | https://timestamp.digicert.com | ~95% | Rate limited | ❌ Non qualifié |

### 7.2 Payants (Qualifiés)

| Service | URL | Prix | eIDAS | Uptime SLA |
|---------|-----|------|-------|-----------|
| GlobalSign | https://timestamp.globalsign.com | ~€500/an | ✅ Qualifié | 99.9% |
| DigiCert Enterprise | https://timestamp.digicert.com | ~€800/an | ✅ Qualifié | 99.95% |
| Entrust | https://timestamp.entrust.net | ~€600/an | ✅ Qualifié | 99.9% |

### 7.3 Auto-hébergé

| Solution | Technologie | Effort | eIDAS |
|----------|-------------|--------|-------|
| FreeTSA (Docker) | OpenSSL + Apache | ~2 jours setup | ❌ Non qualifié (sauf certificat qualifié) |
| OpenXPKI | PKI complète | ~1 semaine | ✅ Si config correcte |

### 7.4 Recommandation Services

**Phase PoC**: FreeTSA (gratuit, acceptable pour tests)
**Phase Production**: GlobalSign ou DigiCert Enterprise (eIDAS qualifié, SLA 99.9%+)
**Phase Auto-hébergé**: Après validation besoin, si volumes élevés (>10k timestamps/jour)

---

## 8. Risques et Mitigations

### 8.1 Risques Techniques

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| FreeTSA instable | 🔴 Haute | 🟡 Moyen | Retry logic + fallback multi-TSA |
| rfc3161ng abandonné | 🟡 Moyenne | 🔴 Haut | Fork interne ou migration Option A |
| Latence TSA >2s | 🟡 Moyenne | 🟡 Moyen | Timeout configurable + async |
| Certificat TSA expiré | 🟢 Basse | 🔴 Haut | Validation chain + monitoring |
| ASN.1 parsing bugs | 🟡 Moyenne (si Option A) | 🔴 Haut | Tests extensifs + code review |

### 8.2 Risques Opérationnels

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Coût service qualifié | 🔴 Haute | 🟡 Moyen | Budget €500-800/an (eIDAS requis) |
| Vendor lock-in | 🟡 Moyenne | 🟡 Moyen | Support multi-TSA dans config |
| Conformité eIDAS | 🟡 Moyenne | 🔴 Haut | Audit légal + certificat qualifié |
| RGPD (logs TSA) | 🟢 Basse | 🟡 Moyen | Hash adresses (déjà fait) |

### 8.3 Plan de Contingence

**Si FreeTSA down pendant PoC**:
1. Basculer sur DigiCert Free (automatique via config)
2. Accepter proof sans TSA (backward compat)
3. Logger événement pour monitoring

**Si rfc3161ng a bug critique**:
1. Fork bibliothèque + fix interne
2. Migrer vers Option A (natif) si récurrent
3. Basculer vers Option C (openssl CLI) temporairement

**Si audit eIDAS échoue**:
1. Migrer vers service qualifié (GlobalSign/DigiCert)
2. Audit configuration TSA
3. Documentation légale complète

---

## 9. Métriques de Succès

### KPIs TSA (Phase PoC)

| Métrique | Cible | Mesure |
|----------|-------|--------|
| **Latence moyenne** | <2s | Moyenne 100 requêtes FreeTSA |
| **Taux succès** | ≥95% | (Succès / Total) × 100 |
| **Cohérence temporelle** | Sigstore-TSA ±5s | Delta timestamps Tier 1 |
| **Taille token** | <5KB | Moyenne token TSR |
| **Uptime FreeTSA** | ≥85% | Monitoring 7 jours |

### KPIs Production

| Métrique | Cible | Mesure |
|----------|-------|--------|
| **Latence P95** | <3s | 95e percentile latence TSA |
| **Taux succès** | ≥99% | Service qualifié SLA |
| **Conformité eIDAS** | 100% | Audit légal OK |
| **Coût par timestamp** | <€0.01 | Total coût / nb timestamps |

---

## 10. Questions Ouvertes

### 10.1 Questions Critiques (Décision requise)

1. **Quelle option choisir?**
   - ✅ **Option B recommandée** (rfc3161ng pour PoC)
   - Valider avec utilisateur final

2. **Service TSA pour PoC?**
   - FreeTSA (gratuit, instable) ← Recommandé pour tests
   - DigiCert Free (rate limited)
   - Auto-hébergé Docker (2 jours setup)

3. **Service TSA pour Production?**
   - GlobalSign (€500/an, eIDAS qualifié) ← Recommandé
   - DigiCert Enterprise (€800/an)
   - Auto-hébergé (si >10k timestamps/jour)

4. **Fallback si TSA échoue?**
   - ✅ Continuer avec Dual proof (Sigstore + OTS)
   - ❌ Bloquer envoi email (trop strict)

5. **Versioning proof schema?**
   - ✅ v0.3.0 avec TSA
   - Backward compat v0.2.0 (dual proof)

### 10.2 Questions Techniques

6. **Retry logic TSA?**
   - Proposé: 3 tentatives, backoff exponentiel (1s, 2s, 4s)
   - Timeout: 10s par tentative

7. **Multi-TSA fallback?**
   - Proposé: FreeTSA → DigiCert Free → Échec graceful
   - Config: `tsa_urls = ["https://freetsa.org/tsr", "https://timestamp.digicert.com"]`

8. **Stockage tokens TSA?**
   - Proposé: `.gwyl_mail/proofs/tsa/token_{message_id}.tsr`
   - Format: DER binaire (3-5 KB par token)
   - Archivage: même que bundles Sigstore

9. **Validation chaîne certificats?**
   - Proposé: rfc3161ng gère validation (trust system roots)
   - Option: embarquer CA roots explicites (plus portable)

10. **Chaining des emails?**
    - Proposé: Ajouter `previous_message_hash` dans proof metadata
    - TSA timestamp prouve ordre chronologique
    - Implémentation: Phase 2 (après TSA fonctionnel)

---

## 11. Prochaines Étapes

### Immédiat (Avant implémentation)

1. **Décision Option**: Valider Option B (rfc3161ng) avec équipe
2. **Budget**: Confirmer budget service TSA production (~€500-800/an)
3. **Service PoC**: Tester FreeTSA manuellement (CLI rfc3161ng)
4. **Conformité**: Consulter expert eIDAS (si requis légalement)

### Sprint 1 (Semaine 1)

1. Implémenter TSAClient avec rfc3161ng
2. Tests unitaires + intégration FreeTSA
3. Documentation technique

### Sprint 2 (Semaine 2)

1. Intégrer dans triple_proof.py
2. Mettre à jour schéma v0.3.0
3. Tests end-to-end

### Sprint 3 (Semaine 3)

1. Retry logic + monitoring
2. Multi-TSA fallback
3. Tests performance

### Phase Production (Mois 2-3)

1. Migration service TSA qualifié (GlobalSign)
2. Audit eIDAS
3. Monitoring production

---

## 12. Conclusion

### Résumé Exécutif

**TSA est INDISPENSABLE** pour GWyl Mail:
- ✅ Conformité eIDAS (horodatage qualifié)
- ✅ Proof-of-send cryptographique (indépendant SMTP)
- ✅ Chaining fonctionnel (cohérence fil emails)
- ✅ Triple timestamping complet (Tier 1 + Tier 2)

**Implémentation actuelle**: Stub non fonctionnel (3/10) - **BLOQUANT**

**Solution recommandée**: **Option B (rfc3161ng)** pour PoC, migration Option A si nécessaire

**Effort estimé**: 5 jours (40h) pour TSA production-ready

**Coût récurrent**: €500-800/an pour service eIDAS qualifié (production)

**Timeline**:
- Semaine 1-3: Implémentation PoC (FreeTSA)
- Mois 2-3: Migration production (GlobalSign/DigiCert)
- Audit eIDAS: Mois 3

### Impact sur Projet

| Aspect | Avant TSA | Après TSA |
|--------|-----------|-----------|
| **Conformité** | ❌ Partielle | ✅ eIDAS complète |
| **Timestamping** | 🟡 Dual (Sigstore + OTS) | ✅ Triple (+ TSA) |
| **Proof-of-send** | ❌ Indirect (Sigstore) | ✅ Direct (TSA qualifié) |
| **Chaining** | ❌ Non fonctionnel | ✅ Fonctionnel |
| **Trust légal** | 🟡 Moyen | ✅ Haute (eIDAS) |

**Décision critique**: TSA n'est pas optionnel - implémentation requise pour Phase 1.

---

**Document créé le**: 2025-11-15 15:00:00
**Auteur**: Claude (Anthropic)
**Révision**: v1.0
**Statut**: Prêt pour revue et décision

**Fichiers liés**:
- `docs/Claude_Zack_imp_20250115_v1.md` (Proposition globale)
- `docs/sigstore_improvements_20251115_144123.md` (Analyse Sigstore)
- `docs/specs/PROOF_SCHEMA_v0.md` (Schéma actuel v0.2)

---

**FIN DE L'ANALYSE TSA**
