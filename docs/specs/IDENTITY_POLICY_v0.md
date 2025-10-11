# GWyl Mail - Politique d'identité v0

**Version**: 0.1.0
**Date**: 2025-01-11
**Status**: Draft
**Auteurs**: Claude Code + Zack

---

## 1. Objectif

Définir comment lier l'identité **email** (header `From:`) à l'identité **cryptographique** (certificat Sigstore).

### Problème résolu

```
Email header:     From: alice@company.com
Sigstore cert:    alice@company.com  ✅ Match
                                     → OK

Email header:     From: noreply@company.com
Sigstore cert:    alice@company.com  ❌ Mismatch
                                     → Rejet ? Ou tolérance ?
```

**Solution**: Politique configurable avec modes `warn` → `strict`.

---

## 2. Format de configuration

### 2.1 Fichier `.gwyl_mail/identity_policy.yml`

```yaml
# GWyl Mail - Identity Policy v0

version: "0.1.0"

# Mode d'enforcement
enforcement_mode: warn  # warn | strict

# OIDC issuers autorisés
allowed_issuers:
  - https://accounts.google.com
  - https://login.microsoftonline.com
  - https://github.com/login/oauth

# Domaines email autorisés
allowed_domains:
  - company.com
  - partner.org
  - trusted-vendor.net

# Aliases (optionnel v0)
aliases:
  alice@company.com:
    allowed_aliases:
      - noreply@company.com
      - support@company.com
    admin_signature: "a3f7b2e9d1c4f5a6b8c9d0e1f2a3b4c5..."  # Sigstore proof
    created_at: "2025-01-11T10:00:00Z"

  bob@company.com:
    allowed_aliases:
      - info@company.com
    admin_signature: "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9..."
    created_at: "2025-01-11T10:30:00Z"

# Règles de validation
validation_rules:
  - name: from_matches_cert
    required: true
    tolerance: exact  # exact | domain | alias
    action: reject    # reject | warn | log

  - name: issuer_whitelist
    required: true
    action: reject

  - name: domain_whitelist
    required: true
    action: reject

# Logging
audit_log: .gwyl_mail/identity_audit.jsonl
log_level: info  # debug | info | warn | error
```

---

### 2.2 Signature et vérification de la politique (DSSE/GPG)

Objectif: garantir l'authenticité et l’intégrité de la politique appliquée.

- Format recommandé: enveloppe DSSE signée par clé opérateur/admin
- Clé pinée: `public_key_id` (ou ancrée via Sigstore)
- Stockage: `.gwyl_mail/identity_policy.yml` + `.gwyl_mail/identity_policy.yml.dsse`

Vérification:
```bash
dsse-verify \
  --key public_key.pem \
  --envelope .gwyl_mail/identity_policy.yml.dsse \
  --payload .gwyl_mail/identity_policy.yml
```

Comportement:
- Mode `strict`: fail-closed si la signature est invalide/absente
- Mode `warn`: log l’événement et continue (à utiliser en phase de découverte)

---

### 2.3 Résolution adresse (From vs Sender)

Règle de résolution:
- Utiliser `Sender:` s’il est présent; sinon `From:`
- Extraire `addr-spec` (RFC 5322) en préservant le local-part
- Normaliser le domaine en lowercase (ex: Alice@EXAMPLE.com → Alice@example.com)

Comparaison identité:
- Comparer l’adresse résolue avec `cert_subject` (ou appliquer tolérance/domain/alias selon `validation_rules`)

---

## 3. Modes d'enforcement

### 3.1 Mode `warn` (défaut v0)

**Comportement**: Log les violations, mais accepte le message.

```python
def verify_identity_warn(from_email: str, cert_subject: str, policy: dict):
    """Mode warn: log seulement"""

    if from_email != cert_subject:
        # Log violation
        log_identity_mismatch(
            from_email=from_email,
            cert_subject=cert_subject,
            severity='WARNING'
        )

        # Mais accepter quand même
        return True  # ✅ OK (avec warning)

    return True
```

**Usage**: Phase de déploiement, découverte des cas edge.

---

### 3.2 Mode `strict` (prod)

**Comportement**: Rejette si violation.

```python
def verify_identity_strict(from_email: str, cert_subject: str, policy: dict):
    """Mode strict: rejette si mismatch"""

    if from_email != cert_subject:
        # Check aliases
        if not is_allowed_alias(from_email, cert_subject, policy):
            raise IdentityMismatchError(
                f"From {from_email} does not match cert {cert_subject} "
                f"and is not in allowed aliases"
            )

    return True
```

**Usage**: Production après phase warn.

---

## 4. Règles de validation

### 4.1 Règle `from_matches_cert`

**Objectif**: Vérifier cohérence `From:` ↔ `cert_subject`.

#### Tolérance `exact`

```python
def validate_exact(from_email: str, cert_subject: str) -> bool:
    """Match exact requis"""
    return from_email.lower() == cert_subject.lower()
```

**Exemple**:
- `From: alice@company.com` + `cert: alice@company.com` → ✅
- `From: Alice@Company.com` + `cert: alice@company.com` → ✅ (case-insensitive)
- `From: noreply@company.com` + `cert: alice@company.com` → ❌

---

#### Tolérance `domain`

```python
def validate_domain(from_email: str, cert_subject: str) -> bool:
    """Même domaine suffit"""
    from_domain = from_email.split('@')[1].lower()
    cert_domain = cert_subject.split('@')[1].lower()
    return from_domain == cert_domain
```

**Exemple**:
- `From: alice@company.com` + `cert: bob@company.com` → ✅ (même domaine)
- `From: noreply@company.com` + `cert: alice@company.com` → ✅
- `From: alice@external.com` + `cert: alice@company.com` → ❌

---

#### Tolérance `alias`

```python
def validate_alias(from_email: str, cert_subject: str, policy: dict) -> bool:
    """Utilise mappings aliases"""

    # 1. Match exact
    if from_email.lower() == cert_subject.lower():
        return True

    # 2. Check aliases
    if cert_subject in policy.get('aliases', {}):
        allowed = policy['aliases'][cert_subject]['allowed_aliases']
        if from_email.lower() in [a.lower() for a in allowed]:
            # Vérifier signature admin
            if verify_alias_signature(cert_subject, policy):
                return True

    return False
```

**Exemple**:
```yaml
aliases:
  alice@company.com:
    allowed_aliases:
      - noreply@company.com
      - support@company.com
    admin_signature: "..."
```

- `From: noreply@company.com` + `cert: alice@company.com` → ✅ (alias autorisé)
- `From: spam@company.com` + `cert: alice@company.com` → ❌ (pas dans aliases)

---

### 4.2 Règle `issuer_whitelist`

**Objectif**: Restreindre les OIDC issuers autorisés.

```python
def validate_issuer(cert_issuer: str, policy: dict) -> bool:
    """Issuer dans whitelist"""
    allowed = policy.get('allowed_issuers', [])

    if not allowed:
        return True  # Pas de restriction

    # Check match
    for issuer_pattern in allowed:
        if issuer_pattern in cert_issuer:
            return True

    return False
```

**Exemple**:
```yaml
allowed_issuers:
  - https://accounts.google.com
  - https://login.microsoftonline.com
```

- `cert_issuer: https://accounts.google.com` → ✅
- `cert_issuer: https://github.com/login/oauth` → ❌ (pas autorisé)

---

### 4.3 Règle `domain_whitelist`

**Objectif**: Restreindre domaines email autorisés.

```python
def validate_domain_whitelist(from_email: str, policy: dict) -> bool:
    """Domaine dans whitelist"""
    allowed_domains = policy.get('allowed_domains', [])

    if not allowed_domains:
        return True  # Pas de restriction

    from_domain = from_email.split('@')[1].lower()

    return from_domain in [d.lower() for d in allowed_domains]
```

**Exemple**:
```yaml
allowed_domains:
  - company.com
  - partner.org
```

- `From: alice@company.com` → ✅
- `From: bob@partner.org` → ✅
- `From: eve@evil.com` → ❌

---

## 5. Gestion des aliases

### 5.1 Création d'alias (admin)

```python
def create_alias_mapping(
    primary_identity: str,
    alias_email: str,
    admin_identity: str
) -> dict:
    """
    Créer mapping alias signé par admin

    Args:
        primary_identity: alice@company.com (cert Sigstore)
        alias_email: noreply@company.com (From: autorisé)
        admin_identity: admin@company.com (signataire)

    Returns:
        Alias mapping avec signature admin
    """

    # 1. Construire mapping
    mapping = {
        'primary_identity': primary_identity,
        'alias_email': alias_email,
        'created_at': utcnow_iso(),
        'created_by': admin_identity
    }

    # 2. Hash mapping
    mapping_hash = sha256(json.dumps(mapping, sort_keys=True).encode())

    # 3. Signer avec Sigstore (admin)
    admin_signature = sign_with_sigstore(
        data=mapping_hash,
        identity=admin_identity
    )

    # 4. Ajouter signature
    # Enregistrer enveloppe DSSE de signature admin (chemin ou objet)
    mapping['admin_signature'] = admin_signature.bundle_path

    return mapping

# Usage
alias = create_alias_mapping(
    primary_identity='alice@company.com',
    alias_email='noreply@company.com',
    admin_identity='admin@company.com'
)

# Ajouter à policy.yml
# aliases:
#   alice@company.com:
#     allowed_aliases:
#       - noreply@company.com
#     admin_signature: "path/to/bundle"
#     created_at: "2025-01-11T10:00:00Z"
```

---

### 5.2 Vérification alias

```python
def verify_alias_signature(primary_identity: str, policy: dict) -> bool:
    """Vérifier signature admin de l'alias"""

    if primary_identity not in policy.get('aliases', {}):
        return False

    alias_config = policy['aliases'][primary_identity]

    # Reconstruire mapping
    mapping = {
        'primary_identity': primary_identity,
        'alias_email': alias_config['allowed_aliases'][0],  # Simplification
        'created_at': alias_config['created_at'],
        'created_by': 'admin@company.com'  # À stocker dans config
    }

    mapping_hash = sha256(json.dumps(mapping, sort_keys=True).encode())

    # Vérifier signature admin
    return verify_sigstore_bundle(
        bundle_path=alias_config['admin_signature'],
        expected_data=mapping_hash
)

```

**Vérification d’un alias (DSSE)**:
```python
def verify_alias_mapping(mapping: dict, admin_public_key: bytes) -> bool:
    """Vérifier la signature DSSE du mapping d’alias"""
    envelope_path = mapping['admin_signature']
    payload = {
        'primary_identity': mapping['primary_identity'],
        'alias_email': mapping['alias_email'],
        'created_at': mapping['created_at'],
        'created_by': mapping['created_by']
    }

    payload_canonical = json.dumps(payload, sort_keys=True).encode()
    # dsse_verify(envelope_path, admin_public_key, payload_canonical) → True/False
    return True  # Exemple: stub
```

---

## 6. Workflow complet

### 6.1 Vérification message

```python
def verify_message_identity(
    message: EmailMessage,
    sigstore_proof: dict,
    policy: dict
) -> VerificationResult:
    """
    Vérifier identité complète d'un message

    Checks:
    1. From matches cert (selon tolérance)
    2. Issuer whitelist
    3. Domain whitelist
    4. Alias signature (si applicable)
    """

    from_email = extract_email(message['From'])
    cert_subject = sigstore_proof['cert_subject']
    cert_issuer = sigstore_proof['cert_issuer']

    results = {}

    # 1. From ↔ cert
    tolerance = policy['validation_rules'][0]['tolerance']

    if tolerance == 'exact':
        results['from_cert'] = validate_exact(from_email, cert_subject)
    elif tolerance == 'domain':
        results['from_cert'] = validate_domain(from_email, cert_subject)
    elif tolerance == 'alias':
        results['from_cert'] = validate_alias(from_email, cert_subject, policy)

    # 2. Issuer whitelist
    results['issuer'] = validate_issuer(cert_issuer, policy)

    # 3. Domain whitelist
    results['domain'] = validate_domain_whitelist(from_email, policy)

    # 4. Decision
    enforcement = policy.get('enforcement_mode', 'warn')

    if not all(results.values()):
        if enforcement == 'strict':
            raise IdentityPolicyViolation(
                f"Identity policy violation: {results}"
            )
        else:
            # warn mode: log seulement
            log_policy_violation(from_email, cert_subject, results)

    return VerificationResult(
        valid=all(results.values()),
        enforcement=enforcement,
        details=results
    )
```

---

### 6.2 Migration warn → strict

**Étapes recommandées**:

```bash
# 1. Démarrer en mode warn (découverte)
enforcement_mode: warn

# Analyser logs pendant 1-2 semaines
cat .gwyl_mail/identity_audit.jsonl | grep WARNING

# 2. Identifier cas légitimes
# Exemple: noreply@company.com utilisé par alice@company.com

# 3. Créer aliases
python gwyl_mail_admin.py create-alias \
  --primary alice@company.com \
  --alias noreply@company.com \
  --admin admin@company.com

# 4. Mettre à jour policy
vim .gwyl_mail/identity_policy.yml

# 5. Passer en strict
enforcement_mode: strict

# 6. Valider
make test-identity-policy
```

---

### 6.3 Exceptions (break-glass, identités de service)

Break-glass:
- Activation via variable d’environnement (ex: `GWYL_IDENTITY_BREAK_GLASS=1`)
- Effet: bypass temporaire de l’enforcement avec log obligatoire (niveau ERROR)
- Contenu log: timestamp, from, cert_subject, issuer, rule violée, opérateur
- Alerte recommandée si politique en mode strict

Identités de service (CI/Bots):
- Whitelist explicite (cert_subject ou domaine) dans `allowed_identities`
- Scopes limités (ex: envoi interne uniquement)
- Audit renforcé (événements dédiés dans l’audit log)

---

## 7. Cas d'usage

### 7.1 Entreprise mono-domaine

```yaml
# Configuration simple
enforcement_mode: strict

allowed_issuers:
  - https://login.microsoftonline.com  # Azure AD

allowed_domains:
  - company.com

validation_rules:
  - name: from_matches_cert
    tolerance: domain  # Même domaine suffit
```

**Comportement**:
- `From: alice@company.com` + `cert: alice@company.com` → ✅
- `From: noreply@company.com` + `cert: bob@company.com` → ✅ (même domaine)
- `From: alice@external.com` + `cert: alice@company.com` → ❌

---

### 7.2 Entreprise multi-domaines

```yaml
enforcement_mode: strict

allowed_issuers:
  - https://accounts.google.com
  - https://login.microsoftonline.com

allowed_domains:
  - company.com
  - subsidiary.com
  - partner.org

validation_rules:
  - name: from_matches_cert
    tolerance: exact  # Match strict

aliases:
  alice@company.com:
    allowed_aliases:
      - noreply@company.com
      - alice@subsidiary.com  # Multi-domaine OK
```

---

### 7.3 Open source / communauté

```yaml
enforcement_mode: warn  # Plus permissif

allowed_issuers:
  - https://accounts.google.com
  - https://github.com/login/oauth
  - https://gitlab.com/oauth

allowed_domains: []  # Tous domaines OK

validation_rules:
  - name: from_matches_cert
    tolerance: exact
    action: warn  # Log seulement

# Identities de service (CI/Bots)
allowed_identities:
  - ci-bot@project.org
  - release@project.org
```

---

## 8. Audit trail

### 8.1 Format log `.gwyl_mail/identity_audit.jsonl`

```json
{"timestamp": "2025-01-11T14:30:22Z", "level": "WARNING", "event": "identity_mismatch", "from": "noreply@company.com", "cert_subject": "alice@company.com", "enforcement": "warn", "action": "accepted"}

{"timestamp": "2025-01-11T14:32:15Z", "level": "ERROR", "event": "identity_mismatch", "from": "eve@evil.com", "cert_subject": "alice@company.com", "enforcement": "strict", "action": "rejected"}

{"timestamp": "2025-01-11T14:35:00Z", "level": "INFO", "event": "alias_used", "from": "noreply@company.com", "cert_subject": "alice@company.com", "alias_verified": true, "action": "accepted"}

{"timestamp": "2025-01-11T14:40:00Z", "level": "ERROR", "event": "issuer_not_allowed", "cert_issuer": "https://untrusted-oidc.com", "enforcement": "strict", "action": "rejected"}
```

---

### 8.2 Analyse logs

```bash
# Violations par jour
cat .gwyl_mail/identity_audit.jsonl | grep WARNING | \
  jq -r '.timestamp[:10]' | sort | uniq -c

# Top violateurs
cat .gwyl_mail/identity_audit.jsonl | grep identity_mismatch | \
  jq -r '"\(.from) -> \(.cert_subject)"' | sort | uniq -c | sort -rn

# Aliases les plus utilisés
cat .gwyl_mail/identity_audit.jsonl | grep alias_used | \
  jq -r .from | sort | uniq -c | sort -rn
```

---

## 9. Sécurité

### 9.1 Protection contre usurpation

**Scénario**: Attaquant avec accès OIDC provider compromis.

**Mitigation**:
```yaml
# Limiter issuers à ceux contrôlés
allowed_issuers:
  - https://sso.company.com  # SSO interne seulement

# Pas de providers publics en prod
# - https://accounts.google.com  # ❌ Trop permissif
```

---

### 9.2 Révocation alias

```python
def revoke_alias(primary_identity: str, alias_email: str, admin_identity: str):
    """Révoquer un alias (admin)"""

    # 1. Charger policy
    policy = load_policy()

    # 2. Retirer alias
    if primary_identity in policy['aliases']:
        aliases = policy['aliases'][primary_identity]['allowed_aliases']
        if alias_email in aliases:
            aliases.remove(alias_email)

    # 3. Logger révocation
    log_alias_revocation(primary_identity, alias_email, admin_identity)

    # 4. Sauver policy
    save_policy(policy)

# Usage
revoke_alias('alice@company.com', 'noreply@company.com', 'admin@company.com')
```

---

## 10. Implémentation de référence

```python
# gwyl_mail/identity_policy.py

import yaml
from pathlib import Path
from dataclasses import dataclass

@dataclass
class IdentityPolicyConfig:
    enforcement_mode: str
    allowed_issuers: list
    allowed_domains: list
    aliases: dict
    validation_rules: list

class IdentityPolicy:
    """Gestion politique d'identité"""

    def __init__(self, config_file: Path):
        with config_file.open() as f:
            config = yaml.safe_load(f)

        self.config = IdentityPolicyConfig(
            enforcement_mode=config.get('enforcement_mode', 'warn'),
            allowed_issuers=config.get('allowed_issuers', []),
            allowed_domains=config.get('allowed_domains', []),
            aliases=config.get('aliases', {}),
            validation_rules=config.get('validation_rules', [])
        )

    def verify(self, from_email: str, cert_subject: str, cert_issuer: str) -> bool:
        """Vérifier identité"""

        # 1. Tolerance check
        tolerance = self._get_tolerance()

        if tolerance == 'exact':
            from_cert_ok = (from_email.lower() == cert_subject.lower())
        elif tolerance == 'domain':
            from_cert_ok = self._same_domain(from_email, cert_subject)
        elif tolerance == 'alias':
            from_cert_ok = self._check_alias(from_email, cert_subject)
        else:
            from_cert_ok = False

        # 2. Issuer whitelist
        issuer_ok = self._check_issuer(cert_issuer)

        # 3. Domain whitelist
        domain_ok = self._check_domain(from_email)

        # 4. Enforcement
        if not (from_cert_ok and issuer_ok and domain_ok):
            if self.config.enforcement_mode == 'strict':
                raise IdentityPolicyViolation(...)
            else:
                self._log_warning(from_email, cert_subject)

        return True

    def _get_tolerance(self) -> str:
        for rule in self.config.validation_rules:
            if rule['name'] == 'from_matches_cert':
                return rule.get('tolerance', 'exact')
        return 'exact'

    def _same_domain(self, email1: str, email2: str) -> bool:
        domain1 = email1.split('@')[1].lower()
        domain2 = email2.split('@')[1].lower()
        return domain1 == domain2

    def _check_alias(self, from_email: str, cert_subject: str) -> bool:
        if cert_subject in self.config.aliases:
            allowed = self.config.aliases[cert_subject].get('allowed_aliases', [])
            return from_email.lower() in [a.lower() for a in allowed]
        return from_email.lower() == cert_subject.lower()

    def _check_issuer(self, cert_issuer: str) -> bool:
        if not self.config.allowed_issuers:
            return True
        return any(issuer in cert_issuer for issuer in self.config.allowed_issuers)

    def _check_domain(self, from_email: str) -> bool:
        if not self.config.allowed_domains:
            return True
        domain = from_email.split('@')[1].lower()
        return domain in [d.lower() for d in self.config.allowed_domains]
```

---

## 11. Changelog

### v0.1.0 (2025-01-11)
- Initial draft
- Modes: warn / strict
- Tolérances: exact / domain / alias
- Whitelist: issuers / domains
- Aliases avec signature admin
- Audit log JSONL

---

## 12. Références

- **Sigstore OIDC**: https://docs.sigstore.dev/cosign/openid_signing/
- **YAML**: https://yaml.org/spec/1.2/spec.html

---

---

## 13. Contributeurs

**Conception et spécification**: Zack, Claude (Anthropic), ChatGPT (OpenAI)

**Remerciements**: ChatGPT pour l'analyse des défis de mapping identité email ↔ certificat Sigstore et la proposition de modes d'enforcement progressifs (warn→strict).

---

**Fin du document IDENTITY_POLICY_v0.md**
# Identities autorisées (CI/Bots)
allowed_identities:
  - ci-bot@company.com
  - build@company.com
