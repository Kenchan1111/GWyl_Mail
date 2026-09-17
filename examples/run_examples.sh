#!/usr/bin/env bash
# GWyl Mail examples — runs with the current Python environment (venv/conda,
# no specific environment name required). See GETTING_STARTED.md for setup.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PY="${PYTHON:-python}"

echo "[1/7] Environment check"
"$PY" -m gwyl_mail.cli doctor --skip-network || echo "(doctor reported issues — proofs will be degraded; see GETTING_STARTED.md)"

echo "[2/7] Canonical hash (plain text)"
"$PY" -m gwyl_mail.cli canonical-hash examples/sample_plain_text.eml

echo "[3/7] Canonical hash (HTML-only)"
"$PY" -m gwyl_mail.cli canonical-hash examples/sample_html.eml

echo "[4/7] Canonical hash (attachments)"
"$PY" -m gwyl_mail.cli canonical-hash examples/sample_with_attachments.eml

echo "[5/7] Create proof file (plain text)"
OUT_PROOF=".gwyl_mail/proofs/sample_plain_text.proof.json"
"$PY" -m gwyl_mail.cli create-proof \
  examples/sample_plain_text.eml \
  --identity alice@company.com \
  --out "$OUT_PROOF"

echo "[6/7] Sign an EML (proof embedded, ready to send)"
rm -rf .gwyl_mail/examples && mkdir -p .gwyl_mail/examples
"$PY" -m gwyl_mail.cli sign \
  examples/sample_plain_text.eml \
  --identity alice@company.com \
  -o .gwyl_mail/examples/signed.eml

echo "[7/7] Check the signed EML (as the recipient would)"
"$PY" -m gwyl_mail.cli check .gwyl_mail/examples/signed.eml

echo "Done."
