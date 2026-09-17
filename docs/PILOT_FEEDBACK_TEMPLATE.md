# Formulaire de retour — pilote GWyl Mail

Un retour par message testé. À remplir par les testeurs (expéditeurs et
destinataires) et à renvoyer au coordinateur du pilote.

## Identification

- Testeur : ______  Rôle : ☐ expéditeur ☐ destinataire
- Date/heure d'envoi (UTC) : ______
- Fournisseur messagerie expéditeur : ______ (ex. Gmail, Outlook, Postfix)
- Fournisseur messagerie destinataire : ______
- OS et version Python : ______

## Envoi (expéditeur)

- Commande utilisée : ☐ sign ☐ create-proof  Profil : ☐ strict ☐ relaxed
- cosign installé : ☐ oui ☐ non  Session OIDC réussie : ☐ oui ☐ non ☐ n/a
- Temps de création ressenti : ☐ <5s ☐ 5-30s ☐ >30s
- Taille ajoutée au message (Ko) : ______

## Réception & vérification (destinataire)

- `check` en strict : ☐ OK ☐ échec (raisons : ______)
- Si échec, `--profile-override relaxed` : ☐ OK ☐ échec
- `trust_level` : ☐ LOW ☐ MEDIUM ☐ HIGH
- Après 48h, `ots: true` : ☐ oui ☐ non ☐ pas testé
- Message falsifié volontairement détecté : ☐ oui ☐ non ☐ pas testé

## UX

- Difficulté d'installation (0 facile → 5 bloquant) : ______
- Clarté des messages de la CLI (0-5) : ______
- frein principal : ______

## Bugs / remarques libres

______
