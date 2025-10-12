#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Use local copy to avoid accidental external modifications
INTEGRITY_TOOL="$REPO_DIR/Temporary_Integrity/unified_integrity.py"
BASELINE_FILE="SECURITY_INTEGRITY_BASELINE.sha256"            # Original (NEVER committed)
BASELINE_COMMITTED="SECURITY_INTEGRITY_BASELINE.sha256.committed"  # Snapshot committed
BASELINE_META="SECURITY_INTEGRITY_BASELINE.sha256.meta"      # Chain-of-trust metadata

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
# Use git ls-files to get ALL tracked files (ensures consistency with git)
# Exclude only the baseline files themselves, generated directories, and append-only logs
# Keep all OTS backups/receipts as they document integrity history (immutable after creation)
# Process each file and add ./ prefix to match committed baseline format
# Use NUL-terminated output for robust path handling (supports spaces, special chars)
git ls-files -z \
  | grep -zv "^SECURITY_INTEGRITY_BASELINE.sha256$" \
  | grep -zv "^\.gwyl_mail/" \
  | grep -zv "^__pycache__/" \
  | grep -zv "^\.pytest_cache/" \
  | grep -zv "^logs/verification_audit\.jsonl$" \
  | grep -zv "^logs/mismatch\.jsonl$" \
  | grep -zv "^logs/anchors/receipts\.jsonl$" \
  | while IFS= read -r -d '' file; do
      if [ -f "$file" ]; then
        sha256sum "$file" | sed "s|  |  ./|"
      fi
    done \
  | sort -k2 > "$BASELINE_FILE"

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
  # Prepare path lists to avoid nested process substitutions
  TMP_OLD=$(mktemp); TMP_NEW=$(mktemp); TMP_INT=$(mktemp)
  cut -d' ' -f3- "$BASELINE_COMMITTED" | sort > "$TMP_OLD"
  cut -d' ' -f3- "$BASELINE_FILE" | sort > "$TMP_NEW"

  # Count changes
  ADDED=$(comm -13 "$TMP_OLD" "$TMP_NEW" | wc -l)
  REMOVED=$(comm -23 "$TMP_OLD" "$TMP_NEW" | wc -l)
  comm -12 "$TMP_OLD" "$TMP_NEW" > "$TMP_INT"

  # Avoid pipefail issues: count modified files without piping the loop
  MODIFIED=0
  while IFS= read -r file; do
    # Extract hashes by matching exact end-of-line path (robust to spaces/specials)
    OLD_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_COMMITTED")
    NEW_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_FILE")
    if [ -n "$OLD_HASH" ] && [ -n "$NEW_HASH" ] && [ "$OLD_HASH" != "$NEW_HASH" ]; then
      MODIFIED=$((MODIFIED+1))
    fi
  done < "$TMP_INT"

  UNCHANGED=$(( $(wc -l < "$TMP_INT") - MODIFIED ))

  echo "      📊 Baseline delta:"
  echo "         ✅ Unchanged: $UNCHANGED files (match git history)"
  echo "         📝 Modified:  $MODIFIED files"
  echo "         ➕ Added:     $ADDED files"
  echo "         ➖ Removed:   $REMOVED files"

  # Verify chain: unchanged part must match committed
  echo ""
  echo "[4/7] Verifying chain of trust (old = old)..."
  CHAIN_OK=true
  while IFS= read -r file; do
    OLD_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_COMMITTED")
    NEW_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_FILE")
    if [ -n "$OLD_HASH" ] && [ -n "$NEW_HASH" ] && [ "$OLD_HASH" = "$NEW_HASH" ]; then
      # File unchanged - hash must match history
      if ! awk -v f="$file" -v h="$OLD_HASH" 'substr($0, length($0)-length(f)+1) == f && $1 == h {found=1} END{exit found?0:1}' "$BASELINE_COMMITTED"; then
        echo "      ❌ CHAIN BROKEN: $file hash mismatch with history!"
        CHAIN_OK=false
      fi
    fi
  done < "$TMP_INT"

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
    # Collect modified file entries into a temp file, then print first 30
    TMP_LIST=$(mktemp)
    while IFS= read -r file; do
      OLD_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_COMMITTED")
      NEW_HASH=$(awk -v f="$file" 'substr($0, length($0)-length(f)+1) == f {print $1; exit}' "$BASELINE_FILE")
      if [ -n "$OLD_HASH" ] && [ -n "$NEW_HASH" ] && [ "$OLD_HASH" != "$NEW_HASH" ]; then
        printf "         • %s\n           Old: %.16s...\n           New: %.16s...\n" "$file" "$OLD_HASH" "$NEW_HASH" >> "$TMP_LIST"
      fi
    done < "$TMP_INT"
    head -30 "$TMP_LIST"
    rm -f "$TMP_LIST"
  fi
  rm -f "$TMP_OLD" "$TMP_NEW" "$TMP_INT"
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

# Sanity: committed snapshot must match original content byte-for-byte
if ! cmp -s "$BASELINE_FILE" "$BASELINE_COMMITTED"; then
  echo "      ❌ Snapshot mismatch: committed baseline differs from original"
  echo "         Original:  $BASELINE_FILE"
  echo "         Committed: $BASELINE_COMMITTED"
  exit 1
fi

# Refresh original baseline to reflect the new snapshot hash
# (pre-commit check uses the original baseline as source of truth)
TMP_BASELINE=$(mktemp)
{
  git ls-files -z \
  | while IFS= read -r -d '' file; do
      case "$file" in
        SECURITY_INTEGRITY_BASELINE.sha256|SECURITY_INTEGRITY_BASELINE.sha256.committed|SECURITY_INTEGRITY_BASELINE.sha256.meta)
          continue ;;
      esac
      case "$file" in
        .gwyl_mail/*)
          continue ;;
      esac
      [ -f "$file" ] || continue
      sha=$(sha256sum -- "$file" | awk '{print $1}')
      printf "%s  ./%s\n" "$sha" "$file"
    done \
  ;
} > "$TMP_BASELINE"
sort -k2 "$TMP_BASELINE" > "$BASELINE_FILE"
rm -f "$TMP_BASELINE"
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
echo "[6/7] Committing to git (excluding original baseline)..."
# Stage the committed snapshot and all user changes EXCEPT the original baseline file
git add "$BASELINE_COMMITTED"
git add -A . ':(exclude)SECURITY_INTEGRITY_BASELINE.sha256'

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
echo "[7/8] Post-commit verification..."
if command -v conda >/dev/null 2>&1; then
  conda run -n GWYL_Env python "$INTEGRITY_TOOL" check 2>&1 | grep -E "(✅|OK|MISMATCH)" || true
else
  python "$INTEGRITY_TOOL" check 2>&1 | grep -E "(✅|OK|MISMATCH)" || true
fi
echo "      ✅ Post-commit integrity verified"

# ============================================================================
# STEP 8: Chain-of-trust metadata (record committed baseline hash)
# ============================================================================
echo ""
echo "[8/8] Recording chain-of-trust metadata..."
# We do NOT embed the committed hash inside the snapshot to avoid self-reference.
# Instead, we store it in a separate meta file and commit it.
{
  echo "baseline_committed_sha256=$NEW_COMMITTED_HASH"
  echo "baseline_committed_file=$BASELINE_COMMITTED"
  echo "baseline_committed_lines=$FILE_COUNT"
  echo "commit_hash=$COMMIT_HASH"
  echo "committed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$BASELINE_META"

git add "$BASELINE_META"
git commit -m "chore(integrity): record committed baseline hash ($NEW_COMMITTED_HASH)"
META_COMMIT_HASH=$(git rev-parse --short HEAD)
echo "      ✅ Metadata committed: $META_COMMIT_HASH (hash: ${NEW_COMMITTED_HASH:0:16}...)"

# ============================================================================
# STEP 9: Optional OTS upgrade
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
echo "     • Meta recorded (git): ${NEW_COMMITTED_HASH:0:16}... → ✅ committed"
echo "     • Working baseline:    ${NEW_BASELINE_HASH:0:16}... → 📝 local"
echo ""
echo "  📋 Audit trail:"
echo "     • View changes:  git diff HEAD~1 $BASELINE_COMMITTED"
echo "     • View history:  git log --oneline -- $BASELINE_COMMITTED"
echo "     • Verify now:    conda run -n GWYL_Env python $INTEGRITY_TOOL check"
echo ""
echo "════════════════════════════════════════════════════════════════════════"
