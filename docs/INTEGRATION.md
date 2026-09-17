# Intégration mail — la preuve voyage avec le message (SPRINT 9)

GWyl Mail ne remplace ni SMTP ni votre client mail : la preuve est **embarquée
dans le message lui-même**, donc n'importe quel client/provider la transporte
sans le savoir.

---

## Flux expéditeur → destinataire

```
Expéditeur                                Destinataire
----------                                ------------
gwyl-mail sign brouillon.eml              reçoit le mail normalement
    --identity moi@x.io                       │
    -o signe.eml                              ▼
      │                                   gwyl-mail check recu.eml
      ▼                                       │
envoie signe.eml depuis                    vérification complète :
son client habituel                        hash canonique, signature DSSE,
                                           bundle Sigstore, ancrage OTS
```

Aucun fichier annexe à transférer à la main : le destinataire n'a besoin que
du message reçu et du paquet `gwyl-mail` installé.

---

## Format d'embarquement

Un message signé porte :

| Élément | Rôle |
|---|---|
| En-tête `X-GWyl-Proof: v1` | Marqueur advisory (un MTA peut le retirer — la détection repose sur la pièce jointe) |
| Pièce jointe `gwylproof.json` | Enveloppe DSSE : la preuve signée (hash canonique, métadonnées, anti-replay) |
| Pièce jointe `gwylproof.ots` | Timbre OpenTimestamps (ancrage Bitcoin, pending ~48h à l'envoi) |
| Pièce jointe `gwylbundle.json` | Bundle Sigstore (certificat + entrée Rekor) — présente si la signature a réussi |

**Invariant de hash canonique** : la preuve couvre le message *sans* ses
pièces jointes de preuve. `check` les retire (`strip_proof`) avant de
recalculer le hash. Ajouter/retirer ces pièces jointes ne change pas le hash :
les en-têtes MIME ne sont pas des en-têtes canoniques (from, to, subject,
date, message-id uniquement) et les pièces de preuve ne sont jamais comptées
comme pièces jointes normales.

**Références portables** : dans une preuve embarquée, `sigstore.bundle_path`
et `opentimestamps.proof_file` valent les noms de fichiers des pièces jointes
(`gwylbundle.json`, `gwylproof.ots`), jamais des chemins locaux. La
vérification les résout via `--lookup-dir` (fait automatiquement par
`check`, qui matérialise les pièces jointes dans `.gwyl_mail/inbox/<ts>/`).

---

## Tolérance aux mutations MTA

En transit, les serveurs ajoutent des en-têtes (`Received`, `X-Spam-*`,
`ARC-*`...), replient les longues lignes, réencodent. Les deux profils de
canonicalisation couvrent ces cas :

- **strict** (défaut à la création) : les en-têtes non canoniques sont
  ignorés, le unfolding gère les re-pliements — les mutations d'en-têtes MTA
  passent déjà en strict.
- **relaxed** (`--profile relaxed` à la création, ou `--profile-override
  relaxed` à la vérification) : tolère en plus ~50 en-têtes MTA connus et
  les variations d'espacement.

Toute modification du **corps** est détectée dans tous les profils — c'est le
but.

---

## Cycle de vie de l'ancrage Bitcoin

1. À l'envoi, `gwylproof.ots` est *pending* (soumis aux calendriers OTS).
2. Sous ~48h, la transaction est confirmée dans un bloc Bitcoin.
3. Le destinataire peut alors confirmer : `gwyl-mail upgrade-ots
   .gwyl_mail/inbox/<ts>/gwylproof.ots` puis re-`check` → `ots: true`,
   `trust_level: HIGH`.

---

## Checklist destinataire (une page)

```bash
pip install gwyl-mail opentimestamps-client   # + cosign (GETTING_STARTED.md)
gwyl-mail doctor                              # environnement complet ?
gwyl-mail check recu.eml --strict             # vérification exigeante
```

Sorties clés : `canonical` (intégrité du contenu), `dsse_signed` (preuve
signée), `sigstore_bundle` (identité Rekor), `ots` (ancrage Bitcoin),
`trust_level` (LOW = hash seul, MEDIUM = +Sigstore, HIGH = +Bitcoin).

---

## Limites connues

- La signature DSSE exige cosign + OIDC interactif côté expéditeur.
- Les preuves dégradées (sans cosign/ots) sont signalées `dsse_signed: false`
  et `ots: false` — jamais silencieusement acceptées comme complètes.
- `check` sur un message dont le corps a été réencodé (ex. HTML réécrit par
  un webmail) échoue : c'est une modification réelle du contenu.
