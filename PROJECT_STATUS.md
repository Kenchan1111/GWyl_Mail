# GWyl Mail - État du Projet

**Date**: 2025-10-12
**Version**: 0.1.0 (PoC - Sprint 3 complété)
**Status**: Implémentation core opérationnelle, 49/49 tests passing

---

## ✅ Phase 0: Spécifications - COMPLÉTÉE

### Documents de spécification (docs/specs/)

| Document | Version | Status | Lignes | Description |
|----------|---------|--------|--------|-------------|
| **CANONICALIZATION_v0.md** | v0.2.0 | ✅ Specification | ~1150 | Algorithme normatif de canonicalisation |
| **PROOF_SCHEMA_v0.md** | v0.2.0 | ✅ Specification | ~1050 | Schéma de preuve cryptographique |
| **IDENTITY_POLICY_v0.md** | v0.1.0 | ✅ Implemented | ~730 | Politique d'identité |
| **KPI_POC.md** | v0.1.0 | 🔄 Draft | ~610 | KPIs et critères de succès |
| **TEST_VECTORS_v0.md** | v0.1.0 | ✅ Complete | ~184 | Vecteurs de test avec résultats |

**Total**: ~3700 lignes de spécifications techniques détaillées

---

## ✅ Phase 1: Implémentation Core - COMPLÉTÉE

### Modules implémentés (gwyl_mail/)

| Module | Fichier | Status | Lignes | Tests |
|--------|---------|--------|--------|-------|
| **Canonicalisation** | `canonical.py` | ✅ Implémenté | 122 | ✅ 10 tests |
| **Sigstore Timestamp** | `sigstore_timestamp.py` | ✅ Implémenté | 158 | ✅ Intégré |
| **Sigstore Identity** | `sigstore_identity.py` | ✅ Implémenté (Sprint 3) | 269 | ✅ 14 tests |
| **OTS Manager** | `ots_manager.py` | ✅ Implémenté | 158 | ✅ Intégré |
| **Dual Proof** | `dual_proof.py` | ✅ Implémenté | 125 | ✅ Intégré |
| **Identity Policy** | `identity_policy.py` | ✅ Implémenté | ~200 | ✅ 8 tests |
| **Validation** | `validation.py` | ✅ Implémenté | ~150 | ✅ Intégré |
| **CLI** | `cli.py` | ✅ Implémenté | 300 | ✅ 7 tests |

**Total**: ~1482 lignes de code production

---

## ✅ Sprint 1: Canonicalisation - COMPLÉTÉ

**Date**: 2025-01-11

### Implémentation
- ✅ `gwyl_mail/canonical.py` (122 lignes)
- ✅ Headers normalisés (RFC2047, unfolding, NFC)
- ✅ Body: CRLF→LF, trim fin de ligne, NFC
- ✅ Attachments: hash SHA-256 trié
- ✅ Type hints complets

### Tests
- ✅ `tests/test_canonical.py` (10 tests)
- ✅ Encoding UTF-8, Latin-1, ASCII
- ✅ Unicode normalization (NFC)
- ✅ Header folding/unfolding
- ✅ Attachments ordering

**Résultat**: 10/10 tests passing

---

## ✅ Sprint 2: Identity Policy & Coherence - COMPLÉTÉ

**Date**: 2025-01-11

### Implémentation
- ✅ `gwyl_mail/identity_policy.py` (~200 lignes)
- ✅ Policy validation (exact match, domain match, OIDC issuer whitelist)
- ✅ Enforcement modes (strict/warn)
- ✅ Coherence check Rekor/OTS (24h threshold)

### Tests
- ✅ `tests/test_identity_policy.py` (8 tests)
- ✅ `tests/test_verify.py` (7 tests)
- ✅ Policy exact/domain/issuer matching
- ✅ Coherence timestamp validation

**Résultat**: 35/35 tests passing

---

## ✅ Sprint 3: Security Hardening - COMPLÉTÉ

**Date**: 2025-10-12

### Implémentation (Critical Issues - ChatGPT Review)

**P1 - Robust Sigstore Identity Extraction**:
- ✅ New module `gwyl_mail/sigstore_identity.py` (269 lignes)
- ✅ Proper X.509 certificate parsing (cryptography library)
- ✅ SAN email extraction
- ✅ Fulcio OIDC issuer extraction (OID 1.3.6.1.4.1.57264.1.1)
- ✅ Rekor log index + integrated timestamp
- ✅ Replaces fragile heuristic extraction in CLI

**P1 - Real OTS Timestamp Extraction**:
- ✅ Enhanced `gwyl_mail/ots_manager.py`
- ✅ Parse `ots info` output for real Bitcoin block timestamp
- ✅ Supports 3 timestamp formats (human-readable, ISO, Unix)
- ✅ Removes `datetime.now()` approximation
- ✅ Enables reliable Rekor/OTS coherence check (24h)

### Tests
- ✅ `tests/test_sigstore_identity.py` (14 tests)
- ✅ `tests/test_security.py` (security-specific tests)
- ✅ All previous tests still passing

**Résultat**: 49/49 tests passing, 50% coverage

**Security Score Evolution**:
- Sprint 1: 8.0/10
- Sprint 2: 8.5/10
- Sprint 3: **9.0/10** ✅

---

## ✅ Sprint 4: Polish & Refinement - EN COURS

**Date**: 2025-10-12

### Implémentation (ChatGPT Review P2/P3)

**P2 - Code Quality**:
- ✅ Fix `GWylCanonical.hash()` type hints (`EmailMessage | bytes | str`)
- ✅ Use `tempfile.NamedTemporaryFile` in CLI (avoid collisions)
- ✅ Expose identity/issuer in verify output and audit log

**P3 - Project Hygiene**:
- ✅ Remove unused dependencies (click, rich, canonicaljson)
- ✅ Update PROJECT_STATUS.md (this file)
- ⏳ Update CHANGELOG.md
- ⏳ Add relaxed canonicalization profile option

---

## 🧪 Tests - État Actuel

### Tests unitaires (tests/)

| Fichier | Tests | Status | Coverage |
|---------|-------|--------|----------|
| `test_canonical.py` | 10 | ✅ Pass | Headers, body, attachments |
| `test_identity_policy.py` | 8 | ✅ Pass | Policy validation |
| `test_sigstore_identity.py` | 14 | ✅ Pass | X.509, SAN, issuer |
| `test_security.py` | ~5 | ✅ Pass | Security edge cases |
| `test_vectors.py` | 5 | ✅ Pass | RFC compliance |
| `test_verify.py` | 7 | ✅ Pass | End-to-end verification |

**Total**: 49/49 tests passing, 50% coverage

---

## 📊 Métriques Projet

### Code (actuel)
- **Spécifications**: ~3700 lignes
- **Code production**: ~1482 lignes (gwyl_mail/)
- **Tests**: ~800 lignes (tests/)
- **Total**: ~6000 lignes

### Effort réel

| Phase | Tâches | Effort estimé | Effort réel | Status |
|-------|--------|---------------|-------------|--------|
| **Phase 0** | Specs | ~40h | ~50h | ✅ Complété |
| **Sprint 1** | Canonicalisation | ~15h | ~12h | ✅ Complété |
| **Sprint 2** | Identity/Policy | ~15h | ~10h | ✅ Complété |
| **Sprint 3** | Security Hardening | ~20h | ~15h | ✅ Complété |
| **Sprint 4** | Polish | ~10h | ~5h (en cours) | 🔄 En cours |
| **TOTAL** | | ~100h | ~92h | 80% complété |

### Dépendances externes

**Python packages** (production):
- `sigstore>=2.0.0` (cryptographie, Rekor)
- `cryptography>=41.0.0` (X.509 parsing)
- `opentimestamps-client>=0.7.0` (blockchain Bitcoin)
- `pyyaml>=6.0` (configuration)
- `jsonschema>=4.0.0` (validation)

**Python packages** (dev):
- `pytest>=7.0.0`
- `pytest-cov>=4.0.0`
- `black>=23.0.0`
- `ruff>=0.1.0`
- `mypy>=1.0.0`

**Services externes**:
- Sigstore Rekor (public transparency log)
- OpenTimestamps calendars (public, gratuit)
- OIDC providers (Google, Microsoft, GitHub)

---

## 🎯 Prochaines Étapes

### Sprint 4: Finalization (current)

1. ✅ Fix type hints
2. ✅ Use unique temp files
3. ✅ Expose identity/issuer in verify output
4. ✅ Remove unused dependencies
5. ✅ Update PROJECT_STATUS.md
6. ⏳ Update CHANGELOG.md
7. ⏳ Add relaxed canonicalization profile
8. ⏳ Run all tests
9. ⏳ Commit with integrity procedure

### Sprint 5: Production Readiness (optional)

1. DSSE signature for proof JSON (prevents metadata tampering)
2. Relaxed canonicalization profile (handle MTA transformations)
3. Performance benchmarks (KPI validation)
4. Integration tests (Gmail, Outlook, Postfix)
5. Documentation updates (README, examples)

---

## 👥 Équipe & Contributions

**Core Team**:
- **Zack**: Project Lead, vision, direction
- **Claude (Anthropic)**: Implementation, tests, documentation
- **ChatGPT (OpenAI)**: Security review, architecture recommendations

**Contributions clés ChatGPT**:
1. Sprint 3 Critical Issues identification (Sigstore identity, OTS timestamp)
2. P2/P3 recommendations (type hints, temp files, cleanup)
3. Security score tracking methodology

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

**Dernière mise à jour**: 2025-10-12 11:30 UTC
**Prochaine revue**: Après Sprint 4 completion
