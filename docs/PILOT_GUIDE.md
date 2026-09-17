# Guide du pilote — GWyl Mail v0.3.0

## Destinataire : vérifier un message signé (1 page)

```bash
# 1. Installation unique
python3 -m venv venv && source venv/bin/activate
pip install gwyl-mail opentimestamps-client
gwyl-mail doctor          # doit afficher ✅ pour ots (cosign optionnel pour vérifier)

# 2. Vérification d'un message reçu
gwyl-mail check recu.eml --strict --expect-identité expediteur@connu.fr
```

Lire la sortie :

| Champ | Signification |
|---|---|
| `canonical: true` | le contenu reçu est identique au contenu signé |
| `dsse_signed: true` | la preuve elle-même est signée (Sigstore) |
| `sigstore_bundle: true` | identité + horodatage Rekor vérifiés |
| `ots: true` | ancrage Bitcoin confirmé (attendre ~48h puis `upgrade-ots`) |
| `trust_level` | LOW = hash seul · MEDIUM = +Sigstore · HIGH = +Bitcoin |

Un `trust_level` bas n'est pas une erreur : la preuve a été créée dans un
environnement incomplet. Une falsification du contenu se voit à
`canonical: false` (code retour ≠ 0).

Après ~48h : `gwyl-mail upgrade-ots .gwyl_mail/inbox/<ts>/gwylproof.ots`
puis relancer `check` → `ots: true`.

## Expéditeur : signer avant envoi

```bash
gwyl-mail sign brouillon.eml --identity vous@exemple.fr -o signe.eml
# envoyer signe.eml depuis votre client mail habituel
```

Avec cosign installé + connexion OIDC (navigateur), la preuve est signée ;
sinon le refus est explicite (`--allow-degraded` pour une preuve hash-only).

## Tests manuels Gmail / Outlook (procédure reproductible)

1. Signer `examples/sample_html.eml` avec votre identité réelle.
2. Envoyer le .eml signé : l'importer dans le client (glisser-déposer .eml
   dans Gmail/Outlook « composer » ou envoyer viaThunderbird).
3. Télécharger le message reçu (.eml) côté destinataire.
4. `gwyl-mail check recu.eml` puis, si échec canonical :
   `gwyl-mail check recu.eml --profile-override relaxed` (les webmails
   réécrivent le HTML).
5. Consigner : fournisseur, résultat strict, résultat relaxed, trust_level,
   overhead constaté.

Formulaire de retour pilote : voir `docs/PILOT_FEEDBACK_TEMPLATE.md`.

## Critères de succès du pilote (KPI_POC.md)

- Interop ≥ 95% (Postfix mesuré à 100% — cf. docs/PERFORMANCE.md)
- Confirmation OTS ≥ 90% sous 48h sur 100 soumissions
- Aucun faux négatif de falsification signalé
- Retours UX destinataire qualifiés
