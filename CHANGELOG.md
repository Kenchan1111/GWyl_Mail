# Changelog - GWyl Mail

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

---

## [Unreleased]

### Sprint 4: Polish & Refinement (2025-10-12)

#### Modifié
- **gwyl_mail/canonical.py**: Fix type hints `GWylCanonical.hash()` to accept `EmailMessage | bytes | str`
- **gwyl_mail/cli.py**:
  - Use `tempfile.NamedTemporaryFile` instead of fixed path to avoid collisions
  - Expose `identity` and `issuer` in verify output JSON and audit log
- **pyproject.toml**: Remove unused dependencies (`click`, `rich`, `canonicaljson`)

#### Documentation
- **PROJECT_STATUS.md**: Complete update reflecting Sprint 1-4 achievements
- **CHANGELOG.md**: Update with Sprint 3 and Sprint 4 changes

---

## [0.1.0] - 2025-10-12

### Sprint 3: Security Hardening (2025-10-12)

#### Ajouté
- **gwyl_mail/sigstore_identity.py** (269 lignes): Robust Sigstore identity extraction
  - Proper X.509 certificate parsing using `cryptography` library
  - SAN (Subject Alternative Name) email extraction
  - Fulcio OIDC issuer extraction from OID `1.3.6.1.4.1.57264.1.1`
  - Rekor log index + integrated timestamp extraction
  - Replaces fragile heuristic extraction (ChatGPT Critical Issue #1)

- **tests/test_sigstore_identity.py** (217 lignes): 14 tests for identity extraction
  - Bundle parsing validation
  - X.509 certificate parsing
  - SAN email extraction
  - OIDC issuer extraction
  - Policy validation integration

#### Modifié
- **gwyl_mail/ots_manager.py**: Real OTS timestamp extraction
  - New method `_extract_real_timestamp()` parsing `ots info` output
  - Supports 3 timestamp formats: human-readable, ISO, Unix
  - Removes `datetime.now()` approximation (ChatGPT Critical Issue #2)
  - Enables reliable Rekor/OTS coherence check (24h threshold)

- **gwyl_mail/cli.py**:
  - Integrate robust identity extraction in `cmd_verify()`
  - Fallback to heuristic if robust extraction fails
  - Enhanced audit logging with extracted identity/issuer

#### Sécurité
- **Identity Policy now enforceable**: Certificate identity properly validated
- **Coherence check now reliable**: Real OTS timestamps enable accurate Rekor/OTS delta
- Security score: **8.5/10 → 9.0/10**

#### Tests
- 49/49 tests passing (vs 35/35 in Sprint 2)
- 50% code coverage

---

### Sprint 2: Identity Policy & Coherence (2025-01-11)

#### Ajouté
- **gwyl_mail/identity_policy.py** (~200 lignes): Identity policy validation
  - Exact match, domain match, alias support
  - OIDC issuer whitelist validation
  - Enforcement modes: strict/warn
  - Policy hash computation (SHA-256 over YAML)

- **gwyl_mail/policy_utils.py**: Policy utilities
  - `compute_policy_hash()`: SHA-256 over canonical YAML
  - `extract_policy_metadata()`: Extract policy_id, policy_url

- **Coherence check** in `gwyl_mail/cli.py`:
  - Rekor timestamp vs OTS timestamp delta
  - Threshold: 24 hours
  - Reports `coherence_ok`, `coherence_failed`, `coherence_unknown`

- **tests/test_identity_policy.py** (8 tests): Policy validation
- **tests/test_verify.py** (7 tests): End-to-end verification with policy

#### Modifié
- **gwyl_mail/canonical.py**: Unicode NFC normalization
  - Headers: `unicodedata.normalize('NFC', v)` (line 61)
  - Body: `unicodedata.normalize('NFC', normalized)` (line 82)
  - Prevents Unicode equivalence attacks

- **gwyl_mail/dual_proof.py**:
  - Add `policy` section in proof JSON
  - Compute `policy_hash` if policy provided
  - Include `policy_id` and `policy_url`

#### Tests
- 35/35 tests passing (vs 10/10 in Sprint 1)
- Policy validation: exact/domain/issuer matching
- Coherence: timestamp delta validation

---

### Sprint 1: Canonicalisation (2025-01-11)

#### Ajouté

**Phase 0: Spécifications**
- ✅ **CANONICALIZATION_v0.md** (v0.2.0): Algorithme normatif de canonicalisation DKIM-inspired
  - RFC 2047 (encoded-words) décodage complet
  - RFC 5322 (header folding) unfolding normalisé
  - Unicode NFC normalization (headers + filenames)
  - Profils strict/relaxed définis
  - 8 test cases détaillés
  - Effets MTA par provider (Gmail, Outlook, Postfix)

- ✅ **PROOF_SCHEMA_v0.md** (v0.2.0): Schéma de preuve cryptographique dual timestamping
  - Normalisation JSON (JCS - RFC 8785)
  - Signature proof (DSSE - Dead Simple Signing Envelope)
  - Champ `policy` avec `policy_id` + `policy_hash`
  - Cohérence temporelle précisée (delta_seconds, threshold_hours)
  - Anti-replay enrichi (created_at, ttl_seconds)

- ✅ **IDENTITY_POLICY_v0.md** (v0.1.0): Politique de mapping identité email ↔ certificat
  - Enforcement modes: warn / strict
  - Tolérances: exact / domain / alias
  - Whitelist issuers/domains
  - Alias management avec signature admin

- ✅ **KPI_POC.md** (v0.1.0): KPIs et critères de succès du PoC
  - Interopérabilité: ≥95% (Gmail, Outlook, Postfix)
  - Performance: <50KB overhead, <150ms vérification
  - Fiabilité: ≥90% confirmation OTS sous 48h
  - Sécurité: 100% détection tampering

- ✅ **TEST_VECTORS_v0.md** (v0.1.0): 7 vecteurs de test avec SHA-256 attendus
  - TV1-TV5: Messages avec résultats calculés
  - TV6-TV7: Cas edge (HTML-only, footer MTA)

**Phase 1: Implémentation Core**

- **gwyl_mail/canonical.py** (122 lignes): Canonicalisation DKIM-inspired
  - Headers: RFC 2047 decode, RFC 5322 unfold, Unicode NFC
  - Body: CRLF→LF, trailing space trim, Unicode NFC
  - Attachments: SHA-256 hash, sorted
  - Function `canonicalize()`, `compute_hash()`
  - Class `GWylCanonical` with static method `hash()`

- **gwyl_mail/sigstore_timestamp.py** (158 lignes): Sigstore timestamping
  - Function `sign_and_timestamp()`: Sign blob with cosign
  - Generates Sigstore bundle (Rekor transparency log)
  - Graceful fallback if cosign unavailable
  - Returns `SigstoreProof` dataclass

- **gwyl_mail/ots_manager.py** (158 lignes): OpenTimestamps manager
  - Class `OTSManager`: Submit, verify, upgrade
  - Status tracking: PENDING, CONFIRMED, FAILED
  - Bitcoin block height extraction
  - Graceful fallback if `ots` CLI unavailable

- **gwyl_mail/dual_proof.py** (125 lignes): Dual proof orchestration
  - Function `create_proof()`: Generate complete proof JSON
  - Combines canonical hash + Sigstore + OTS
  - Validates against JSON Schema (gwyl_mail/schemas/proof-v0.2.0.json)
  - Computes `proof_canonical_digest`

- **gwyl_mail/validation.py** (~150 lignes): JSON Schema validation
  - Class `ProofValidator`: Strict schema validation
  - Schema: proof-v0.2.0.json (comprehensive)
  - Returns `ValidationResult` with detailed errors

- **gwyl_mail/cli.py** (300 lignes): Command-line interface
  - Commands:
    - `canonical-hash <eml>`: Compute canonical hash
    - `create-proof <eml> --identity <email>`: Create proof
    - `verify --eml <eml> --proof <json>`: Verify proof
    - `upgrade-ots <proof>`: Upgrade OTS proof
  - Audit logging: `logs/verification_audit.jsonl`
  - Path safety validation
  - Subprocess timeout protection

- **gwyl_mail/schemas/proof-v0.2.0.json**: JSON Schema for proof validation

#### Tests

- **tests/test_canonical.py** (10 tests): Canonicalisation
  - Simple message (plain text)
  - Encoding: UTF-8, Latin-1, ASCII
  - Unicode normalization (NFC)
  - Header folding/unfolding
  - Attachments ordering
  - Empty message edge case

- **tests/test_vectors.py** (5 tests): RFC compliance
  - Validates against TEST_VECTORS_v0.md
  - Ensures canonical hash reproducibility

#### Infrastructure projet
- Structure de projet Python moderne (`pyproject.toml`)
- Configuration développement (Makefile, .gitignore)
- Documentation complète (README.md)
- Licence GPL-3.0
- Contributeurs reconnus (CONTRIBUTORS.md)
- Integrity system: `Temporary_Integrity/` (baseline verification, Merkle tree)

#### Résultat
- **10/10 tests passing** (Sprint 1)
- Canonicalisation validée RFC-compliant
- Sigstore + OTS integration fonctionnelle
- CLI opérationnelle pour workflows de base

---

## Contexte

**Origine**: Specs développées dans le cadre du projet GWyl_Integrity, puis extraites vers projet dédié GWyl_Mail.

**Contributions**:
- **Zack**: Vision et direction projet
- **Claude (Anthropic)**: Rédaction specs, implémentation, tests, documentation
- **ChatGPT (OpenAI)**: Revue critique et recommandations architecturales
  - Sprint 0: Identification canonicalisation comme priorité #1
  - Sprint 0: Simplification architecture (élimination dépendance Roughtime)
  - Sprint 0: Recommandations DSSE, JCS, policy_hash
  - Sprint 3: Critical security issues (Sigstore identity, OTS timestamp)
  - Sprint 4: Code quality recommendations (type hints, temp files, cleanup)

---

## À venir

### Sprint 5: Production Readiness (optional)

#### Prévu
- DSSE signature for proof JSON (prevents metadata tampering)
- Relaxed canonicalization profile (handle MTA transformations)
- Performance benchmarks (KPI validation)
- Integration tests (Gmail, Outlook, Postfix)
- Documentation updates (README, examples)

#### Phase 3: Pilote
- Déploiement pilote (10 utilisateurs, 1 mois)
- Monitoring & métriques
- Feedback & ajustements

---

**Format**: [Unreleased] | [X.Y.Z] - AAAA-MM-JJ
**Types**: Ajouté | Modifié | Déprécié | Supprimé | Corrigé | Sécurité
