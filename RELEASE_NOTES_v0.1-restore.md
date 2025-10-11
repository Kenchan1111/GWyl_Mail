# Release v0.1-restore

Date (UTC): 2025-10-11

Summary
- Restauration des modules essentiels (`gwyl_mail/*.py`), ajout d’un test unitaire de canonicalisation, et mise en place d’un flux d’intégrité automatisé (script + hooks).
- Baseline signée et ancrée via OpenTimestamps (OTS). Vérifications OK.

What’s new
- Code restauré: `canonical.py`, `cli.py`, `dual_proof.py`, `identity_policy.py`, `ots_manager.py`, `sigstore_timestamp.py`
- Tests: `tests/test_canonical.py` (2 tests OK)
- Scripts intégrité: `Temporary_Integrity/commit_with_integrity.sh`, hooks `pre-commit` et `pre-push`
- Specs consolidées (V0.2/V0.3): canonicalisation stricte, privacy SHA‑256, receipt log, draft sessions

Integrity
- Baseline: `SECURITY_INTEGRITY_BASELINE.sha256`
- OTS proof (baseline): `logs/anchors/ots/init_merkle_*.ots`
- Receipt: `logs/anchors/receipts.jsonl`

Notes
- Cosign installé pour signatures Sigstore (optionnel)
- OTS upgrade à faire manuellement (hook pre‑push le tente automatiquement)

