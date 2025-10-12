# Traversal Concept — Preuve à travers les relais, PJ vs Hybride, E2E

Objectif
- Dresser une stratégie pragmatique pour transporter et vérifier la preuve cryptographique à travers la chaîne SMTP/IMAP (relais, DLP, AV) et cadrer l’attestation d’ouverture avec et sans E2E.

Contexte (code actuel)
- Canonicalisation stable (headers [from,to,subject,date,message-id], corps normalisé, pièces jointes → SHA‑256 trié): `gwyl_mail/canonical.py:49` et `gwyl_mail/canonical.py:66`.
- Preuve JSON (Sigstore best‑effort, OTS différé, policy optionnelle): `gwyl_mail/dual_proof.py:20` et `gwyl_mail/schemas/proof-v0.2.0.json:1`.
- Vérification offline CLI, protections path/injection, audit: `gwyl_mail/cli.py:42`, `gwyl_mail/cli.py:96`, `gwyl_mail/cli.py:231`.

Constats Traversal (relais)
- Modifications fréquentes: réencodage, footers, réécritures d’en‑têtes; DLP/AV peuvent supprimer des PJ.
- DKIM protège uniquement les champs listés dans `h=`; tout le reste peut être modifié.
- Invariant robuste minimal: le `content_hash` calculé côté destinataire (à partir du message reçu) reste vérifiable localement.

Méthodes de transport de la preuve
- Pièce jointe (PJ) auto‑contenue
  - Avantages: vérification offline complète (bundle cosign + .ots); indépendance réseau.
  - Risques: suppression par DLP/AV; taille; friction UX (fichier .json visible).
  - Atténuations: format MIME dédié `application/gwyl-proof+json`; DSSE unique (preuve + bundle + OTS) compacte (<50KB); si environnement maîtrisé, attacher en egress après DLP.

- En‑tête compact (référence) + Out‑of‑band
  - Ajouter un en‑tête court, protégé par DKIM, du type: `GWyl-Proof-Ref: sha256=<content_hash>; ts=rekor:<logIndex>; ots=<commit>`.
  - Le destinataire recalcule le hash; s’il manque la PJ, il peut récupérer la preuve via un store adressé par contenu (hash).
  - Résilience: même si le corps est modifié, le header protégé par DKIM survit mieux que la PJ.

- Hybride (recommandé)
  - Combiner: PJ DSSE auto‑contenue + header compact signé DKIM + lien de secours dans le corps.
  - Si la PJ est supprimée: header + récupération out‑of‑band suffisent. Si le header est perdu: le lien + PJ suffisent. À défaut, le hash reste vérifier le contenu.

Attestation d’ouverture (“scellé”)
- Sans E2E
  - Un “open receipt” ne peut pas prouver la lecture humaine: des relais/AV/DLP “ouvrent” souvent.
  - À présenter comme indicateur opt‑in (clic, daemon local + OIDC), journalisé et ancré OTS; valeur probante limitée.
- Avec E2E
  - Le destinataire seul peut déchiffrer; il peut signer un accusé d’ouverture qui prouve la capacité de décryptage et lie l’événement au scellé initial (plaintext canonique + destinataire).
  - Placez la preuve et la référence dans la partie chiffrée (PGP/MIME ou S/MIME) pour résister aux relais.

Recommandations Priorisées
- P1 Sigstore/Identity: extraire identité/issuer du bundle cosign de manière fiable (X.509 SAN email), nourrir la policy d’identité, exposer ces champs à la vérification: `gwyl_mail/cli.py:96`.
- P1 OTS: produire un timestamp attesté (pas “now()”) lors de `verify()`, ainsi la cohérence Rekor↔OTS 24h est significative: `gwyl_mail/ots_manager.py:70` et `gwyl_mail/cli.py:205`.
- P2 DSSE: signer la preuve JSON (et, côté PJ, emballer bundle+OTS) pour portabilité/immutabilité.
- P2 Transport: implémenter un header `GWyl-Proof-Ref` minimal et le signer via DKIM (côté MTA du domaine expéditeur); conserver la PJ DSSE pour l’offline.
- P3 Canonicalisation “relaxed”: prévoir un profil du corps plus tolérant aux footers/disclaimers ajoutés par des MTAs.
- P3 E2E: POC PGP/MIME ou S/MIME où le hash canonique s’applique au plaintext avant chiffrement; l’accusé d’ouverture est signé par le destinataire après déchiffrement.

Alignement avec Deepseek (extraits pertinents)
- Adoption/UX (juste): proposer API/daemon, plugin MUA, Docker; à encadrer par des exigences sécurité (authN/CSRF/CORS/chemins confinés) — `Deepseek_Propostions.txt:200–400`.
- Méthode du scellé (idée utile) mais non probante sans E2E et identité fiable côté destinataire — `Deepseek_Propostions.txt:2763–3860`.
- “Impossible de prouver la lecture”, “ouverture par qui/quand” sans modèle fiable: d’accord — `Deepseek_Propostions.txt:2583–2586`.

Actions Concrètes (projet)
- Ajouter un header compact “Proof‑Ref” et exemple DKIM: doc + tests.
- Créer un pack PJ DSSE (preuve+bundle+OTS) avec MIME dédié.
- Étendre CLI verify pour afficher identité/issuer et statuts cohérence.
- Prototyper un micro‑daemon local (sécurisé) en lecture seule pour la vérif offline, si besoin.

