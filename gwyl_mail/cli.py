from __future__ import annotations

import argparse
import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

from .canonical import GWylCanonical
from .dual_proof import create_proof
from .ots_manager import OTSManager


def cmd_canonical(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    h = GWylCanonical.hash(msg)
    print(h)
    return 0


def cmd_proof(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    proof = create_proof(msg, identity=args.identity)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    print(f"Proof written to {out}")
    return 0


def cmd_ots_upgrade(args: argparse.Namespace) -> int:
    proof_file = Path(args.proof)
    ok = OTSManager.upgrade(proof_file)
    print("Upgraded" if ok else "No upgrade performed")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="gwyl-mail", description="GWyl Mail CLI (minimal)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("canonical-hash", help="Compute canonical hash for an EML file")
    c.add_argument("eml")
    c.set_defaults(func=cmd_canonical)

    pr = sub.add_parser("create-proof", help="Create proof for an EML file")
    pr.add_argument("eml")
    pr.add_argument("--identity", required=True)
    pr.add_argument("--out", default=".gwyl_mail/proofs/proof.json")
    pr.set_defaults(func=cmd_proof)

    up = sub.add_parser("upgrade-ots", help="Upgrade an OTS proof file")
    up.add_argument("proof")
    up.set_defaults(func=cmd_ots_upgrade)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

