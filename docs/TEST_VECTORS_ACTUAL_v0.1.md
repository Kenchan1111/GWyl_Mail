# Test Vectors - Résultats Actuels v0.1

Ce document contient les **hashes réellement produits** par l'implémentation gwyl_mail v0.1.0.

**Note**: Ces hashes diffèrent de TEST_VECTORS_v0.md original car l'implémentation :
- Préserve le display name dans `From:` (ex: `Alice <alice@example.com>`)
- Format exact de la canonicalisation peut varier

## TV1 - Plain text simple

**Input**:
```
From: Alice <alice@example.com>
To: bob@example.com
Subject: Hello
Date: Fri, 10 Jan 2025 10:20:30 +0000
Message-ID: <id-001@example.com>

Hello world!

Best,
Alice
```

**Canonical Form**:
```
from:Alice <alice@example.com>
to:bob@example.com
subject:Hello
date:Fri, 10 Jan 2025 10:20:30 +0000
message-id:<id-001@example.com>

Hello world!

Best,
Alice
```

**SHA-256**: `c85bb3fa8d13811100c3f0e7ecac6dec97bdbe04727dbfe581f0651ab93aa4dd`

---

## TV2 - Unicode (Café crème)

**Input**:
```
From: alice@example.com
To: bob@example.com
Subject: Café crème
Date: Fri, 10 Jan 2025 10:25:30 +0000
Message-ID: <id-002@example.com>

Café crème
```

**Canonical Form**:
```
from:alice@example.com
to:bob@example.com
subject:Café crème
date:Fri, 10 Jan 2025 10:25:30 +0000
message-id:<id-002@example.com>

Café crème
```

**SHA-256**: `cef87f4e120945d5545b09f74c07406a429fe9faa45d061108008ef761cf81a1`

---

## TV3 - RFC 2047 Encoded Subject

**Input**:
```
From: alice@example.com
To: bob@example.com
Subject: =?UTF-8?Q?R=C3=A9sum=C3=A9_=E2=80=93_=C3=A9dition_2?=
Date: Fri, 10 Jan 2025 10:30:30 +0000
Message-ID: <id-003@example.com>

Body normalized line.
```

**Canonical Form** (decoded):
```
from:alice@example.com
to:bob@example.com
subject:Résumé – édition 2
date:Fri, 10 Jan 2025 10:30:30 +0000
message-id:<id-003@example.com>

Body normalized line.
```

**SHA-256**: `e9d03e725de8de34dd6481494d900561aa51c192efe1dfe8d9fb0f8574bfe18c`

---

## Divergence avec spec originale

| Test | Hash Spec Original | Hash Implémentation Réelle | Status |
|------|-------------------|---------------------------|--------|
| TV1  | `a5511ab5...`     | `c85bb3fa...`             | ❌ Diverge |
| TV2  | `d9bcb5ec...`     | `cef87f4e...`             | ❌ Diverge |
| TV3  | `4d40a4e6...`     | `e9d03e72...`             | ❌ Diverge |

**Cause probable** : Format canonique différent (display name préservé)

---

**Date**: 2025-10-12
**Version gwyl_mail**: 0.1.0
