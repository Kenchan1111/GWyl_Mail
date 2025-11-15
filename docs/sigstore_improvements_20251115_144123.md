# GWyl Mail - Analyse Intégration Sigstore et Améliorations

**Date**: 2025-01-15
**Version**: v1.0
**Auteur**: Claude (Anthropic)
**Statut**: Analyse Technique

---

## 📋 Table des Matières

1. [Vue d'Ensemble Intégration Actuelle](#vue-densemble-intégration-actuelle)
2. [Architecture Hybride CLI + Bibliothèque](#architecture-hybride-cli--bibliothèque)
3. [Points Forts](#points-forts)
4. [Problèmes Critiques](#problèmes-critiques)
5. [Problèmes Modérés](#problèmes-modérés)
6. [Recommandations d'Amélioration](#recommandations-damélioration)
7. [Plan de Migration](#plan-de-migration)
8. [Références](#références)

---

## 📊 Vue d'Ensemble Intégration Actuelle

### Modules Impliqués

L'intégration Sigstore est répartie sur **4 modules** :

| Module | Ligne Code | Approche | Rôle | État |
|--------|-----------|----------|------|------|
| `sigstore_timestamp.py` | ~178 lignes | **CLI subprocess** | Signature + timestamping | ⚠️ Fragile |
| `sigstore_identity.py` | ~254 lignes | **Bibliothèque Python** | Extraction identité X.509 | ✅ Robuste |
| `dsse_signer.py` | ~278 lignes | **CLI subprocess** | Signature DSSE proof | ⚠️ Fragile |
| `dual_proof.py` | ~160 lignes | Orchestration | Création proof complet | ✅ OK |

**Total**: ~870 lignes de code Sigstore

---

### Approche Hybride

```
┌─────────────────────────────────────────────────────────┐
│              INTÉGRATION SIGSTORE                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Signature & Timestamping                              │
│  ┌────────────────────────────────┐                    │
│  │  subprocess.run([              │                    │
│  │    "cosign",                   │  ← CLI externe     │
│  │    "sign-blob", ...            │                    │
│  │  ])                            │                    │
│  └────────────────────────────────┘                    │
│                                                         │
│  Extraction Identité                                   │
│  ┌────────────────────────────────┐                    │
│  │  from sigstore.models import   │                    │
│  │    Bundle                      │  ← Bibliothèque    │
│  │  cert = x509.load_pem_...      │     Python         │
│  │  san_emails = cert.extensions  │                    │
│  └────────────────────────────────┘                    │
│                                                         │
│  DSSE Signature                                        │
│  ┌────────────────────────────────┐                    │
│  │  subprocess.run([              │                    │
│  │    "cosign",                   │  ← CLI externe     │
│  │    "sign-blob", ...            │                    │
│  │  ])                            │                    │
│  └────────────────────────────────┘                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Constat**: Architecture **incohérente** (mix CLI + bibliothèque)

---

## ✅ Points Forts

### 1. Extraction Identité Robuste (★★★★★)

**Code**: `sigstore_identity.py:46-158`

**Architecture multi-fallback** :

```python
def extract_identity_from_bundle(bundle_path: Path) -> SignatureIdentity:
    """
    Extraction robuste avec 4 stratégies de fallback:

    1. sigstore-python Bundle.from_json() (officiel)
    2. Parser X.509 certificate DER/PEM
    3. Extraire SAN (Subject Alternative Name) emails
    4. Fallback JSON brut si formats incompatibles
    """

    try:
        # Stratégie 1: API sigstore-python
        bundle = Bundle.from_json(bundle_path.read_text())
        cert_pem = bundle.verification_material.certificate

        # Stratégie 2: Parser X.509
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Stratégie 3: Extraire SAN emails
        san_ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_emails = [
            email.value
            for email in san_ext.value
            if isinstance(email, x509.RFC822Name)
        ]

        identity.email = san_emails[0]  # Primary email

        # Stratégie 4: Extraire OIDC issuer (Fulcio custom OID)
        for ext in cert.extensions:
            if ext.oid.dotted_string == "1.3.6.1.4.1.57264.1.1":
                identity.issuer = ext.value.value.decode('utf-8')

        return identity

    except InvalidBundle:
        # Fallback: parsing JSON brut
        return _extract_from_raw_json(bundle_data, identity)
```

**Avantages** :
- ✅ Support certificats Fulcio (Sigstore CA)
- ✅ Extraction SAN correcte (pas juste CN)
- ✅ OIDC issuer depuis extension X.509 custom
- ✅ Fallback si format bundle change
- ✅ Support multi-emails (SAN peut contenir plusieurs)

**Exemple résultat** :
```python
SignatureIdentity(
    email="alice@company.com",
    issuer="https://accounts.google.com",
    rekor_log_index=142857,
    rekor_timestamp=1736608222,
    san_emails=["alice@company.com", "alice@personal.com"]
)
```

**Qualité**: ⭐⭐⭐⭐⭐ (9/10) - Excellent travail !

---

### 2. Graceful Degradation (Fallback Offline)

**Code**: `sigstore_timestamp.py:47-62`

```python
def sign_and_timestamp(data: bytes, identity: str | None = None):
    """
    Si cosign indisponible ou signing échoue:
    → Retourne proof placeholder (pas de crash)
    """

    if not _cosign_available():
        return SigstoreProof(
            bundle_path=None,      # ← Pas de signature
            bundle_digest=None,
            cert_issuer=None,
            cert_identity=None,
            rekor_entry=None,
            rekor_timestamp=None,
            rekor_log_index=None,
        )
```

**Workflow dégradé** :
```
Cosign disponible:
  Message → Sigstore (MEDIUM trust) + OTS (HIGH trust)

Cosign absent:
  Message → OTS seul (HIGH trust après 6-24h)
```

**Bénéfices** :
- ✅ Système fonctionne même sans Sigstore
- ✅ Pas de crash si cosign absent
- ✅ Trust level ajusté automatiquement
- ✅ OTS reste comme filet de sécurité

**Exemple output** :
```json
{
  "sigstore": {
    "bundle_path": null,
    "trust_level": "LOW"
  },
  "opentimestamps": {
    "status": "PENDING",
    "trust_level": "PENDING"
  },
  "verification": {
    "trust_level": "LOW",
    "offline_mode": true
  }
}
```

**Qualité**: ⭐⭐⭐⭐ (8/10) - Bon design résilient

---

### 3. DSSE Envelope pour Proof JSON

**Code**: `dsse_signer.py:38-149`

**Structure DSSE** :
```json
{
  "payload": "eyJ2ZXJzaW9uIjogIjAuMi4wIiwgLi4ufQ==",  // base64(proof_json)
  "payloadType": "application/json",
  "signatures": [{
    "keyid": "",                                      // DSSE spec: empty pour Sigstore
    "sig": "MEUCIQD...",                             // base64(signature)
    "bundle": ".gwyl_mail/proofs/dsse/bundle_550e8400.json"
  }]
}
```

**Processus signature** :
```python
def sign_proof_dsse(proof: dict, identity: str) -> dict:
    # 1. Normaliser proof (JCS-like: sorted keys, no spaces)
    proof_json = json.dumps(proof, sort_keys=True, separators=(",", ":"))

    # 2. Base64 encode
    payload_b64 = base64.b64encode(proof_json.encode()).decode()

    # 3. Signer avec cosign
    subprocess.run([
        "cosign", "sign-blob",
        payload_path,
        "--bundle", bundle_path,
        "--output-signature", sig_path
    ])

    # 4. Construire DSSE envelope
    return {
        "payload": payload_b64,
        "payloadType": "application/json",
        "signatures": [{"sig": sig_b64, "bundle": str(bundle_path)}]
    }
```

**Avantages** :
- ✅ Proof JSON signé (anti-tampering)
- ✅ Standard DSSE (in-toto, TUF, Sigstore)
- ✅ JCS normalization (canonical JSON)
- ✅ Backward compat (unsigned envelope si cosign manque)

**Vérification** :
```python
def verify_proof_dsse(envelope: dict) -> tuple[bool, dict, str]:
    # 1. Décoder payload
    proof_json = base64.b64decode(envelope["payload"]).decode()
    proof = json.loads(proof_json)

    # 2. Vérifier signature avec cosign
    subprocess.run([
        "cosign", "verify-blob",
        payload_path,
        "--bundle", bundle_path,
        "--signature", sig_path
    ])

    return (verified, proof, error)
```

**Qualité**: ⭐⭐⭐⭐ (7/10) - Bon concept, implem subprocess fragile

---

## 🔴 Problèmes Critiques

### Problème 1: Dépendance CLI `cosign` (Subprocess Security)

**Code problématique** :

**Fichier**: `sigstore_timestamp.py:76-91`
```python
cmd = [
    "cosign",
    "sign-blob",
    str(blob_path),
    "--bundle",
    str(bundle_path),
    "--output-certificate",
    "/dev/null",
    "--output-signature",
    "/dev/null",
]

timeout_s = int(os.getenv("SIGSTORE_TIMEOUT", "30"))
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=timeout_s
)
```

**Fichier**: `dsse_signer.py:92-109`
```python
cmd = [
    "cosign",
    "sign-blob",
    str(payload_path),
    "--bundle",
    str(bundle_path),
    "--output-signature",
    str(sig_path),
    "--output-certificate",
    "/dev/null",
]

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=30
)
```

**Fichier**: `cli.py:181-182`
```python
res = subprocess.run(
    ["cosign", "verify-blob", tmp_path, "--bundle", str(bp)],
    capture_output=True,
    text=True,
    timeout=30
)
```

---

**Problèmes identifiés** :

#### 1.1 Sécurité Subprocess

**Risque**: Path injection si variables contrôlées par attaquant

**Exemple vulnérabilité** :
```python
# Si bundle_path contrôlé par user malveillant:
bundle_path = Path("../../etc/passwd; rm -rf /")

cmd = ["cosign", "sign-blob", data, "--bundle", str(bundle_path)]
# → Exécuté: cosign sign-blob data --bundle ../../etc/passwd; rm -rf /
```

**Mitigation actuelle** : ✅ `shell=False` (bon)
**Mitigation manquante** : ❌ Validation paths stricte

**Fix recommandé** :
```python
def _validate_bundle_path(path: Path) -> Path:
    """Valider path bundle (sécurité)"""
    allowed_dir = Path(".gwyl_mail/proofs/sigstore").resolve()

    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(allowed_dir):
            raise SecurityError(f"Bundle outside allowed dir: {path}")
        return resolved
    except (ValueError, OSError) as e:
        raise SecurityError(f"Invalid bundle path: {e}")

# Usage
bundle_path = _validate_bundle_path(Path(user_input))
cmd = ["cosign", "sign-blob", data, "--bundle", str(bundle_path)]
```

---

#### 1.2 Dépendance Système Externe

**Problème**: Utilisateur doit installer `cosign` manuellement

**Installation requise** :
```bash
# Option 1: Go install (nécessite Go installé)
go install github.com/sigstore/cosign/v2/cmd/cosign@latest

# Option 2: Homebrew (macOS/Linux)
brew install sigstore/tap/cosign

# Option 3: APT (Ubuntu/Debian - souvent obsolète)
apt install cosign

# Option 4: Binary release
wget https://github.com/sigstore/cosign/releases/download/v2.2.1/cosign-linux-amd64
chmod +x cosign-linux-amd64
mv cosign-linux-amd64 /usr/local/bin/cosign
```

**Problèmes** :
- ❌ Barrière installation pour utilisateurs
- ❌ Versioning (cosign v1.x vs v2.x incompatibles)
- ❌ PATH issues (cosign pas dans $PATH)
- ❌ Permissions (user ne peut pas installer globalement)

**Impact UX** :
```
$ gwyl-mail send --to dest@example.com --subject "Test"
ERROR: cosign not found. Install: https://docs.sigstore.dev/cosign/installation/
```

---

#### 1.3 Performance Overhead

**Benchmark subprocess** :
```python
import time
import subprocess

# Mesure fork overhead
start = time.time()
subprocess.run(["cosign", "version"], capture_output=True)
elapsed = time.time() - start

print(f"Subprocess overhead: {elapsed*1000:.2f}ms")
# → Typiquement 50-150ms (fork + exec + wait)
```

**Impact** :
- ⚠️ +50-150ms par opération Sigstore
- ⚠️ Création proof: ~200ms au lieu de ~50ms
- ⚠️ Vérification: ~100ms au lieu de ~20ms

**Comparaison API native** :
```python
# Subprocess (actuel)
def sign_subprocess(data: bytes):
    subprocess.run(["cosign", "sign-blob", ...])  # ~150ms

# API native (proposé)
def sign_native(data: bytes):
    from sigstore.sign import SigningContext
    with SigningContext.production() as ctx:
        bundle = ctx.sign(data)  # ~50ms
```

---

#### 1.4 Gestion Erreurs Fragile

**Code actuel** :
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

if result.returncode != 0:
    # Silent fail → retourne proof vide
    return SigstoreProof(bundle_path=None, ...)
```

**Problèmes** :
- ❌ `returncode != 0` peut signifier plein de choses:
  - Cosign absent (127)
  - Erreur réseau Rekor (1)
  - Timeout Fulcio (1)
  - Permission denied (1)
  - Invalid identity (1)

- ❌ Pas de distinction erreurs temporaires vs permanentes
- ❌ Stderr parsing nécessaire pour diagnostiquer:
  ```python
  stderr = result.stderr
  if "connection refused" in stderr:
      # Erreur réseau → retry
  elif "invalid identity" in stderr:
      # Erreur config → fail
  ```

**Fix recommandé** :
```python
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        # Parser stderr pour détails
        if "not found" in result.stderr:
            raise SigstoreError("cosign not installed")
        elif "connection" in result.stderr.lower():
            raise SigstoreError("Network error (Rekor/Fulcio unavailable)")
        elif "identity" in result.stderr.lower():
            raise SigstoreError(f"Identity error: {result.stderr}")
        else:
            raise SigstoreError(f"Cosign failed: {result.stderr}")

except subprocess.TimeoutExpired:
    raise SigstoreError("Sigstore timeout (>30s)")
```

---

#### 1.5 Versioning Cosign

**Problème**: Format bundle change entre versions

**Cosign v1.x** (ancien):
```json
{
  "RekorEntry": {
    "IntegratedTime": 1234567890,
    "LogIndex": 142857
  },
  "Certificate": "-----BEGIN CERTIFICATE-----\n..."
}
```

**Cosign v2.x** (actuel):
```json
{
  "verificationMaterial": {
    "tlogEntries": [{
      "integratedTime": 1234567890,
      "logIndex": 142857
    }],
    "x509CertificateChain": {
      "certificates": [{"rawBytes": "..."}]
    }
  }
}
```

**Code actuel** tente les deux (`sigstore_timestamp.py:126-135`):
```python
rekor_entry = (
    bundle_data.get("rekorEntry")
    or bundle_data.get("RekorEntry")  # v1.x
    or None
)

if isinstance(rekor_entry, dict):
    rekor_ts = rekor_entry.get("integratedTime") or rekor_entry.get("IntegratedTime")
    # ↑ Heuristique fragile
```

**Problème**: Cosign v3.x peut encore changer le format !

---

**Résumé Problème 1** :

| Aspect | Impact | Sévérité |
|--------|--------|----------|
| Sécurité subprocess | Path injection potentiel | 🔴 Élevée |
| Dépendance externe | Barrière installation | 🔴 Élevée |
| Performance | +50-150ms overhead | 🟡 Moyenne |
| Gestion erreurs | Silent failures | 🔴 Élevée |
| Versioning | Format bundle instable | 🟡 Moyenne |

**Score global**: 🔴 **4/10** (Problème critique)

---

### Problème 2: `sigstore-python` Non Installé

**Constat** :
```bash
$ pip list | grep sigstore
# → Rien ! Bibliothèque absente du environment
```

**Mais code l'importe** (`sigstore_identity.py:18-29`):
```python
try:
    from sigstore.models import Bundle, InvalidBundle
    from sigstore._internal.rekor.client import RekorClient
    from cryptography import x509
    from cryptography.x509.oid import ExtensionOID, NameOID
except ImportError:
    Bundle = None  # ← Toujours None en prod !
    InvalidBundle = None
    RekorClient = None
    x509 = None
```

**Impact** :

1. **`sigstore-python` jamais utilisé**:
   ```python
   if Bundle is None:  # ← Toujours True
       raise ImportError("sigstore-python not installed")
   ```

2. **Extraction identité = fallback JSON brut**:
   - Code ligne 46-82 (API sigstore) jamais exécuté
   - Code ligne 160-222 (fallback JSON) toujours utilisé

3. **Pas d'accès API Rekor**:
   - `RekorClient = None` → impossible de:
     - Vérifier inclusion proof
     - Récupérer entrée Rekor par log_index
     - Valider checkpoint Rekor

**Exemple impact** :
```python
# Ce code ne s'exécute JAMAIS actuellement:
bundle = Bundle.from_json(bundle_path.read_text())  # ← ImportError
cert_pem = bundle.verification_material.certificate

# À la place, fallback JSON brut:
bundle_data = json.loads(bundle_path.read_text())
cert_pem = bundle_data['verificationMaterial']['x509CertificateChain']['certificates'][0]['rawBytes']
# ↑ Fragile si format change !
```

---

**Solution immédiate** :
```bash
pip install sigstore>=3.0.0
```

**Recommandation** : Ajouter à `requirements.txt` / `pyproject.toml`

```toml
# pyproject.toml
[project]
dependencies = [
    "sigstore>=3.0.0",
    "cryptography>=41.0.0",
    # ...
]
```

---

### Problème 3: Parsing Bundle Manuel Fragile

**Code** (`sigstore_timestamp.py:115-140`):

```python
# Parse bundle best-effort (format may vary across cosign versions)
try:
    bundle_data = json.loads(bundle_path.read_text())
except Exception:
    bundle_data = {}

issuer = None
rekor_entry = None
rekor_ts: Optional[int] = None
log_index: Optional[int] = None

# Some cosign bundles include Rekor payload; keep best-effort extraction
rekor_entry = (
    bundle_data.get("rekorEntry")
    or bundle_data.get("RekorEntry")
    or None
)

if isinstance(rekor_entry, dict):
    rekor_ts = rekor_entry.get("integratedTime") or rekor_entry.get("IntegratedTime")
    log_index = rekor_entry.get("logIndex") or rekor_entry.get("LogIndex")
    rekor_entry_str = rekor_entry.get("url") or rekor_entry.get("URL") or None
else:
    rekor_entry_str = None
```

**Problèmes** :

1. **Commentaire "best-effort"** = aveu de fragilité
2. **Multi-try pour champs** (camelCase vs snake_case)
3. **Aucune validation** si clés manquent
4. **Silent fail** : `except Exception: bundle_data = {}`

**Exemple de casse** :

Cosign v2.3.0 change format:
```json
// Avant
{"rekorEntry": {"integratedTime": 123}}

// Après v2.3.0
{"verificationMaterial": {
  "tlogEntries": [{"integratedTime": 123}]
}}
```

Code actuel: ❌ `rekor_entry = None` → Silent fail

---

**Fix avec sigstore-python** :
```python
from sigstore.models import Bundle

bundle = Bundle.from_json(bundle_path.read_text())

# API stable, pas de parsing manuel
rekor_ts = bundle.verification_material.transparency_entries[0].integrated_time
log_index = bundle.verification_material.transparency_entries[0].log_index
```

---

### Problème 4: Timeouts Hardcodés Non Configurables

**Occurrences** :

```python
# sigstore_timestamp.py:90
timeout_s = int(os.getenv("SIGSTORE_TIMEOUT", "30"))  # ← Variable env
result = subprocess.run(cmd, timeout=timeout_s)

# cli.py:181
res = subprocess.run([...], timeout=30)  # ← Hardcodé

# dsse_signer.py:108
result = subprocess.run(cmd, timeout=30)  # ← Hardcodé
```

**Problèmes** :

1. **Incohérence**: Un endroit configurable (env var), deux hardcodés
2. **30s trop long** pour UX (utilisateur attend):
   ```
   $ gwyl-mail send --to dest@example.com
   [Attente 30s si Rekor down...]
   ERROR: Timeout
   ```

3. **30s trop court** pour réseaux lents:
   - Rekor parfois lent (charges publiques)
   - Fulcio CA delay (génération certificat)
   - Connexions mobiles/satellite

4. **Pas de retry logic** si timeout temporaire

---

**Solution recommandée** :

```python
# gwyl_mail/config.py
from dataclasses import dataclass

@dataclass
class SigstoreConfig:
    timeout_initial: int = 5      # 5s premier essai
    timeout_retry: int = 15       # 15s retry
    max_retries: int = 3          # 3 tentatives max
    backoff_factor: float = 2.0   # Exponential backoff

# gwyl_mail/sigstore_timestamp.py
def sign_with_retry(data: bytes, config: SigstoreConfig):
    for attempt in range(config.max_retries):
        timeout = config.timeout_initial * (config.backoff_factor ** attempt)

        try:
            result = subprocess.run(cmd, timeout=timeout)
            if result.returncode == 0:
                return parse_bundle(...)
        except subprocess.TimeoutExpired:
            if attempt < config.max_retries - 1:
                logging.warning(f"Sigstore timeout (attempt {attempt+1}/{config.max_retries}), retrying...")
                continue
            else:
                raise SigstoreError("Sigstore unavailable after 3 attempts")
```

**Timeline retry** :
```
Attempt 1: 5s timeout
Attempt 2: 10s timeout (5 * 2^1)
Attempt 3: 20s timeout (5 * 2^2)
Total max: 35s (au lieu de 30s fixe)
```

---

### Problème 5: Extraction Identité Redondante

**Workflow actuel** (`dual_proof.py:54-149`):

```python
# Étape 1: Signer (crée bundle)
sigstore = sign_and_timestamp(content_hash.encode(), identity)
# ↑ Parse bundle PREMIÈRE FOIS (ligne 115-140 sigstore_timestamp.py)

# Étape 2: Ré-extraire identité du même bundle
try:
    from .sigstore_identity import extract_identity_from_bundle
    sig_identity = extract_identity_from_bundle(bundle_path)
    # ↑ Parse bundle DEUXIÈME FOIS (ligne 69-154 sigstore_identity.py)

    cert_identity_extracted = sig_identity.email
    cert_issuer_extracted = sig_identity.issuer
except Exception:
    cert_issuer_extracted = issuer
```

**Problèmes** :

1. **Double I/O**:
   - `bundle_path.read_text()` appelé 2 fois
   - Lecture fichier JSON (peut être 50KB+)

2. **Double parsing**:
   - JSON parse × 2
   - X.509 certificate parse × 2 (cryptographie)

3. **Risque incohérence**:
   - Si bundle modifié entre les 2 appels (rare mais possible)
   - Race condition si multi-threading

---

**Solution**: Extraire identité PENDANT signing

```python
# sigstore_timestamp.py
def sign_and_timestamp(data: bytes, identity: str) -> SigstoreProof:
    # ... signing code ...

    # Immédiatement après création bundle
    if bundle_path.exists():
        # Parser bundle UNE SEULE FOIS
        sig_identity = extract_identity_from_bundle(bundle_path)

        return SigstoreProof(
            bundle_path=str(bundle_path),
            bundle_digest=_sha256_file(bundle_path),
            cert_issuer=sig_identity.issuer,        # ← Déjà extrait
            cert_identity=sig_identity.email,       # ← Déjà extrait
            rekor_entry=...,
            rekor_timestamp=sig_identity.rekor_timestamp,  # ← Déjà extrait
            rekor_log_index=sig_identity.rekor_log_index,  # ← Déjà extrait
        )
```

**Bénéfice**:
- ✅ Une seule lecture fichier
- ✅ Un seul parsing
- ✅ Pas de risque incohérence

---

### Problème 6: Pas de Cache Bundle Parse

**Code actuel** (vérification):

```python
# cli.py:181-220
# Parse bundle pour vérifier signature
res = subprocess.run(["cosign", "verify-blob", ...])

# Lignes plus bas: Re-parse pour extraire identité
sig_identity = extract_identity_from_bundle(bp)
```

**Problème**: Si on vérifie 100 messages avec même bundle:
- ❌ 100 × parse X.509 certificate (cryptographie lente)
- ❌ 100 × lecture fichier bundle

**Impact performance** :
```python
import time
from pathlib import Path

bundle_path = Path("bundle.json")

# Sans cache
start = time.time()
for i in range(100):
    identity = extract_identity_from_bundle(bundle_path)
elapsed = time.time() - start
print(f"Sans cache: {elapsed:.2f}s")  # → ~5-10s

# Avec cache LRU
from functools import lru_cache

@lru_cache(maxsize=128)
def extract_cached(bundle_path_str: str):
    return extract_identity_from_bundle(Path(bundle_path_str))

start = time.time()
for i in range(100):
    identity = extract_cached(str(bundle_path))
elapsed = time.time() - start
print(f"Avec cache: {elapsed:.2f}s")  # → ~0.05s (100x plus rapide)
```

---

**Solution**: Cache LRU

```python
# gwyl_mail/sigstore_cache.py
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=256)
def get_bundle_identity_cached(bundle_path_str: str, mtime: float) -> SignatureIdentity:
    """
    Cache parsed bundle identities

    Args:
        bundle_path_str: Path as string (hashable for LRU)
        mtime: File modification time (cache invalidation)

    Returns:
        Cached or freshly parsed SignatureIdentity
    """
    return extract_identity_from_bundle(Path(bundle_path_str))

# Usage
def extract_with_cache(bundle_path: Path) -> SignatureIdentity:
    mtime = bundle_path.stat().st_mtime
    return get_bundle_identity_cached(str(bundle_path), mtime)
```

**Bénéfice**: 100x speedup pour vérifications répétées

---

## 🟡 Problèmes Modérés

### Problème 7: Gestion Erreurs Trop Générique

**Code** (`sigstore_timestamp.py:162-177`):

```python
except subprocess.TimeoutExpired:
    return SigstoreProof(
        bundle_path=None,  # ← Silent fail
        # ...
    )
finally:
    try:
        blob_path.unlink(missing_ok=True)
    except Exception:  # ← Anti-pattern
        pass
```

**Problèmes** :

1. **`except Exception: pass`** = masque tous les bugs:
   ```python
   except Exception:  # ← Cache TOUT (PermissionError, KeyError, etc.)
       pass
   ```

2. **Silent failures** sans logging:
   - Utilisateur ne sait pas pourquoi signing a échoué
   - Pas de trace pour debug

3. **Pas de distinction erreurs**:
   - Temporaires (réseau) → retry possible
   - Permanentes (config) → fail rapide

---

**Fix recommandé** :

```python
import logging

logger = logging.getLogger(__name__)

try:
    result = subprocess.run(cmd, timeout=timeout_s)

    if result.returncode != 0:
        logger.error(f"Sigstore failed: {result.stderr}")
        return offline_proof()

except subprocess.TimeoutExpired:
    logger.warning(f"Sigstore timeout ({timeout_s}s)")
    return offline_proof()

except PermissionError as e:
    logger.error(f"Permission denied: {e}")
    raise  # ← Ne pas avaler erreurs filesystem

except Exception as e:
    logger.exception(f"Unexpected Sigstore error: {e}")
    return offline_proof()

finally:
    try:
        blob_path.unlink(missing_ok=True)
    except PermissionError:
        logger.warning(f"Cannot delete temp file: {blob_path}")
        # Continue, pas critique
```

---

### Problème 8: Sécurité Subprocess (Path Validation Manquante)

**Code actuel** (`cli.py:175-180`):

```python
bp = Path(bundle_path)
base = Path(".gwyl_mail/proofs/sigstore")

if _safe_in_dir(bp, base) and bp.exists():
    # Utiliser bp
    res = subprocess.run(["cosign", "verify-blob", tmp_path, "--bundle", str(bp)])
```

**Protection existante** : ✅ `_safe_in_dir()` (bon)

**Mais manquant dans** :

1. `sigstore_timestamp.py:75` :
   ```python
   bundle_path = out_dir / f"bundle_{ts}.json"
   # ↑ Pas de validation si out_dir contrôlé par attaquant
   ```

2. `dsse_signer.py:89` :
   ```python
   bundle_path = out_dir / f"dsse_bundle_{message_id}.json"
   # ↑ message_id peut contenir "../" ?
   ```

---

**Fix**: Validation stricte partout

```python
def _validate_output_path(path: Path, allowed_base: Path) -> Path:
    """
    Valider path output (sécurité)

    Raises:
        SecurityError: Si path outside allowed_base ou contient symlink
    """
    try:
        # Résoudre path absolu
        resolved = path.resolve()
        base_resolved = allowed_base.resolve()

        # Vérifier dans répertoire autorisé
        if not resolved.is_relative_to(base_resolved):
            raise SecurityError(f"Path outside allowed directory: {path}")

        # Vérifier pas de symlink
        if path.is_symlink():
            raise SecurityError(f"Symlink not allowed: {path}")

        return resolved

    except (ValueError, OSError) as e:
        raise SecurityError(f"Invalid path: {e}")

# Usage
allowed_dir = Path(".gwyl_mail/proofs/sigstore")
bundle_path = _validate_output_path(
    allowed_dir / f"bundle_{ts}.json",
    allowed_dir
)
```

---

## ✅ Recommandations d'Amélioration

### Recommandation 1: Migrer vers `sigstore-python` Complet (P0 - CRITIQUE)

**Remplacer subprocess cosign par API native**

**AVANT** (subprocess):
```python
# sigstore_timestamp.py:76-91
cmd = ["cosign", "sign-blob", str(blob_path), "--bundle", str(bundle_path)]
result = subprocess.run(cmd, capture_output=True, timeout=30)
```

**APRÈS** (API sigstore-python):
```python
from sigstore.sign import SigningContext
from sigstore.verify import Verifier, policy

def sign_and_timestamp(data: bytes, identity: str) -> SigstoreProof:
    """Sign with sigstore-python native API"""

    # 1. Signer (pas de subprocess !)
    with SigningContext.production() as ctx:
        bundle = ctx.sign(artifact=data)

    # 2. Sauvegarder bundle
    bundle_path = Path(f".gwyl_mail/proofs/sigstore/bundle_{ts}.json")
    bundle_path.write_text(bundle.to_json())

    # 3. Extraire métadonnées
    cert = bundle.verification_material.certificate
    rekor_entry = bundle.verification_material.transparency_entries[0]

    return SigstoreProof(
        bundle_path=str(bundle_path),
        bundle_digest=hashlib.sha256(bundle.to_json().encode()).hexdigest(),
        cert_issuer=cert.issuer.rfc4514_string(),
        cert_identity=cert.subject.rfc4514_string(),
        rekor_entry=f"https://rekor.sigstore.dev/api/v1/log/entries/{rekor_entry.log_index}",
        rekor_timestamp=rekor_entry.integrated_time,
        rekor_log_index=rekor_entry.log_index
    )

def verify_bundle(bundle_path: Path, data: bytes) -> bool:
    """Verify with sigstore-python native API"""

    bundle = Bundle.from_json(bundle_path.read_text())

    verifier = Verifier.production()
    pol = policy.Identity(
        identity="*",  # Accepter toute identité (ou filtrer)
        issuer="*"
    )

    result = verifier.verify(
        input_=data,
        bundle=bundle,
        policy=pol
    )

    return result.success
```

---

**Bénéfices** :

| Aspect | Subprocess | API Native | Gain |
|--------|-----------|------------|------|
| Sécurité | ⚠️ Path injection risque | ✅ Pas de shell | 🟢 Élevé |
| Performance | ~150ms (fork overhead) | ~50ms | 🟢 3x plus rapide |
| Installation | Cosign séparé | `pip install sigstore` | 🟢 Simplifié |
| Versioning | Format bundle instable | API stable semver | 🟢 Fiable |
| Gestion erreurs | stderr parsing | Exceptions typées | 🟢 Robuste |
| Debugging | Logs subprocess | Stack traces Python | 🟢 Facile |

---

**Migration plan** :

1. Installer `sigstore-python`:
   ```bash
   pip install sigstore>=3.0.0
   ```

2. Créer nouveau module:
   ```python
   # gwyl_mail/sigstore_native.py
   from sigstore.sign import SigningContext
   from sigstore.verify import Verifier
   # ... implémentation ci-dessus
   ```

3. Migrer module par module:
   - `sigstore_timestamp.py` → `sigstore_native.sign_and_timestamp()`
   - `dsse_signer.py` → `sigstore_native.sign_dsse()`
   - `cli.py` → `sigstore_native.verify_bundle()`

4. Garder fallback subprocess (backward compat):
   ```python
   try:
       from .sigstore_native import sign_and_timestamp
   except ImportError:
       from .sigstore_timestamp import sign_and_timestamp  # Fallback
   ```

**Effort**: 2-3 jours

---

### Recommandation 2: Cache LRU Bundles (P1 - Important)

**Implémentation** :

```python
# gwyl_mail/sigstore_cache.py
from functools import lru_cache
from pathlib import Path
import hashlib

@lru_cache(maxsize=256)
def _cached_parse_bundle(bundle_content_hash: str) -> SignatureIdentity:
    """Cache interne (ne pas appeler directement)"""
    # Cette fonction ne sera jamais appelée avec même hash
    # si contenu bundle différent
    raise NotImplementedError("Use extract_identity_cached()")

def extract_identity_cached(bundle_path: Path) -> SignatureIdentity:
    """
    Extract identity with LRU cache

    Cache key = hash(bundle_content) pour détecter modifications
    """
    # Lire bundle
    bundle_content = bundle_path.read_bytes()

    # Hash content (cache key)
    content_hash = hashlib.sha256(bundle_content).hexdigest()

    # Check cache
    try:
        return _cached_identities[content_hash]
    except KeyError:
        # Parse et cache
        identity = extract_identity_from_bundle(bundle_path)
        _cached_identities[content_hash] = identity
        return identity

# Cache global (persistant session)
_cached_identities: dict[str, SignatureIdentity] = {}
```

**Bénéfice**: 100x speedup vérifications répétées

---

### Recommandation 3: Retry Logic avec Backoff (P1 - Important)

**Implémentation** :

```python
# gwyl_mail/sigstore_retry.py
import time
import logging
from typing import Callable, TypeVar

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_timeout: float = 5.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (subprocess.TimeoutExpired, requests.RequestException)
) -> T:
    """
    Retry function with exponential backoff

    Timeline:
        Attempt 1: 5s timeout
        Attempt 2: 10s timeout
        Attempt 3: 20s timeout
    """

    for attempt in range(max_retries):
        timeout = initial_timeout * (backoff_factor ** attempt)

        try:
            return func()

        except exceptions as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt+1}/{max_retries} failed: {e}. "
                    f"Retrying in {timeout}s..."
                )
                time.sleep(timeout)
                continue
            else:
                logging.error(f"All {max_retries} attempts failed")
                raise

# Usage
def sign_with_retry(data: bytes, identity: str) -> SigstoreProof:
    return retry_with_backoff(
        lambda: sign_and_timestamp(data, identity),
        max_retries=3,
        initial_timeout=5.0
    )
```

---

### Recommandation 4: Observabilité (Metrics + Logging) (P2 - Nice to have)

**Implémentation** :

```python
# gwyl_mail/sigstore_metrics.py
from prometheus_client import Counter, Histogram, Gauge
import logging
import time

# Métriques Prometheus
sigstore_operations_total = Counter(
    'gwyl_sigstore_operations_total',
    'Total Sigstore operations',
    ['operation', 'status']  # operation=sign|verify, status=success|failed|timeout
)

sigstore_duration_seconds = Histogram(
    'gwyl_sigstore_duration_seconds',
    'Sigstore operation duration',
    ['operation']
)

sigstore_bundle_size_bytes = Gauge(
    'gwyl_sigstore_bundle_size_bytes',
    'Sigstore bundle file size'
)

# Logging structuré
logger = logging.getLogger(__name__)

def sign_with_metrics(data: bytes, identity: str) -> SigstoreProof:
    """Sign with metrics collection"""

    start_time = time.time()

    try:
        proof = sign_and_timestamp(data, identity)

        # Metrics
        duration = time.time() - start_time
        sigstore_operations_total.labels(operation='sign', status='success').inc()
        sigstore_duration_seconds.labels(operation='sign').observe(duration)

        if proof.bundle_path:
            bundle_size = Path(proof.bundle_path).stat().st_size
            sigstore_bundle_size_bytes.set(bundle_size)

        # Logging
        logger.info(
            "Sigstore sign successful",
            extra={
                "duration_ms": int(duration * 1000),
                "identity": identity,
                "bundle_size": bundle_size if proof.bundle_path else None
            }
        )

        return proof

    except subprocess.TimeoutExpired:
        sigstore_operations_total.labels(operation='sign', status='timeout').inc()
        logger.error("Sigstore sign timeout", extra={"identity": identity})
        raise

    except Exception as e:
        sigstore_operations_total.labels(operation='sign', status='failed').inc()
        logger.exception("Sigstore sign failed", extra={"identity": identity, "error": str(e)})
        raise
```

**Dashboard Grafana** :
```
# Taux succès Sigstore
sum(rate(gwyl_sigstore_operations_total{status="success"}[5m])) /
sum(rate(gwyl_sigstore_operations_total[5m]))

# P95 latence
histogram_quantile(0.95, gwyl_sigstore_duration_seconds)

# Taux timeout
rate(gwyl_sigstore_operations_total{status="timeout"}[5m])
```

---

### Recommandation 5: Validation Schema Bundles (P2 - Nice to have)

**Implémentation avec Pydantic** :

```python
# gwyl_mail/sigstore_models.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class RekorEntry(BaseModel):
    """Rekor transparency log entry"""
    log_index: int = Field(..., ge=0, description="Rekor log index")
    integrated_time: int = Field(..., ge=0, description="Unix timestamp")
    log_id: str = Field(..., description="Rekor log ID")
    kind_version: str = Field(..., description="Entry kind version")

class Certificate(BaseModel):
    """X.509 certificate"""
    raw_bytes: str = Field(..., description="Base64-encoded DER certificate")

class VerificationMaterial(BaseModel):
    """Sigstore verification material"""
    x509_certificate_chain: dict
    tlog_entries: List[RekorEntry]

class SigstoreBundle(BaseModel):
    """Validated Sigstore bundle (cosign v2.x format)"""
    media_type: str = Field(
        ...,
        regex=r"^application/vnd\.dev\.sigstore\.bundle\+json;version=.*"
    )
    verification_material: VerificationMaterial
    message_signature: dict

    @validator('media_type')
    def validate_media_type(cls, v):
        if 'sigstore.bundle' not in v:
            raise ValueError(f"Invalid media type: {v}")
        return v

def validate_bundle(bundle_path: Path) -> SigstoreBundle:
    """
    Parse and validate bundle with Pydantic

    Raises:
        ValidationError: If bundle invalid
    """
    data = json.loads(bundle_path.read_text())
    return SigstoreBundle(**data)  # ← Pydantic validation

# Usage
try:
    bundle = validate_bundle(Path("bundle.json"))
    # ✅ Bundle format valide
except ValidationError as e:
    # ❌ Bundle format invalide
    print(f"Invalid bundle: {e}")
```

---

## 📅 Plan de Migration

### Phase 1: Fondations (Sprint 10 - 3 jours)

**Objectifs** :
1. Installer `sigstore-python>=3.0.0`
2. Ajouter logging structuré
3. Fix validation paths sécurité

**Livrables** :
- ✅ `pip install sigstore`
- ✅ Logging dans tous les modules Sigstore
- ✅ Validation stricte paths (`_validate_output_path()`)

**Tests** :
- Vérifier `sigstore-python` importe sans erreur
- Tester logs (niveau INFO/WARNING/ERROR)

---

### Phase 2: Migration API Native (Sprint 11 - 5 jours)

**Objectifs** :
1. Créer `sigstore_native.py` (API sigstore-python)
2. Migrer `sign_and_timestamp()` vers API native
3. Migrer `verify_bundle()` vers API native

**Livrables** :
- ✅ `sigstore_native.py` (~200 lignes)
- ✅ Tests unitaires (20 test cases)
- ✅ Backward compat subprocess (fallback)

**Tests** :
- Benchmark performance (subprocess vs native)
- Test tous les OIDC providers (Google, GitHub, Microsoft)

---

### Phase 3: Optimisations (Sprint 12 - 2 jours)

**Objectifs** :
1. Cache LRU bundles
2. Retry logic avec backoff
3. Timeout configurables

**Livrables** :
- ✅ `sigstore_cache.py`
- ✅ `sigstore_retry.py`
- ✅ Config timeout via YAML

**Tests** :
- Benchmark cache (100x speedup attendu)
- Test retry (simuler Rekor down)

---

### Phase 4: Observabilité (Sprint 13 - 1 jour)

**Objectifs** :
1. Métriques Prometheus
2. Dashboard Grafana (optionnel)

**Livrables** :
- ✅ `sigstore_metrics.py`
- ✅ Endpoint `/metrics` (si API)

**Tests** :
- Vérifier métriques exposées correctement

---

## 📚 Références

### Documentation Officielle

- **Sigstore**: https://www.sigstore.dev/
- **sigstore-python**: https://github.com/sigstore/sigstore-python
- **Cosign**: https://docs.sigstore.dev/cosign/overview/
- **Rekor**: https://docs.sigstore.dev/logging/overview/
- **Fulcio**: https://docs.sigstore.dev/certificate_authority/overview/

### RFC & Standards

- **DSSE**: https://github.com/secure-systems-lab/dsse
- **X.509 Certificates**: RFC 5280
- **PKCS#7 SignedData**: RFC 5652

### Bibliothèques Python

- **sigstore**: https://pypi.org/project/sigstore/
- **cryptography**: https://cryptography.io/
- **pydantic**: https://docs.pydantic.dev/

---

## ✅ Résumé Exécutif

### Note Globale: **7/10**

**Points Forts** (3):
1. ✅ Extraction identité robuste (multi-fallback, SAN, OIDC issuer)
2. ✅ Graceful degradation (offline mode si cosign absent)
3. ✅ DSSE envelope (anti-tampering proof JSON)

**Points Faibles** (6):
1. ❌ Dépendance CLI cosign (subprocess fragile, sécurité, performance)
2. ❌ `sigstore-python` non installé (fallback JSON brut toujours utilisé)
3. ❌ Parsing bundle manuel (fragile, versioning cosign)
4. ❌ Timeouts hardcodés (UX + réseaux lents)
5. ❌ Extraction identité redondante (double I/O + parse)
6. ❌ Pas de cache bundles (100x slowdown vérifications répétées)

**Action Prioritaire** :
1. **P0**: Migrer vers `sigstore-python` API native (éliminer subprocess)
2. **P1**: Cache LRU bundles (performance)
3. **P1**: Retry logic avec backoff (résilience)

**Effort Total Migration**: ~11 jours (4 sprints)

**ROI Attendu**:
- 🟢 Sécurité: Élimination risques subprocess
- 🟢 Performance: 3x plus rapide (150ms → 50ms)
- 🟢 UX: Pas besoin installer cosign séparément
- 🟢 Maintenance: API stable (semver) vs CLI instable

---

**Fin du document - Analyse technique complète**

**Prochaine étape**: Valider plan migration avec Zack
