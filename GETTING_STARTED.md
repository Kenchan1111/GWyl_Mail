# Getting Started - GWyl Mail

Guide rapide pour démarrer le développement sur GWyl Mail.

---

## 📦 Installation

### Prérequis

- Python 3.9+
- pip
- virtualenv (recommandé)

### Setup environnement

```bash
# Cloner le repo
cd /home/zack/GWyl_Mail

# Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Installer dépendances dev
make dev

# Vérifier installation
python -c "import gwyl_mail; print(gwyl_mail.__version__)"
# → 0.1.0
```

---

## 🏗️ Structure du Projet

```
GWyl_Mail/
├── docs/
│   └── specs/              # Spécifications techniques
│       ├── CANONICALIZATION_v0.md
│       ├── PROOF_SCHEMA_v0.md
│       ├── IDENTITY_POLICY_v0.md
│       ├── KPI_POC.md
│       └── TEST_VECTORS_v0.md
│
├── gwyl_mail/              # Code source
│   ├── __init__.py
│   ├── canonical.py        # ⏳ À implémenter
│   ├── sigstore_timestamp.py
│   ├── ots_manager.py
│   ├── dual_proof.py
│   ├── identity_policy.py
│   └── cli.py
│
├── tests/                  # Tests unitaires
│   ├── test_canonical.py   # ⏳ À créer
│   ├── test_sigstore.py
│   ├── test_ots.py
│   └── test_dual_proof.py
│
├── examples/               # Exemples d'usage
│
├── .gwyl_mail/            # Configuration locale
│   ├── identity_policy.yml
│   └── proofs/
│
├── pyproject.toml         # Configuration Python
├── Makefile               # Commandes développement
└── README.md
```

---

## 🚀 Commandes Développement

### Makefile

```bash
make help        # Afficher aide
make install     # Installer production
make dev         # Installer développement
make test        # Lancer tests
make lint        # Vérifier code (ruff, mypy)
make format      # Formatter code (black)
make clean       # Nettoyer artifacts
```

### Tests

```bash
# Tous les tests
pytest

# Test spécifique
pytest tests/test_canonical.py -v

# Avec coverage
pytest --cov=gwyl_mail --cov-report=html
```

---

## 📚 Lire les Spécifications

### Ordre de lecture recommandé

1. **README.md**: Vue d'ensemble du projet
2. **PROJECT_STATUS.md**: État actuel et roadmap
3. **docs/specs/CANONICALIZATION_v0.md**: Algorithme de base (PRIORITÉ 1)
4. **docs/specs/PROOF_SCHEMA_v0.md**: Structure des preuves
5. **docs/specs/IDENTITY_POLICY_v0.md**: Gestion identité
6. **docs/specs/TEST_VECTORS_v0.md**: Vecteurs de test
7. **docs/specs/KPI_POC.md**: Critères de succès

### Concepts clés à comprendre

**Canonicalisation**:
- DKIM-inspired normalization
- 5 headers canoniques: from, to, subject, date, message-id
- Normalisation corps: CRLF→LF, trim whitespace
- Attachments: hash SHA-256, tri NFC
- Profils: strict (v0) vs relaxed (v1)

**Dual Timestamping**:
- Sigstore: Timestamp immédiat (Rekor), trust MEDIUM
- OpenTimestamps: Ancrage Bitcoin différé, trust HIGH
- Cohérence: |rekor_ts - ots_ts| < 24h

**Identity Policy**:
- Mapping: From (email) ↔ cert_subject (Sigstore)
- Modes: warn (log) → strict (reject)
- Tolérances: exact / domain / alias

---

## 🛠️ Premier Sprint: Canonicalisation

### Objectif

Implémenter et tester le module de canonicalisation selon spec v0.2.0.

### Tâches

1. **Créer `gwyl_mail/canonical.py`**:
   ```python
   class GWylCanonical:
       VERSION = "0.2.0"
       HEADERS = ['from', 'to', 'subject', 'date', 'message-id']

       @classmethod
       def canonicalize(cls, message: EmailMessage, profile: str = 'strict') -> bytes:
           """Canonise message selon profil"""
           pass  # À implémenter

       @classmethod
       def hash(cls, message: EmailMessage, profile: str = 'strict') -> str:
           """Hash SHA-256 du message canonique"""
           pass  # À implémenter
   ```

2. **Créer `tests/test_canonical.py`**:
   - Test vectors TV1-TV5
   - Edge cases (encoding, Unicode, HTML)
   - Validation SHA-256 attendus

3. **Valider contre TEST_VECTORS_v0.md**:
   ```bash
   pytest tests/test_canonical.py -v
   # Tous les tests doivent passer ✅
   ```

### Critères d'acceptation

- ✅ Classe `GWylCanonical` implémentée
- ✅ Méthodes `canonicalize()` et `hash()`
- ✅ RFC 2047 (encoded-words) décodage
- ✅ RFC 5322 (folding) unfolding
- ✅ Unicode NFC normalization
- ✅ Tous les test vectors passent
- ✅ Coverage ≥90%

---

## 📖 Ressources

### Documentation externe

- **Sigstore**: https://docs.sigstore.dev
- **OpenTimestamps**: https://opentimestamps.org
- **DKIM (RFC 6376)**: https://www.rfc-editor.org/rfc/rfc6376.html
- **JCS (RFC 8785)**: https://tools.ietf.org/html/rfc8785
- **DSSE**: https://github.com/secure-systems-lab/dsse

### Standards référencés

- RFC 2047 (Encoded-words)
- RFC 5322 (Email format)
- RFC 6376 (DKIM)
- RFC 8785 (JSON Canonicalization Scheme)
- Unicode TR15 (Normalization Forms)

---

## 🐛 Debugging & Troubleshooting

### Problèmes courants

**Import Error: No module named 'gwyl_mail'**:
```bash
# Installer en mode éditable
pip install -e .
```

**Tests échouent: SHA-256 mismatch**:
- Vérifier normalisation Unicode (NFC)
- Vérifier line endings (CRLF→LF)
- Vérifier décodage RFC 2047

**Sigstore/OTS not available**:
```bash
# Installer dépendances
pip install sigstore opentimestamps-client
```

---

## 💡 Conseils Développement

### Best Practices

1. **Lire la spec d'abord**: Comprendre l'algorithme avant de coder
2. **TDD**: Écrire tests avant implémentation (test vectors disponibles)
3. **Coverage**: Viser ≥90% de couverture
4. **Docstrings**: Documenter toutes les fonctions publiques
5. **Type hints**: Utiliser mypy pour vérification types

### Workflow Git (recommandé)

```bash
# Créer branche feature
git checkout -b feature/canonical-implementation

# Commit réguliers
git commit -m "feat(canonical): implement header canonicalization"

# Tests avant push
make test lint

# Push et PR
git push origin feature/canonical-implementation
```

---

## 🎯 Checklist Démarrage

- [ ] Python 3.9+ installé
- [ ] Environnement virtuel créé
- [ ] Dépendances dev installées (`make dev`)
- [ ] Specs lues (CANONICALIZATION_v0.md minimum)
- [ ] Structure projet comprise
- [ ] Premier test écrit (`test_canonical.py`)
- [ ] Premier module implémenté (`canonical.py`)
- [ ] Tests passent (`make test`)

---

## 📞 Support

**Questions techniques**: Voir spécifications dans `docs/specs/`
**Bugs**: Créer issue GitHub (à venir)
**Contributions**: Voir `CONTRIBUTORS.md`

---

**Bon développement! 🚀**
