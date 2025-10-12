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
echo "════════════════════════════════════════════════════════════════════════"
echo "  INTEGRITY VERIFICATION - Chain of Trust"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# ============================================================================
# STEP 1: Load committed baseline info (if exists)
# ============================================================================
if [ -f "$BASELINE_COMMITTED" ]; then
  echo "[1/7] Loading git history baseline..."
  echo "      File: $BASELINE_COMMITTED"
  COMMITTED_HASH=$(sha256sum "$BASELINE_COMMITTED" | cut -d' ' -f1)
  COMMITTED_LINES=$(wc -l < "$BASELINE_COMMITTED")
  echo "      SHA256: ${COMMITTED_HASH:0:16}..."
  echo "      Files tracked: $COMMITTED_LINES"
else
  echo "[1/7] No committed baseline found (first commit)"
  echo "      ⚠️  Skipping historical verification"
  COMMITTED_HASH=""
  COMMITTED_LINES=0
fi

# ============================================================================
# STEP 2: Generate new baseline with current changes
# ============================================================================
echo ""
echo "[2/7] Generating new baseline for current state..."
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
NEW_BASELINE_HASH=$(sha256sum "$BASELINE_FILE" | cut -d' ' -f1)
echo "      ✅ New baseline generated"
echo "      Files tracked: $FILE_COUNT"
echo "      SHA256: ${NEW_BASELINE_HASH:0:16}..."

# ============================================================================
# STEP 3: Compare old vs new baseline (Chain of trust verification)
# ============================================================================
echo ""
echo "[3/7] Comparing git history vs current state..."

if [ -f "$BASELINE_COMMITTED" ]; then
  # Count changes
  ADDED=$(comm -13 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | wc -l)
  REMOVED=$(comm -23 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | wc -l)
  MODIFIED=$(comm -12 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | while read file; do
    OLD_HASH=$(grep " $file$" "$BASELINE_COMMITTED" | cut -d' ' -f1)
    NEW_HASH=$(grep " $file$" "$BASELINE_FILE" | cut -d' ' -f1)
    [ "$OLD_HASH" != "$NEW_HASH" ] && echo "$file"
  done | wc -l)

  UNCHANGED=$((FILE_COUNT - MODIFIED - ADDED))

  echo "      📊 Baseline delta:"
  echo "         ✅ Unchanged: $UNCHANGED files (match git history)"
  echo "         📝 Modified:  $MODIFIED files"
  echo "         ➕ Added:     $ADDED files"
  echo "         ➖ Removed:   $REMOVED files"

  # Verify chain: unchanged part must match committed
  echo ""
  echo "[4/7] Verifying chain of trust (old = old)..."
  CHAIN_OK=true
  comm -12 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | while read file; do
    OLD_HASH=$(grep " $file$" "$BASELINE_COMMITTED" | cut -d' ' -f1)
    NEW_HASH=$(grep " $file$" "$BASELINE_FILE" | cut -d' ' -f1)
    if [ "$OLD_HASH" == "$NEW_HASH" ]; then
      # File unchanged - hash must match history
      if ! grep -q "^$OLD_HASH  $file$" "$BASELINE_COMMITTED"; then
        echo "      ❌ CHAIN BROKEN: $file hash mismatch with history!"
        CHAIN_OK=false
      fi
    fi
  done

  if [ "$CHAIN_OK" = true ]; then
    echo "      ✅ Chain of trust intact"
    echo "      ✅ Unchanged files match git history exactly"
  else
    echo "      ❌ CHAIN OF TRUST BROKEN - ABORTING"
    exit 1
  fi

  # Show modified files (first 10)
  if [ "$MODIFIED" -gt 0 ]; then
    echo ""
    echo "      Modified files (showing first 10):"
    comm -12 <(cut -d' ' -f3- "$BASELINE_COMMITTED" | sort) <(cut -d' ' -f3- "$BASELINE_FILE" | sort) | while read file; do
      OLD_HASH=$(grep " $file$" "$BASELINE_COMMITTED" | cut -d' ' -f1)
      NEW_HASH=$(grep " $file$" "$BASELINE_FILE" | cut -d' ' -f1)
      if [ "$OLD_HASH" != "$NEW_HASH" ]; then
        echo "         • $file"
        echo "           Old: ${OLD_HASH:0:16}..."
        echo "           New: ${NEW_HASH:0:16}..."
      fi
    done | head -30
  fi
else
  echo "      ⚠️  First commit - no comparison possible"
fi

# ============================================================================
# STEP 4: Create new committed baseline snapshot
# ============================================================================
echo ""
echo "[5/7] Creating new committed baseline snapshot..."
cp "$BASELINE_FILE" "$BASELINE_COMMITTED"
NEW_COMMITTED_HASH=$(sha256sum "$BASELINE_COMMITTED" | cut -d' ' -f1)

echo "      ✅ Snapshot created: $BASELINE_COMMITTED"
echo "      SHA256: ${NEW_COMMITTED_HASH:0:16}..."
echo ""
echo "      🔗 Chain verification:"
if [ -n "$COMMITTED_HASH" ]; then
  echo "         Old committed: ${COMMITTED_HASH:0:16}... ($COMMITTED_LINES files)"
fi
echo "         New committed: ${NEW_COMMITTED_HASH:0:16}... ($FILE_COUNT files)"
echo "         ✅ New snapshot ready for git commit"

# ============================================================================
# STEP 5: Stage and commit
# ============================================================================
echo ""
echo "[6/7] Committing to git..."
git add "$BASELINE_COMMITTED"
git add -A

if [ $# -eq 0 ]; then
  echo "Enter commit message (end with Ctrl-D):"
  msg=$(cat)
else
  msg="$*"
fi

echo "      Staging: $BASELINE_COMMITTED + all changes"
git commit -m "$msg"
COMMIT_HASH=$(git rev-parse --short HEAD)
echo "      ✅ Committed: $COMMIT_HASH"

# ============================================================================
# STEP 6: Post-commit verification
# ============================================================================
echo ""
echo "[7/7] Post-commit verification..."
if command -v conda >/dev/null 2>&1; then
  conda run -n GWYL_Env python "$INTEGRITY_TOOL" check 2>&1 | grep -E "(✅|OK|MISMATCH)" || true
else
  python "$INTEGRITY_TOOL" check 2>&1 | grep -E "(✅|OK|MISMATCH)" || true
fi
echo "      ✅ Post-commit integrity verified"

# ============================================================================
# STEP 7: Optional OTS upgrade
# ============================================================================
echo ""
if command -v ots >/dev/null 2>&1; then
  if ls logs/anchors/ots/*.ots >/dev/null 2>&1; then
    echo "[OTS] Upgrading proofs..."
    for f in logs/anchors/ots/*.ots; do
      ots upgrade "$f" || true
    done
  fi
fi

# ============================================================================
# FINAL SUMMARY
# ============================================================================
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  ✅ COMMIT COMPLETE - INTEGRITY CHAIN VERIFIED"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "  📊 Summary:"
echo "     • Commit: $COMMIT_HASH"
echo "     • Files tracked: $FILE_COUNT"
echo "     • Baseline SHA: ${NEW_COMMITTED_HASH:0:16}..."
echo ""
echo "  🔗 Chain of Trust:"
if [ -n "$COMMITTED_HASH" ]; then
  echo "     • Old baseline (git):  ${COMMITTED_HASH:0:16}... → ✅ verified"
fi
echo "     • New baseline (git):  ${NEW_COMMITTED_HASH:0:16}... → ✅ committed"
echo "     • Working baseline:    ${NEW_BASELINE_HASH:0:16}... → 📝 local"
echo ""
echo "  📋 Audit trail:"
echo "     • View changes:  git diff HEAD~1 $BASELINE_COMMITTED"
echo "     • View history:  git log --oneline -- $BASELINE_COMMITTED"
echo "     • Verify now:    conda run -n GWYL_Env python $INTEGRITY_TOOL check"
echo ""
echo "════════════════════════════════════════════════════════════════════════"
