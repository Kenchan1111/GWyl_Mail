# GWyl Mail — Receipt Log v0 (append-only)

Version: 0.1.0
Date: 2025-01-11
Status: Specification (Draft)
Authors: Zack, ChatGPT

---

## 1. Objectif

Définir le journal append-only des preuves par message (mail_proofs.jsonl) pour audit, résilience et opérations (upgrade OTS, cohérence temporelle, privacy).

---

## 2. Format et atomicité

Fichier: `proofs/mail_proofs.jsonl`

Chaque ligne = un JSON indépendant (append-only). Écriture atomique recommandée:

- Ouvrir avec `O_APPEND | O_CREAT`
- Écrire la ligne sérialisée (UTF-8) suivie de `\n`
- `fsync()` sur le descripteur

Exemple d’entrée:
```json
{
  "timestamp": "2025-01-11T14:30:25Z",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "canonical": {
    "algorithm": "gwyl-canonical-v0.2",
    "content_hash": "a3f7b2..."
  },
  "sigstore": {
    "bundle_path": "./proofs/gwyl-proof-550e8400.sigstore.bundle",
    "bundle_digest": "1f8ac1...",
    "cert_subject": "alice@company.com",
    "rekor_timestamp": 1736608222,
    "rekor_log_index": 142857
  },
  "opentimestamps": {
    "status": "PENDING",
    "proof_file": "./proofs/gwyl-proof-550e8400.ots",
    "submitted_at": "2025-01-11T14:30:25Z",
    "confirmed_at": null,
    "bitcoin_block": null
  },
  "coherence": {
    "rekor_ots_delta_seconds": null,
    "rekor_ots_delta_hours": null,
    "threshold_hours": 24,
    "valid": null
  },
  "privacy": {
    "sender_hash": "<sha256(sender)>",
    "recipient_hash": "<sha256(recipient)>",
    "salted": false,
    "salt_id": null
  },
  "proof_canonical_digest": "<sha256(JCS(proof))>",
  "verification": {
    "trust_level": "MEDIUM",
    "instant_verifiable": ["sigstore"],
    "legal_grade": []
  }
}
```

---

## 3. Cycle de vie OTS

États: `PENDING` → `CONFIRMED` (ou `FAILED`)

Upgrade périodique (cron):
- `ots upgrade <file.ots>` puis `ots verify <file.ots>`
- Si confirmé: renseigner `confirmed_at` (ISO) + `bitcoin_block`
- Idempotence: ne pas réécrire les entrées déjà confirmées

Raisons d’échec à journaliser (reason codes):
- `ots_submit_failed`, `ots_upgrade_failed`, `ots_verify_failed`

---

## 4. Protection contre rollback/suppression

- Vérifier régulièrement que tous les `proof_file` référencés existent
- Sauvegarde périodique (tar.gz) des répertoires `proofs/`
- Option: copie hors bande (WORM storage)

---

## 5. Rotation et rétention

- Rotation hebdomadaire ou mensuelle (ex: `mail_proofs_2025-01.jsonl`)
- Index optionnel (`mail_proofs.index`) pour accélérer les recherches par `message_id`
- Politique de rétention conforme exigences (ex: 12–24 mois)

---

## 6. Cohérence temporelle

- Si `status=CONFIRMED`: calculer et stocker `rekor_ots_delta_seconds` et `rekor_ots_delta_hours`
- Valider `valid = (delta_hours < threshold_hours)` (par défaut 24 h)

---

## 7. Sécurité & Privacy

- Champ `privacy` uniquement en hash SHA-256 (option `salted` + `salt_id`)
- Aucune PII en clair par défaut
- Preuves portables (vérification offline)

---

## 8. Changelog

v0.1.0 — Draft initial
- Journal append-only atomique
- Cycle de vie OTS
- Cohérence temporelle
- Sauvegarde & rotation

