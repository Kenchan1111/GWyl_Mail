# GWyl Mail - Proof Schema v0

**Version**: 0.2.0
**Date**: 2025-01-11
**Status**: Specification
**Auteurs**: Claude Code + Zack + ChatGPT

---

## 1. Vue d'ensemble

Schéma de preuve cryptographique pour messages GWyl Mail, basé sur **dual timestamping**:
- **Sigstore**: Identité + timestamp immédiat (Rekor log)
- **OpenTimestamps**: Ancrage blockchain Bitcoin (différé)

### Architecture

```
Message Email
    ↓
Canonicalisation (gwyl-canonical-v0)
    ↓
Content Hash (SHA-256)
    ↓
┌─────────────────────────────────┐
│     DUAL PROOF                  │
├─────────────────────────────────┤
│                                 │
│  Sigstore:                      │
│    - Signature ECDSA            │
│    - Cert OIDC (identité)       │
│    - Rekor timestamp (immédiat) │
│    → Trust: MEDIUM              │
│                                 │
│  OpenTimestamps:                │
│    - Bitcoin anchor             │
│    - Bloc timestamp             │
│    → Trust: HIGH                │
│                                 │
│  Coherence:                     │
│    |rekor_ts - ots_ts| < 24h    │
│                                 │
└─────────────────────────────────┘
```

---

## 2. Format JSON

### 2.1 Structure complète

```json
{
  "$schema": "https://gwyl.io/schemas/mail-proof-v0.json",
  "version": "0.2.0",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",

  "canonical": {
    "algorithm": "gwyl-canonical-v0.2",
    "profile": "strict",
    "nfc_scope": "filenames_only",
    "content_hash": "a3f7b2e9d1c4f5a6b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
  },

  "policy": {
    "policy_id": "gwyl-mail-policy-v1",
    "policy_hash": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5",
    "policy_url": "https://company.com/.well-known/gwyl-mail-policy.yml"
  },

  "sigstore": {
    "bundle_path": "./proofs/gwyl-proof-550e8400.sigstore.bundle",
    "bundle_digest": "<sha256(bundle)>",
    "cert_subject": "alice@company.com",
    "cert_issuer": "https://accounts.google.com",
    "rekor_entry": "https://rekor.sigstore.dev/api/v1/log/entries/24296fb24b8ad77a51ce59274c8b131dc0b35c00cc7476614bf45570bbfc7446b764df44e82a5bfb",
    "rekor_timestamp": 1736608222,
    "rekor_log_index": 142857,
    "trust_level": "MEDIUM"
  },

  "opentimestamps": {
    "status": "CONFIRMED",
    "proof_file": "./proofs/gwyl-proof-550e8400.ots",
    "submitted_at": "2025-01-11T14:30:25Z",
    "confirmed_at": "2025-01-11T20:15:43Z",
    "bitcoin_block": 829456,
    "trust_level": "HIGH"
  },

  "coherence": {
    "rekor_ots_delta_seconds": 20733,
    "rekor_ots_delta_hours": 5.76,
    "threshold_hours": 24,
    "valid": true
  },

  "anti_replay": {
    "nonce": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "created_at": "2025-01-11T14:30:22Z",
    "expires_at": "2025-01-11T14:35:22Z",
    "ttl_seconds": 300
  },

  "privacy": {
    "metadata_disclosure": "minimal",
    "sender_hash": "<sha256(sender_email)>",
    "recipient_hash": "<sha256(recipient_email)>",
    "salted": false,
    "salt_id": null
  },

  "verification": {
    "trust_level": "HIGH",
    "offline_mode": false,
    "instant_verifiable": ["sigstore"],
    "legal_grade": ["opentimestamps"],
    "revocation_status": "ok",
    "reasons": ["check_coherence", "canonical_ok"]
  },

  "proof_canonical_digest": "<sha256(JCS(proof))>",
  "local_timestamp": {
    "issued_at": "2025-01-11T14:30:25Z",
    "algorithm": "ECDSA-P256",
    "public_key_id": "sha256:<keyid>"
  },
  "proof_signature": {
    "algorithm": "DSSE",
    "signature": "MEUCIQDx...",
    "public_key_id": "sha256:a3f7b2..."
  }
}
```

---

### 2.2 Normalisation JSON (JCS)

**Problème**: JSON permet plusieurs sérialisations équivalentes:
```json
{"a":1,"b":2}  vs  {"b":2,"a":1}  vs  {"a": 1, "b": 2}
```

**Solution**: [JSON Canonicalization Scheme (JCS - RFC 8785)](https://tools.ietf.org/html/rfc8785)

**Règles JCS**:
1. Clés triées par ordre lexicographique
2. Pas d'espaces superflus
3. Unicode escaped (\uXXXX) pour caractères non-ASCII
4. Nombres en format IEEE 754

**Implémentation**:
```python
import json
import canonicaljson  # pip install canonicaljson

def normalize_json(proof: dict) -> bytes:
    """Normaliser proof selon JCS (RFC 8785)"""
    # Option 1: canonicaljson
    return canonicaljson.encode_canonical_json(proof)

    # Option 2: json avec sort_keys (approximation)
    # return json.dumps(proof, sort_keys=True, separators=(',', ':')).encode('utf-8')
```

**Usage**:
```python
# Avant signature
proof_normalized = normalize_json(proof)
proof_hash = hashlib.sha256(proof_normalized).hexdigest()

# Signature DSSE du proof
signature = sign_dsse(proof_normalized, identity)
```

---

### 2.3 Signature du proof (DSSE)

**Objectif**: Garantir l'intégrité du fichier proof.json lui-même.

**Problème v0.1**: Le proof JSON n'est pas signé → altérable hors canal.

**Solution v0.2**: Utiliser [DSSE (Dead Simple Signing Envelope)](https://github.com/secure-systems-lab/dsse).

**Format DSSE**:
```json
{
  "payload": "<base64(proof_json_canonicalisé)>",
  "payloadType": "application/vnd.gwyl.mail.proof+json",
  "signatures": [
    {
      "keyid": "sha256:a3f7b2...",
      "sig": "MEUCIQD..."
    }
  ]
}
```

**Intégration**:
1. **Option A** (recommandée): Enveloppe DSSE séparée
   ```
   proofs/
     gwyl-proof-550e8400.json        # Proof non signé
     gwyl-proof-550e8400.json.dsse   # Enveloppe DSSE
   ```

2. **Option B**: Champ `proof_signature` dans le JSON
   ```json
   {
     "version": "0.2.0",
     ...
     "proof_signature": {
       "algorithm": "DSSE",
       "signature": "MEUCIQDx...",
       "public_key_id": "sha256:a3f7b2..."
     }
   }
   ```

**Vérification**:
```python
import dsse

def verify_proof_signature(proof_dsse_path: Path) -> bool:
    """Vérifier signature DSSE du proof"""
    with proof_dsse_path.open('rb') as f:
        envelope = dsse.Envelope.from_json(f.read())

    # Extraire payload
    payload = base64.b64decode(envelope.payload)
    proof = json.loads(payload)

    # Vérifier avec clé publique Sigstore
    public_key = extract_public_key_from_bundle(proof['sigstore']['bundle_path'])

    return dsse.verify(envelope, public_key)
```

**Avantages**:
- ✅ Proof altérable détecté
- ✅ Compatible Sigstore (même clé)
- ✅ Vérification offline
- ✅ Standard DSSE (utilisé par Sigstore, in-toto)

---

### 2.4 JSON Schema (validation)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://gwyl.io/schemas/mail-proof-v0.json",
  "title": "GWyl Mail Proof v0",
  "description": "Preuve cryptographique pour email GWyl Mail",
  "type": "object",

  "required": ["version", "message_id", "canonical", "sigstore", "opentimestamps", "anti_replay"],

  "properties": {
    "version": {
      "type": "string",
      "const": "0.2.0",
      "description": "Version du schéma"
    },

    "message_id": {
      "type": "string",
      "format": "uuid",
      "description": "UUID v4 unique du message"
    },

    "canonical": {
      "type": "object",
      "required": ["algorithm", "content_hash"],
      "properties": {
        "algorithm": {
          "type": "string",
          "const": "gwyl-canonical-v0.2",
          "description": "Algorithme de canonicalisation"
        },
        "profile": {
          "type": "string",
          "enum": ["strict", "relaxed"],
          "description": "Profil de canonicalisation (v0: strict)"
        },
        "nfc_scope": {
          "type": "string",
          "enum": ["filenames_only"],
          "description": "Périmètre NFC (v0: filenames uniquement)"
        },
        "content_hash": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$",
          "description": "SHA-256 du message canonique (64 hex chars)"
        }
      }
    },

    "sigstore": {
      "type": "object",
      "required": ["bundle_path", "cert_subject", "rekor_timestamp"],
      "properties": {
        "bundle_path": {
          "type": "string",
          "description": "Chemin vers bundle Sigstore (.sigstore.bundle)"
        },
        "bundle_digest": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$",
          "description": "SHA-256 du bundle (.sigstore.bundle)"
        },
        "cert_subject": {
          "type": "string",
          "format": "email",
          "description": "Identité du signataire (OIDC cert subject)"
        },
        "cert_issuer": {
          "type": "string",
          "format": "uri",
          "description": "Issuer OIDC (Google, Microsoft, GitHub...)"
        },
        "rekor_entry": {
          "type": "string",
          "format": "uri",
          "description": "URL de l'entrée Rekor (transparency log)"
        },
        "rekor_timestamp": {
          "type": "integer",
          "minimum": 0,
          "description": "Timestamp Unix (integratedTime Rekor)"
        },
        "rekor_log_index": {
          "type": "integer",
          "minimum": 0,
          "description": "Index dans le log Rekor"
        },
        "trust_level": {
          "type": "string",
          "enum": ["MEDIUM"],
          "description": "Niveau de confiance (serveur Rekor)"
        }
      }
    },

    "opentimestamps": {
      "type": "object",
      "required": ["status", "proof_file"],
      "properties": {
        "status": {
          "type": "string",
          "enum": ["PENDING", "CONFIRMED", "FAILED"],
          "description": "État de l'ancrage OTS"
        },
        "proof_file": {
          "type": "string",
          "description": "Chemin vers fichier .ots"
        },
        "submitted_at": {
          "type": "string",
          "format": "date-time",
          "description": "Date soumission OTS (ISO 8601)"
        },
        "confirmed_at": {
          "type": "string",
          "format": "date-time",
          "description": "Date confirmation Bitcoin (ISO 8601)"
        },
        "bitcoin_block": {
          "type": "integer",
          "minimum": 0,
          "description": "Numéro bloc Bitcoin contenant la preuve"
        },
        "trust_level": {
          "type": "string",
          "enum": ["PENDING", "HIGH"],
          "description": "PENDING si non confirmé, HIGH si confirmé"
        }
      }
    },

    "coherence": {
      "type": "object",
      "properties": {
        "rekor_ots_delta_hours": {
          "type": "number",
          "description": "Delta en heures entre timestamps Rekor et OTS"
        },
        "valid": {
          "type": "boolean",
          "description": "true si delta < 24h"
        }
      }
    },

    "anti_replay": {
      "type": "object",
      "required": ["nonce", "expires_at"],
      "properties": {
        "nonce": {
          "type": "string",
          "format": "uuid",
          "description": "Nonce unique (UUID v4)"
        },
        "expires_at": {
          "type": "string",
          "format": "date-time",
          "description": "Date expiration (ISO 8601), typiquement +5min"
        }
      }
    },

    "privacy": {
      "type": "object",
      "properties": {
        "metadata_disclosure": {
          "type": "string",
          "enum": ["minimal", "standard", "full"],
          "description": "Niveau de disclosure des métadonnées"
        },
        "sender_hash": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$",
          "description": "SHA-256 de l'email expéditeur (pas de PII)"
        },
        "recipient_hash": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$",
          "description": "SHA-256 de l'email destinataire (pas de PII)"
        },
        "salted": {
          "type": "boolean",
          "description": "Indique si un salt/pepper a été utilisé"
        },
        "salt_id": {
          "type": "string",
          "description": "Identifiant du salt/pepper (si applicable)"
        }
      }
    },

    "verification": {
      "type": "object",
      "properties": {
        "trust_level": {
          "type": "string",
          "enum": ["LOW", "MEDIUM", "HIGH"],
          "description": "Niveau de confiance global"
        },
        "offline_mode": {
          "type": "boolean",
          "description": "Indique si un mode offline/fallback a été utilisé"
        },
        "instant_verifiable": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Preuves vérifiables immédiatement"
        },
        "legal_grade": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Preuves de grade juridique"
        },
        "revocation_status": {
          "type": "string",
          "enum": ["ok", "revoked", "unknown"],
          "description": "Statut de révocation du certificat"
        },
        "reasons": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Raisons/codes de décision de vérification"
        }
      }
    },
    "local_timestamp": {
      "type": "object",
      "properties": {
        "issued_at": {"type": "string", "format": "date-time"},
        "algorithm": {"type": "string"},
        "public_key_id": {"type": "string"}
      },
      "description": "Horodatage local non légal (fallback offline)"
    },

    "proof_canonical_digest": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$",
      "description": "SHA-256 de la sérialisation JCS du proof"
    }
  }
}
```

---

## 3. Champs détaillés

### 2.5 Vérification offline (pas-à-pas)

1. Normaliser le proof en JCS (RFC 8785) et calculer `proof_canonical_digest` (SHA-256)
2. Vérifier la signature DSSE de l’enveloppe (clé opérateur/admin pinée)
3. Vérifier le Sigstore bundle offline:
   - `cosign verify-blob --bundle <bundle> <content_bytes>`
   - comparer `bundle_digest`
4. Si OTS `CONFIRMED`:
   - `ots verify <proof.ots>` → extraire `bitcoin_block` et `confirmed_at`
5. Vérifier cohérence temporelle: |rekor_timestamp − confirmed_at| < 24h

Sortie recommandée: `verification.offline_steps` = ["jcs_canon", "verify_dsse", "verify_bundle", "verify_ots", "check_coherence"].

### 3.1 Champ `canonical`

**Objectif**: Référence à l'algorithme de canonicalisation et hash résultant.

```json
"canonical": {
  "algorithm": "gwyl-canonical-v0.2",
  "content_hash": "a3f7b2e9d1c4f5a6..."
}
```

- `algorithm`: Toujours `"gwyl-canonical-v0.2"` pour cette version
- `content_hash`: SHA-256 (64 hex chars) du message canonisé selon `CANONICALIZATION_v0.md`

**Validation**:
```python
def verify_canonical(proof: dict, message: EmailMessage) -> bool:
    expected_hash = proof['canonical']['content_hash']
    actual_hash = GWylCanonical.hash(message)
    return expected_hash == actual_hash
```

---

### 3.2 Champ `policy` ⭐ NOUVEAU v0.2

**Objectif**: Référencer la politique d'identité utilisée pour créer/valider le proof.

```json
"policy": {
  "policy_id": "gwyl-mail-policy-v1",
  "policy_hash": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5",
  "policy_url": "https://company.com/.well-known/gwyl-mail-policy.yml"
}
```

**Détails**:
- `policy_id`: Identifiant unique de la politique (ex: org-policy-v2, personal-strict)
- `policy_hash`: SHA-256 du fichier YAML de politique canonicalisé
- `policy_url` (optionnel): URL publique de la politique

**Calcul du policy_hash**:
```python
import hashlib
import yaml

def compute_policy_hash(policy_path: Path) -> str:
    """
    Hash SHA-256 de la politique YAML

    Normalisation:
    1. Charger YAML
    2. Trier clés récursivement
    3. Sérialiser en YAML canonique
    4. Hash SHA-256
    """
    with policy_path.open() as f:
        policy = yaml.safe_load(f)

    # Canonicaliser (tri clés)
    canonical_yaml = yaml.dump(
        policy,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True
    )

    return hashlib.sha256(canonical_yaml.encode('utf-8')).hexdigest()
```

**Usage**:
```python
def create_proof_with_policy(message: EmailMessage, identity: str, policy_path: Path):
    """Créer proof avec référence à la politique"""

    # Charger politique
    with policy_path.open() as f:
        policy = yaml.safe_load(f)

    policy_id = policy.get('policy_id', 'default')
    policy_hash = compute_policy_hash(policy_path)

    # ... créer proof ...

    proof['policy'] = {
        'policy_id': policy_id,
        'policy_hash': policy_hash,
        'policy_url': policy.get('policy_url')  # optionnel
    }

    return proof
```

**Vérification**:
```python
def verify_proof_policy(proof: dict, policy_path: Path) -> bool:
    """Vérifier que le proof utilise la bonne politique"""

    expected_hash = compute_policy_hash(policy_path)
    actual_hash = proof['policy']['policy_hash']

    if expected_hash != actual_hash:
        raise PolicyMismatchError(
            f"Policy hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    return True
```

**Rationale**:
- ✅ Lie proof à la politique d'identité utilisée
- ✅ Détecte modifications de politique entre création et vérification
- ✅ Permet audit: "quelle politique était en vigueur?"
- ✅ Facilite migration politique (warn→strict)

---

### 3.3 Champ `sigstore`

**Objectif**: Preuve Sigstore (identité + timestamp Rekor immédiat).

```json
"sigstore": {
  "bundle_path": "./proofs/abc.sigstore.bundle",
  "cert_subject": "alice@company.com",
  "cert_issuer": "https://accounts.google.com",
  "rekor_entry": "https://rekor.sigstore.dev/...",
  "rekor_timestamp": 1736608222,
  "rekor_log_index": 142857,
  "trust_level": "MEDIUM"
}
```

**Détails**:
- `bundle_path`: Fichier bundle Sigstore (portable, contient tout)
- `cert_subject`: Email du signataire (extrait du certificat OIDC)
- `cert_issuer`: Provider OIDC (Google, Microsoft, GitHub...)
- `rekor_entry`: URL publique de l'entrée Rekor (transparency log)
- `rekor_timestamp`: Unix timestamp (secondes depuis epoch) du log Rekor
- `rekor_log_index`: Position dans le log Rekor (append-only)
- `trust_level`: Toujours `"MEDIUM"` (confiance serveur Rekor)

**Vérification**:
```bash
# Offline
cosign verify-blob \
  --bundle ./proofs/abc.sigstore.bundle \
  --certificate-identity alice@company.com \
  --certificate-oidc-issuer https://accounts.google.com \
  message.canonical
```

---

### 3.3 Champ `opentimestamps`

**Objectif**: Preuve OpenTimestamps (ancrage Bitcoin différé).

```json
"opentimestamps": {
  "status": "CONFIRMED",
  "proof_file": "./proofs/abc.ots",
  "submitted_at": "2025-01-11T14:30:25Z",
  "confirmed_at": "2025-01-11T20:15:43Z",
  "bitcoin_block": 829456,
  "trust_level": "HIGH"
}
```

**États `status`**:
- `"PENDING"`: Soumis, pas encore dans Bitcoin (0-24h)
- `"CONFIRMED"`: Inclus dans bloc Bitcoin
- `"FAILED"`: Échec ancrage (rare)

**Détails**:
- `proof_file`: Fichier `.ots` (portable)
- `submitted_at`: Date/heure soumission
- `confirmed_at`: Date/heure inclusion dans bloc Bitcoin
- `bitcoin_block`: Numéro du bloc contenant la preuve
- `trust_level`: `"PENDING"` ou `"HIGH"` (si confirmé)

**Lifecycle**:
```python
# 1. Submit (t=0)
ots stamp message.canonical  # → message.canonical.ots (PENDING)

# 2. Upgrade (t=6-24h)
ots upgrade message.canonical.ots  # → mise à jour si confirmé

# 3. Verify
ots verify message.canonical.ots  # → Success! Bitcoin block 829456
```

---

### 3.4 Champ `coherence`

**Objectif**: Vérifier cohérence temporelle entre Sigstore et OTS.

```json
"coherence": {
  "rekor_ots_delta_hours": 5.75,
  "valid": true
}
```

**Règle**:
```python
def check_coherence(proof: dict) -> bool:
    if proof['opentimestamps']['status'] != 'CONFIRMED':
        return True  # OTS pending, pas de check

    rekor_ts = datetime.fromtimestamp(proof['sigstore']['rekor_timestamp'])
    ots_ts = parse(proof['opentimestamps']['confirmed_at'])

    delta = abs((rekor_ts - ots_ts).total_seconds())
    delta_hours = delta / 3600

    return delta_hours < 24  # Tolérance 24h
```

**Rationale**: Si |rekor_timestamp - ots_timestamp| > 24h → suspect (backdating possible).

Cas HTML-only en V0 strict:
- Si le message est uniquement `text/html` (sans `text/plain`), et que le HTML a été modifié en transit → mismatch attendu.
- Politique de vérification recommandée: `trust_level = LOW` et `verification.reasons += ["html_only_strict"]` (incitation à basculer en profil relaxed V1 pour tolérance contrôlée).

---

### 3.5 Champ `anti_replay`

**Objectif**: Prévenir attaques replay.

```json
"anti_replay": {
  "nonce": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "expires_at": "2025-01-11T14:35:22Z"
}
```

**Mécanisme**:
```python
class ReplayProtection:
    def __init__(self):
        self.seen_nonces = set()  # En mémoire ou DB

    def verify_no_replay(self, proof: dict):
        nonce = proof['anti_replay']['nonce']
        expires = parse(proof['anti_replay']['expires_at'])

        # 1. Check nonce pas déjà vu
        if nonce in self.seen_nonces:
            raise ReplayError("Nonce already used")

        # 2. Check pas expiré
        if datetime.utcnow() > expires:
            raise ReplayError("Proof expired")

        # 3. Enregistrer
        self.seen_nonces.add(nonce)
```

**Expiration**: Typiquement `created_at + 5 minutes`.

**Registre des nonces (réception)**:
- Persistance: fichier JSONL append-only ou KV store local
- TTL: par défaut 5 minutes (configurable)
- Stratégie collision: rejet (fail-closed) et audit de l’événement
- Rotation/GC: purge périodique des entrées expirées

---

### 3.6 Champ `privacy`

**Objectif**: Minimiser disclosure métadonnées PII.

```json
"privacy": {
  "metadata_disclosure": "minimal",
  "sender_hash": "5d41402abc4b2a76b9719d911017c592",
  "recipient_hash": "098f6bcd4621d373cade4e832627b4f6"
}
```

**Niveaux disclosure**:
- `"minimal"`: Hash seulement (emails non visibles)
- `"standard"`: Hash + domaine (ex: `*@company.com`)
- `"full"`: Emails en clair (audit interne)

**Calcul hash**:
```python
def hash_email(email: str, salt: bytes | None = None) -> str:
    data = email.lower().encode()
    if salt:
        data = salt + b"|" + data
    return hashlib.sha256(data).hexdigest()
```

---

### 3.7 Champ `verification`

**Objectif**: Résumé capacités de vérification.

```json
"verification": {
  "trust_level": "HIGH",
  "instant_verifiable": ["sigstore"],
  "legal_grade": ["opentimestamps"]
}
```

**Trust levels**:
- `"HIGH"`: OTS confirmé (blockchain Bitcoin)
- `"MEDIUM"`: Sigstore valide (serveur Rekor)
- `"LOW"`: Aucune preuve valide

**Preuves**:
- `instant_verifiable`: Vérifiables < 1s (Sigstore bundle offline)
- `legal_grade`: Valeur juridique (OTS blockchain)

---

## 4. Exemples complets

### 4.1 Message simple (OTS pending)

```json
{
  "version": "0.2.0",
  "message_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",

  "canonical": {
    "algorithm": "gwyl-canonical-v0.2",
    "content_hash": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5"
  },

  "sigstore": {
    "bundle_path": "./proofs/gwyl-proof-a1b2c3d4.sigstore.bundle",
    "bundle_digest": "<sha256(bundle)>",
    "cert_subject": "alice@company.com",
    "cert_issuer": "https://accounts.google.com",
    "rekor_entry": "https://rekor.sigstore.dev/api/v1/log/entries/abc123...",
    "rekor_timestamp": 1736608222,
    "rekor_log_index": 142857,
    "trust_level": "MEDIUM"
  },

  "opentimestamps": {
    "status": "PENDING",
    "proof_file": "./proofs/gwyl-proof-a1b2c3d4.ots",
    "submitted_at": "2025-01-11T14:30:25Z",
    "confirmed_at": null,
    "bitcoin_block": null,
    "trust_level": "PENDING"
  },

  "coherence": {
    "rekor_ots_delta_hours": null,
    "valid": null
  },

  "anti_replay": {
    "nonce": "f1e2d3c4-b5a6-497b-8c9d-0e1f2a3b4c5d",
    "expires_at": "2025-01-11T14:35:25Z"
  },

  "privacy": {
    "metadata_disclosure": "minimal",
    "sender_hash": "<sha256(sender_email)>",
    "recipient_hash": "<sha256(recipient_email)>"
  },

  "verification": {
    "trust_level": "MEDIUM",
    "instant_verifiable": ["sigstore"],
    "legal_grade": []
  }
}
```

---

### 4.2 Message avec OTS confirmé

```json
{
  "version": "0.2.0",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",

  "canonical": {
    "algorithm": "gwyl-canonical-v0.2",
    "content_hash": "a3f7b2e9d1c4f5a6b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
  },

  "sigstore": {
    "bundle_path": "./proofs/gwyl-proof-550e8400.sigstore.bundle",
    "bundle_digest": "<sha256(bundle)>",
    "cert_subject": "bob@partner.org",
    "cert_issuer": "https://login.microsoftonline.com",
    "rekor_entry": "https://rekor.sigstore.dev/api/v1/log/entries/xyz789...",
    "rekor_timestamp": 1736608800,
    "rekor_log_index": 143000,
    "trust_level": "MEDIUM"
  },

  "opentimestamps": {
    "status": "CONFIRMED",
    "proof_file": "./proofs/gwyl-proof-550e8400.ots",
    "submitted_at": "2025-01-11T14:40:00Z",
    "confirmed_at": "2025-01-11T20:25:30Z",
    "bitcoin_block": 829460,
    "trust_level": "HIGH"
  },

  "coherence": {
    "rekor_ots_delta_hours": 5.76,
    "valid": true
  },

  "anti_replay": {
    "nonce": "9a8b7c6d-5e4f-4321-ba09-8765fedcba09",
    "expires_at": "2025-01-11T14:45:00Z"
  },

  "privacy": {
    "metadata_disclosure": "minimal",
    "sender_hash": "<sha256(sender_email)>",
    "recipient_hash": "<sha256(recipient_email)>"
  },

  "verification": {
    "trust_level": "HIGH",
    "instant_verifiable": ["sigstore"],
    "legal_grade": ["opentimestamps"]
  }
}
```

---

## 5. Workflow de création

```python
from gwyl_mail.canonical import GWylCanonical
from gwyl_mail.sigstore_timestamp import sign_and_timestamp
from gwyl_mail.ots_manager import OTSManager
from uuid import uuid4
from datetime import datetime, timedelta

def create_proof(message: EmailMessage, identity: str) -> dict:
    """Créer proof complet pour un message"""

    # 1. Générer message_id
    message_id = str(uuid4())

    # 2. Canoniser + hash
    content_hash = GWylCanonical.hash(message)

    # 3. Sigstore (immédiat)
    sigstore_proof = sign_and_timestamp(
        content_hash.encode(),
        identity
    )

    # 4. OTS (différé)
    ots_manager = OTSManager()
    ots_file = ots_manager.submit(content_hash.encode())

    # 5. Anti-replay
    nonce = str(uuid4())
    expires = (datetime.utcnow() + timedelta(minutes=5)).isoformat() + 'Z'

    # 6. Privacy
    sender_hash = hashlib.sha256(identity.lower().encode()).hexdigest()
    recipient_hash = hashlib.sha256(message['To'].lower().encode()).hexdigest()

    # 7. Assembler proof
    return {
        "version": "0.2.0",
        "message_id": message_id,

        "canonical": {
            "algorithm": "gwyl-canonical-v0.2",
            "content_hash": content_hash
        },

        "sigstore": {
            "bundle_path": sigstore_proof.bundle_path,
            "cert_subject": identity,
            "cert_issuer": sigstore_proof.cert_issuer,
            "rekor_entry": sigstore_proof.rekor_entry,
            "rekor_timestamp": sigstore_proof.rekor_timestamp,
            "rekor_log_index": sigstore_proof.rekor_log_index,
            "trust_level": "MEDIUM"
        },

        "opentimestamps": {
            "status": "PENDING",
            "proof_file": str(ots_file),
            "submitted_at": datetime.utcnow().isoformat() + 'Z',
            "confirmed_at": None,
            "bitcoin_block": None,
            "trust_level": "PENDING"
        },

        "coherence": {
            "rekor_ots_delta_hours": None,
            "valid": None
        },

        "anti_replay": {
            "nonce": nonce,
            "expires_at": expires
        },

        "privacy": {
            "metadata_disclosure": "minimal",
            "sender_hash": sender_hash,
            "recipient_hash": recipient_hash
        },

        "verification": {
            "trust_level": "MEDIUM",
            "instant_verifiable": ["sigstore"],
            "legal_grade": []
        }
    }
```

---

## 6. Workflow de vérification

```python
def verify_proof(proof: dict, message: EmailMessage) -> dict:
    """Vérifier proof complet"""

    results = {}

    # 1. Canonical hash
    expected_hash = proof['canonical']['content_hash']
    actual_hash = GWylCanonical.hash(message)
    results['canonical'] = (expected_hash == actual_hash)

    # 2. Sigstore bundle
    results['sigstore'] = verify_sigstore_bundle(
        proof['sigstore']['bundle_path'],
        expected_hash.encode()
    )

    # 3. OTS (si confirmé)
    if proof['opentimestamps']['status'] == 'CONFIRMED':
        ots_manager = OTSManager()
        ots_status = ots_manager.verify(Path(proof['opentimestamps']['proof_file']))
        results['ots'] = (ots_status.status == 'CONFIRMED')
    else:
        results['ots'] = False

    # 4. Cohérence
    if results['ots']:
        rekor_ts = datetime.fromtimestamp(proof['sigstore']['rekor_timestamp'])
        ots_ts = parse(proof['opentimestamps']['confirmed_at'])
        delta_hours = abs((rekor_ts - ots_ts).total_seconds()) / 3600
        results['coherence'] = (delta_hours < 24)
    else:
        results['coherence'] = True  # OTS pending, OK

    # 5. Anti-replay
    # (Dépend du contexte: vérifier nonce + expiration)

    # 6. Trust level
    if results['ots']:
        trust = 'HIGH'
    elif results['sigstore']:
        trust = 'MEDIUM'
    else:
        trust = 'LOW'

    return {
        'valid': all([results['canonical'], results['sigstore'], results['coherence']]),
        'trust_level': trust,
        'details': results
    }
```

---

## 7. Changelog

### v0.2.0 (2025-01-11) - Révision ChatGPT

**Améliorations majeures**:
- ✅ **Normalisation JSON (JCS - RFC 8785)**: Canonicalisation du proof pour signature
- ✅ **Signature proof (DSSE)**: Le proof JSON est maintenant signé (détection altération)
- ✅ **Champ `policy`**: Référence `policy_id` + `policy_hash` (SHA-256 du YAML)
- ✅ **Cohérence temporelle précisée**: `delta_seconds`, `delta_hours`, `threshold_hours`
- ✅ **Anti-replay enrichi**: Ajout `created_at` + `ttl_seconds`
- ✅ **Canonicalisation profile**: Référence au profil (strict/relaxed)

**Nouveaux champs**:
```json
{
  "policy": {
    "policy_id": "gwyl-mail-policy-v1",
    "policy_hash": "d4e5f6a7...",
    "policy_url": "https://..."
  },
  "proof_signature": {
    "algorithm": "DSSE",
    "signature": "MEUCIQD...",
    "public_key_id": "sha256:..."
  },
  "coherence": {
    "rekor_ots_delta_seconds": 20733,
    "threshold_hours": 24
  }
}
```

**Standards intégrés**:
- RFC 8785 (JCS - JSON Canonicalization Scheme)
- DSSE (Dead Simple Signing Envelope)
- Compatibilité Sigstore/in-toto

### v0.1.0 (2025-01-11)
- Initial draft
- Dual timestamping: Sigstore + OTS
- Canonicalisation v0
- Anti-replay avec nonce
- Privacy minimal disclosure
- Trust levels: LOW/MEDIUM/HIGH

---

## 8. Références

- **Sigstore**: https://www.sigstore.dev
- **Rekor**: https://docs.sigstore.dev/logging/overview
- **OpenTimestamps**: https://opentimestamps.org
- **JSON Schema**: https://json-schema.org

---

---

## 9. Contributeurs

**Conception et spécification**: Zack, Claude (Anthropic), ChatGPT (OpenAI)

**Remerciements**: ChatGPT pour la validation de l'architecture dual timestamping (Sigstore + OTS) et la simplification du système en éliminant la dépendance Roughtime.

---

**Fin du document PROOF_SCHEMA_v0.md**
