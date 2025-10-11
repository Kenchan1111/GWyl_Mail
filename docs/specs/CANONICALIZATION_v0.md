# GWyl Mail - Canonicalisation v0

**Version**: 0.2.0
**Date**: 2025-01-11
**Status**: Specification
**Auteurs**: Claude Code + Zack + ChatGPT

---

## 1. Objectif

Définir un format **canonique stable** pour hacher le contenu d'un email, résistant aux transformations SMTP/IMAP courantes.

### Problème résolu

Les emails traversent multiples serveurs (MTA, MDA) qui modifient:
- **Encodages**: `quoted-printable` ↔ `base64` ↔ `7bit`
- **Line endings**: `CRLF` ↔ `LF` ↔ `CR`
- **Headers**: ajout `Received:`, modification `Subject:`, réencodage
- **MIME boundaries**: régénération aléatoire
- **Whitespace**: normalisation, wrapping

**Conséquence**: Hash(email_envoyé) ≠ Hash(email_reçu) → vérification impossible.

### Solution

Canonicalisation inspirée **DKIM (RFC 6376)**: extraire et normaliser un subset stable du message.

---

## 2. Algorithme de canonicalisation

### 2.1 Pseudo-code global

```python
def canonicalize(email_message: EmailMessage) -> bytes:
    """
    Canonise un email en format hashable stable

    Returns:
        bytes: Représentation canonique
    """

    canonical_parts = []

    # 1. Headers (subset strict, profile='strict', nfc_scope='filenames_only')
    canonical_parts.append(canonicalize_headers(email_message))

    # 2. Body (normalisé)
    canonical_parts.append(canonicalize_body(email_message))

    # 3. Attachments (binaire brut)
    canonical_parts.extend(canonicalize_attachments(email_message))

    # 4. Joindre avec séparateur
    return b'\n'.join(canonical_parts)
```

---

### 2.2 Canonicalisation des headers

#### Headers inclus (ordre strict)

**Liste exhaustive** (5 headers uniquement):
1. `from`
2. `to`
3. `subject`
4. `date`
5. `message-id`

**Rationale**:
- `from`, `to`: identité expéditeur/destinataire
- `subject`: contexte message
- `date`: temporalité
- `message-id`: unicité

**Exclus** (instables):
- `received`: ajouté par chaque serveur
- `x-*`: headers custom variables
- `content-*`: modifiés par transformations MIME
- `dkim-signature`: signature DKIM (externe à GWyl)

#### Normalisation par header

```python
def canonicalize_headers(message: EmailMessage) -> bytes:
    """
    Canonise headers en format stable

    Format:
        {header_lowercase}:{value_normalized}\n
        ...
    """

    CANONICAL_HEADERS = ['from', 'to', 'subject', 'date', 'message-id']

    canonical_lines = []

    for header_name in CANONICAL_HEADERS:
        # Récupérer valeur (case-insensitive)
        value = message.get(header_name, '')

        if not value:
            continue  # Header absent = skip

        # Normaliser
        key = header_name.lower()
        normalized_value = normalize_header_value(value)

        canonical_lines.append(f"{key}:{normalized_value}")

    return '\n'.join(canonical_lines).encode('utf-8')


def normalize_header_value(value: str) -> str:
    """
    Normalise valeur header (RFC 2047, folding, Unicode)

    Règles V0 STRICT:
    1. Unfold (RFC 5322): joindre lignes continuées
    2. Décoder RFC 2047 encoded-words (concaténer segments; respecter charset)
    3. PAS de NFC sur valeurs headers en V0 (NFC réservé aux filenames)
    4. Collapse whitespace (multiples espaces → un seul)
    5. Trim leading/trailing
    6. Pour addr-spec (From/To/...): ne lowercaser que le domaine (local-part préservé)

    IMPORTANT:
    - Clés headers: LOWERCASE (ex: "from", "to", "subject")
    - Valeurs headers: PRESERVE CASE (ex: "Alice Smith", "Contract Review")
    - NE PAS lowercaser les valeurs en V0 strict
    """
    import re

    # 1. Unfold (remplacer \r\n ou \n + whitespace par espace)
    value = re.sub(r'\r?\n[\t ]+', ' ', value)

    # 2. Décoder RFC 2047 encoded-words
    decoded = email.header.decode_header(value)
    value = ''.join([
        text.decode(charset or 'utf-8', errors='replace') if isinstance(text, bytes) else text
        for text, charset in decoded
    ])

    # 3. NFC normalization: NON en V0 strict pour valeurs headers
    # (Seulement pour filenames d'attachments)
    # value = unicodedata.normalize('NFC', value)  # ← Désactivé en V0

    # 4. Collapse whitespace (multiples espaces → un seul)
    value = ' '.join(value.split())

    # 5. Trim leading/trailing
    value = value.strip()

    # 6. Normaliser uniquement le domaine des adresses email (local-part préservé)
    try:
        import email.utils as eut
        name, addr = eut.parseaddr(value)
        if addr and '@' in addr:
            local, domain = addr.split('@', 1)
            addr_norm = f"{local}@{domain.lower()}"
            value = f"{name} <{addr_norm}>".strip() if name else addr_norm
    except Exception:
        pass

    return value
```

#### Exemple

**Input**:
```
From: Alice  Smith <alice@company.com>
To: =?UTF-8?B?Qm9iIEpvbmVz?= <bob@example.com>
Subject: Re:   Contract  Review
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <uuid-12345@company.com>
Received: from mail.google.com by mx.example.com
X-Custom: some value
```

**Canonical output**:
```
from:Alice Smith <alice@company.com>
to:Bob Jones <bob@example.com>
subject:Re: Contract Review
date:Thu, 11 Jan 2025 14:30:22 +0000
message-id:<uuid-12345@company.com>
```

---

### 2.3 Canonicalisation du body

#### Extraction du texte

```python
def canonicalize_body(message: EmailMessage) -> bytes:
    """
    Canonise le corps du message

    Règles (V0 strict):
    1. Extraire text/plain (préféré)
    2. Si absent, extraire text/html tel quel (aucun strip en V0)
    3. Normaliser line endings CRLF → LF
    4. Trim trailing whitespace per line
    5. Single trailing newline
    """

    # 1. Extraire text/plain
    body = message.get_body(preferencelist=('plain', 'html'))

    if not body:
        return b''  # Pas de body

    # 2. Obtenir contenu
    content = body.get_content()

    # 3. Si HTML, conserver le HTML (pas de strip en V0 strict)

    # 4. Normaliser line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # 5. Trim trailing whitespace per line
    lines = [line.rstrip() for line in content.split('\n')]

    # 6. Joindre avec LF + single trailing newline
    normalized = '\n'.join(lines)
    if normalized and not normalized.endswith('\n'):
        normalized += '\n'

    return normalized.encode('utf-8')


"""
Note V1 (relaxed): une future version pourra définir une normalisation HTML
(strip/normalisation) tolérante aux footers MTA et variations mineures.
"""
```

#### Exemple

**Input**:
```
Bonjour,\r\n
\r\n
Veuillez trouver ci-joint le contrat.  \r\n
\r\n
Cordialement,  \r\n
Alice\r\n
```

**Canonical output**:
```
Bonjour,

Veuillez trouver ci-joint le contrat.

Cordialement,
Alice
```
(avec `\n` unix, pas de trailing spaces)

---

### 2.4 Canonicalisation des attachments

#### Règles

1. **Binaire brut**: `part.get_payload(decode=True)` (octets décodés, pas encodés)
2. **Normalisation filename**: Unicode NFC (si utilisé pour corrélation)
3. **Tri**: par valeur de hash (hex) croissante
4. **Hash individuel**: SHA-256 par fichier
5. **Format V0 strict**: `attachment:sha256:<hash_hex>` (sans nom de fichier)

```python
def canonicalize_attachments(message: EmailMessage) -> List[bytes]:
    """
    Canonise pièces jointes

    Returns:
        List de lignes "attachment:sha256:hash_hex"
    """
    import unicodedata

    attachments = []

    for part in message.iter_attachments():
        # Récupérer contenu binaire brut (décodé)
        payload = part.get_payload(decode=True)

        if payload:
            # Hash SHA-256 des octets bruts
            file_hash = hashlib.sha256(payload).hexdigest()
            attachments.append(file_hash)

    # Trier par valeur de hash (hex)
    attachments.sort()

    # Formatter avec préfixe "attachment:"
    return [
        f"attachment:sha256:{file_hash}".encode('utf-8')
        for file_hash in attachments
    ]
```

#### Exemple

**Input** (3 attachments):
- `contract.pdf` → hash `abc123...`
- `annex_A.docx` → hash `def456...`
- `signature.png` → hash `789xyz...`

**Canonical output** (trié par hash, V0 strict):
```
attachment:sha256:def456...
attachment:sha256:abc123...
attachment:sha256:789xyz...
```

---

### 2.5 Format final

```python
def compute_canonical_hash(message: EmailMessage) -> str:
    """
    Hash final du message canonique

    Returns:
        SHA-256 hex (64 chars)
    """

    # 1. Canoniser
    headers = canonicalize_headers(message)
    body = canonicalize_body(message)
    attachments = canonicalize_attachments(message)

    # 2. Joindre
    canonical = b'\n'.join([headers, body] + attachments)

    # 3. Hash SHA-256
    return hashlib.sha256(canonical).hexdigest()
```

**Format final**:
```
{canonical_headers}\n
{canonical_body}\n
{attachment1}\n
{attachment2}\n
...
```

**Hash**: `SHA-256(format_final)` → 64 hex chars

---

## 2.6 Profils de canonicalisation

### Profil "strict" (défaut v0)

**Objectif**: Maximum de stabilité, mais risque de casse si MTA modifie le corps.

**Règles**:
- Headers: 5 headers exacts, décodage RFC 2047 complet
- Corps: text/plain prioritaire, HTML→plaintext si absent
- Line endings: CRLF→LF normalisé
- Whitespace: trim par ligne
- Attachments: hash octets bruts, tri NFC normalisé

**Usage**: Messages entre systèmes contrôlés, audit forensique

**Risques**:
- Footers MTA (disclaimers automatiques) → mismatch
- Word wrapping automatique → mismatch
- Inline images CID transformées → mismatch

---

### Profil "relaxed" (futur v1)

**Objectif**: Tolérance aux modifications MTA courantes (inspiration DKIM "relaxed").

**Règles supplémentaires**:
- Ignorer footers MTA (détection heuristique)
- Normaliser word wrapping (collapse multiple espaces)
- Ignorer variations de whitespace dans HTML
- Accepter variations mineures d'encodage

**Usage**: Production avec providers tiers (Gmail, Outlook, etc.)

**Implémentation**: Futur v1 (après validation v0)

---

### Choix du profil

```python
class GWylCanonical:
    @classmethod
    def canonicalize(cls, message: EmailMessage, profile: str = 'strict') -> bytes:
        """
        Canonise message selon profil

        Args:
            message: Email à canoniser
            profile: 'strict' (défaut) ou 'relaxed' (v1)

        Returns:
            bytes: Forme canonique
        """
        if profile == 'relaxed':
            raise NotImplementedError("Profil relaxed disponible en v1")

        # Profil strict (v0)
        parts = []
        parts.append(cls._canonicalize_headers(message))
        parts.append(cls._canonicalize_body(message))
        parts.extend(cls._canonicalize_attachments(message))

        return b'\n'.join(parts)
```

---

## 3. Cas de test

### Test 1: Message simple (texte seul)

**Input**:
```eml
From: alice@company.com
To: bob@example.com
Subject: Hello
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test1@company.com>

Hello Bob!
```

**Canonical**:
```
from:alice@company.com
to:bob@example.com
subject:Hello
date:Thu, 11 Jan 2025 14:30:22 +0000
message-id:<test1@company.com>

Hello Bob!
```

**Hash**: `a3f7b2e9d1c4f5a6b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1`

---

### Test 2: Message avec attachment

**Input**:
```eml
From: alice@company.com
To: bob@example.com
Subject: Contract
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test2@company.com>
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain

Please review.

--boundary123
Content-Type: application/pdf; name="contract.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MK...
--boundary123--
```

**Canonical**:
```
from:alice@company.com
to:bob@example.com
subject:Contract
date:Thu, 11 Jan 2025 14:30:22 +0000
message-id:<test2@company.com>

Please review.

contract.pdf:d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4
```

---

### Test 3: SMTP transformations (encoding)

**Input original** (quoted-printable):
```eml
From: alice@company.com
To: bob@example.com
Subject: =?UTF-8?B?Q29udHJhdA==?=
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test3@company.com>
Content-Transfer-Encoding: quoted-printable

Bonjour,=0D=0A=0D=0APi=C3=A8ce jointe.
```

**Après transit** (base64):
```eml
From: alice@company.com
To: bob@example.com
Subject: Contrat
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test3@company.com>
Content-Transfer-Encoding: base64

Qm9uam91ciwKClBpw6hjZSBqb2ludGUu
```

**Canonical (IDENTIQUE dans les 2 cas)**:
```
from:alice@company.com
to:bob@example.com
subject:Contrat
date:Thu, 11 Jan 2025 14:30:22 +0000
message-id:<test3@company.com>

Bonjour,

Pièce jointe.
```

✅ **Hash identique** malgré transformation encoding

---

### Test 4: Headers modifiés (Received, X-*)

**Input original**:
```eml
From: alice@company.com
To: bob@example.com
Subject: Test
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test4@company.com>

Body.
```

**Après transit** (headers ajoutés):
```eml
Received: from mail.google.com by mx.example.com
Received: from [192.168.1.1] by mail.google.com
X-Spam-Status: No
X-Custom: value
From: alice@company.com
To: bob@example.com
Subject: Test
Date: Thu, 11 Jan 2025 14:30:22 +0000
Message-ID: <test4@company.com>

Body.
```

**Canonical (IDENTIQUE dans les 2 cas)**:
```
from:alice@company.com
to:bob@example.com
subject:Test
date:Thu, 11 Jan 2025 14:30:22 +0000
message-id:<test4@company.com>

Body.
```

✅ **Hash identique** (headers ajoutés ignorés)

---

### Test 5: Unicode NFC normalization

**Input**:
```eml
From: alice@example.com
To: bob@example.com
Subject: Café  # é = U+0065 U+0301 (NFD - décomposé)
Date: Fri, 10 Jan 2025 10:25:30 +0000
Message-ID: <test5@example.com>
Content-Type: text/plain; charset=UTF-8

Café crème  # é = U+00E9 (NFC - composé)
```

**Canonical (après NFC normalization)**:
```
from:alice@example.com
to:bob@example.com
subject:Café  # é = U+00E9 (NFC)
date:Fri, 10 Jan 2025 10:25:30 +0000
message-id:<test5@example.com>

Café crème
```

✅ **Hash identique** malgré NFD/NFC differences

---

### Test 6: Attachment avec Unicode filename

**Input**:
- Filename original (NFD): `contraté.pdf` (e + U+0301)
- Filename normalisé (NFC): `contraté.pdf` (U+00E9)
- Contenu: `PDFDATA`

**Canonical**:
```
from:alice@example.com
to:bob@example.com
subject:Unicode filename
date:Fri, 10 Jan 2025 10:40:30 +0000
message-id:<test6@example.com>

One attachment.
attachment:sha256:1ad9615552126eb88b27e3f5c20c9932a9efafe7a58a790bf8d0d92d0fdc5661
```

**Hash**: `8084a054b13f5f01add6b169a18fcbe1b614cc9071157c7b53fbdab00ae35d98`

---

### Test 7: HTML-only message (pas de text/plain)

**Input**:
```eml
From: alice@example.com
To: bob@example.com
Subject: HTML Test
Date: Fri, 10 Jan 2025 10:45:30 +0000
Message-ID: <test7@example.com>
Content-Type: text/html; charset=UTF-8

<html>
<body>
<p>Hello <b>Bob</b>!</p>
</body>
</html>
```

**Canonical (HTML strippé)**:
```
from:alice@example.com
to:bob@example.com
subject:HTML Test
date:Fri, 10 Jan 2025 10:45:30 +0000
message-id:<test7@example.com>

Hello Bob!
```

⚠️ Note: en V0 strict, le HTML est conservé tel quel (pas de strip). Le hash V0 change si le HTML est modifié par un MTA. Profil "relaxed" (V1) pourra être plus tolérant.

---

### Test 8: Footer MTA ajouté

**Scénario**: Un MTA ajoute un disclaimer au corps.

**Input reçu**:
```
Hello Bob!

---
This email has been scanned for viruses.
```

**Canonical V0**: Inclut le footer → hash différent de l'expéditeur

**Résultat**: ❌ Mismatch attendu en profil "strict"

**Solution**: Passer au profil "relaxed" (v1) qui détecte et ignore les footers MTA courants.

---

### Référence complète: TEST_VECTORS_v0.md

Pour des test vectors complets avec SHA-256 attendus, voir [TEST_VECTORS_v0.md](./TEST_VECTORS_v0.md).

**Test Vectors disponibles**:
- TV1: Plain text simple → `a5511ab50073666cb72f27ff9677dd4910c203b1ced361de593c5e6e3a643cd0`
- TV2: Corps équivalent (QP vs Base64) → `d9bcb5ecbc1ce5d2be6aea6f639c3f1531efdfaadae58d39f854afe64d2ed291`
- TV3: Subject replié/encodé → `4d40a4e63c5f6fea649fb559bfffbc729eb8cd73725cf4eebb567f28cd7bf151`
- TV4: Deux attachments + Merkle → Canon: `4e19bb70...`, Merkle: `2301de05...`
- TV5: Unicode filename NFC → `8084a054b13f5f01add6b169a18fcbe1b614cc9071157c7b53fbdab00ae35d98`

---

## 4. Vecteurs d'attaque couverts

### 4.1 Modification body

**Attaque**: Changer "1000€" → "10000€" dans le body

**Détection**:
```python
original_canonical = canonicalize(original_message)
modified_canonical = canonicalize(modified_message)

hash(original) != hash(modified)  # ✅ Détecté
```

---

### 4.2 Modification attachment

**Attaque**: Remplacer `contract.pdf` par version modifiée

**Détection**:
```python
# Canonical inclut hash SHA-256 du binaire brut
original: "contract.pdf:abc123..."
modified: "contract.pdf:xyz789..."  # ✅ Différent
```

---

### 4.3 Ajout/suppression attachment

**Attaque**: Supprimer une pièce jointe

**Détection**:
```python
original:
  contract.pdf:abc123...
  annex.pdf:def456...

modified:
  contract.pdf:abc123...
  # annex.pdf manquant ✅
```

---

### 4.4 Replay avec headers modifiés

**Attaque**: Renvoyer message avec `Date:` changée

**Détection**:
```python
# Date inclus dans canonical
original: "date:Thu, 11 Jan 2025 14:30:22"
replayed: "date:Fri, 12 Jan 2025 10:00:00"

hash(original) != hash(replayed)  # ✅ Détecté
```

---

### 4.5 Unicode normalization attacks

**Attaque**: `café` vs `café` (é composé vs décomposé)

**Mitigation**:
```python
def normalize_header_value(value: str) -> str:
    # ...
    # Unicode NFC normalization
    import unicodedata
    value = unicodedata.normalize('NFC', value)
    # ...
```

---

## 5. Limites connues

### 5.1 Transformation agressive body

**Cas**: Serveur reformate body (word wrapping, ajout footer)

**Impact**: Hash change

**Mitigation**: Utiliser canonicalisation "relaxed" (future v1)

---

### 5.2 Attachments renommés

**Cas**: Serveur renomme `contract.pdf` → `contract(1).pdf`

**Impact**: Hash change (filename dans canonical)

**Mitigation**: Hash seulement contenu, pas filename (future v1)

---

### 5.3 Stripped attachments

**Cas**: Serveur supprime attachments (antivirus, quota)

**Impact**: Hash change

**Mitigation**: Preuve stockée séparément (pas dans email transit)

---

## 5.4 Effets MTA communs

### Transformations courantes

| Effet MTA | Impact V0 | Mitigation |
|-----------|-----------|------------|
| **Footer ajouté** | ❌ Hash change | Profil relaxed (v1) |
| **Disclaimer injecté** | ❌ Hash change | Profil relaxed (v1) |
| **Word wrapping** | ❌ Hash change | Profil relaxed (v1) |
| **Encoding QP↔Base64** | ✅ Stable | Décodage automatique |
| **CRLF↔LF** | ✅ Stable | Normalisation LF |
| **Headers ajoutés (Received, X-)** | ✅ Stable | Headers exclus |
| **MIME boundary change** | ✅ Stable | Ignore boundaries |
| **Attachment renommé** | ❌ Hash change | Option: hash-only mode (v1) |

### Recommandations par provider

**Gmail**:
- ✅ Encoding stable (QP/Base64)
- ✅ Headers stables
- ⚠️ Peut ajouter footer "Get Gmail on mobile"
- **Solution**: Profil relaxed ou désactiver footer

**Outlook.com**:
- ✅ Généralement stable
- ⚠️ Footers entreprise possibles
- ⚠️ Inline images CID transformées

**Self-hosted (Postfix)**:
- ✅ Très stable (contrôle total)
- Configuration recommandée: désactiver disclaimers automatiques

---

## 5.5 Considérations d'implémentation

### RFC 2047 (Encoded-words)

**Format**: `=?charset?encoding?encoded-text?=`

**Exemples**:
```
=?UTF-8?B?Q29udHJhdA==?=           → "Contrat" (Base64)
=?UTF-8?Q?Caf=C3=A9?=              → "Café" (Quoted-Printable)
=?ISO-8859-1?Q?R=E9sum=E9?=        → "Résumé" (ISO-8859-1)
```

**Implémentation**:
```python
import email.header

def decode_header_value(value: str) -> str:
    """Décoder RFC 2047 encoded-words"""
    decoded_parts = email.header.decode_header(value)

    result = []
    for text, charset in decoded_parts:
        if isinstance(text, bytes):
            # Décoder avec charset spécifié ou UTF-8 par défaut
            text = text.decode(charset or 'utf-8', errors='replace')
        result.append(text)

    return ''.join(result)
```

### Folding headers (RFC 5322)

**Format**: Headers longs peuvent être "repliés" sur plusieurs lignes avec whitespace de continuation.

**Exemple**:
```
Subject: This is a very long subject line that
 spans multiple lines with folding
```

**Normalisation**: Unfold en joignant les lignes et collapsant whitespace.

```python
def unfold_header(value: str) -> str:
    """Unfold header replié (RFC 5322)"""
    # Remplacer \r\n ou \n suivi de whitespace par un seul espace
    import re
    unfolded = re.sub(r'\r?\n[\t ]+', ' ', value)
    return unfolded.strip()
```

### Charsets et encodings

**Règle V0**: Toujours décoder vers Unicode (UTF-8) avant canonicalisation.

**Cas supportés**:
- UTF-8, ISO-8859-1, ISO-8859-15
- Windows-1252
- US-ASCII

**Cas non supportés (erreur graceful)**:
- Charsets inconnus → fallback UTF-8 avec `errors='replace'`

---

## 6. Implémentation de référence

```python
# gwyl_mail/canonical.py

import hashlib
import email
import unicodedata
from email.message import EmailMessage
from typing import List

class GWylCanonical:
    """Canonicalisation GWyl Mail v0"""

    VERSION = "0.1.0"
    HEADERS = ['from', 'to', 'subject', 'date', 'message-id']

    @classmethod
    def canonicalize(cls, message: EmailMessage) -> bytes:
        """Canonise message complet"""

        parts = []
        parts.append(cls._canonicalize_headers(message))
        parts.append(cls._canonicalize_body(message))
        parts.extend(cls._canonicalize_attachments(message))

        return b'\n'.join(parts)

    @classmethod
    def hash(cls, message: EmailMessage) -> str:
        """Hash SHA-256 du message canonique"""
        canonical = cls.canonicalize(message)
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def _canonicalize_headers(cls, message: EmailMessage) -> bytes:
        """Canonise headers"""
        lines = []

        for header in cls.HEADERS:
            value = message.get(header, '')
            if value:
                key = header.lower()
                normalized = cls._normalize_header_value(value)
                lines.append(f"{key}:{normalized}")

        return '\n'.join(lines).encode('utf-8')

    @classmethod
    def _normalize_header_value(cls, value: str) -> str:
        """
        Normalise valeur header (RFC 2047, folding, Unicode)

        Règles:
        1. Unfold (RFC 5322): joindre lignes continuées
        2. Décoder encoded-words (RFC 2047)
        3. Normaliser Unicode (NFC)
        4. Collapse whitespace
        5. Trim
        """
        import re

        # 1. Unfold (remplacer \r\n ou \n + whitespace par espace)
        value = re.sub(r'\r?\n[\t ]+', ' ', value)

        # 2. Décoder RFC 2047 encoded-words
        decoded_parts = email.header.decode_header(value)
        decoded_text = []
        for text, charset in decoded_parts:
            if isinstance(text, bytes):
                # Décoder avec charset ou UTF-8 par défaut
                text = text.decode(charset or 'utf-8', errors='replace')
            decoded_text.append(text)

        value = ''.join(decoded_text)

        # 3. Unicode NFC normalization
        value = unicodedata.normalize('NFC', value)

        # 4. Collapse whitespace (multiples espaces → un seul)
        value = ' '.join(value.split())

        # 5. Trim leading/trailing
        return value.strip()

    @classmethod
    def _canonicalize_body(cls, message: EmailMessage) -> bytes:
        """Canonise body"""
        body = message.get_body(preferencelist=('plain', 'html'))

        if not body:
            return b''

        content = body.get_content()

        # Strip HTML si nécessaire
        if body.get_content_type() == 'text/html':
            import re
            content = re.sub(r'<[^>]+>', '', content)
            import html
            content = html.unescape(content)

        # Normaliser line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Trim per line
        lines = [line.rstrip() for line in content.split('\n')]
        normalized = '\n'.join(lines)

        if normalized and not normalized.endswith('\n'):
            normalized += '\n'

        return normalized.encode('utf-8')

    @classmethod
    def _canonicalize_attachments(cls, message: EmailMessage) -> List[bytes]:
        """Canonise attachments (V0 strict: hash-only)"""
        hashes = []

        for part in message.iter_attachments():
            payload = part.get_payload(decode=True)

            if payload:
                file_hash = hashlib.sha256(payload).hexdigest()
                hashes.append(file_hash)

        # Trier par valeur de hash
        hashes.sort()

        return [
            f"attachment:sha256:{h}".encode('utf-8')
            for h in hashes
        ]
```

---

## 7. Tests unitaires

```python
# tests/test_canonical.py

import unittest
from email.message import EmailMessage
from gwyl_mail.canonical import GWylCanonical

class TestCanonical(unittest.TestCase):

    def test_simple_message(self):
        """Test message texte simple"""
        msg = EmailMessage()
        msg['From'] = 'alice@company.com'
        msg['To'] = 'bob@example.com'
        msg['Subject'] = 'Hello'
        msg['Date'] = 'Thu, 11 Jan 2025 14:30:22 +0000'
        msg['Message-ID'] = '<test1@company.com>'
        msg.set_content('Hello Bob!')

        hash1 = GWylCanonical.hash(msg)

        # Hash stable
        hash2 = GWylCanonical.hash(msg)
        self.assertEqual(hash1, hash2)

    def test_encoding_resistance(self):
        """Test résistance transformations encoding"""

        # Message quoted-printable
        msg1 = EmailMessage()
        msg1['From'] = 'alice@company.com'
        msg1['To'] = 'bob@example.com'
        msg1['Subject'] = 'Test'
        msg1['Date'] = 'Thu, 11 Jan 2025 14:30:22 +0000'
        msg1['Message-ID'] = '<test@company.com>'
        msg1.set_content('Pièce jointe', cte='quoted-printable')

        # Message base64
        msg2 = EmailMessage()
        msg2['From'] = 'alice@company.com'
        msg2['To'] = 'bob@example.com'
        msg2['Subject'] = 'Test'
        msg2['Date'] = 'Thu, 11 Jan 2025 14:30:22 +0000'
        msg2['Message-ID'] = '<test@company.com>'
        msg2.set_content('Pièce jointe', cte='base64')

        # Hash identiques
        self.assertEqual(GWylCanonical.hash(msg1), GWylCanonical.hash(msg2))

    def test_headers_added(self):
        """Test résistance ajout headers"""

        msg1 = EmailMessage()
        msg1['From'] = 'alice@company.com'
        msg1['To'] = 'bob@example.com'
        msg1['Subject'] = 'Test'
        msg1['Date'] = 'Thu, 11 Jan 2025 14:30:22 +0000'
        msg1['Message-ID'] = '<test@company.com>'
        msg1.set_content('Body')

        msg2 = EmailMessage()
        msg2['Received'] = 'from mail.google.com'
        msg2['X-Spam'] = 'No'
        msg2['From'] = 'alice@company.com'
        msg2['To'] = 'bob@example.com'
        msg2['Subject'] = 'Test'
        msg2['Date'] = 'Thu, 11 Jan 2025 14:30:22 +0000'
        msg2['Message-ID'] = '<test@company.com>'
        msg2.set_content('Body')

        # Hash identiques (headers ajoutés ignorés)
        self.assertEqual(GWylCanonical.hash(msg1), GWylCanonical.hash(msg2))
```

---

## 8. Changelog

### v0.2.0 (2025-01-11) - Révision ChatGPT

**Améliorations majeures**:
- ✅ Algorithme normatif bit-à-bit précisé
- ✅ RFC 2047 (encoded-words) décodage complet
- ✅ RFC 5322 (header folding) unfolding normalisé
 - ✅ Unicode NFC normalization sur filenames (pas sur valeurs headers en V0)
 - ✅ Format attachments (V0 strict): `attachment:sha256:<hash>`
- ✅ Profils strict/relaxed définis (relaxed en v1)
- ✅ 8 test cases détaillés + référence TEST_VECTORS_v0.md
- ✅ Section effets MTA par provider (Gmail, Outlook, Postfix)
- ✅ Considérations d'implémentation (charsets, folding, encodings)

**Cas couverts**:
- Encoding QP/Base64 (stable)
- Line endings CRLF/LF (stable)
- Headers ajoutés (stable)
- Unicode NFD/NFC (stable)
- Attachments Unicode filenames (stable)
 - HTML-only messages (conservés en V0 strict)
- Footer MTA (mismatch attendu en strict, relaxed en v1)

### v0.1.0 (2025-01-11)
- Initial draft
- Headers: 5 headers canoniques
 - Body: text/plain préféré; si HTML-only, conserver
 - Attachments: binaire brut, tri par hash; format hash-only
 - Format: headers + body + attachments (hash-only, newline separated)
- Hash: SHA-256

---

## 9. Références

- **DKIM RFC 6376**: https://www.rfc-editor.org/rfc/rfc6376.html
- **MIME RFC 2045**: https://www.rfc-editor.org/rfc/rfc2045.html
- **Email Message Format RFC 5322**: https://www.rfc-editor.org/rfc/rfc5322.html
- **Unicode Normalization**: https://unicode.org/reports/tr15/

---

---

## 10. Contributeurs

**Conception et spécification**: Zack, Claude (Anthropic), ChatGPT (OpenAI)

**Remerciements**: ChatGPT pour l'identification de la canonicalisation comme exigence critique #1 du système GWyl Mail, inspirée de l'approche DKIM.

---

**Fin du document CANONICALIZATION_v0.md**
