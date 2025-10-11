# GWyl Mail — Examples

This folder contains end-to-end examples to exercise the CLI and the proof flow.

Prerequisites
- Conda environment: `GWYL_Env`
- Run commands from the project root: `/home/zack/GWyl_Mail`

Quick start
```bash
# 1) Compute canonical hash (strict profile) for a plain text message
conda run -n GWYL_Env python -m gwyl_mail.cli canonical-hash examples/sample_plain_text.eml

# 2) Create a dual proof (Sigstore best-effort, OTS pending) for a message
conda run -n GWYL_Env python -m gwyl_mail.cli create-proof \
  examples/sample_plain_text.eml \
  --identity alice@company.com \
  --out .gwyl_mail/proofs/sample_plain_text.proof.json

# 3) Inspect proof
cat .gwyl_mail/proofs/sample_plain_text.proof.json | jq .

# 4) Upgrade OTS (may confirm after some hours)
ots upgrade .gwyl_mail/proofs/ots/*.ots || true

# 5) (Optional) Integrity check of repository baseline
conda run -n GWYL_Env python /home/zack/GWyl_Integrity/unified_integrity.py check
```

Files
- `sample_plain_text.eml` — Simple plain-text email
- `sample_html.eml` — HTML‑only email (strict profile keeps HTML as-is)
- `sample_with_attachments.eml` — Multipart with two attachments
- `sample_policy.yml` — Example identity policy (warn mode)
- `verify_proof_offline.py` — Offline verifier for a proof JSON
- `run_examples.sh` — Helper script to run all the above

Verify a proof offline
```bash
# 1) Create a proof (see above or reuse the sample)
conda run -n GWYL_Env python -m gwyl_mail.cli create-proof \
  examples/sample_plain_text.eml \
  --identity alice@company.com \
  --out .gwyl_mail/proofs/sample_plain_text.proof.json

# 2) Verify offline (canonical + cosign bundle if present + OTS if confirmed)
conda run -n GWYL_Env python examples/verify_proof_offline.py \
  --eml examples/sample_plain_text.eml \
  --proof .gwyl_mail/proofs/sample_plain_text.proof.json
```
