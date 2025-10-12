# RFC — Flux d’Intégrité (Temporary_Integrity)

Statut: Draft
Portée: Répertoire `Temporary_Integrity/` uniquement
Auteur: GWyl Team

## 1. Objectif
Définir, documenter et stabiliser le flux de vérification/commit d’intégrité utilisé localement durant le développement. L’objectif est d’obtenir un enchaînement reproductible, auditable et robuste aux cas réels (fichiers dynamiques, chemins avec espaces, hooks git, etc.).

## 2. Résumé du flux
1) Génération d’une baseline « originale » non committée (`SECURITY_INTEGRITY_BASELINE.sha256`).
2) Comparaison avec la baseline « snapshot » committée précédente (`*.committed`) pour valider la chaîne de confiance (fichiers inchangés = hachés identiques).
3) Création de la nouvelle baseline « snapshot » committée (`*.committed`) et contrôle byte‑à‑byte contre l’originale.
4) Commit Git (en excluant l’originale) puis vérification post‑commit (outil Python local).
5) Commit d’un fichier meta qui chaîne la clé SHA256 du snapshot committé au commit courant (`*.meta`).
6) (Optionnel) Upgrade des preuves OTS locales.

## 3. Détails d’implémentation
### 3.1 Génération de baseline
- Commande: `find … -print0 | sort -z | xargs -0 sha256sum > SECURITY_INTEGRITY_BASELINE.sha256`
- Fichiers suivis: `*.py, *.md, *.yml, *.yaml, *.json, *.toml, *.sh, *.txt`
- Exclusions dossier: `./.git/*, ./.venv/*, ./htmlcov/*, ./__pycache__/*, ./.pytest_cache/*, ./.gwyl_mail/*, ./logs/*, ./.claude/*`
- Format: lignes « `sha256  chemin/relatif` » (double espace entre hash et chemin)
- Raison: NUL‑séparé pour gérer chemins avec espaces/caractères spéciaux, tri stable, format déterministe.

### 3.2 Chaîne de confiance (comparaison)
- Objectif: vérifier que les fichiers « inchangés » entre l’ancienne baseline committée et l’actuelle ont exactement le même hash qu’historiquement.
- Méthode:
  - Construire l’intersection des listes de chemins (via `comm -12` sur la 3e colonne = chemins).
  - Pour chaque chemin, extraire le hash précédent et le hash courant (matching exact fin de ligne via `awk`), comparer.
  - Si un fichier est « inchangé » mais que le hash diffère → CHAIN BROKEN → abort.
- Robustesse:
  - Évite les sous‑shells (les boucles utilisent des process substitutions avec redirection d’entrée) pour préserver l’état des variables.
  - Matching fin de ligne (EOL) par `awk` au lieu de `grep` pour supporter espaces et cas limites.

### 3.3 Snapshot committé + contrôle
- `cp SECURITY_INTEGRITY_BASELINE.sha256 SECURITY_INTEGRITY_BASELINE.sha256.committed`
- `cmp -s` pour s’assurer que la copie est byte‑à‑byte identique à l’originale.
- `git add SECURITY_INTEGRITY_BASELINE.sha256.committed` et `git add -A ':(exclude)SECURITY_INTEGRITY_BASELINE.sha256'` pour exclure l’originale du commit.

### 3.4 Meta de chaînage
- Fichier: `SECURITY_INTEGRITY_BASELINE.sha256.meta`
- Contenu (exemple):
  - `baseline_committed_sha256=<SHA256 du snapshot>`
  - `baseline_committed_file=SECURITY_INTEGRITY_BASELINE.sha256.committed`
  - `baseline_committed_lines=<N>`
  - `commit_hash=<HEAD court>`
  - `committed_at=<ISO UTC>`
- Commit séparé: « chore(integrity): record committed baseline hash (…) »
- Raison: éviter l’auto‑référence (le SHA du snapshot ne doit pas dépendre d’une valeur qu’il contient).

### 3.5 Hooks Git locaux
- pre‑commit (`.git/hooks/pre-commit`):
  - Exécute `python Temporary_Integrity/unified_integrity.py check`
  - Bloque le commit si mismatch/missing (détails enregistrés dans `logs/mismatch.jsonl`).
- pre‑push (`.git/hooks/pre-push`):
  - Tente `ots upgrade` sur `logs/anchors/ots/*.ots` et `.gwyl_mail/proofs/ots/*.ots`.
  - Non bloquant (best effort).
- Installation via Makefile (cf. §3.6).

### 3.6 Makefile (cibles pratiques)
- `make integrity-install` → installe pre‑commit + pre‑push.
- `make integrity-install-pre-commit` → installe uniquement pre‑commit.
- `make integrity-install-pre-push` → installe uniquement pre‑push.
- `make integrity-baseline` → régénère baseline + snapshot + meta (sans commit).
- `make integrity-commit MSG="…"` → lance le flux complet de commit avec intégrité.

## 4. Journalisation & erreurs
- OK / MISMATCH / MISSING affichés par l’outil Python.
- `logs/mismatch.jsonl`: log JSON canonique des anomalies (timestamp, user, type, path, expected/actual).
- En cas de « CHAIN BROKEN » (fichier inchangé dont le hash ne matche pas l’historique): abort immédiat.

## 5. Sécurité & design
- Outil local: le hook utilise `Temporary_Integrity/unified_integrity.py` pour éviter les dérives liées à un chemin externe mutable.
- Baseline originale non committée: évite les boucles d’auto‑référence et limite le bruit des diffs.
- Exclusions explicites: évite de « sucer » des fichiers volatiles (caches, .claude/) dans la baseline.
- Robustesse parsing: matching EOL via `awk`; NUL‑séparé côté `find/xargs`.

## 6. Limites connues & améliorations futures
- Harmonisation exclusions: s’assurer que `commit_with_integrity.sh` et `unified_integrity.py` partagent la même liste d’exclusions.
- DSSE/OTS pour baseline: signer le snapshot et/ou ancrer la racine Merkle dans OTS.
- Index JSON: publier un index JSON de la baseline (fichier → sha) pour inspection out‑of‑band.
- CI: job de vérification d’intégrité sur la branche principale.
- UX: rapport des différences plus synthétique (top N par type), option de bypass ponctuel documentée (`--no-verify`).
- Perf: paralléliser le hashing si besoin (GNU parallel), tout en gardant l’ordre déterministe.

## 7. Décisions & alternatives
- Local vs externe: local retenu (prédictible, auditable, reproductible). Externe possible plus tard si versionné et signé.
- 1 commit vs 2 commits: 2 commits retenus (snapshot puis meta) pour éviter l’auto‑référence.
- `grep` vs `awk` pour matching: `awk` retenu (fin de ligne exacte, robustesse espaces/symboles).

## 8. Références
- Script: `Temporary_Integrity/commit_with_integrity.sh`
- Outil: `Temporary_Integrity/unified_integrity.py`
- Logs: `logs/mismatch.jsonl`
- Makefile: cibles `integrity-*`

*** Fin du document ***
