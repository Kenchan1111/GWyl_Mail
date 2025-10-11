# GWyl Mail - État du Projet

**Date**: 2025-01-11
**Version**: 0.1.0 (PoC - Phase 0 complétée)
**Status**: Spécifications complètes, implémentation à démarrer

---

## ✅ Phase 0: Spécifications - COMPLÉTÉE

### Documents de spécification (docs/specs/)

| Document | Version | Status | Lignes | Description |
|----------|---------|--------|--------|-------------|
| **CANONICALIZATION_v0.md** | v0.2.0 | ✅ Specification | ~1150 | Algorithme normatif de canonicalisation |
| **PROOF_SCHEMA_v0.md** | v0.2.0 | ✅ Specification | ~1050 | Schéma de preuve cryptographique |
| **IDENTITY_POLICY_v0.md** | v0.1.0 | 🔄 Draft | ~730 | Politique d'identité |
| **KPI_POC.md** | v0.1.0 | 🔄 Draft | ~610 | KPIs et critères de succès |
| **TEST_VECTORS_v0.md** | v0.1.0 | ✅ Complete | ~184 | Vecteurs de test avec résultats |

**Total**: ~3700 lignes de spécifications techniques détaillées

### Qualité des spécifications

**CANONICALIZATION_v0.md** (v0.2.0):
- ✅ Algorithme normatif bit-à-bit
- ✅ RFC 2047 (encoded-words) complet
- ✅ RFC 5322 (header folding) normalisé
- ✅ Unicode NFC normalization
- ✅ Profils strict/relaxed définis
- ✅ 8 test cases détaillés
- ✅ Effets MTA documentés (Gmail, Outlook, Postfix)
- ✅ Implémentation de référence Python

**PROOF_SCHEMA_v0.md** (v0.2.0):
- ✅ Normalisation JSON (JCS - RFC 8785)
- ✅ Signature proof (DSSE)
- ✅ Champ `policy` avec hash
- ✅ Cohérence temporelle formalisée
- ✅ Anti-replay enrichi
- ✅ JSON Schema complet
- ✅ Workflows création/vérification

**Améliorations critiques intégrées** (feedback ChatGPT):
1. ✅ Canonicalisation comme priorité #1 identifiée
2. ✅ Architecture simplifiée (élimination Roughtime)
3. ✅ DSSE pour signature proof
4. ✅ JCS pour normalisation JSON
5. ✅ policy_hash pour lier preuve à politique

---

## 🏗️ Phase 1: Implémentation Core - À DÉMARRER

### Modules à implémenter (gwyl_mail/)

| Module | Fichier | Status | Dépendances | Complexité |
|--------|---------|--------|-------------|------------|
| **Canonicalisation** | `canonical.py` | ⏳ À faire | stdlib email, unicodedata | Moyenne |
| **Sigstore Timestamp** | `sigstore_timestamp.py` | ⏳ À faire | sigstore, pathlib | Moyenne |
| **OTS Manager** | `ots_manager.py` | ⏳ À faire | opentimestamps-client | Moyenne |
| **Dual Proof** | `dual_proof.py` | ⏳ À faire | canonical, sigstore, ots | Élevée |
| **Identity Policy** | `identity_policy.py` | ⏳ À faire | pyyaml | Moyenne |
| **CLI** | `cli.py` | ⏳ À faire | click, rich | Moyenne |

### Ordre d'implémentation recommandé

1. **canonical.py** (base de tout)
   - Classe `GWylCanonical`
   - Méthodes: `canonicalize()`, `hash()`, `_canonicalize_headers()`, etc.
   - Tests unitaires avec TEST_VECTORS

2. **sigstore_timestamp.py** (timestamp immédiat)
   - Classe `SigstoreTimestamp`
   - Signature + Rekor logging
   - Bundle portable

3. **ots_manager.py** (timestamp différé)
   - Classe `OTSManager`
   - Submit, upgrade, verify
   - Gestion états PENDING/CONFIRMED/FAILED

4. **identity_policy.py** (validation identité)
   - Classe `IdentityPolicy`
   - Parsing YAML
   - Validation rules (exact/domain/alias)

5. **dual_proof.py** (orchestration)
   - Classe `DualProof`
   - Création proof complet
   - Vérification proof
   - Signature DSSE

6. **cli.py** (interface utilisateur)
   - Commandes: `gwyl-mail send`, `gwyl-mail verify`
   - Rich output
   - Configuration

---

## 🧪 Phase 2: Tests - À PLANIFIER

### Tests unitaires (tests/)

- `test_canonical.py`: Canonicalisation (8+ cas)
- `test_sigstore.py`: Sigstore integration
- `test_ots.py`: OTS integration
- `test_dual_proof.py`: Workflow complet
- `test_identity_policy.py`: Validation identité

### Tests d'intégration

- Gmail: 50 messages (interop, encoding, headers)
- Outlook: 50 messages (footers, transformations)
- Postfix: 50 messages (contrôle, baseline)

### Validation KPIs

- Interopérabilité: ≥95%
- Performance: <50KB overhead, <150ms vérif
- Fiabilité: ≥90% OTS confirmation
- Sécurité: 100% tampering detection

---

## 📊 Métriques Projet

### Code (actuellement)
- **Spécifications**: ~3700 lignes
- **Code implémenté**: 0 lignes (phase 1 à démarrer)
- **Tests**: 0 (à écrire avec implémentation)

### Effort estimé

| Phase | Tâches | Effort estimé | Status |
|-------|--------|---------------|--------|
| **Phase 0** | Specs | ~40h | ✅ Complété |
| **Phase 1** | Implémentation | ~60h | ⏳ À faire |
| **Phase 2** | Tests & KPIs | ~40h | ⏳ À faire |
| **Phase 3** | Pilote | ~20h | ⏳ À faire |
| **TOTAL** | | ~160h | 25% complété |

### Dépendances externes

**Python packages**:
- `sigstore` (cryptographie, Rekor)
- `opentimestamps-client` (blockchain Bitcoin)
- `pyyaml` (configuration)
- `canonicaljson` (JCS RFC 8785)
- `click`, `rich` (CLI)

**Services externes**:
- Sigstore Rekor (public transparency log)
- OpenTimestamps calendars (public, gratuit)
- OIDC providers (Google, Microsoft, GitHub)

---

## 🎯 Prochaines Étapes Immédiates

### Sprint 1: Canonicalisation (priorité 1)

1. ✅ Créer structure projet ✅
2. ⏳ Implémenter `gwyl_mail/canonical.py`
   - Classe `GWylCanonical`
   - Méthodes canonicalisation headers/body/attachments
   - Implémentation RFC 2047, RFC 5322, Unicode NFC
3. ⏳ Tests unitaires `test_canonical.py`
   - Valider contre TEST_VECTORS_v0.md
   - Cas: simple, encoding, Unicode, attachments
4. ⏳ Validation: Tous les test vectors passent

**Objectif**: Base de canonicalisation opérationnelle et testée

---

## 👥 Équipe & Contributions

**Core Team**:
- **Zack**: Project Lead, vision, direction
- **Claude (Anthropic)**: Specs, implémentation, documentation
- **ChatGPT (OpenAI)**: Revue architecture, recommandations critiques

**Contributions clés ChatGPT**:
1. Identification canonicalisation comme blocker #1
2. Correction NTS → Sigstore (élimination Roughtime)
3. Recommandations DSSE, JCS, policy_hash
4. Définition KPIs mesurables

---

## 📜 Licence & Références

**Licence**: GPL-3.0

**Standards**:
- RFC 6376 (DKIM)
- RFC 2047 (Encoded-words)
- RFC 5322 (Email format)
- RFC 8785 (JCS)
- DSSE (Sigstore/in-toto)

**Projets connexes**:
- Sigstore (sigstore.dev)
- OpenTimestamps (opentimestamps.org)
- DKIM (RFC 6376)

---

**Dernière mise à jour**: 2025-01-11 17:45 UTC
**Prochaine revue**: Après implémentation Sprint 1
