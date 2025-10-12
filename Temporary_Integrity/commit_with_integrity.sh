#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INTEGRITY_TOOL="/home/zack/GWyl_Integrity/unified_integrity.py"
BASELINE_FILE="SECURITY_INTEGRITY_BASELINE.sha256"
BASELINE_COMMITTED="SECURITY_INTEGRITY_BASELINE.sha256.committed"

cd "$REPO_DIR"

# ============================================================================
# STEP 1: Verify integrity against committed baseline (if exists)
# ============================================================================
echo "[integrity] Checking against committed baseline history..."
if [ -f "$BASELINE_COMMITTED" ]; then
  if command -v conda >/dev/null 2>&1; then
    conda run -n GWYL_Env python "$INTEGRITY_TOOL" check
  else
    python "$INTEGRITY_TOOL" check
  fi
  echo "✅ Integrity check passed against historical baseline"
else
  echo "⚠️  No committed baseline found (first commit?)"
fi

# ============================================================================
# STEP 2: Generate new baseline with current changes
# ============================================================================
echo "[integrity] Generating new baseline for current state..."
find . -type f \( -name "*.py" -o -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.json" -o -name "*.toml" -o -name "*.sh" -o -name "*.txt" \) \
  -not -path "./.git/*" \
  -not -path "./.venv/*" \
  -not -path "./htmlcov/*" \
  -not -path "./__pycache__/*" \
  -not -path "./.pytest_cache/*" \
  -not -path "./.gwyl_mail/*" \
  -not -path "./logs/*" \
  | sort | xargs sha256sum > "$BASELINE_FILE"

FILE_COUNT=$(wc -l < "$BASELINE_FILE")
echo "✅ New baseline generated: $FILE_COUNT files"

# ============================================================================
# STEP 3: Show diff between old committed baseline and new baseline
# ============================================================================
if [ -f "$BASELINE_COMMITTED" ]; then
  echo ""
  echo "[integrity] Baseline changes (committed → current):"
  echo "────────────────────────────────────────────────────────────"

  # Count changes
  ADDED=$(comm -13 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | wc -l)
  REMOVED=$(comm -23 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | wc -l)
  MODIFIED=$(comm -12 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | while read file; do
    OLD_HASH=$(grep " $file$" "$BASELINE_COMMITTED" | cut -d' ' -f1)
    NEW_HASH=$(grep " $file$" "$BASELINE_FILE" | cut -d' ' -f1)
    [ "$OLD_HASH" != "$NEW_HASH" ] && echo "$file"
  done | wc -l)

  echo "  📝 Modified: $MODIFIED files"
  echo "  ➕ Added:    $ADDED files"
  echo "  ➖ Removed:  $REMOVED files"

  # Show modified files (first 10)
  if [ "$MODIFIED" -gt 0 ]; then
    echo ""
    echo "  Modified files (showing first 10):"
    comm -12 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | while read file; do
      OLD_HASH=$(grep " $file$" "$BASELINE_COMMITTED" | cut -d' ' -f1)
      NEW_HASH=$(grep " $file$" "$BASELINE_FILE" | cut -d' ' -f1)
      if [ "$OLD_HASH" != "$NEW_HASH" ]; then
        echo "    • $file"
      fi
    done | head -10
  fi
  echo "────────────────────────────────────────────────────────────"
fi

# ============================================================================
# STEP 4: Copy current baseline to .committed (this will be in git)
# ============================================================================
echo ""
echo "[integrity] Creating committed baseline snapshot..."
cp "$BASELINE_FILE" "$BASELINE_COMMITTED"
echo "✅ Baseline snapshot created: $BASELINE_COMMITTED"

# ============================================================================
# STEP 5: Stage and commit
# ============================================================================
echo ""
echo "[git] Staging changes (including .committed baseline)..."
git add "$BASELINE_COMMITTED"
git add -A

if [ $# -eq 0 ]; then
  echo "Enter commit message (end with Ctrl-D):"
  msg=$(cat)
else
  msg="$*"
fi

echo "[git] Committing..."
git commit -m "$msg"

# ============================================================================
# STEP 6: Post-commit verification
# ============================================================================
echo ""
echo "[integrity] Post-commit verification..."
if command -v conda >/dev/null 2>&1; then
  conda run -n GWYL_Env python "$INTEGRITY_TOOL" check
else
  python "$INTEGRITY_TOOL" check
fi

# ============================================================================
# STEP 7: Optional OTS upgrade
# ============================================================================
echo ""
echo "[integrity] (optional) Upgrading any OTS proofs present..."
if command -v ots >/dev/null 2>&1; then
  if ls logs/anchors/ots/*.ots >/dev/null 2>&1; then
    for f in logs/anchors/ots/*.ots; do
      ots upgrade "$f" || true
    done
  fi
fi

echo ""
echo "✅ Commit complete with integrity verification!"
echo "   • Baseline history: tracked in git ($BASELINE_COMMITTED)"
echo "   • Current baseline: local working copy ($BASELINE_FILE)"
echo "   • Use 'git diff HEAD~1 $BASELINE_COMMITTED' to audit changes"
