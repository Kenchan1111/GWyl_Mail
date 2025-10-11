#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INTEGRITY_TOOL="/home/zack/GWyl_Integrity/unified_integrity.py"

cd "$REPO_DIR"

echo "[integrity] Checking baseline before commit..."
if command -v conda >/dev/null 2>&1; then
  conda run -n GWYL_Env python "$INTEGRITY_TOOL" check
else
  python "$INTEGRITY_TOOL" check
fi

echo "[git] Staging changes..."
git add -A

if [ $# -eq 0 ]; then
  echo "Enter commit message (end with Ctrl-D):"
  msg=$(cat)
else
  msg="$*"
fi

echo "[git] Committing..."
git commit -m "$msg"

echo "[integrity] Post-commit verification..."
if command -v conda >/dev/null 2>&1; then
  conda run -n GWYL_Env python "$INTEGRITY_TOOL" check
else
  python "$INTEGRITY_TOOL" check
fi

echo "[integrity] (optional) Upgrading any OTS proofs present..."
if command -v ots >/dev/null 2>&1; then
  if ls logs/anchors/ots/*.ots >/dev/null 2>&1; then
    for f in logs/anchors/ots/*.ots; do
      ots upgrade "$f" || true
    done
  fi
fi

echo "Done."
