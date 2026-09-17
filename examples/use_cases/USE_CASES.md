# Cas d'usage — GWyl Mail

Trois scénarios concrets pour l'intégrité de courrier vérifiable.
Les scripts utilisent la CLI (`sign` / `check`) et les exemples EML du dépôt.

## 1. Preuve d'intégrité contractuelle (expéditeur)

Vous envoyez une proposition commerciale par email et voulez pouvoir prouver
plus tard qu'elle n'a pas été modifiée.

```bash
gwyl-mail sign proposition.eml --identity vous@entreprise.fr -o proposition_signee.eml
# envoi de proposition_signee.eml depuis votre client habituel
```

La preuve (hash, signature Sigstore, ancrage Bitcoin en ~48h) voyage avec le
message. En cas de litige : `gwyl-mail check` sur le message reçu prouve
l'intégrité, OpenTimestamps prouve la date d'existence.

## 2. Vérification par le destinataire

Vous recevez un message marqué `X-GWyl-Proof` (ou avec gwylproof.json joint).

```bash
gwyl-mail check recu.eml --strict --expect-identity expediteur@connu.fr
# après ~48h pour l'ancrage Bitcoin :
gwyl-mail upgrade-ots .gwyl_mail/inbox/<ts>/gwylproof.ots && gwyl-mail check recu.eml
```

## 3. Archive à valeur probante

Conservez le .eml reçu + sa pièce jointe gwylproof.ots : la vérification est
possible offline indéfiniment (le hash canonique ne dépend d'aucun service),
et l'ancrage Bitcoin se vérifie sans tiers de confiance.

---

Voir `docs/INTEGRATION.md` pour le format d'embarquement et la tolérance MTA,
et lancer `examples/run_examples.sh` pour une démonstration complète.
