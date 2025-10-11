# Changelog - GWyl Mail

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

---

## [0.1.0] - 2025-01-11

### Ajouté

#### Phase 0: Spécifications
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

#### Infrastructure projet
- Structure de projet Python moderne (pyproject.toml)
- Configuration développement (Makefile, .gitignore)
- Documentation complète (README.md)
- Licence GPL-3.0
- Contributeurs reconnus (CONTRIBUTORS.md)

### Contexte

**Origine**: Specs développées dans le cadre du projet GWyl_Integrity, puis extraites vers projet dédié GWyl_Mail.

**Contributions**:
- **Zack**: Vision et direction projet
- **Claude (Anthropic)**: Rédaction specs et implémentation
- **ChatGPT (OpenAI)**: Revue critique et recommandations architecturales clés
  - Identification canonicalisation comme priorité #1
  - Simplification architecture (élimination dépendance Roughtime)
  - Recommandations DSSE, JCS, policy_hash

### À venir

#### Phase 1: Implémentation Core
- ⏳ Module canonicalisation (gwyl_mail/canonical.py)
- ⏳ Module Sigstore timestamp (gwyl_mail/sigstore_timestamp.py)
- ⏳ Module OTS manager (gwyl_mail/ots_manager.py)
- ⏳ Module dual proof (gwyl_mail/dual_proof.py)
- ⏳ Module identity policy (gwyl_mail/identity_policy.py)

#### Phase 2: CLI & Tests
- ⏳ CLI send/verify
- ⏳ Tests unitaires
- ⏳ Tests d'intégration (Gmail, Outlook, Postfix)
- ⏳ Validation KPIs

#### Phase 3: Pilote
- ⏳ Déploiement pilote (10 utilisateurs, 1 mois)
- ⏳ Monitoring & métriques
- ⏳ Feedback & ajustements

---

## [Unreleased]

### En développement
- Module canonicalisation
- Module Sigstore timestamp
- Module OTS manager

---

**Format**: [Unreleased] | [X.Y.Z] - AAAA-MM-JJ
**Types**: Ajouté | Modifié | Déprécié | Supprimé | Corrigé | Sécurité
