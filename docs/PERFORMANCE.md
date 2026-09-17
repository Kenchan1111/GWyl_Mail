# Performance — mesures réelles (SPRINT 10)

Chiffres mesurés le 2026-09-17 avec `scripts/benchmark.py` et
`scripts/interop_postfix.py`, comparés aux seuils Go/NoGo de
[specs/KPI_POC.md](specs/KPI_POC.md).

Environnement de mesure : Fedora Linux x86_64, Python 3.14.6, cosign **absent**
(la signature Sigstore nécessite une session OIDC interactive — mesure à
compléter), binaire `ots` v0.7.2 présent (réseau réel).

## Résultats vs seuils KPI

| KPI | Seuil Go | Mesure | Statut |
|---|---|---|---|
| Vérification offline | < 150 ms | **4,5 ms** (moyenne, n=20) | ✅ PASS |
| Overhead preuve embarquée | < 50 Ko | **4,4 Ko** (avec vrai timbre OTS) | ✅ PASS |
| Soumission OTS (réseau réel) | < 5 s | **1,5 s** | ✅ PASS |
| Interopérabilité MTA réel | ≥ 95 % | **100 %** (50/50 via Postfix Docker) | ✅ PASS |
| Détection de falsification | 100 % | 100 % (tests suite, corps modifié → échec) | ✅ PASS |
| Création Sigstore | < 1 s | non mesurable sans cosign/OIDC | ⏳ à mesurer au pilote |
| Confirmation OTS < 48h (100 soumissions) | ≥ 90 % | structure en place, mesure longue durée | ⏳ pilote |
| Cohérence Rekor↔OTS < 24h | 100 % | implémentée (verify), mesure au pilote | ⏳ pilote |

## Détails

### Latence de canonicalisation (moyenne n=20)

| Message | Taille | Hash canonique |
|---|---|---|
| Texte simple | ~0,3 Ko | 3–4 ms |
| HTML | ~1 Ko | ~3 ms |
| Avec pièces jointes | ~2 Ko | ~4 ms |
| Pièce jointe 5 Mo | 5 Mo | ~28 ms |
| Pièce jointe 25 Mo | 25 Mo | ~171 ms |

### Vérification — deux variantes

- **offline_core: 4,5 ms** — le scénario KPI du destinataire (hash + enveloppe,
  sans appel réseau). C'est la mesure retenue pour le seuil 150 ms.
- **avec binaire ots: ~270 ms** — le coût supplémentaire est l'appel
  subprocess `ots verify` sur un timbre pending ; informatif, hors KPI offline.

### Création de preuve (mode dégradé, sans cosign)

~3,1 s par preuve avec soumission OTS réelle comprise (stamp + verify
initial). La part Python est de quelques ms ; le reste est le réseau OTS.
La mesure « création Sigstore < 1 s » exige cosign + OIDC interactif et sera
documentée lors du pilote.

### Interopérabilité Postfix (50 messages)

Boucle complète : signature → SMTP réel (Postfix 3.x, conteneur
boky/postfix) → livraison locale `/var/mail/rcpt` (en-têtes Received,
Delivered-To, Return-Path ajoutés par le MTA) → `gwyl-mail check` sur chaque
message délivré. **50/50 vérifiés (100 %)** en profil strict — les en-têtes
ajoutés par le MTA ne touchent pas les en-têtes canoniques.

Reproduire : `python scripts/interop_postfix.py --count 50 --docker`

### Overhead embarqué

Preuve DSSE dégradée + vrai timbre OTS pending : **~4,4 Ko** ajoutés au
message (json ~3,3 Ko + timbre OTS ~0,9 Ko). Avec bundle Sigstore complet
(cosign), prévoir ~15-20 Ko — reste sous le seuil de 50 Ko (mesure au pilote).

## Non-mesurés (reportés au pilote)

- **Gmail / Outlook** : la procédure manuelle (envoi signé depuis un compte
  réel, réception, `check`) est documentée dans `docs/PILOT_GUIDE.md` ; les
  fournisseurs grand public réécrivant parfois le HTML, le profil `relaxed`
  est recommandé pour ces tests.
- **Confirmation OTS 48h** : nécessite une fenêtre d'observation de 48h —
  tâche du pilote (upgrade-ots puis re-check).
