# Test Vectors v0 — Canonicalisation et Preuves

Objectif: fournir des exemples EML synthétiques avec une forme canonique V0 et les résultats attendus (SHA‑256, Merkle, cohérences). Ces vecteurs servent de référence pour implémentations et audits.

Hypothèses V0 (profil « strict minimal »)
- Headers inclus (ordre strict): from, to, subject, date, message-id
- Normalisation des headers:
  - clé en minuscules (ex: From → from)
  - valeur trim + collapse des espaces internes, décodage RFC 2047
  - pour addr-spec, normaliser uniquement le domaine en lowercase (local-part préservé)
- Corps (text/plain préféré): EOL → LF, trim espaces de fin de ligne, une seule newline finale
- Pièces jointes: hash SHA‑256 des octets bruts décodés; représenter chaque pièce jointe par une ligne `attachment:sha256:<hex>`, triées par hash (hex) croissant
- Format canonique: lignes headers normalisés, une ligne vide, corps normalisé, puis lignes `attachment:` (s’il y en a)
- Hash final: SHA‑256 de l’intégralité de la chaîne canonique UTF‑8

Note: ces vecteurs fixent le périmètre V0 des tests; les spécifications finales pourront étendre/assouplir (profil relaxed pour HTML‑only, etc.).

---

TV1 — Plain text simple

EML (synt.)
  From: Alice <alice@example.com>
  To: bob@example.com
  Subject: Hello
  Date: Fri, 10 Jan 2025 10:20:30 +0000
  Message-ID: <id-001@example.com>

  Hello world!\r\n\r\nBest,\r\nAlice\r\n

Canonique V0
  from:alice@example.com
  to:bob@example.com
  subject:Hello
  date:Fri, 10 Jan 2025 10:20:30 +0000
  message-id:<id-001@example.com>

  Hello world!

  Best,
  Alice

SHA‑256 attendu
  a5511ab50073666cb72f27ff9677dd4910c203b1ced361de593c5e6e3a643cd0

---

TV2 — Corps équivalent (QP vs Base64), texte identique

EML (synt.)
  From: alice@example.com
  To: bob@example.com
  Subject: Café crème
  Date: Fri, 10 Jan 2025 10:25:30 +0000
  Message-ID: <id-002@example.com>

  Café crème\n

Canonique V0
  from:alice@example.com
  to:bob@example.com
  subject:Café crème
  date:Fri, 10 Jan 2025 10:25:30 +0000
  message-id:<id-002@example.com>

  Café crème

SHA‑256 attendu
  d9bcb5ecbc1ce5d2be6aea6f639c3f1531efdfaadae58d39f854afe64d2ed291

---

TV3 — Subject replié/encodé (valeur finale décodée ciblée en V1)

EML (synt.)
  From: alice@example.com
  To: bob@example.com
  Subject: =?UTF-8?Q?R=C3=A9sum=C3=A9_=E2=80=93_=C3=A9dition_2?=
  Date: Fri, 10 Jan 2025 10:30:30 +0000
  Message-ID: <id-003@example.com>

  Body normalized line.\n

Canonique V0 (valeur cible « résolue »)
  from:alice@example.com
  to:bob@example.com
  subject:Résumé – édition 2
  date:Fri, 10 Jan 2025 10:30:30 +0000
  message-id:<id-003@example.com>

  Body normalized line.

SHA‑256 attendu
  4d40a4e63c5f6fea649fb559bfffbc729eb8cd73725cf4eebb567f28cd7bf151

Note: En V0 strict, le décodage RFC 2047 peut être omis; cette TV fixe la valeur « décodée » comme cible de conformité V1.

---

TV4 — Deux pièces jointes (ordre indépendant), Merkle

Pièces
  contract.pdf  (octets):  PDFDATA
  logo.png      (octets):  IMAGEDATA

SHA‑256 pièces (octets bruts)
  contract.pdf: 1ad9615552126eb88b27e3f5c20c9932a9efafe7a58a790bf8d0d92d0fdc5661
  logo.png:     792f5746376162ad94517e952a298fdc83040970ae4bade9017813f06461e318

Canonique V0 (attachments triés par hash)
  ... (headers)…

  See attachments.
  attachment:sha256:1ad9615552126eb88b27e3f5c20c9932a9efafe7a58a790bf8d0d92d0fdc5661
  attachment:sha256:792f5746376162ad94517e952a298fdc83040970ae4bade9017813f06461e318

SHA‑256 attendu (du canonique complet)
  4e19bb70238626aa0d0f18864e079a68cf7f7308373903f9bea59af865e8d749

Merkle (racine, feuilles [contract.pdf, logo.png])
  2301de0509acd96daf626223e3a231dae6c9d5ce721f207e50c5109a6cd1ebc3

---

TV5 — Nom de fichier Unicode (NFC vs NFD) → normalisé NFC

Nom original (NFD): contraté.pdf   (e + \u0301)
Nom canonique (NFC): contraté.pdf   (\u00e9)

Canonique V0 (ligne attachment)
  attachment:sha256:1ad9615552126eb88b27e3f5c20c9932a9efafe7a58a790bf8d0d92d0fdc5661

SHA‑256 attendu (canonique complet)
  8084a054b13f5f01add6b169a18fcbe1b614cc9071157c7b53fbdab00ae35d98

---

TV6 — HTML‑only (fallback V0 = bytes du text/html)

EML (synt.)
  Content-Type: text/html; charset=UTF-8

  <html>\r\n<body>\r\n<p>Hello <b>Bob</b>!</p>\r\n</body>\r\n</html>\r\n

Canonique V0 (corps = bytes text/html normalisés EOL→LF)
  …
  <html>
  <body>
  <p>Hello <b>Bob</b>!</p>
  </body>
  </html>

Attendu: le hash V0 change si un MTA modifie le HTML. Cette TV valide le comportement « casse visible ».

---

TV7 — Footer MTA injecté → mismatch attendu

Cas: un MTA ajoute un disclaimer au corps. La canonicalisation V0 inclut le corps tel que reçu → le SHA‑256 diverge du côté expéditeur. TV pour valider l’alerte mismatch.

---

TV8 — Mailing list / réécriture To:

EML (synt.)
  From: alice@example.com
  To: list@lists.example.org
  Subject: Broadcast
  Date: Fri, 10 Jan 2025 11:10:30 +0000
  Message-ID: <id-008@example.com>

Cas: route transit remplace `To:` par des destinataires individuels.
V0 strict: mismatch attendu (headers canoniques inclus `to:`). Profil V1 relaxed: option d’ignorer rewriting contrôlé.

---

TV9 — OTS failed → reason code

Cas: `ots verify` échoue (proof introuvable ou invalide).
Attendu: `verification.trust_level` reste `MEDIUM` si Sigstore OK; `verification.reasons += ["ots_verify_failed"]`.
Audit: receipt log append-only avec reason code.

---

Section Proofs — Exigences V0

- Sigstore (immédiat)
  - `bundle_path` présent et vérifiable offline (cosign verify‑blob --bundle)
  - `rekor_entry_url`, `logIndex`, `integratedTime` (Unix)
- OpenTimestamps (différé)
  - États: pending → confirmed; `proof_path`, `confirmed_at` ISO, `bitcoin_block`
- Cohérence temporelle
  - Si OTS confirmé: |rekor_timestamp − confirmed_at| < 24h → OK, sinon → Alerte
- Anti‑replay
  - `nonce` (uuid‑v4), `expires_at` (ISO); registre de nonces côté réception
- Privacy
  - Pas d’adresses email en clair si non nécessaire: privilégier hash(addr) SHA‑256 (option salt/pepper)
- Politique
  - `policy_id` et `policy_hash` (sha256 du YAML canonicalisé) à inclure dans les proofs/baseline

---

Notes d’implémentation

Recalcul requis (format attachments modifié → hash-only):
- TV4 (attachments)
- TV5 (filename Unicode)

- Les TV montrent la « forme canonique » (chaîne exacte) pour des cas courants. Si une implémentation dévie (ex: gestion RFC 2047), alignez‑vous sur la cible V1 décrite dans CANONICALIZATION_v0.md.
- Publiez vos résultats et divergences via une matrice de tests (voir KPI_POC.md) pour affiner la spec.
