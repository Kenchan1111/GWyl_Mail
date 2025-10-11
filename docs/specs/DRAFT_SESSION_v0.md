# GWyl Mail — DraftSession v0

Version: 0.1.0
Date: 2025-01-11
Status: Specification (Draft)
Authors: Zack, ChatGPT

---

## 1. Objectif

Définir un mécanisme de « session de rédaction » qui permet de modifier en sécurité un message en cours (body, subject, etc.) tout en garantissant que les éléments dits « stables » ne changent pas hors périmètre.

Cas d’usage: prévenir les altérations non désirées (attachments, destinataires) pendant la rédaction; refuser la finalisation si ces éléments ont été modifiés.

---

## 2. Modèle

État de session (fichier JSON): `.gwyl_mail/draft_session.json`

```json
{
  "started_at": "2025-01-11T14:30:22Z",
  "reason": "Rédaction contrat",
  "working_fields": ["subject", "body"],
  "stable_fingerprint": {
    "stable_count": 3,
    "stable_merkle": "c4d5e6f7..."
  },
  "policy_id": "gwyl-mail-policy-v1"
}
```

Définitions:
- `working_fields`: champs éditables (p.ex. `body`, `subject`)
- `stable_fingerprint`: empreinte des champs non éditables (p.ex. `to`, `attachments`, `from`), sous forme d’un Merkle root calculé sur les hashs individuels

---

## 3. Règles

- `start-session`: créer `.gwyl_mail/draft_session.json`, calculer `stable_merkle`
- `verify-session`: comparer l’état courant des champs « stables » avec `stable_merkle`
  - si mismatch: session invalide → log + interdiction de finaliser
- `end-session`: recalculer la canonicalisation + hash, créer le proof, mettre à jour le receipt log, supprimer l’état de session

Scope stable recommandé en V0:
- Destinataires: `to`, `cc`, `bcc`
- Expéditeur: `from` (ou `sender` si présent)
- Pièces jointes: contenu (hash SHA-256), nombre de pièces

Calcul du `stable_merkle`:
- Feuilles: paires `(clé, valeur_hash)` triées lexicographiquement
- Hash feuille: `sha256(key || ":" || value_hash)`
- Combinaison Merkle: concaténation binaire des hashs de niveaux adjacents

---

## 4. CLI recommandée

```bash
gwyl-mail start-session --reason "Rédaction" --fields subject body
gwyl-mail verify-session
gwyl-mail end-session --anchor  # (sigstore + OTS)
gwyl-mail abort-session
```

Codes de sortie:
- 0: OK
- 1: stable mismatch / session invalide

---

## 5. Audit & erreurs

Audit JSONL: `.gwyl_mail/verification_audit.jsonl`

- `event`: `session_started`, `session_verified`, `session_failed`, `session_finalized`
- `details`: `issues` (liste), `stable_count`, `stable_merkle`

Erreurs courantes:
- `stable_mismatch`: éléments stables modifiés (ex: destinataires/attachments)
- `session_missing`: aucune session active
- `policy_violation`: identité non conforme à la politique au moment de la finalisation

---

## 6. Sécurité

- Empreinte des stables dépendante uniquement des champs non éditables
- Finalisation refuse tout mismatch; journalisation obligatoire
- Option: signer l’état de session (DSSE) pour audit fort

---

## 7. Changelog

v0.1.0 — Draft initial
- Modèle de session + fingerprint des stables
- CLI minimale
- Audit JSONL

