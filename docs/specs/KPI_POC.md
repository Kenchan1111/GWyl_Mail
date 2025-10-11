# GWyl Mail - KPIs Proof of Concept

**Version**: 0.1.0
**Date**: 2025-01-11
**Status**: Draft
**Auteurs**: Claude Code + Zack

---

## 1. Objectifs du PoC

Démontrer la **faisabilité technique** de GWyl Mail avec métriques mesurables.

### Critères de succès

**Le PoC est validé si**:
1. ✅ Interopérabilité SMTP/IMAP ≥ 95%
2. ✅ Overhead proof < 50 KB/message
3. ✅ Performance vérification < 150 ms
4. ✅ Fiabilité OTS ≥ 90%
5. ✅ Cohérence temporelle 100%

---

## 2. KPIs Interopérabilité

### 2.1 Providers testés

| Provider | Type | Version | Priorité |
|----------|------|---------|----------|
| **Gmail** | Cloud | Current | Haute |
| **Outlook.com** | Cloud | Current | Haute |
| **Postfix** | Self-hosted | 3.8+ | Moyenne |
| Protonmail | Cloud | Current | Basse |
| Exchange | Enterprise | 2019+ | Basse |

**PoC minimum**: Gmail + Outlook + Postfix

---

### 2.2 Métrique: Taux de vérification réussie

**Formule**:
```
Taux_succès = (Messages_vérifiés_OK / Messages_envoyés) × 100
```

**Objectif**: ≥ 95%

**Test**:
```python
def test_interop_success_rate():
    """
    Test interop sur 3 providers × 50 messages
    """
    providers = ['gmail', 'outlook', 'postfix']
    total_sent = 0
    total_verified = 0

    for provider in providers:
        for i in range(50):
            # 1. Créer message + proof
            msg = create_test_message(i)
            proof = create_gwyl_proof(msg, 'alice@company.com')

            # 2. Envoyer via provider
            send_email(msg, proof, provider)
            total_sent += 1

            # 3. Recevoir
            received = receive_email(provider, timeout=30)

            # 4. Vérifier
            if verify_gwyl_proof(received, proof):
                total_verified += 1

    success_rate = (total_verified / total_sent) * 100

    print(f"Success rate: {success_rate:.1f}%")
    assert success_rate >= 95.0, f"FAIL: {success_rate}% < 95%"
```

**Résultat attendu**:
```
Provider: gmail     → 49/50 OK (98%)
Provider: outlook   → 48/50 OK (96%)
Provider: postfix   → 50/50 OK (100%)
─────────────────────────────────────
TOTAL:              → 147/150 OK (98%) ✅
```

---

### 4.3 Upgrade OTS et idempotence

Objectif: tous les proofs `PENDING` sont upgradés automatiquement (cron) et l’opération est idempotente.

Tests:
- Réexécuter `upgrade-ots` ne modifie pas les entrées déjà `CONFIRMED`
- Statistiques: nombre d’upgrades, délais moyens, distribution de `bitcoin_block`

Logs:
- Ajouter reason codes: `ots_submit_failed`, `ots_upgrade_failed`, `ots_verify_failed`

---

### 2.3 Métrique: Scénarios edge cases

**Tests spécifiques**:

| Scénario | Description | Objectif |
|----------|-------------|----------|
| **Encoding** | QP → Base64 transformation | Hash stable ✅ |
| **Headers added** | Received:, X-Spam ajoutés | Hash stable ✅ |
| **Line endings** | CRLF ↔ LF | Hash stable ✅ |
| **Attachments reordered** | Ordre modifié par serveur | Hash stable ✅ |
| **HTML-only (inchangé)** | text/html conservé | Hash stable ✅ |
| **Footer MTA injecté** | Disclaimer ajouté | Mismatch attendu ❌ |
| **HTML réécrit** | Balises/format altérés | Mismatch attendu ❌ |

**Test**:
```python
def test_edge_cases():
    """Test transformations SMTP courantes"""

    # 1. Encoding transformation
    msg_qp = create_message(encoding='quoted-printable')
    msg_b64 = create_message(encoding='base64')
    assert hash(msg_qp) == hash(msg_b64)  # ✅

    # 2. Headers added
    msg_clean = create_message()
    msg_with_headers = add_received_headers(msg_clean)
    assert hash(msg_clean) == hash(msg_with_headers)  # ✅

    # ... (autres scénarios)
```

---

## 3. KPIs Performance

### 3.1 Métrique: Overhead taille proof

**Formule**:
```
Overhead = Taille_proof_JSON + Taille_bundle_sigstore + Taille_ots
```

**Objectif**: < 50 KB total

**Mesure**:
```python
def test_proof_size():
    """Mesurer overhead proof"""

    msg = create_test_message()
    proof = create_gwyl_proof(msg, 'alice@company.com')

    # Tailles
    proof_json_size = len(json.dumps(proof))
    bundle_size = Path(proof['sigstore']['bundle_path']).stat().st_size
    ots_size = Path(proof['opentimestamps']['proof_file']).stat().st_size

    total_size = proof_json_size + bundle_size + ots_size

    print(f"Proof JSON:   {proof_json_size:>8} bytes")
    print(f"Sigstore bundle: {bundle_size:>8} bytes")
    print(f"OTS proof:    {ots_size:>8} bytes")
    print(f"─────────────────────────────")
    print(f"TOTAL:        {total_size:>8} bytes ({total_size/1024:.1f} KB)")

    assert total_size < 50 * 1024, f"FAIL: {total_size} bytes > 50 KB"
```

**Résultat attendu**:
```
Proof JSON:        2048 bytes
Sigstore bundle:  15360 bytes
OTS proof:         1024 bytes
─────────────────────────────
TOTAL:            18432 bytes (18.0 KB) ✅
```

---

### 3.2 Métrique: Latence création proof

**Objectif**:
- Sigstore: < 1s
- OTS submit: < 5s

**Test**:
```python
def test_proof_creation_latency():
    """Mesurer latence création"""

    msg = create_test_message()

    # 1. Sigstore
    start = time.time()
    sigstore_proof = sign_and_timestamp(msg.hash, 'alice@company.com')
    sigstore_latency = time.time() - start

    print(f"Sigstore: {sigstore_latency*1000:.0f} ms")
    assert sigstore_latency < 1.0  # < 1s

    # 2. OTS
    start = time.time()
    ots_file = ots_manager.submit(msg.hash)
    ots_latency = time.time() - start

    print(f"OTS submit: {ots_latency*1000:.0f} ms")
    assert ots_latency < 5.0  # < 5s
```

**Résultat attendu**:
```
Sigstore:    450 ms ✅
OTS submit:  1200 ms ✅
```

---

### 3.3 Métrique: Latence vérification offline

**Objectif**: < 150 ms

**Test**:
```python
def test_verification_latency():
    """Mesurer latence vérification offline"""

    msg = create_test_message()
    proof = create_gwyl_proof(msg, 'alice@company.com')

    # Vérification complète
    start = time.time()
    result = verify_gwyl_proof(msg, proof)
    latency = time.time() - start

    print(f"Verification: {latency*1000:.0f} ms")
    assert latency < 0.150  # < 150 ms
    assert result['valid'] == True
```

**Résultat attendu**:
```
Verification: 87 ms ✅
```

---

### 3.4 Hachage en streaming / tailles pièces jointes

Objectif: maîtriser l’utilisation CPU/mémoire jusqu’à 25 MB par pièce jointe.

Recommandations:
- Lire les pièces jointes en chunks (ex: 8–64 KiB)
- SHA-256 streaming (pas de chargement complet en mémoire)
- Benchmarks: 1 B → 25 MB, formats: PDF, PNG, DOCX

Métriques à collecter:
- Temps de hash par taille (ms)
- Conso mémoire max (MB)

---

## 4. KPIs Fiabilité

### 4.1 Métrique: Taux confirmation OTS

**Objectif**: ≥ 90% confirmés sous 48h

**Test**:
```python
def test_ots_confirmation_rate():
    """
    Mesurer taux de confirmation OTS

    Test sur 100 submissions
    Window: 48h
    """
    submissions = []

    # 1. Soumettre 100 OTS
    for i in range(100):
        hash_data = f"test_{i}_{time.time()}".encode()
        ots_file = ots_manager.submit(hash_data)
        submissions.append({
            'file': ots_file,
            'submitted_at': time.time()
        })

    # 2. Attendre 48h (en test: mock ou attente réelle)
    time.sleep(48 * 3600)  # Production: cron job

    # 3. Vérifier confirmations
    confirmed = 0
    for sub in submissions:
        status = ots_manager.verify(sub['file'])
        if status.status == 'CONFIRMED':
            confirmed += 1

    confirmation_rate = (confirmed / len(submissions)) * 100

    print(f"OTS confirmation rate: {confirmation_rate:.1f}%")
    assert confirmation_rate >= 90.0
```

**Résultat attendu**:
```
OTS confirmation rate: 94.0% ✅
(94/100 confirmés sous 48h)
```

---

### 4.2 Métrique: Cohérence temporelle

**Objectif**: 100% (delta Rekor ↔ OTS < 24h)

**Test**:
```python
def test_timestamp_coherence():
    """
    Vérifier cohérence Sigstore ↔ OTS

    Test: 50 messages avec OTS confirmé
    """
    coherence_ok = 0
    total = 50

    for i in range(total):
        msg = create_test_message()
        proof = create_gwyl_proof(msg, 'alice@company.com')

        # Attendre confirmation OTS (mock: upgrade direct)
        ots_manager.upgrade(Path(proof['opentimestamps']['proof_file']))
        ots_status = ots_manager.verify(Path(proof['opentimestamps']['proof_file']))

        if ots_status.status == 'CONFIRMED':
            # Vérifier cohérence
            rekor_ts = datetime.fromtimestamp(proof['sigstore']['rekor_timestamp'])
            ots_ts = parse(ots_status.confirmed_at)
            delta = abs((rekor_ts - ots_ts).total_seconds())

            if delta < 86400:  # 24h
                coherence_ok += 1

    coherence_rate = (coherence_ok / total) * 100

    print(f"Coherence rate: {coherence_rate:.1f}%")
    assert coherence_rate == 100.0
```

**Résultat attendu**:
```
Coherence rate: 100.0% ✅
(50/50 avec delta < 24h)
```

---

## 5. KPIs Sécurité

### 5.1 Métrique: Détection tampering

**Objectif**: 100% détection

**Test**:
```python
def test_tampering_detection():
    """
    Test détection modifications

    Scénarios:
    1. Body modifié
    2. Attachment modifié
    3. Header From modifié
    4. Attachment supprimé
    """
    attacks = []

    # 1. Body tampering
    msg = create_test_message()
    proof = create_gwyl_proof(msg, 'alice@company.com')

    msg_tampered = msg.copy()
    msg_tampered.set_content("MODIFIED BODY")

    result = verify_gwyl_proof(msg_tampered, proof)
    attacks.append(('body_tamper', not result['valid']))

    # 2. Attachment tampering
    msg = create_message_with_attachment()
    proof = create_gwyl_proof(msg, 'alice@company.com')

    msg_tampered = replace_attachment(msg, 'malicious.pdf')

    result = verify_gwyl_proof(msg_tampered, proof)
    attacks.append(('attach_tamper', not result['valid']))

    # ... (autres scénarios)

    detection_rate = sum(1 for _, detected in attacks if detected) / len(attacks) * 100

    print(f"Tampering detection: {detection_rate:.1f}%")
    assert detection_rate == 100.0
```

**Résultat attendu**:
```
Body tampering:       DETECTED ✅
Attachment tampering: DETECTED ✅
Header tampering:     DETECTED ✅
Attachment deletion:  DETECTED ✅
─────────────────────────────────
Detection rate: 100.0% ✅
```

---

### 5.2 Métrique: Anti-replay efficacité

**Objectif**: 100% détection replay

**Test**:
```python
def test_anti_replay():
    """Test protection replay"""

    replay_protection = ReplayProtection()

    msg = create_test_message()
    proof = create_gwyl_proof(msg, 'alice@company.com')

    # 1. Première vérification (OK)
    replay_protection.verify_no_replay(proof)  # ✅

    # 2. Replay (doit échouer)
    try:
        replay_protection.verify_no_replay(proof)
        assert False, "Replay not detected!"
    except ReplayError:
        print("Replay detected ✅")

    # 3. Proof expiré
    proof['anti_replay']['expires_at'] = '2020-01-01T00:00:00Z'

    try:
        replay_protection.verify_no_replay(proof)
        assert False, "Expired proof not detected!"
    except ReplayError:
        print("Expiration detected ✅")
```

---

## 6. Tableau de bord PoC

### 6.1 Commande de test globale

```bash
make test-poc
```

**Exécute**:
```python
# tests/test_poc.py

def run_poc_validation():
    """Suite complète tests PoC"""

    results = {}

    # 1. Interopérabilité
    results['interop_rate'] = test_interop_success_rate()

    # 2. Performance
    results['proof_size'] = test_proof_size()
    results['sigstore_latency'] = test_sigstore_latency()
    results['verify_latency'] = test_verification_latency()

    # 3. Fiabilité
    results['ots_confirmation'] = test_ots_confirmation_rate()
    results['coherence'] = test_timestamp_coherence()

    # 4. Sécurité
    results['tampering_detection'] = test_tampering_detection()
    results['anti_replay'] = test_anti_replay()

    # Rapport
    print_poc_report(results)

    return all_tests_passed(results)
```

---

### 6.2 Rapport résultat

```
═══════════════════════════════════════════════════════════
           GWYL MAIL - POC VALIDATION REPORT
═══════════════════════════════════════════════════════════

📊 INTEROPERABILITÉ
──────────────────────────────────────────────────────────
  Providers testés:         3 (Gmail, Outlook, Postfix)
  Messages envoyés:        150
  Messages vérifiés:       147
  Taux de succès:          98.0% ✅ (objectif: ≥95%)

⚡ PERFORMANCE
──────────────────────────────────────────────────────────
  Overhead proof:          18.0 KB ✅ (objectif: <50 KB)
  Latence Sigstore:       450 ms ✅ (objectif: <1s)
  Latence OTS submit:    1200 ms ✅ (objectif: <5s)
  Latence vérification:    87 ms ✅ (objectif: <150ms)

🔒 FIABILITÉ
──────────────────────────────────────────────────────────
  OTS confirmation (48h):  94.0% ✅ (objectif: ≥90%)
  Cohérence temporelle:   100.0% ✅ (objectif: 100%)

🛡️  SÉCURITÉ
──────────────────────────────────────────────────────────
  Tampering detection:    100.0% ✅
  Anti-replay efficacité: 100.0% ✅

═══════════════════════════════════════════════════════════
VERDICT: ✅ POC VALIDÉ (8/8 KPIs atteints)
═══════════════════════════════════════════════════════════

Prochaines étapes recommandées:
  1. Phase pilote (10 utilisateurs, 1 mois)
  2. Monitoring production (métriques continues)
  3. Optimisations performance (si nécessaire)
  4. Documentation utilisateur
```

---

## 7. Métriques continues (post-PoC)

### 7.1 Monitoring production

```yaml
# .gwyl_mail/metrics.yml

metrics:
  interop_success_rate:
    window: 24h
    alert_threshold: 90  # Alert si < 90%

  proof_creation_p95:
    window: 1h
    alert_threshold: 2000  # Alert si P95 > 2s

  ots_confirmation_rate:
    window: 7d
    alert_threshold: 85  # Alert si < 85%

  storage_size:
    window: 30d
    alert_threshold: 10GB  # Alert si > 10GB
```

---

## 6. Diagnostics — Reason codes

Normaliser les raisons d’échec pour faciliter l’analyse:

- `canonical_mismatch`
- `sigstore_verify_failed`
- `ots_pending`
- `ots_verify_failed`
- `identity_mismatch`
- `issuer_not_allowed`
- `domain_not_allowed`
- `coherence_failed`
- `replay_detected`

Chaque vérification journalise le reason code + contexte (message_id, provider, timestamps) dans un audit JSONL.

---

### 7.2 Dashboard Grafana

```promql
# Taux de succès (24h)
sum(rate(gwyl_mail_verify_success_total[24h])) /
sum(rate(gwyl_mail_verify_attempts_total[24h])) * 100

# Latence P95 vérification
histogram_quantile(0.95,
  rate(gwyl_mail_verify_duration_seconds_bucket[5m])
) * 1000

# OTS confirmation rate (7d)
sum(gwyl_mail_ots_confirmed_total[7d]) /
sum(gwyl_mail_ots_submitted_total[7d]) * 100
```

---

## 8. Critères Go/NoGo

### 8.1 Go (PoC validé)

**Conditions**:
- ✅ Interop ≥ 95%
- ✅ Overhead < 50 KB
- ✅ Vérification < 150 ms
- ✅ OTS confirmation ≥ 90%
- ✅ Cohérence 100%
- ✅ Tampering detection 100%

**Action**: Passer Phase 1 (pilote)

---

### 8.2 NoGo (PoC échoué)

**Conditions**:
- ❌ Interop < 95%
- ❌ Overhead > 100 KB
- ❌ Vérification > 500 ms
- ❌ OTS confirmation < 80%

**Action**: Revoir architecture

---

## 9. Changelog

### v0.1.0 (2025-01-11)
- Initial draft
- 8 KPIs définis
- Objectifs chiffrés
- Tests automatisés
- Rapport validation

---

---

## 10. Contributeurs

**Conception et spécification**: Zack, Claude (Anthropic), ChatGPT (OpenAI)

**Remerciements**: ChatGPT pour la définition des KPIs mesurables (95% interop, <50KB overhead, <150ms vérification) et l'analyse de faisabilité du PoC.

---

**Fin du document KPI_POC.md**
