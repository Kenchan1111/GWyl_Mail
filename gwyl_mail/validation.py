from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover
    jsonschema = None


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None


class ProofValidationError(RuntimeError):
    pass


class ProofValidator:
    def __init__(self) -> None:
        self.schema = self._load_schema()

    def _load_schema(self) -> Dict[str, Any]:
        schema_path = Path(__file__).parent / "schemas" / "proof-v0.2.0.json"
        if not schema_path.exists():
            return {}
        return json.loads(schema_path.read_text())

    def validate(self, proof: Dict[str, Any]) -> ValidationResult:
        if not self.schema or jsonschema is None:
            # If schema or library missing, do not block
            return ValidationResult(valid=True)
        try:
            jsonschema.validate(proof, self.schema)
            return ValidationResult(valid=True)
        except jsonschema.ValidationError as e:  # type: ignore[attr-defined]
            return ValidationResult(valid=False, error=f"Schema validation failed: {e.message}")
        except Exception as e:
            return ValidationResult(valid=False, error=f"Validation system error: {e}")

