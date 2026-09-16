# Getting Started - GWyl Mail

Guide de démarrage : installation, vérification de l'environnement, premiers pas.

---

## 📦 Prérequis (réels)

GWyl Mail s'appuie sur **deux binaires externes** qui ne s'installent pas via les
dépendances pip du projet. Sans eux, `create-proof` refuse de s'exécuter (ou
requiert `--allow-degraded`, garanties réduites : pas de signature, pas
d'ancrage Bitcoin).

| Outil | Rôle | Installation |
|---|---|---|
| Python ≥ 3.9 | runtime | système |
| **cosign** | signature Sigstore (DSSE) + timestamp Rekor | binaire Go — voir ci-dessous |
| **ots** | ancrage OpenTimestamps (Bitcoin) | `pip install opentimestamps-client` (fournit le binaire `ots`) |

### Installer cosign

cosign est un binaire Go distribué par Sigstore (ce n'est **pas** un paquet pip) :

```bash
# Linux amd64 — ajustez la version/ARCH à la dernière release :
curl -sSfL https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64 \
  -o ~/.local/bin/cosign && chmod +x ~/.local/bin/cosign

# ou via package manager si disponible (ex. Fedora : dnf install cosign)
cosign version
```

> Note : `pip install sigstore` installe la bibliothèque Python sigstore
> (utilisée pour l'extraction d'identité), **pas** le binaire cosign.

### Installer ots

```bash
pip install opentimestamps-client   # fournit la commande 'ots'
ots --version
```

---

## 🚀 Installation du projet

```bash
git clone https://github.com/Kenchan1111/GWyl_Mail.git
cd GWyl_Mail

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

make dev                        # pip install -e ".[dev]"
```

## 🩺 Étape 1 : vérifier l'environnement

```bash
gwyl-mail doctor
```

Vérifie cosign, ots, les paquets Python requis et (best-effort) la joignabilité
de Rekor et d'un calendrier OTS. Code retour 0 = environnement complet ;
`--json` pour une sortie machine, `--skip-network` pour l'offline.

## 🔧 Premiers pas

```bash
# 1. Hash canonique d'un email (aucun outil externe requis)
gwyl-mail canonical-hash examples/sample_plain_text.eml

# 2. Créer une preuve complète (signée DSSE + ancrage Bitcoin soumis)
#    cosign ouvrira une authentification OIDC (navigateur) au premier usage
gwyl-mail create-proof examples/sample_plain_text.eml \
    --identity vous@example.com --out .gwyl_mail/proofs/proof.json

# 3. Vérifier un email contre sa preuve (offline pour le hash)
gwyl-mail verify --eml examples/sample_plain_text.eml \
    --proof .gwyl_mail/proofs/proof.json --strict

# 4. Après ~48h : confirmer l'ancrage Bitcoin
gwyl-mail upgrade-ots .gwyl_mail/proofs/ots/hash_*.ots
```

**Sans cosign/ots** : `create-proof` échoue volontairement avec un message
explicite. Pour créer malgré tout une preuve hash-only :
`--allow-degraded` (bandeau d'avertissement, garanties réduites).

---

## 🏗️ Structure du projet

```
GWyl_Mail/
├── gwyl_mail/                 # Code source
│   ├── canonical.py           #   Canonicalisation DKIM-inspired (strict/relaxed)
│   ├── sigstore_timestamp.py  #   cosign sign-blob + bundle Rekor
│   ├── sigstore_identity.py   #   Extraction identité X.509 (SAN, issuer OIDC)
│   ├── ots_manager.py         #   Ancrage OpenTimestamps
│   ├── dsse_signer.py         #   Enveloppe DSSE (signature de la preuve)
│   ├── dual_proof.py          #   Assemblage de la preuve
│   ├── identity_policy.py     #   Politique From ↔ certificat
│   ├── validation.py          #   Validation JSON Schema
│   ├── doctor.py              #   Vérification environnement
│   └── cli.py                 #   CLI (canonical-hash, create-proof, verify,
│                              #   upgrade-ots, doctor)
├── tests/                     # 104 tests (pytest, déterministes sans outils)
├── examples/                  #   EMLs d'exemple + vérificateur standalone
├── docs/specs/                #   Spécifications normatives
├── pyproject.toml
└── Makefile
```

---

## 🛠️ Commandes développement

```bash
make help        # Aide
make dev         # Installer dépendances dev
make test        # Tests (aucun binaire externe requis)
make lint        # ruff + mypy
make format      # black
```

---

## 📚 Pour aller plus loin

### Ordre de lecture recommandé

1. **README.md** : vue d'ensemble
2. **docs/specs/CANONICALIZATION_v0.md** : algorithme de canonicalisation
3. **docs/specs/PROOF_SCHEMA_v0.md** : structure des preuves
4. **docs/specs/IDENTITY_POLICY_v0.md** : politique d'identité
5. **docs/specs/KPI_POC.md** : critères de succès du PoC

### Concepts clés

**Canonicalisation** : 5 en-têtes canoniques (from, to, subject, date,
message-id), normalisation du corps (CRLF→LF, trim), attachments hashés ;
profils `strict` (aucune tolérance) et `relaxed` (tolère les mutations MTA).

**Dual timestamping** : Sigstore/Rekor (immédiat, trust MEDIUM) +
OpenTimestamps/Bitcoin (différé ~48h, trust HIGH) ; cohérence exigée < 24h.

**DSSE** : la preuve JSON elle-même est signée (enveloppe DSSE via cosign) pour
détecter la falsification des métadonnées. Une enveloppe non signée est
rapportée comme telle (`dsse_signed: false`).

---

## 🐛 Troubleshooting

**`ERROR: refusing to create a degraded proof`**
→ cosign ou ots manque. `gwyl-mail doctor` pour le diagnostic, voir
« Prérequis » ci-dessus pour l'installation.

**`dsse_signed: false` + raison `dsse_unsigned_envelope`**
→ La preuve a été créée sans signature (cosign absent ou échec OIDC).
Recréez-la avec cosign fonctionnel pour obtenir une preuve signée.

**`ots: FAILED` dans la preuve**
→ Submission OTS impossible (binaire absent ou calendrier injoignable).
Réessayez plus tard ; l'ancrage existant se confirme avec `upgrade-ots`.

**Import Error: No module named 'gwyl_mail`**
```bash
pip install -e .
```

**Tests SHA-256 mismatch**
→ Vérifier normalisation Unicode (NFC), line endings (CRLF→LF), décodage
RFC 2047, et le profil (`--profile strict|relaxed`).

---

## 📞 Support

- Spécifications : `docs/specs/`
- Bugs : issues GitHub du dépôt
- Contributions : `CONTRIBUTING.md`
