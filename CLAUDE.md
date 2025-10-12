# Mémoire de Projet - GWyl Mail

## Contexte Global

**GWyl Mail** est une couche de confidentialité et d'intégrité pour email qui garantit :
- Intégrité cryptographique (détection de modifications)
- Non-répudiation via blockchain (OpenTimestamps)
- Identité vérifiée (OIDC via Sigstore)
- Privacy by design
- Compatible avec SMTP/IMAP existant

**Version actuelle** : 0.1.0 (PoC)
**Licence** : GPL-3.0
**Statut** : Développement actif - Phase 1 (~70% complété)

---

## Architecture Technique

### Dual Timestamping
```
Message Email → Canonicalisation → Hash SHA-256
    ↓
┌─────────────────────────────────┐
│ Sigstore (immédiat)             │ → Trust: MEDIUM
│ OpenTimestamps (différé)        │ → Trust: HIGH (Bitcoin)
│ Politique d'identité            │ → Mapping From ↔ Cert
└─────────────────────────────────┘
```

### Stack Technique
- **Langage** : Python 3.9+
- **Dépendances core** :
  - `sigstore` - Signature + Rekor timestamping
  - `opentimestamps-client` - Ancrage blockchain Bitcoin
  - `pyyaml` - Configuration politique
  - `canonicaljson` - Normalisation JSON (JCS RFC 8785)
- **Standards** : RFC 6376 (DKIM), RFC 2047, RFC 5322, RFC 8785 (JCS), DSSE

---

## État d'Avancement

### ✅ Phase 0 : Spécifications - COMPLÉTÉE (100%)
- **~3700 lignes** de spécifications techniques dans `docs/specs/`
- CANONICALIZATION_v0.md (v0.2.0) - Algorithme normatif
- PROOF_SCHEMA_v0.md (v0.2.0) - Schéma de preuve dual timestamping
- IDENTITY_POLICY_v0.md (v0.1.0) - Politique de mapping identité
- KPI_POC.md (v0.1.0) - KPIs de succès
- TEST_VECTORS_v0.md (v0.1.0) - Vecteurs de test

### ⏳ Phase 1 : Implémentation Core - EN COURS (~80%)

**Modules implémentés dans `gwyl_mail/`** :
- ✅ `canonical.py` - Canonicalisation DKIM-inspired
- ✅ `sigstore_timestamp.py` - Timestamping Sigstore/Rekor
- ✅ `ots_manager.py` - Gestionnaire OpenTimestamps
- ✅ `dual_proof.py` - Orchestration des preuves
- ✅ `identity_policy.py` - Politique d'identité
- ✅ `validation.py` - Validation JSON Schema
- ✅ `cli.py` - Interface CLI avec commandes send/verify

**Tests implémentés dans `tests/`** :
- ✅ `test_canonical.py` - Tests canonicalisation
- ✅ `test_security.py` - Tests sécurité
- ✅ `test_verify.py` - Tests vérification

### 📋 À Faire (Phase 2 & 3)
- ⏳ Tests d'intégration (Gmail, Outlook, Postfix)
- ⏳ Validation KPIs (interop ≥95%, perf <50KB/<150ms)
- ⏳ Tests de bout-en-bout avec vrais emails
- ⏳ Déploiement pilote (10 utilisateurs, 1 mois)

---

## Fonctionnalités Récentes (derniers commits)

1. ✅ Logs d'audit explicites pour erreurs sécurité
2. ✅ Validation stricte schémas JSON
3. ✅ Soumission OTS robuste
4. ✅ Tests de sécurité ajoutés
5. ✅ Commande `verify` dans CLI
6. ✅ Politique identité/cohérence
7. ✅ Workflow CI ajouté
8. ✅ Validation Sigstore + OTS robuste
9. ✅ Protection anti-replay

---

## Commandes CLI Principales

```bash
# Envoyer un email avec preuve cryptographique
gwyl-mail send --to dest@example.com --subject "Sujet" --body "Message"

# Vérifier un email reçu
gwyl-mail verify email.eml proof.json

# Session de rédaction (spec DRAFT_SESSION_v0.md)
gwyl-mail start-session --reason "Rédaction" --fields subject body
gwyl-mail verify-session
gwyl-mail end-session --anchor
```

---

## Structure du Projet

```
GWyl_Mail/
├── gwyl_mail/              # Code source principal
│   ├── canonical.py        # Canonicalisation
│   ├── sigstore_timestamp.py
│   ├── ots_manager.py
│   ├── dual_proof.py
│   ├── identity_policy.py
│   ├── validation.py
│   └── cli.py
├── tests/                  # Tests unitaires/intégration
├── docs/specs/             # Spécifications techniques
├── examples/               # Exemples d'utilisation
└── Temporary_Integrity/    # Outils intégrité Git (hooks)
```

---

## Intégration Git (Integrity Hooks) — Mise à jour

Objectif: fiabiliser le flux baseline sans dépendre d’un script externe mutable.

Changements clés
- L’outil d’intégrité utilisé par les hooks pointe maintenant vers la copie locale: `Temporary_Integrity/unified_integrity.py` (au lieu de `/home/zack/GWyl_Integrity/unified_integrity.py`).
- Le script `Temporary_Integrity/commit_with_integrity.sh` a été renforcé:
  - Scan baseline robuste (NUL‑séparé) + exclusions supplémentaires (`.claude/`) pour réduire les faux positifs.
  - Vérification byte‑à‑byte que la copie `.committed` == l’original.
  - Commit en excluant l’original (`SECURITY_INTEGRITY_BASELINE.sha256`).
  - Chaînage post‑commit: création d’un fichier meta `SECURITY_INTEGRITY_BASELINE.sha256.meta` qui enregistre le SHA256 de la baseline committée, l’ID de commit et le timestamp, puis commit séparé du meta.

Installation rapide après clonage
```bash
# 1) Installer les hooks locaux (pre-commit + pre-push)
make integrity-install

# 2) (Optionnel) Générer baseline + snapshot + meta sans commit
make integrity-baseline

# 3) Commit avec intégrité (wrapper du script)
make integrity-commit MSG="Votre message de commit"

# Alternativement
./Temporary_Integrity/commit_with_integrity.sh "Votre message de commit"
```

Détails hook pre-commit
- Le hook local exécute: `python Temporary_Integrity/unified_integrity.py check`
- En cas de mismatch/missing, le commit est bloqué et les détails sont loggés dans `logs/mismatch.jsonl`.

Hook pre-push (OTS)
- Le hook local exécute une mise à jour des preuves OTS si présentes:
  - `logs/anchors/ots/*.ots` (intégrité dépôt)
  - `.gwyl_mail/proofs/ots/*.ots` (preuves applicatives)
- Si `ots` n'est pas disponible, le hook ne bloque pas le push; il affiche simplement un message.

Flux “baseline originale → copie committée → meta”
1. Générer `SECURITY_INTEGRITY_BASELINE.sha256` (original, non committé).
2. Copier en `SECURITY_INTEGRITY_BASELINE.sha256.committed` (committé) et vérifier l’égalité.
3. Commit 1: inclut `.committed` et les changements, en excluant l’original.
4. Commit 2: écrit et commit `SECURITY_INTEGRITY_BASELINE.sha256.meta` avec le SHA256 de la baseline committée, l’ID de commit et l’horodatage.

Notes
- Le hook local `.git/hooks/pre-commit` n’est pas versionné; la cible `make integrity-install` le (ré)installe.
- De même pour `.git/hooks/pre-push`.
- Si d’autres répertoires “vivants” provoquent des mismatches, les ajouter aux exclusions du scan baseline dans `Temporary_Integrity/commit_with_integrity.sh` et dans `make integrity-baseline`.

---

## KPIs de Succès PoC

**Interopérabilité** : ≥95% (Gmail, Outlook, Postfix)
**Performance** : <50KB overhead, <150ms vérification
**Fiabilité** : ≥90% confirmation OTS sous 48h
**Sécurité** : 100% détection tampering

---

## Équipe & Contributions

- **Zack** : Project Lead, vision, direction
- **Claude (Anthropic)** : Specs, implémentation, documentation
- **ChatGPT (OpenAI)** : Revue architecture, recommandations critiques
  - Identification canonicalisation comme priorité #1
  - Simplification architecture (élimination Roughtime)
  - Recommandations DSSE, JCS, policy_hash

---

## Standards & Références

**RFC implémentés** :
- RFC 6376 (DKIM) - Inspiration canonicalisation
- RFC 2047 (Encoded-words) - Décodage headers
- RFC 5322 (Email format) - Structure email
- RFC 8785 (JCS) - Canonicalisation JSON

**Projets connexes** :
- Sigstore (sigstore.dev)
- OpenTimestamps (opentimestamps.org)
- DSSE (Dead Simple Signing Envelope)

---

## Notes Importantes

### Sécurité
- Hash des adresses email (pas de PII en clair)
- Preuves portables (vérification offline)
- Profils canonicalisation (strict/relaxed)
- Politique d'identité configurable

### Privacy by Design
- Divulgation minimale métadonnées
- Vérification possible sans serveur central
- Ancrage blockchain décentralisé

### Menaces Couvertes
- ✅ Modification silencieuse du message
- ✅ Usurpation d'identité expéditeur
- ✅ Backdating / timestamping frauduleux
- ✅ Replay attacks
- ✅ Divulgation métadonnées

---

**Dernière mise à jour** : 2025-10-12
**Branche principale** : `main`
**Status Git** : Clean (d'après dernier snapshot)
