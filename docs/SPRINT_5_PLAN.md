# Sprint 5: Production Readiness - Plan d'Implémentation

**Date**: 2025-10-12
**Version**: v0.2.0
**Status**: 🔄 Draft
**Effort estimé**: ~25h
**Objectif**: Atteindre Security Score 9.5/10 et production-ready status

---

## Contexte

Suite à la revue ChatGPT post-Sprint 4, plusieurs problèmes critiques ont été identifiés qui empêchent le déploiement en production :

**Security Score Actuel**: 9.0/10
**Objectif Sprint 5**: 9.5/10

**Points bloquants identifiés** (ChatGPT Review):
- P1: DSSE signature manquante (proof JSON pas signé → risque modification)
- P1: Identity pas extraite à `create_proof()` (seulement à verify)
- P2: Issuer substring match trop permissif (`"google.com" in "evil-accounts.google.com"`)
- P2: Path traversal symlink possible (`_safe_in_dir` fallback)
- P2: OTS parsing fragile (dépend de patterns texte)
- P3: Coherence delta Rekor↔OTS pas visible en détail
- P3: Privacy metadata incomplet (`from_hash` manquant du vrai From EML)

---

## Sprint 5.1: Priorité P1 - Blockers Production

### Tâche 5.1.1: DSSE Signature for Proof JSON

**Problème**: Le fichier `proof.json` n'est pas signé → un attaquant peut modifier les métadonnées (`privacy`, `policy`, timestamps) sans invalider la preuve.

**Solution**: Signer le proof JSON complet avec DSSE (Dead Simple Signing Envelope) comme spécifié dans PROOF_SCHEMA_v0.md.

**Implémentation**:

1. **Nouveau module**: `gwyl_mail/dsse_signer.py`
   - Function `sign_proof_json(proof: dict, identity: str) -> dict`
   - Wrapper DSSE autour du proof JSON
   - Signature avec Sigstore cosign
   - Returns: DSSE envelope avec `payload`, `payloadType`, `signatures`

2. **Modification**: `gwyl_mail/dual_proof.py`
   - Appeler `sign_proof_json()` après génération du proof
   - Option `--no-dsse` pour désactiver (backward compatibility)

3. **Modification**: `gwyl_mail/cli.py`
   - Argument optionnel `--no-dsse` pour `create-proof`
   - Vérifier signature DSSE dans `cmd_verify()`

4. **Tests**: `tests/test_dsse_signer.py`
   - DSSE envelope structure validation
   - Signature verification with Sigstore
   - Invalid signature detection
   - Backward compatibility (proof without DSSE)

**Effort estimé**: ~8h
**Fichiers modifiés**: 4 fichiers (1 nouveau)
**Tests ajoutés**: ~10 tests

---

### Tâche 5.1.2: Extract Identity at create_proof() Time

**Problème**: L'identité (`identity`, `issuer`) est seulement extraite à la vérification, pas à la création de la preuve. Cela empêche de stocker ces infos dans le proof JSON.

**Solution**: Extraire l'identité immédiatement après la signature Sigstore et l'inclure dans le proof JSON.

**Implémentation**:

1. **Modification**: `gwyl_mail/sigstore_timestamp.py`
   - Appeler `extract_identity_from_bundle()` après signature
   - Retourner `SigstoreProof` avec champs `identity` et `issuer` remplis

2. **Modification**: `gwyl_mail/dual_proof.py`
   - Ajouter section `"signer"` dans proof JSON:
     ```json
     "signer": {
       "identity": "user@example.com",
       "issuer": "https://accounts.google.com",
       "extracted_at": "2025-10-12T12:00:00Z"
     }
     ```

3. **Modification**: `gwyl_mail/schemas/proof-v0.2.0.json`
   - Ajouter schéma pour section `"signer"` (optional pour backward compat)

4. **Tests**: `tests/test_dual_proof.py`
   - Vérifier présence de `signer` dans proof JSON
   - Valider identity/issuer correctement extraits
   - Backward compatibility (proof sans `signer`)

**Effort estimé**: ~5h
**Fichiers modifiés**: 3 fichiers
**Tests ajoutés**: ~5 tests

---

## Sprint 5.2: Priorité P2 - Security Hardening

### Tâche 5.2.1: Fix Issuer Exact Match

**Problème**: L'issuer matching utilise `in` substring check:
```python
if policy_issuer in bundle_issuer:  # VULNERABLE
```
Cela permet `"google.com"` de matcher `"evil-accounts.google.com"`.

**Solution**: Utiliser exact match ou suffix match strict avec dot boundary.

**Implémentation**:

1. **Modification**: `gwyl_mail/identity_policy.py`
   - Remplacer substring match par exact match:
     ```python
     # Old (vulnerable):
     if policy_issuer in bundle_issuer:

     # New (secure):
     if bundle_issuer == policy_issuer or bundle_issuer.endswith('.' + policy_issuer):
     ```

2. **Tests**: `tests/test_identity_policy.py`
   - Test exact match: `"accounts.google.com"` matches `"accounts.google.com"`
   - Test suffix match: `"accounts.google.com"` matches `"*.google.com"`
   - Test attack: `"google.com"` DOES NOT match `"evil-accounts.google.com"`
   - Test attack: `"google.com"` DOES NOT match `"googlemail.com"`

**Effort estimé**: ~2h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~4 tests

---

### Tâche 5.2.2: Robust Path Traversal Protection

**Problème**: `_safe_in_dir()` a un fallback permissif en cas d'exception.

**Solution**: Renforcer la validation et retirer le fallback.

**Implémentation**:

1. **Modification**: `gwyl_mail/cli.py`
   - Ajouter check symlink explicit:
     ```python
     def _safe_in_dir(path: Path, base_dir: Path) -> bool:
         # Resolve symlinks
         path = path.resolve()
         base_dir = base_dir.resolve()

         # Check if path is under base_dir
         try:
             path.relative_to(base_dir)
             return True
         except ValueError:
             return False
     ```
   - Retirer le `except Exception: return False` fallback

2. **Tests**: `tests/test_cli_security.py`
   - Test path traversal attack: `../../../etc/passwd`
   - Test symlink attack: symlink pointant hors du répertoire
   - Test path normal: fichier dans le répertoire autorisé

**Effort estimé**: ~2h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~3 tests

---

### Tâche 5.2.3: Resilient OTS Parsing

**Problème**: Le parsing de `ots info` dépend de patterns texte fragiles.

**Solution**: Parser plus robuste avec fallback gracieux.

**Implémentation**:

1. **Modification**: `gwyl_mail/ots_manager.py`
   - Ajouter support pour parsing JSON output (si disponible)
   - Multiple regex patterns pour chaque format timestamp
   - Fallback chain: JSON → regex human-readable → regex ISO → regex Unix
   - Log warning si parsing échoue

2. **Tests**: `tests/test_ots_manager.py`
   - Test parsing avec différents formats de sortie `ots info`
   - Test parsing avec sortie malformée
   - Test graceful degradation (retourner None si échec)

**Effort estimé**: ~3h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~5 tests

---

## Sprint 5.3: Priorité P3 - UX & Audit

### Tâche 5.3.1: Expose Coherence Delta Details

**Problème**: Le delta Rekor↔OTS est calculé mais pas visible dans les logs.

**Solution**: Ajouter champs `coherence_details` dans la sortie JSON.

**Implémentation**:

1. **Modification**: `gwyl_mail/cli.py`
   - Ajouter section `coherence_details` dans output JSON:
     ```json
     "coherence_details": {
       "rekor_timestamp": "2025-10-12T12:00:00Z",
       "ots_timestamp": "2025-10-12T12:00:05Z",
       "delta_seconds": 5,
       "threshold_hours": 24,
       "status": "ok"
     }
     ```

2. **Tests**: `tests/test_verify.py`
   - Vérifier présence de `coherence_details` dans output
   - Vérifier calcul delta correct

**Effort estimé**: ~2h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~2 tests

---

### Tâche 5.3.2: Complete Privacy Metadata

**Problème**: `privacy.from_hash` devrait être le hash du vrai champ `From` de l'EML, pas seulement l'identity du certificat.

**Solution**: Extraire le `From` header de l'EML et hacher.

**Implémentation**:

1. **Modification**: `gwyl_mail/dual_proof.py`
   - Extraire `From` header de l'EML:
     ```python
     from_header = message.get("From", "")
     from_hash = hashlib.sha256(from_header.encode('utf-8')).hexdigest()
     ```
   - Ajouter dans section `privacy`:
     ```json
     "privacy": {
       "from_hash": "abc123...",
       "from_domain": "example.com",
       "subject_hash": "def456..."
     }
     ```

2. **Tests**: `tests/test_dual_proof.py`
   - Vérifier `from_hash` correspond au From header de l'EML
   - Vérifier `from_domain` extrait correctement

**Effort estimé**: ~2h
**Fichiers modifiés**: 1 fichier
**Tests ajoutés**: ~2 tests

---

## Récapitulatif Sprint 5

### Effort total estimé
| Priorité | Tâches | Effort |
|----------|--------|--------|
| **P1** | 2 tâches | ~13h |
| **P2** | 3 tâches | ~7h |
| **P3** | 2 tâches | ~4h |
| **Testing & QA** | - | ~1h |
| **TOTAL** | 7 tâches | **~25h** |

### Fichiers impactés
| Fichier | Modifications |
|---------|---------------|
| `gwyl_mail/dsse_signer.py` | ✅ Nouveau (DSSE signature) |
| `gwyl_mail/sigstore_timestamp.py` | 📝 Modifié (extract identity at creation) |
| `gwyl_mail/dual_proof.py` | 📝 Modifié (signer section, privacy from_hash) |
| `gwyl_mail/identity_policy.py` | 📝 Modifié (issuer exact match) |
| `gwyl_mail/ots_manager.py` | 📝 Modifié (resilient parsing) |
| `gwyl_mail/cli.py` | 📝 Modifié (path safety, coherence details, DSSE verify) |
| `gwyl_mail/schemas/proof-v0.2.0.json` | 📝 Modifié (signer section) |

### Tests ajoutés
| Test File | Nouveaux Tests |
|-----------|----------------|
| `tests/test_dsse_signer.py` | ✅ Nouveau (~10 tests) |
| `tests/test_dual_proof.py` | +7 tests |
| `tests/test_identity_policy.py` | +4 tests |
| `tests/test_cli_security.py` | ✅ Nouveau (~3 tests) |
| `tests/test_ots_manager.py` | +5 tests |
| `tests/test_verify.py` | +2 tests |
| **TOTAL** | **+31 tests** |

**Tests finaux attendus**: 49 → **80 tests**, coverage 50% → **55%**

---

## Critères de succès Sprint 5

### Security
- ✅ DSSE signature implémentée et validée
- ✅ Identity extraite à creation time
- ✅ Issuer exact match (pas de substring vulnérable)
- ✅ Path traversal protection robuste
- ✅ OTS parsing résilient avec fallback

### Audit & Transparency
- ✅ Coherence delta Rekor↔OTS visible dans logs
- ✅ Privacy metadata complet (from_hash du vrai From)
- ✅ Signer identity/issuer dans proof JSON

### Tests
- ✅ 80/80 tests passing
- ✅ Coverage ≥55%
- ✅ Security tests ajoutés (attacks, edge cases)

### Security Score
- **Actuel**: 9.0/10
- **Objectif**: **9.5/10** ✅

---

## Risques & Mitigations

### Risque 1: DSSE Breaking Changes
**Impact**: Medium
**Probabilité**: Low
**Mitigation**: Backward compatibility via `--no-dsse` flag, vérifier que les anciens proofs sont encore valides.

### Risque 2: OTS Parsing Regression
**Impact**: High
**Probabilité**: Medium
**Mitigation**: Tests exhaustifs avec différentes versions de `ots` CLI, fallback gracieux si parsing échoue.

### Risque 3: Path Traversal False Positives
**Impact**: Medium
**Probabilité**: Low
**Mitigation**: Tests avec chemins réels, symlinks valides, cas edge.

---

## Prochaines Étapes (Post-Sprint 5)

### Sprint 6: Performance & Integration (Optional)
- Relaxed canonicalization profile (handle MTA transformations)
- Performance benchmarks (KPI validation)
- Integration tests (Gmail, Outlook, Postfix)
- Documentation updates (README, examples)

### Phase 3: Pilote
- Déploiement pilote (10 utilisateurs, 1 mois)
- Monitoring & métriques
- Feedback & ajustements

---

**Prochaine revue**: Après implémentation des tâches P1
**Owner**: Claude (implementation) + ChatGPT (security review)
**Date cible**: 2025-10-15
