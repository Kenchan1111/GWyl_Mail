# RFC - GWyl Mail v0.1.1 - Critical Fixes & Improvements

**Date**: 2025-10-12
**Status**: Implementation In Progress
**Authors**: Claude (Anthropic), Zack
**Baseline**: v0.1.0 (d538be0)

---

## 1. Executive Summary

This RFC addresses critical gaps identified in the audit of GWyl Mail v0.1.0:
- **Critical bugs** blocking production use
- **Missing features** from PROOF_SCHEMA v0.2 specification
- **Incomplete test coverage** (<20%)
- **Parsing deficiencies** in OTS and Sigstore components

**Target**: Achieve 8-9/10 production-readiness score within 2-3 weeks.

---

## 2. Audit Findings Summary

### Current Score: 6.5/10

**Strengths**:
- Excellent specifications (~3700 lines)
- Solid architecture and separation of concerns
- Security considerations (path traversal, audit logging)

**Critical Issues**:
1. ❌ Missing `policy` field in proof (spec v0.2.0 requirement)
2. ❌ OTS output not parsed (bitcoin_block, confirmed_at always null)
3. ❌ Import bug (sys not imported in cli.py)
4. ❌ JSON Schema validation fails for nullable+pattern fields
5. ❌ Test coverage <20%, TEST_VECTORS not validated
6. ⚠️ Fragile Sigstore bundle metadata extraction

---

## 3. Implementation Plan

### 🔴 SPRINT 1: Critical Fixes (2-3 days)

#### 3.1. Bug Fixes (Priority: CRITICAL)

**Issue #1: Missing import sys in cli.py**
- **File**: `gwyl_mail/cli.py`
- **Line**: 59
- **Fix**: Add `import sys` at top of file
- **Impact**: Prevents crash when audit logging fails

**Issue #2: JSON Schema validation for nullable fields with pattern**
- **File**: `gwyl_mail/schemas/proof-v0.2.0.json`
- **Lines**: 24, 57-58, 74
- **Fix**: Use `oneOf` for nullable+pattern fields
- **Affected fields**: `bundle_digest`, `sender_hash`, `recipient_hash`, `proof_canonical_digest`

**Example**:
```json
"bundle_digest": {
  "oneOf": [
    {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    {"type": "null"}
  ]
}
```

---

#### 3.2. Feature: Policy Field Implementation

**Specification Reference**: PROOF_SCHEMA_v0.md (v0.2.0), lines 537-621

**New Files**:
- `gwyl_mail/policy_utils.py`: Policy hash computation and metadata extraction

**Modified Files**:
- `gwyl_mail/dual_proof.py`: Add policy field to proof generation
- `gwyl_mail/schemas/proof-v0.2.0.json`: Add policy schema

**API**:
```python
def compute_policy_hash(policy_path: Path) -> str:
    """Compute SHA-256 hash of canonicalized YAML policy."""

def extract_policy_metadata(policy_path: Path) -> Dict[str, Any]:
    """Extract policy_id and policy_url from YAML."""
```

**Proof Format**:
```json
{
  "version": "0.2.0",
  "policy": {
    "policy_id": "gwyl-mail-policy-v1",
    "policy_hash": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9...",
    "policy_url": "https://company.com/.well-known/gwyl-mail-policy.yml"
  }
}
```

**Backwards Compatibility**: Field is optional (null allowed) for graceful degradation.

---

#### 3.3. Feature: OTS Output Parsing

**Specification Reference**: PROOF_SCHEMA_v0.md (v0.2.0), lines 680-705

**Modified Files**:
- `gwyl_mail/ots_manager.py`: Parse `ots verify` output
- `gwyl_mail/dual_proof.py`: Use parsed OTS metadata

**OTS Output Format** (example):
```
Success! Bitcoin block 829456 attests data existed as of Thu 11 Jan 2025 20:15:43 UTC
```

**Parsing Strategy**:
```python
# Extract bitcoin_block
block_match = re.search(r'block\s+(\d+)', output, re.IGNORECASE)
bitcoin_block = int(block_match.group(1)) if block_match else None

# Extract timestamp (best effort)
time_match = re.search(r'as of\s+(.+?)(?:\n|$)', output, re.IGNORECASE)
```

**Impact**: Enables coherence check (|rekor_ts - ots_ts| < 24h) as per spec.

---

#### 3.4. Development Environment: pytest Setup

**New Files**:
- `pyproject.toml` (or update existing)
- `requirements-dev.txt`

**Dependencies**:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
```

**Installation**:
```bash
pip install -e ".[dev]"
```

---

### 🟠 SPRINT 2: Test Coverage (3-5 days)

#### 3.5. TEST_VECTORS Validation

**Specification Reference**: TEST_VECTORS_v0.md

**New Files**:
- `tests/test_vectors.py`

**Test Cases**:
- TV1: Plain text simple → `a5511ab5...`
- TV2: Café crème (Unicode) → `d9bcb5ec...`
- TV3: RFC 2047 encoded subject → `4d40a4e6...`
- TV4: Attachments sorted by hash → `4e19bb70...`
- TV5: Unicode filename NFC → `8084a054...`

**Coverage Target**: 100% of TEST_VECTORS pass

---

#### 3.6. Encoding & RFC 2047 Tests

**New Tests** (in `test_canonical.py`):
- Encoding transformation (QP ↔ Base64) stability
- Line endings normalization (CRLF ↔ LF)
- RFC 2047 encoded-words decoding
- Address domain normalization (local-part preserved)

**Coverage Target**: All spec scenarios validated

---

#### 3.7. Identity Policy Tests

**New Files**:
- `tests/test_identity_policy.py`

**Test Cases**:
- Exact match (alice@company.com = alice@company.com)
- Exact mismatch (noreply@company.com ≠ alice@company.com)
- Domain tolerance (noreply@company.com ~ alice@company.com)
- Alias tolerance (with YAML config)
- Issuer whitelist enforcement
- Domain whitelist enforcement

**Coverage Target**: All validation rules tested

---

#### 3.8. Dual Proof with Policy Tests

**New Tests** (in `test_dual_proof.py`):
- Proof generation with policy file
- Policy hash computation correctness
- Policy field schema validation
- Backwards compatibility (policy=null)

---

### 🟡 SPRINT 3: Robustness (1-2 weeks)

#### 3.9. Sigstore Bundle Parsing Enhancement

**Options**:
1. **Option A** (recommended): Use `sigstore-python` library for robust parsing
2. **Option B**: Parse `cosign verify-blob --output-json` stable format

**Rationale**: Current heuristic parsing (walk dict, find '@') is fragile.

**Modified Files**:
- `gwyl_mail/sigstore_timestamp.py`

---

#### 3.10. Integration Tests (Gmail, Outlook, Postfix)

**Specification Reference**: KPI_POC.md, lines 51-93

**New Files**:
- `tests/integration/test_interop.py`

**Test Strategy**:
- Send 50 messages per provider (Gmail, Outlook, Postfix)
- Measure success rate: (verified / sent) × 100
- **Target**: ≥95% success rate per provider

**Note**: Requires real SMTP setup or mocking framework.

---

#### 3.11. Monitoring & Metrics

**Specification Reference**: KPI_POC.md, lines 545-606

**New Files**:
- `gwyl_mail/metrics.py`

**Metrics**:
- `gwyl_mail_verify_attempts_total` (Counter)
- `gwyl_mail_verify_success_total` (Counter)
- `gwyl_mail_verify_duration_seconds` (Histogram)
- `gwyl_mail_ots_confirmation_rate` (Gauge)

**Export**: Prometheus format

---

#### 3.12. User Documentation

**New Files**:
- `docs/INSTALLATION.md`
- `docs/QUICKSTART.md`
- `docs/TROUBLESHOOTING.md`
- `examples/send_email.py`
- `examples/verify_email.py`

---

## 4. Timeline

| Sprint | Duration | Effort | Deliverables |
|--------|----------|--------|--------------|
| **Sprint 1** | 2-3 days | 16-20h | Bugs fixed, policy implemented, OTS parsing, pytest setup |
| **Sprint 2** | 3-5 days | 24-32h | TEST_VECTORS validated, comprehensive tests, coverage >80% |
| **Sprint 3** | 1-2 weeks | 40-60h | Robust Sigstore parsing, interop tests, monitoring, docs |
| **Total** | 2.5-3.5 weeks | 80-112h | Production-ready (score 8-9/10) |

---

## 5. Success Criteria

### Sprint 1 (Critical Fixes)
- ✅ All bugs fixed (import sys, schema validation)
- ✅ Policy field implemented and schema-validated
- ✅ OTS parsing extracts bitcoin_block and confirmed_at
- ✅ pytest runs without errors

### Sprint 2 (Test Coverage)
- ✅ All TEST_VECTORS pass (TV1-TV5)
- ✅ Encoding/RFC2047/Unicode tests pass
- ✅ Identity policy tests pass
- ✅ Test coverage ≥80%

### Sprint 3 (Production-Ready)
- ✅ Sigstore parsing robust (no heuristics)
- ✅ Interop tests: ≥95% success rate (Gmail, Outlook, Postfix)
- ✅ Monitoring metrics exported
- ✅ User documentation complete

---

## 6. Risk Assessment

### High Risk
- **Interop tests** may reveal new canonicalization edge cases
- **OTS parsing** format may vary across versions (mitigation: regex fallbacks)

### Medium Risk
- **Sigstore parsing** requires external library (sigstore-python) or cosign dependency

### Low Risk
- **Policy field** is additive (backwards compatible)
- **Bug fixes** are isolated and non-breaking

---

## 7. Backwards Compatibility

### Breaking Changes: NONE

All changes are additive or bug fixes:
- `policy` field is optional (null allowed)
- OTS parsing enhances existing data (no API change)
- Bug fixes restore intended behavior

### Migration Path
- v0.1.0 → v0.1.1: Drop-in replacement
- Old proofs remain valid (policy field optional)

---

## 8. Alternatives Considered

### Alternative 1: Skip policy field implementation
**Rejected**: Core spec v0.2.0 requirement, needed for identity enforcement.

### Alternative 2: Use cosign CLI JSON output instead of sigstore-python
**Accepted as Option B**: Simpler, no new dependencies, but less robust.

### Alternative 3: Defer interop tests to post-pilot
**Accepted if time-constrained**: Can start with manual testing, automate later.

---

## 9. Implementation Checklist

### Sprint 1: Critical Fixes
- [ ] Fix: Add `import sys` to cli.py
- [ ] Fix: Update JSON Schema for nullable+pattern fields
- [ ] Feature: Implement `policy_utils.py`
- [ ] Feature: Add policy field to `dual_proof.py`
- [ ] Feature: Update proof schema with policy
- [ ] Feature: Parse OTS output in `ots_manager.py`
- [ ] Feature: Use OTS metadata in `dual_proof.py`
- [ ] Setup: Add pytest to pyproject.toml
- [ ] Setup: Install dev dependencies

### Sprint 2: Test Coverage
- [ ] Tests: Implement `test_vectors.py` (TV1-TV5)
- [ ] Tests: Add encoding tests to `test_canonical.py`
- [ ] Tests: Add RFC2047 tests
- [ ] Tests: Add Unicode tests
- [ ] Tests: Create `test_identity_policy.py`
- [ ] Tests: Add dual_proof policy tests
- [ ] Validation: Run pytest, achieve >80% coverage

### Sprint 3: Robustness
- [ ] Enhancement: Improve Sigstore parsing
- [ ] Tests: Create `test_interop.py` (integration)
- [ ] Monitoring: Implement `metrics.py`
- [ ] Docs: Write INSTALLATION.md
- [ ] Docs: Write QUICKSTART.md
- [ ] Docs: Write TROUBLESHOOTING.md
- [ ] Examples: Create example scripts

---

## 10. References

- **Audit Report**: Analysis 2025-10-12 (score 6.5/10)
- **CANONICALIZATION_v0.md**: Specification v0.2.0
- **PROOF_SCHEMA_v0.md**: Specification v0.2.0
- **IDENTITY_POLICY_v0.md**: Specification v0.1.0
- **TEST_VECTORS_v0.md**: Test cases v0.1.0
- **KPI_POC.md**: Success criteria v0.1.0

---

## 11. Changelog

### v0.1.1 (In Progress)
- **Added**: Policy field support (PROOF_SCHEMA v0.2.0)
- **Added**: OTS output parsing (bitcoin_block, confirmed_at)
- **Added**: TEST_VECTORS validation tests
- **Added**: Comprehensive encoding/RFC2047 tests
- **Fixed**: Missing import sys in cli.py
- **Fixed**: JSON Schema validation for nullable+pattern
- **Improved**: Test coverage from <20% to >80%

---

## 12. Approval

**Status**: Approved for Implementation
**Start Date**: 2025-10-12
**Target Completion**: 2025-11-02 (3 weeks)
**Review Date**: End of each sprint

---

**End of RFC**
