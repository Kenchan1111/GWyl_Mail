#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] Canonical hash (plain text)"
conda run -n GWYL_Env python -m gwyl_mail.cli canonical-hash examples/sample_plain_text.eml

echo "[2/5] Canonical hash (HTML-only)"
conda run -n GWYL_Env python -m gwyl_mail.cli canonical-hash examples/sample_html.eml || true

echo "[3/5] Canonical hash (attachments)"
conda run -n GWYL_Env python -m gwyl_mail.cli canonical-hash examples/sample_with_attachments.eml

echo "[4/5] Create proof (plain text)"
OUT_PROOF=".gwyl_mail/proofs/sample_plain_text.proof.json"
conda run -n GWYL_Env python -m gwyl_mail.cli create-proof \
  examples/sample_plain_text.eml \
  --identity alice@company.com \
  --out "$OUT_PROOF"
cat "$OUT_PROOF" | jq '.canonical, .sigstore, .opentimestamps, .verification' || true

echo "[5/5] Integrity check of repository baseline"
conda run -n GWYL_Env python /home/zack/GWyl_Integrity/unified_integrity.py check

echo "Done."

