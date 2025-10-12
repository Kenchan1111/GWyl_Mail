# Sprint 6: Performance, Integration & Documentation - Plan d'Implémentation

**Date**: 2025-10-12
**Version**: v0.2.0 → v0.3.0
**Status**: 🔄 Draft
**Effort estimé**: ~20h
**Objectif**: Performance optimization, real-world integration, comprehensive documentation

---

## Contexte

Suite à Sprint 5 (Security Score 9.5/10), le système est production-ready du point de vue sécurité. Sprint 6 se concentre sur :

**Security Score Actuel**: 9.5/10
**Objectif Sprint 6**: Maintenir 9.5/10 + améliorer performance, intégration, documentation

**Besoins identifiés**:
- Performance: Valider les KPI (< 2s signature, < 1s vérification)
- Integration: Tester avec vrais MTA (Gmail, Outlook, Postfix)
- Canonicalization: Support "relaxed" profile pour transformations MTA
- Documentation: README complet, exemples, troubleshooting
- CI/CD: Automatisation tests, release process

---

## Sprint 6.1: Priorité P1 - Performance & KPI Validation

### Tâche 6.1.1: Performance Benchmarks

**Problème**: Pas de benchmarks formels pour valider les KPI de performance (voir KPI_POC.md).

**Objectif**: Valider que le système respecte les KPI :
- Signature: < 2 secondes
- Vérification offline: < 1 seconde
- Vérification avec OTS: < 5 secondes

**Implémentation**:

1. **Nouveau module**: `tests/test_performance.py`
   - Benchmark `create_proof()` avec différentes tailles d'email (10KB, 100KB, 1MB)
   - Benchmark `verify()` offline (sans network)
   - Benchmark `verify()` avec OTS upgrade
   - Mesurer temps CPU, mémoire, I/O

2. **Script**: `scripts/benchmark.py`
   - CLI pour lancer benchmarks
   - Output JSON avec métriques détaillées
   - Comparaison avec baseline

3. **Documentation**: `docs/PERFORMANCE.md`
   - Résultats benchmarks
   - Recommandations optimisation
   - Profiling guides

**Effort estimé**: ~4h
**Fichiers créés**: 3 fichiers (tests, script, doc)
**Tests ajoutés**: ~5 tests

---

### Tâche 6.1.2: Optimize Canonicalization

**Problème**: La canonicalization peut être lente sur gros emails (> 1MB).

**Objectif**: Optimiser l'algorithme de canonicalization pour respecter KPI < 2s.

**Implémentation**:

1. **Analyse**: Profiling de `GWylCanonical.hash()`
   - Identifier bottlenecks (regex, parsing, encoding)
   - Mesurer impact de chaque étape

2. **Optimisations**:
   - Cache pour headers décodés
   - Lazy parsing des attachments
   - Streaming pour gros fichiers

3. **Tests**: `tests/test_canonical.py`
   - Benchmark avec gros emails (1MB, 5MB)
   - Vérifier que résultat hash reste identique

**Effort estimé**: ~3h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~3 tests

---

## Sprint 6.2: Priorité P2 - Integration & Compatibility

### Tâche 6.2.1: Relaxed Canonicalization Profile

**Problème**: Le profile "strict" échoue sur emails transformés par MTA (ajout headers, wrapping, etc.).

**Objectif**: Implémenter profile "relaxed" qui tolère les transformations MTA courantes.

**Implémentation**:

1. **Modification**: `gwyl_mail/canonical.py`
   - Ajouter `RELAXED_PROFILE`:
     - Ignorer headers ajoutés par MTA (`Received`, `X-*`, `DKIM-Signature`, etc.)
     - Normaliser whitespace plus agressivement
     - Tolérer line wrapping RFC 5322
   - Paramètre `profile="strict"|"relaxed"` dans `GWylCanonical.hash()`

2. **Configuration**: `gwyl_mail/canonical_profiles.yml`
   - Liste des headers ignorés par profile
   - Règles de normalisation par profile

3. **CLI**: Argument `--profile` pour `create-proof` et `verify`

4. **Tests**: `tests/test_canonical_relaxed.py`
   - Test avec email avant/après passage MTA
   - Test que relaxed tolère transformations courantes
   - Test que strict échoue (regression check)

**Effort estimé**: ~5h
**Fichiers modifiés**: 2 fichiers (1 nouveau config)
**Tests ajoutés**: ~10 tests

---

### Tâche 6.2.2: Integration Tests avec MTA Réels

**Problème**: Pas de tests avec vrais MTA (Gmail, Outlook, Postfix).

**Objectif**: Valider que le système fonctionne end-to-end avec MTA réels.

**Implémentation**:

1. **Tests**: `tests/integration/test_mta_gmail.py`
   - Envoyer email via Gmail SMTP
   - Récupérer via IMAP
   - Créer proof + vérifier
   - Valider que relaxed profile fonctionne

2. **Tests**: `tests/integration/test_mta_postfix.py`
   - Setup Postfix local (Docker)
   - Envoyer email via Postfix
   - Vérifier avec relaxed profile

3. **Documentation**: `docs/INTEGRATION.md`
   - Setup guides pour Gmail, Outlook, Postfix
   - Exemples de configuration
   - Troubleshooting communs

**Effort estimé**: ~4h
**Fichiers créés**: 3 fichiers (tests, doc)
**Tests ajoutés**: ~8 tests (marqués `@pytest.mark.integration`)

---

### Tâche 6.2.3: Example Scripts & Use Cases

**Problème**: Manque d'exemples concrets d'utilisation.

**Objectif**: Fournir scripts prêts à l'emploi pour cas d'usage courants.

**Implémentation**:

1. **Scripts**: `examples/use_cases/`
   - `email_notarization.py`: Notariser email important (contrat, facture)
   - `compliance_archival.py`: Archive email avec preuve pour conformité
   - `dispute_resolution.py`: Prouver qu'un email a été envoyé/reçu à date T
   - `batch_processing.py`: Traiter lot d'emails

2. **Documentation**: `examples/USE_CASES.md`
   - Description de chaque cas d'usage
   - Workflow détaillé
   - Exemples de commandes

**Effort estimé**: ~2h
**Fichiers créés**: 5 fichiers (4 scripts + 1 doc)

---

## Sprint 6.3: Priorité P3 - Documentation & DevEx

### Tâche 6.3.1: Comprehensive README

**Problème**: README actuel est basique.

**Objectif**: README complet avec quick start, exemples, FAQ.

**Implémentation**:

1. **Modification**: `README.md`
   - Section "Quick Start" (5 minutes to first proof)
   - Section "Use Cases" avec exemples concrets
   - Section "How It Works" (architecture overview)
   - Section "FAQ" (questions courantes)
   - Section "Contributing" (guidelines)
   - Badges (tests, coverage, license)

2. **Visuels**: `docs/diagrams/`
   - Diagramme architecture
   - Diagramme workflow proof creation
   - Diagramme workflow verification

**Effort estimé**: ~3h
**Fichiers modifiés**: 1 fichier (+ 3 diagrammes)

---

### Tâche 6.3.2: Troubleshooting Guide

**Problème**: Pas de guide pour diagnostiquer problèmes courants.

**Objectif**: Documentation complète pour debugging.

**Implémentation**:

1. **Documentation**: `docs/TROUBLESHOOTING.md`
   - Section "Common Errors" avec solutions
   - Section "Debugging Tools" (logs, verbose mode)
   - Section "Network Issues" (Sigstore, OTS timeouts)
   - Section "Compatibility Issues" (MTA transformations)
   - Section "Performance Issues" (profiling, optimization)

2. **CLI Enhancement**: `gwyl_mail/cli.py`
   - Argument `--verbose` pour debug output
   - Argument `--log-level` (DEBUG, INFO, WARNING, ERROR)
   - Better error messages avec suggestions

**Effort estimé**: ~2h
**Fichiers créés**: 1 fichier
**Fichiers modifiés**: 1 fichier

---

### Tâche 6.3.3: CI/CD Enhancements

**Problème**: CI basique, pas de release automation.

**Objectif**: Pipeline CI/CD complet.

**Implémentation**:

1. **GitHub Actions**: `.github/workflows/release.yml`
   - Workflow release automatique
   - Build package PyPI
   - Generate changelog
   - Create GitHub release
   - Upload assets

2. **GitHub Actions**: `.github/workflows/performance.yml`
   - Run benchmarks sur chaque PR
   - Comparer avec baseline
   - Fail si regression > 10%

3. **Pre-commit hooks**: `.pre-commit-config.yaml`
   - Ajouter black (formatting)
   - Ajouter mypy (type checking)
   - Ajouter bandit (security linting)

**Effort estimé**: ~3h
**Fichiers créés**: 2 workflows
**Fichiers modifiés**: 1 fichier

---

## Récapitulatif Sprint 6

### Effort total estimé
| Priorité | Tâches | Effort |
|----------|--------|--------|
| **P1** | 2 tâches | ~7h |
| **P2** | 3 tâches | ~11h |
| **P3** | 3 tâches | ~8h |
| **Testing & QA** | - | ~2h |
| **TOTAL** | 8 tâches | **~28h** |

### Fichiers impactés
| Fichier | Modifications |
|---------|---------------|
| `tests/test_performance.py` | ✅ Nouveau (benchmarks) |
| `scripts/benchmark.py` | ✅ Nouveau (CLI benchmarks) |
| `gwyl_mail/canonical.py` | 📝 Modifié (relaxed profile) |
| `gwyl_mail/canonical_profiles.yml` | ✅ Nouveau (config profiles) |
| `gwyl_mail/cli.py` | 📝 Modifié (verbose, log-level) |
| `tests/integration/test_mta_*.py` | ✅ Nouveau (integration tests) |
| `examples/use_cases/*.py` | ✅ Nouveau (4 scripts) |
| `README.md` | 📝 Modifié (comprehensive) |
| `docs/TROUBLESHOOTING.md` | ✅ Nouveau |
| `docs/PERFORMANCE.md` | ✅ Nouveau |
| `docs/INTEGRATION.md` | ✅ Nouveau |
| `.github/workflows/release.yml` | ✅ Nouveau |
| `.github/workflows/performance.yml` | ✅ Nouveau |

### Tests ajoutés
| Test File | Nouveaux Tests |
|-----------|----------------|
| `tests/test_performance.py` | ✅ Nouveau (~5 tests) |
| `tests/test_canonical.py` | +3 tests |
| `tests/test_canonical_relaxed.py` | ✅ Nouveau (~10 tests) |
| `tests/integration/test_mta_gmail.py` | ✅ Nouveau (~4 tests) |
| `tests/integration/test_mta_postfix.py` | ✅ Nouveau (~4 tests) |
| **TOTAL** | **+26 tests** |

**Tests finaux attendus**: 66 → **92 tests**, coverage 50% → **60%**

---

## Critères de succès Sprint 6

### Performance
- ✅ Signature < 2s (emails jusqu'à 1MB)
- ✅ Vérification offline < 1s
- ✅ Benchmarks automatisés dans CI

### Integration
- ✅ Relaxed profile implémenté et testé
- ✅ Integration tests avec Gmail, Postfix
- ✅ Exemples use cases fonctionnels

### Documentation
- ✅ README complet avec quick start
- ✅ Troubleshooting guide
- ✅ Diagrams architecture

### DevEx
- ✅ CI/CD avec release automation
- ✅ Pre-commit hooks (formatting, linting)
- ✅ Better error messages avec `--verbose`

### Tests
- ✅ 92/92 tests passing
- ✅ Coverage ≥60%
- ✅ Integration tests marqués séparément

---

## Risques & Mitigations

### Risque 1: Relaxed Profile Trop Permissif
**Impact**: High
**Probabilité**: Medium
**Mitigation**: Tests exhaustifs avec MTA réels, documentation claire sur quand utiliser strict vs relaxed.

### Risque 2: Integration Tests Flaky
**Impact**: Medium
**Probabilité**: High
**Mitigation**: Mock external services, marqueur `@pytest.mark.slow`, retry logic.

### Risque 3: Performance Regressions
**Impact**: Medium
**Probabilité**: Low
**Mitigation**: CI performance checks automatiques, fail si régression > 10%.

---

## Prochaines Étapes (Post-Sprint 6)

### Sprint 7: Pilote & Production (Optional)
- Beta release (v0.3.0-beta)
- Pilote avec 10 utilisateurs
- Monitoring & observability
- Production hardening

### Phase 3: v1.0 Release
- Stabilisation API
- Production documentation
- Support & maintenance plan
- Marketing & communication

---

**Prochaine revue**: Après implémentation des tâches P1
**Owner**: Claude (implementation)
**Date cible**: 2025-10-16
