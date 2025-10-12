# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


def compute_policy_hash(policy_path: Path) -> str:
    """
    Compute SHA-256 hash of canonicalized YAML policy.

    Algorithm:
    1. Load YAML
    2. Sort keys recursively
    3. Dump to canonical YAML
    4. Compute SHA-256

    Args:
        policy_path: Path to YAML policy file

    Returns:
        SHA-256 hex digest (64 chars)

    Raises:
        FileNotFoundError: If policy file doesn't exist
        RuntimeError: If pyyaml not available
    """
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    if yaml is None:
        raise RuntimeError("pyyaml not installed, cannot compute policy hash")

    with policy_path.open() as f:
        policy = yaml.safe_load(f)

    # Canonicalize: sort keys recursively
    canonical_yaml = yaml.dump(
        policy,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True
    )

    return hashlib.sha256(canonical_yaml.encode('utf-8')).hexdigest()


def extract_policy_metadata(policy_path: Path) -> Dict[str, Any]:
    """
    Extract policy_id and policy_url from YAML file.

    Args:
        policy_path: Path to YAML policy file

    Returns:
        Dict with 'policy_id' and 'policy_url' keys
        Empty dict if file doesn't exist or pyyaml unavailable
    """
    if not policy_path.exists() or yaml is None:
        return {}

    try:
        with policy_path.open() as f:
            policy = yaml.safe_load(f) or {}

        return {
            'policy_id': policy.get('policy_id', 'default'),
            'policy_url': policy.get('policy_url')
        }
    except Exception:
        return {}
