from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # Fallback if pyyaml not available; minimal parsing not provided


@dataclass
class IdentityPolicyConfig:
    enforcement_mode: str = "warn"  # warn | strict
    allowed_issuers: List[str] = None  # type: ignore
    allowed_domains: List[str] = None  # type: ignore
    allowed_identities: List[str] = None  # type: ignore
    aliases: Dict[str, Dict[str, Any]] = None  # type: ignore
    validation_rules: List[Dict[str, Any]] = None  # type: ignore


class IdentityPolicy:
    def __init__(self, config_file: Optional[Path] = None):
        self.config = IdentityPolicyConfig(
            allowed_issuers=[],
            allowed_domains=[],
            allowed_identities=[],
            aliases={},
            validation_rules=[{"name": "from_matches_cert", "tolerance": "exact"}],
        )
        if config_file and config_file.exists() and yaml:
            cfg = yaml.safe_load(config_file.read_text()) or {}
            self.config.enforcement_mode = cfg.get("enforcement_mode", self.config.enforcement_mode)
            self.config.allowed_issuers = cfg.get("allowed_issuers", [])
            self.config.allowed_domains = cfg.get("allowed_domains", [])
            self.config.allowed_identities = cfg.get("allowed_identities", [])
            self.config.aliases = cfg.get("aliases", {})
            self.config.validation_rules = cfg.get("validation_rules", self.config.validation_rules)

    def _same_domain(self, a: str, b: str) -> bool:
        try:
            da = a.split("@", 1)[1].lower()
            db = b.split("@", 1)[1].lower()
            return da == db
        except Exception:
            return False

    def _check_alias(self, from_email: str, cert_subject: str) -> bool:
        aliases = self.config.aliases or {}
        rec = aliases.get(cert_subject, {})
        allowed = [x.lower() for x in rec.get("allowed_aliases", [])]
        return from_email.lower() in allowed or from_email.lower() == cert_subject.lower()

    def _issuer_ok(self, issuer: str) -> bool:
        allowed = self.config.allowed_issuers or []
        return True if not allowed else any(i in issuer for i in allowed)

    def _domain_ok(self, email: str) -> bool:
        allowed = self.config.allowed_domains or []
        if not allowed:
            return True
        try:
            return email.split("@", 1)[1].lower() in [d.lower() for d in allowed]
        except Exception:
            return False

    def verify(self, from_email: str, cert_subject: str, cert_issuer: str) -> Dict[str, Any]:
        rules = {r["name"]: r for r in (self.config.validation_rules or [])}
        tol = (rules.get("from_matches_cert", {}).get("tolerance") or "exact").lower()
        if tol == "exact":
            from_ok = from_email.lower() == cert_subject.lower()
        elif tol == "domain":
            from_ok = self._same_domain(from_email, cert_subject)
        else:
            from_ok = self._check_alias(from_email, cert_subject)
        issuer_ok = self._issuer_ok(cert_issuer)
        domain_ok = self._domain_ok(from_email)
        all_ok = from_ok and issuer_ok and domain_ok
        result = {"from_cert": from_ok, "issuer": issuer_ok, "domain": domain_ok, "valid": all_ok}
        if not all_ok and self.config.enforcement_mode == "strict":
            result["enforcement"] = "strict"
        else:
            result["enforcement"] = "warn"
        return result

