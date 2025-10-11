# 🔗 Git Integration - Guide Complet

**Protection automatique et continue de vos commits avec dual anchoring**

---

## 📋 Table des matières

1. [Vue d'ensemble](#-vue-densemble)
2. [Installation rapide](#-installation-rapide)
3. [Architecture](#-architecture)
4. [Workflows](#-workflows)
5. [GitLab vs GitHub](#-gitlab-vs-github)
6. [Scénarios de sécurité](#-scénarios-de-sécurité)
7. [Migration](#-migration)
8. [FAQ](#-faq)

---

## 🎯 Vue d'ensemble

### Le problème

Avec le système actuel :
- ✅ Protection locale excellente (Sigstore + OTS)
- ❌ Pas de lien avec Git
- ❌ Preuves locales uniquement (perte si machine compromise)
- ❌ Pas de vérification remote
- ❌ Risque : commit compromis après push

### La solution : Git Integration

```
┌──────────────────────────────────────────────────────┐
│          GIT + DUAL ANCHORING                        │
├──────────────────────────────────────────────────────┤
│                                                      │
│  LOCAL                    REMOTE                    │
│  ┌────────────┐          ┌────────────┐            │
│  │ Commit     │          │ Commit     │            │
│  │ + Metadata │  ──────► │ + Metadata │            │
│  │            │   push   │            │            │
│  └────────────┘          └────────────┘            │
│       ↓                        ↓                    │
│  ┌────────────┐          ┌────────────┐            │
│  │ .integrity/│          │ .integrity/│            │
│  │ • Sigstore │  ──────► │ • Sigstore │            │
│  │ • OTS      │   sync   │ • OTS      │            │
│  └────────────┘          └────────────┘            │
│       ↓                        ↓                    │
│  VERIFICATION            VERIFICATION               │
│  local ↔ commit          remote ↔ commit            │
│                                                      │
└──────────────────────────────────────────────────────┘

Résultat : Protection TOTALE (local + remote)
```

### Avantages

| Aspect | Avant | Après (Git Integration) |
|--------|-------|------------------------|
| **Protection commits** | ❌ Manuel | ✅ Automatique (hooks) |
| **Backup preuves** | ❌ Local seulement | ✅ Versionné + Remote |
| **Vérification remote** | ❌ Impossible | ✅ Bidirectionnelle |
| **Identité** | ⚠️ Sigstore ≠ Git | ✅ Liées (metadata) |
| **Force-push attack** | ❌ Non détecté | ✅ Détection immédiate |
| **Audit trail** | ⚠️ Partiel | ✅ Complet (Git + Rekor) |

---

## ⚡ Installation rapide

### Prérequis

```bash
# Système de base déjà installé
ls unified_integrity.py
ls unified_integrity_sigstore.py

# Git initialisé
git --version

# Sigstore installé
cosign version
```

### Setup en 3 étapes

```bash
# 1. Copier les nouveaux fichiers
cp unified_integrity_git.py .
cp Makefile.git .

# 2. Initialiser Git integration
make git-init

# Sortie:
# ✅ Initialized .integrity/
# ✅ Installed: pre-commit
# ✅ Installed: post-commit  
# ✅ Installed: pre-push
# ✅ GitLab detected: https://gitlab.com/user/repo

# 3. Commit initial
git add .integrity/
git commit -m "Add integrity system"

# → Hook activé automatiquement !
# 🔐 Post-commit: Creating dual anchor...
# ✅ Dual anchor created for commit abc123
```

**C'est tout !** Les prochains commits seront automatiquement protégés.

---

## 🏗️ Architecture

### Structure de fichiers

```
project/
├── .git/
│   └── hooks/                    # Hooks automatiques
│       ├── pre-commit            # Vérification baseline
│       ├── post-commit           # Dual anchor
│       └── pre-push              # Vérification avant push
│
├── .integrity/                   # NOUVEAU : Versionné dans Git
│   ├── config.yml               # Configuration
│   ├── index.jsonl              # Index searchable
│   └── proofs/
│       ├── commits/             # Preuves par commit
│       │   ├── abc123def.json   # Commit abc123...
│       │   └── xyz789ghi.json   # Commit xyz789...
│       └── sessions/            # Sessions locales (backup)
│
├── logs/                        # Reste inchangé (local)
│   ├── baseline.json
│   ├── session_active.json
│   ├── anchors/
│   └── proofs/
│       ├── ots/                 # OTS local
│       ├── sigstore/            # Sigstore local
│       └── dual_receipts.jsonl  # Receipts local
│
├── unified_integrity.py          # Système de base
├── unified_integrity_sigstore.py # Dual anchoring
├── unified_integrity_git.py      # NOUVEAU : Git integration
├── Makefile
├── Makefile.sigstore
└── Makefile.git                  # NOUVEAU
```

### Flux de données

#### 1. Commit normal

```bash
git commit -m "Add feature"

# ┌─────────────────────────────────────┐
# │  PRE-COMMIT HOOK                    │
# ├─────────────────────────────────────┤
# │  • Vérifie baseline                 │
# │  • Détecte fichiers modifiés        │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  GIT COMMIT                         │
# ├─────────────────────────────────────┤
# │  • Crée commit                      │
# │  • SHA: abc123...                   │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  POST-COMMIT HOOK                   │
# ├─────────────────────────────────────┤
# │  • Calcule Merkle root              │
# │  • Dual anchor (Sigstore + OTS)     │
# │  • Sauvegarde dans .integrity/      │
# │  • Ajoute metadata (trailers)       │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  RÉSULTAT                           │
# ├─────────────────────────────────────┤
# │  Commit: abc123...                  │
# │  Metadata:                          │
# │    Integrity-Proof: sigstore+ots    │
# │    Integrity-Merkle: xyz789...      │
# │    Integrity-Rekor: 12345678        │
# │  Proof: .integrity/proofs/commits/  │
# │         abc123def.json              │
# └─────────────────────────────────────┘
```

#### 2. Push avec vérification

```bash
make git-push-with-proofs

# ┌─────────────────────────────────────┐
# │  VÉRIFICATION LOCALE                │
# ├─────────────────────────────────────┤
# │  • Verify commit actuel             │
# │  • Check Sigstore signature         │
# │  • Check baseline coherence         │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  SYNC PREUVES                       │
# ├─────────────────────────────────────┤
# │  • Add .integrity/ si modifié       │
# │  • Amend commit si nécessaire       │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  PRE-PUSH HOOK                      │
# ├─────────────────────────────────────┤
# │  • Vérifie tous commits à pusher    │
# │  • Check que tous ont des preuves   │
# └─────────────────────────────────────┘
#              ↓
# ┌─────────────────────────────────────┐
# │  GIT PUSH                           │
# ├─────────────────────────────────────┤
# │  • Push commits                     │
# │  • Push .integrity/                 │
# └─────────────────────────────────────┘
```

### Format du proof commit

```json
{
  "commit_sha": "abc123def456...",
  "commit_message": "Add new feature",
  "commit_author": "John Doe <john@example.com>",
  "commit_date": "2025-01-10T14:30:00Z",
  "dual_proof": {
    "timestamp": "2025-01-10T14:30:05Z",
    "merkle_root": "xyz789...",
    "files": ["cosmic_laws/agent.py"],
    "sigstore": {
      "timestamp": "2025-01-10T14:30:05Z",
      "rekor_uuid": "abc...",
      "rekor_url": "https://rekor.sigstore.dev/...",
      "rekor_log_index": 12345678,
      "cert_path": "logs/proofs/sigstore/certificates/...",
      "cert_subject": "john@example.com",
      "cert_issuer": "https://accounts.google.com",
      "sig_path": "logs/proofs/sigstore/signatures/...",
      "hash_signed": "xyz789...",
      "files": ["cosmic_laws/agent.py"]
    },
    "opentimestamps": {
      "proof_path": "logs/proofs/ots/commit_abc123.ots",
      "status": "pending",
      "confirmed_at": null,
      "bitcoin_block": null
    }
  },
  "files_modified": ["cosmic_laws/agent.py"]
}
```

---

## 📖 Workflows

### Workflow 1 : Premier commit avec protection

```bash
# État initial
ls .integrity/
# Pas de .integrity/

# Initialisation
make git-init

# Développement
vim README.md
git add README.md
git commit -m "Update README"

# → Automatique :
# 🔍 Pre-commit: Verifying baseline...
# 🔐 Post-commit: Creating dual anchor...
# ✅ Sigstore signature created
#    Identity: john@example.com
# ⏳ OTS proof: Pending
# ✅ Dual anchor created for commit abc123

# Vérification immédiate
make git-verify-commit

# Sortie:
# 🔍 Verifying commit abc123...
# 
# Commit: abc123def456...
# Local state: valid
# Proof status: protected
# 
# ✅ Commit integrity VERIFIED

# Voir la preuve
cat .integrity/proofs/commits/abc123def*.json | jq
```

### Workflow 2 : Collaboration (pull + verify)

```bash
# Collègue pousse un commit
# (sur GitLab ou GitHub)

# Vous récupérez
make git-pull-verify

# Sortie:
# 📥 Pull avec vérification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# 1️⃣  Pull...
# Updating abc123..xyz789
# Fast-forward
#  cosmic_laws/agent.py | 10 +++++++
#  1 file changed, 10 insertions(+)
# 
# 2️⃣  Vérification des nouveaux commits...
# ✅ xyz789ghi
# ✅ def456abc
# 
# ✅ Pull vérifié
```

### Workflow 3 : Détection force-push malveillant

```bash
# Scénario : Attaquant a accès au remote et force-push

# Vous exécutez
make git-verify-remote

# Sortie:
# 🚨 INTEGRITY VIOLATION DETECTED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# Remote HEAD: xyz789... (NO PROOF)
# Expected: abc123... (Sigstore ✅ + OTS ✅)
# 
# Timeline reconstruction:
#   10:00 : Original commit abc123 (Sigstore verified)
#   12:00 : Force-push to xyz789 (no signature)
# 
# 🔐 Rekor public log proves:
#   - abc123 signed by john@example.com at 10:00
#   - xyz789 has NO entry in Rekor
# 
# ⚠️  RECOMMENDATION:
#   1. git reset --hard abc123
#   2. Investigate xyz789 (likely malicious)
#   3. Contact admin about force-push

# Vous restaurez l'état sûr
git reset --hard abc123
```

### Workflow 4 : Migration d'un projet existant

```bash
# Projet Git existant (142 commits)

# 1. Initialiser integrity
make git-init

# 2. Option A : Protéger uniquement les futurs commits
# → Rien de plus à faire, hooks activés

# 3. Option B : Ancrage rétroactif (optionnel)
make git-retroactive-anchor

# Sortie:
# 🔄 Ancrage rétroactif des commits
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# ⚠️  Cette opération peut prendre du temps
# Continuer? (y/n) y
# 
# Processing abc123...
# ✅ Dual anchor created
# Processing def456...
# ✅ Dual anchor created
# [...]
# 
# ✅ 142 commits ancrés rétroactivement

# Vérifier tout
make git-verify-all
```

---

## 🔀 GitLab vs GitHub

### Détection automatique

```bash
make git-detect-provider

# GitLab:
# ✅ GitLab détecté: https://gitlab.com/user/repo
#    Config recommandée: CI/CD GitLab

# GitHub:
# ✅ GitHub détecté: https://github.com/user/repo
#    Config recommandée: GitHub Actions
```

### Différences d'implémentation

| Aspect | GitLab | GitHub |
|--------|--------|--------|
| **Hooks** | Identiques | Identiques |
| **Preuves (.integrity/)** | Identiques | Identiques |
| **CI/CD** | `.gitlab-ci.yml` | `.github/workflows/` |
| **Protected branches** | Settings → Protected | Settings → Branches |
| **Webhooks** | Settings → Webhooks | Settings → Webhooks |

### GitLab CI/CD (recommandé)

```yaml
# .gitlab-ci.yml

stages:
  - verify

verify_integrity:
  stage: verify
  image: python:3.11
  before_script:
    - pip install opentimestamps-client
    - curl -sSfL https://github.com/sigstore/cosign/releases/download/v2.2.0/cosign-linux-amd64 -o /usr/local/bin/cosign
    - chmod +x /usr/local/bin/cosign
  script:
    # Vérifier tous les commits du push
    - make git-verify-all
    # Vérifier commit actuel
    - make git-verify-commit
  only:
    - branches
  except:
    - main  # Main protégée séparément

verify_main:
  stage: verify
  extends: verify_integrity
  script:
    - make git-verify-all
    - make git-verify-remote
  only:
    - main
  when: manual  # Vérification manuelle sur main
```

### GitHub Actions (recommandé)

```yaml
# .github/workflows/integrity.yml

name: Integrity Verification

on:
  push:
    branches: [ "**" ]
  pull_request:
    branches: [ main ]

jobs:
  verify:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0  # Full history
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install opentimestamps-client
        curl -sSfL https://github.com/sigstore/cosign/releases/download/v2.2.0/cosign-linux-amd64 -o /usr/local/bin/cosign
        chmod +x /usr/local/bin/cosign
    
    - name: Verify commits
      run: |
        make git-verify-all
        make git-verify-commit
    
    - name: Verify remote (main only)
      if: github.ref == 'refs/heads/main'
      run: make git-verify-remote
```

### Configuration branches protégées

#### GitLab

```
Settings → Repository → Protected Branches
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Branch: main
Allowed to merge: Maintainers
Allowed to push: No one
Require approval: 1
CI must pass: ✅ (verify_integrity)
```

#### GitHub

```
Settings → Branches → Branch protection rules
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Branch: main
☑ Require pull request reviews (1)
☑ Require status checks to pass
  - integrity-verification
☑ Require branches to be up to date
```

---

## 🔐 Scénarios de sécurité

### Scénario 1 : Développeur compromise

**Situation** : L'ordinateur d'un dev est compromis

**Sans Git Integration** ❌
```
1. Attaquant modifie code
2. Commit local (pas de vérification)
3. Push vers remote
4. Code malveillant déployé
5. Détection : trop tard
```

**Avec Git Integration** ✅
```
1. Attaquant modifie code
2. git commit → Hook pre-commit
   → Baseline verification: ❌ FAIL
   → Commit bloqué
   
   OU (si baseline bypassed)
   
3. git commit → Hook post-commit
   → Dual anchor créé
   → Sigstore: Identity = attaquant@malicious.com
   → OTS: Pending
   
4. git push → Hook pre-push
   → Vérification: ❌ Identity mismatch
   → Push bloqué
   
5. CI/CD: make git-verify-commit
   → Sigstore cert_subject ≠ expected dev
   → 🚨 ALERT: Unauthorized commit
```

### Scénario 2 : Force-push malveillant

**Situation** : Attaquant a accès admin au remote

**Sans Git Integration** ❌
```
1. Attaquant force-push malicious code
2. Historique réécrit
3. Détection : impossible (Git history altered)
```

**Avec Git Integration** ✅
```
1. Attaquant force-push
2. make git-verify-remote
   → Compare remote HEAD vs local proofs
   → Remote: xyz789 (NO PROOF in .integrity/)
   → Local: abc123 (Sigstore ✅ + OTS ✅)
   
3. Reconstruction timeline via Rekor
   → abc123 signed at 10:00 by dev@company.com
   → xyz789 NO Rekor entry
   
4. 🚨 ALERT: Force-push detected
   → Restore: git reset --hard abc123
   → Investigate: xyz789 (malicious)
```

### Scénario 3 : Insider malveillant

**Situation** : Employé mécontent insère backdoor

**Sans Git Integration** ❌
```
1. Insider commit backdoor
2. Code review bypass (social engineering)
3. Merge to main
4. Détection : audit de code (aléatoire)
```

**Avec Git Integration** ✅
```
1. Insider commit
   → Sigstore cert_subject: insider@company.com
   → Rekor log: PUBLIC, AUDITABLE
   
2. CI/CD: make git-verify-commit
   → ✅ Signature valid
   → ⚠️  Log unusual patterns:
      • Commit time: 2 AM (inhabituel)
      • Files: crypto/auth.py (sensible)
      • Size: +500 lines (gros changement)
   
3. Automatic review trigger
   → Senior dev notified
   → Code review approfondi
   
4. Post-mortem forensique
   → Rekor log PROVE:
     • WHO: insider@company.com
     • WHEN: 2025-01-10T02:14:32Z
     • WHAT: crypto/auth.py modified
   → Non-répudiation garantie
```

---

## 🔄 Migration

### Depuis système OTS-only

```bash
# État actuel : OTS seul (logs/anchors/)

# 1. Installer Git integration
make git-init

# 2. Migrer receipts existants vers .integrity/
make migrate-to-dual  # Du Makefile.sigstore

# 3. (Optionnel) Ancrage rétroactif
make git-retroactive-anchor

# 4. Futurs commits : dual automatique
git commit -m "New feature"
# → Hooks activés automatiquement
```

### Depuis système manuel

```bash
# État actuel : Signatures manuelles sporadiques

# 1. Setup complet
make git-init
git add .integrity/
git commit -m "Add integrity system"

# 2. Tous les futurs commits protégés
# (Aucune action manuelle requise)
```

---

## ❓ FAQ

### Q1 : Que se passe-t-il si je commit sans .integrity/ ?

**R** : Le hook post-commit crée automatiquement la preuve et suggère :

```bash
git commit -m "Feature"

# → Post-commit hook:
# ✅ Dual anchor created
# 
# 💡 Add proofs to Git:
#    git add .integrity/
#    git commit --amend --no-edit

# Vous exécutez:
make git-amend-proofs
# → Preuves ajoutées au commit automatiquement
```

### Q2 : .integrity/ doit-il être versionné ?

**R** : **OUI !** C'est le cœur de la protection remote.

```
.gitignore:
logs/           # ✅ Exclure (preuves locales)
.integrity/     # ❌ NE PAS exclure (preuves versionnées)
```

### Q3 : Compatibilité avec Git LFS ?

**R** : Oui, compatible. Les fichiers LFS sont hashés normalement.

### Q4 : Performance avec gros repos ?

**R** : 

| Taille repo | Hook overhead | Recommandation |
|-------------|---------------|----------------|
| < 100 commits | ~0.5s | Aucun problème |
| 100-1000 commits | ~2s | OK |
| > 1000 commits | ~5-10s | Ancrage sélectif |

**Optimisation** :
```yaml
# .integrity/config.yml
auto_anchor: true
anchor_strategy: selective  # Seulement main + tags
skip_ots_on_branches: true  # OTS seulement sur main
```

### Q5 : Hooks fonctionnent sur tous les systèmes ?

**R** : Oui (Python cross-platform)

```bash
# Linux/macOS
make git-init  # → Hooks Python

# Windows
make git-init  # → Hooks Python (via Git Bash)
```

### Q6 : Différence avec GPG commit signing ?

**R** :

| | GPG signing | Integrity System |
|-|-------------|------------------|
| **Identité** | Clé GPG (vous gérez) | OIDC (Google/GitHub) |
| **Preuve** | Signature commit | Dual (Sigstore + OTS) |
| **Immuabilité** | ❌ (clé révocable) | ✅ (Bitcoin + Rekor) |
| **Audit** | Local seulement | Public (Rekor) |
| **Intégrité fichiers** | ❌ | ✅ (Merkle tree) |

**Complémentaires !** Vous pouvez utiliser GPG signing + Integrity System.

### Q7 : Coût de stockage .integrity/ ?

**R** : Très léger.

```bash
# Exemple : 100 commits
du -sh .integrity/

# Résultat :
# 2.3 MB    # JSON proofs
# 1.8 MB    # Sigstore certs
# 500 KB    # OTS proofs
# ━━━━━━━━
# 4.6 MB total

# Pour 1000 commits : ~46 MB
# → Négligeable comparé au code source
```

---

## 📊 Résumé des bénéfices

| Bénéfice | Avant | Après |
|----------|-------|-------|
| **Protection commits** | ❌ Manuel | ✅ Auto (hooks) |
| **Vérification immédiate** | ⏳ 1-24h (OTS) | ✅ 0-5s (Sigstore) |
| **Backup preuves** | ❌ Local | ✅ Remote (Git) |
| **Détection attaques** | ⚠️ Partielle | ✅ Complète |
| **Audit trail** | ⚠️ Local | ✅ Git + Rekor |
| **Collaboration** | ❌ Non sécurisée | ✅ Vérifiée |
| **Force-push protection** | ❌ | ✅ |
| **Identité prouvée** | ⚠️ OIDC seul | ✅ OIDC + Git |
| **Forensique** | ⚠️ Timeline | ✅ Timeline + Identity + Git history |

---

## 🚀 Prochaines étapes

1. **Installer** : `make git-init`
2. **Commiter** : `git commit -m "First protected commit"`
3. **Vérifier** : `make git-verify-commit`
4. **Collaborer** : `make git-push-with-proofs`
5. **Profiter** : Protection continue automatique !

---

**🔒 Git + Sigstore + OTS = Protection totale de votre code 🔒**