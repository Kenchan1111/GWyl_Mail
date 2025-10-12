#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
Unified Integrity System - Solution complète sans auto-référence
================================================================

Combine les meilleurs aspects de :
- integrity_improved.py (tamper-evident log, sessions)
- secure_integrity_manager.py (Merkle Tree, résolution auto-référence)

Architecture :
1. Fichiers sources → Merkle Tree → Racine ancrée (OTS)
2. Baseline EXCLUT les fichiers auto-générés
3. Sessions de travail avec baseline temporaire
4. Receipts centralisés avec chaîne de preuves
"""

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import subprocess
import getpass

# ============================================================================
# CONFIGURATION GLOBALE
# ============================================================================

class Config:
    """Configuration centralisée"""
    
    # Fichiers EXCLUS de la baseline (auto-générés)
    EXCLUDED_FROM_BASELINE = {
        'SECURITY_INTEGRITY_BASELINE.sha256',
        'SECURITY_INTEGRITY_LOG.jsonl',
        'CODING_HISTORY.md',
        'CODING_HISTORY_RESUME.md',
        'secure_integrity_manifest.json',
        '.integrity_work_session.json',
    }
    
    # Patterns de dossiers exclus (CORRECTION: liste explicite complète)
    EXCLUDED_DIRS = {
        '.git',
        '.venv',
        '__pycache__',
        '.mypy_cache',
        '.pytest_cache',
        '.integrity_store',
        'logs',  # Géré par rotation
        'node_modules',
        '.tox',
        '.eggs',
        'build',
        'dist',
        '.coverage',
    }
    
    # Fichiers
    BASELINE = Path('SECURITY_INTEGRITY_BASELINE.sha256')
    LOG = Path('SECURITY_INTEGRITY_LOG.jsonl')
    ANCHOR = Path('SECURITY_ANCHOR.txt')
    MANIFEST = Path('secure_integrity_manifest.json')
    SESSION = Path('.integrity_work_session.json')
    
    # Logs centralisés
    MISMATCH_LOG = Path('logs/mismatch.jsonl')
    RECEIPTS_LOG = Path('logs/anchors/receipts.jsonl')
    OTS_DIR = Path('logs/anchors/ots')


# ============================================================================
# UTILITAIRES
# ============================================================================

def utcnow_iso() -> str:
    """Timestamp ISO UTC"""
    return datetime.now(timezone.utc).isoformat()


def compute_sha256(path: Path) -> str:
    """Hash SHA-256 d'un fichier"""
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def canonical_json(obj: dict) -> str:
    """JSON canonique pour hashing"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


# ============================================================================
# MERKLE TREE
# ============================================================================

class MerkleTree:
    """Arbre de Merkle pour les fichiers"""
    
    def __init__(self, file_hashes: List[Tuple[str, str]]):
        """
        Args:
            file_hashes: [(path, sha256), ...]
        """
        self.leaves = sorted(file_hashes, key=lambda x: x[0])
        self.root = self._build()
    
    def _build(self) -> str:
        if not self.leaves:
            return hashlib.sha256(b"empty").hexdigest()
        
        level = [h for _, h in self.leaves]
        
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                combined = hashlib.sha256(
                    bytes.fromhex(left) + bytes.fromhex(right)
                ).hexdigest()
                next_level.append(combined)
            level = next_level
        
        return level[0]


# ============================================================================
# SCANNER DE FICHIERS
# ============================================================================

class FileScanner:
    """Scanne les fichiers du workspace"""
    
    PATTERNS = ['**/*.py', '**/*.md', '**/*.json', '**/*.yaml', '**/*.yml', 
                '**/*.toml', '**/*.txt', '**/*.sh']
    
    @staticmethod
    def scan(root: Path = Path('.')) -> List[Path]:
        """Retourne la liste des fichiers à tracker"""
        files = set()
        
        for pattern in FileScanner.PATTERNS:
            for f in root.glob(pattern):
                # Exclure fichiers auto-générés
                if f.name in Config.EXCLUDED_FROM_BASELINE:
                    continue
                
                # CORRECTION: Exclure UNIQUEMENT dossiers listés explicitement
                # Principe: tout inclure par défaut (y compris dotfiles), sauf exclusions
                if any(d in f.parts for d in Config.EXCLUDED_DIRS):
                    continue

                if f.is_file():
                    files.add(f)
        
        return sorted(files)


# ============================================================================
# GESTIONNAIRE DE BASELINE
# ============================================================================

class BaselineManager:
    """Gère la baseline sans auto-référence"""
    
    def __init__(self):
        self.mapping: Dict[str, str] = {}
        self.merkle_root: Optional[str] = None
    
    def build(self) -> Tuple[int, str]:
        """
        Construit la baseline complète
        
        Returns:
            (nb_files, merkle_root)
        """
        files = FileScanner.scan()
        
        hashes = []
        for f in files:
            sha = compute_sha256(f)
            rel_path = str(f)
            self.mapping[rel_path] = sha
            hashes.append((rel_path, sha))
        
        # Merkle Tree
        tree = MerkleTree(hashes)
        self.merkle_root = tree.root
        
        return len(files), self.merkle_root
    
    def save(self):
        """Sauvegarde la baseline (CORRECTION: format unifié sans '*')"""
        # CORRECTION: Format unifié "sha  path" (double espace, sans *)
        lines = [f"{sha}  {path}\n" for path, sha in sorted(self.mapping.items())]
        Config.BASELINE.write_text(''.join(lines))
    
    def load(self) -> Dict[str, str]:
        """Charge la baseline"""
        if not Config.BASELINE.exists():
            return {}
        
        mapping = {}
        for line in Config.BASELINE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                sha = parts[0]
                path = parts[1].lstrip('*')
                mapping[path] = sha
        
        self.mapping = mapping
        return mapping
    
    def verify(self) -> Dict:
        """Vérifie tous les fichiers"""
        results = {'ok': [], 'mismatch': [], 'missing': []}
        
        for path, expected_sha in self.mapping.items():
            f = Path(path)
            
            if not f.exists():
                results['missing'].append({
                    'path': path,
                    'expected_sha': expected_sha
                })
                continue
            
            actual_sha = compute_sha256(f)
            
            if actual_sha == expected_sha:
                results['ok'].append(path)
            else:
                results['mismatch'].append({
                    'path': path,
                    'expected': expected_sha,
                    'actual': actual_sha
                })
        
        return results


# ============================================================================
# GESTIONNAIRE DE SESSIONS
# ============================================================================

class SessionManager:
    """Gère les sessions de travail"""
    
    def __init__(self):
        self.session: Optional[dict] = None
    
    def start(self, files: List[str], reason: str = "Work session"):
        """
        Démarre une session
        
        Cette fonction :
        1. Vérifie que tous les fichiers sont dans la baseline
        2. Crée une baseline TEMPORAIRE excluant ces fichiers
        3. Enregistre l'état des autres fichiers (stable_files)
        """
        baseline = BaselineManager()
        baseline.load()
        
        # Vérifier que les fichiers existent dans baseline
        working = []
        for f in files:
            if f not in baseline.mapping:
                raise ValueError(f"File not in baseline: {f}")
            working.append(f)
        
        # Fichiers stables = tous sauf working
        stable = {k: v for k, v in baseline.mapping.items() if k not in working}
        
        # Merkle des stables
        stable_hashes = [(p, h) for p, h in stable.items()]
        stable_merkle = MerkleTree(stable_hashes).root
        
        session = {
            'started_at': utcnow_iso(),
            'reason': reason,
            'working_files': working,
            'stable_merkle': stable_merkle,
            'stable_count': len(stable)
        }
        
        Config.SESSION.write_text(json.dumps(session, indent=2))
        
        print(f"✅ Session started")
        print(f"   Working files: {len(working)}")
        print(f"   Stable files: {len(stable)}")
        print(f"   Stable Merkle: {stable_merkle[:16]}...")
        
        return session
    
    def verify_stable(self) -> Tuple[bool, List[str]]:
        """Vérifie que les fichiers stables n'ont pas changé"""
        if not Config.SESSION.exists():
            raise ValueError("No active session")
        
        session = json.loads(Config.SESSION.read_text())
        baseline = BaselineManager()
        baseline.load()
        
        # Recalculer Merkle des stables
        working_set = set(session['working_files'])
        stable = {k: v for k, v in baseline.mapping.items() if k not in working_set}
        
        issues = []
        for path, expected_sha in stable.items():
            f = Path(path)
            if not f.exists():
                issues.append(f"MISSING: {path}")
                continue
            
            actual = compute_sha256(f)
            if actual != expected_sha:
                issues.append(f"MODIFIED: {path}")
        
        # Vérifier Merkle
        stable_hashes = [(p, h) for p, h in stable.items() if Path(p).exists()]
        current_merkle = MerkleTree(stable_hashes).root
        
        if current_merkle != session['stable_merkle']:
            issues.append("MERKLE MISMATCH: stable files altered")
        
        return len(issues) == 0, issues
    
    def finalize(self, reason: str = "Session completed") -> Dict:
        """Finalise la session et met à jour la baseline"""
        if not Config.SESSION.exists():
            raise ValueError("No active session")
        
        # Vérifier stables
        ok, issues = self.verify_stable()
        if not ok:
            raise ValueError(f"Stable verification failed: {issues}")
        
        session = json.loads(Config.SESSION.read_text())
        
        # Recalculer baseline complète
        baseline = BaselineManager()
        nb_files, merkle = baseline.build()
        baseline.save()
        
        # Nettoyer session
        Config.SESSION.unlink()
        
        print(f"✅ Session finalized")
        print(f"   Files updated: {nb_files}")
        print(f"   New Merkle root: {merkle[:16]}...")
        
        return {
            'finalized_at': utcnow_iso(),
            'merkle_root': merkle,
            'total_files': nb_files
        }


# ============================================================================
# GESTIONNAIRE D'ANCRAGE (OTS)
# ============================================================================

class AnchorManager:
    """Gère les ancrages OpenTimestamps"""
    
    @staticmethod
    def ots_available() -> bool:
        """Vérifie si OTS est installé"""
        return subprocess.run(['which', 'ots'], capture_output=True).returncode == 0
    
    @staticmethod
    def anchor(data: str, label: str = "anchor") -> Optional[Path]:
        """
        Ancre un hash via OTS
        
        Returns:
            Path vers le .ots file ou None
        """
        if not AnchorManager.ots_available():
            print("⚠️  OTS not installed: pip install opentimestamps-client")
            return None
        
        Config.OTS_DIR.mkdir(parents=True, exist_ok=True)
        
        ts = utcnow_iso().replace(':', '').replace('-', '')
        msg_file = Config.OTS_DIR / f"{label}_{ts}.txt"
        
        try:
            msg_file.write_text(data)
            
            # Stamp
            result = subprocess.run(
                ['ots', 'stamp', str(msg_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ OTS stamp failed: {result.stderr}")
                return None
            
            # Proof file
            proof = Path(f"{msg_file}.ots")
            
            if proof.exists():
                print(f"⛓️  Anchored: {data[:16]}...")
                print(f"   Proof: {proof}")
                return proof
            
        except Exception as e:
            print(f"❌ Anchor failed: {e}")
        
        return None


# ============================================================================
# GESTIONNAIRE DE RECEIPTS
# ============================================================================

class ReceiptManager:
    """Gère le log centralisé des receipts"""
    
    @staticmethod
    def append(receipt: dict):
        """Ajoute un receipt au log"""
        Config.RECEIPTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        
        with Config.RECEIPTS_LOG.open('a') as f:
            f.write(canonical_json(receipt) + '\n')
    
    @staticmethod
    def get_latest() -> Optional[dict]:
        """Récupère le dernier receipt"""
        if not Config.RECEIPTS_LOG.exists():
            return None
        
        last = None
        with Config.RECEIPTS_LOG.open('r') as f:
            for line in f:
                if line.strip():
                    try:
                        last = json.loads(line)
                    except:
                        pass
        
        return last


# ============================================================================
# GESTIONNAIRE DE MISMATCHES
# ============================================================================

class MismatchLogger:
    """Log centralisé des erreurs d'intégrité"""
    
    @staticmethod
    def log(mismatch: dict):
        """Enregistre un mismatch"""
        Config.MISMATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            'timestamp': utcnow_iso(),
            'user': getpass.getuser(),
            **mismatch
        }
        
        with Config.MISMATCH_LOG.open('a') as f:
            f.write(canonical_json(entry) + '\n')


# ============================================================================
# COMMANDES CLI
# ============================================================================

def cmd_init(args):
    """Initialise le système"""
    print("🔒 Initializing integrity system...")
    print("─" * 60)
    
    baseline = BaselineManager()
    nb_files, merkle = baseline.build()
    baseline.save()
    
    print(f"\n✅ Baseline created")
    print(f"   Files tracked: {nb_files}")
    print(f"   Merkle root: {merkle}")
    
    # Ancrer
    if args.anchor:
        proof = AnchorManager.anchor(merkle, "init_merkle")
        if proof:
            receipt = {
                'action': 'init',
                'merkle_root': merkle,
                'ots_proof': str(proof),
                'files_count': nb_files
            }
            ReceiptManager.append(receipt)


def cmd_check(args):
    """Vérifie l'intégrité"""
    print("🔍 Checking integrity...")
    print("─" * 60)
    
    baseline = BaselineManager()
    baseline.load()
    
    results = baseline.verify()
    
    print(f"\n✅ OK: {len(results['ok'])} files")
    
    if results['mismatch']:
        print(f"\n❌ MISMATCH: {len(results['mismatch'])} files")
        for item in results['mismatch'][:10]:
            print(f"   • {item['path']}")
            print(f"     Expected: {item['expected'][:16]}...")
            print(f"     Actual:   {item['actual'][:16]}...")
            
            # Logger
            MismatchLogger.log({
                'type': 'hash_mismatch',
                'path': item['path'],
                'expected': item['expected'],
                'actual': item['actual']
            })
    
    if results['missing']:
        print(f"\n⚠️  MISSING: {len(results['missing'])} files")
        for item in results['missing'][:10]:
            print(f"   • {item['path']}")
            
            MismatchLogger.log({
                'type': 'missing_file',
                'path': item['path'],
                'expected': item['expected_sha']
            })
    
    return 0 if not (results['mismatch'] or results['missing']) else 1


def cmd_start_session(args):
    """Démarre une session de travail"""
    session_mgr = SessionManager()
    session_mgr.start(args.files, args.reason or "Work session")


def cmd_verify_session(args):
    """Vérifie les fichiers stables durant session"""
    session_mgr = SessionManager()
    ok, issues = session_mgr.verify_stable()
    
    if ok:
        print("✅ Stable files: OK")
    else:
        print("❌ Stable files COMPROMISED:")
        for issue in issues:
            print(f"   • {issue}")
    
    return 0 if ok else 1


def cmd_end_session(args):
    """Finalise la session"""
    session_mgr = SessionManager()
    result = session_mgr.finalize(args.reason or "Session completed")
    
    # Ancrer si demandé
    if args.anchor:
        proof = AnchorManager.anchor(result['merkle_root'], "session_end")
        if proof:
            receipt = {
                'action': 'session_end',
                'merkle_root': result['merkle_root'],
                'ots_proof': str(proof),
                'files_count': result['total_files']
            }
            ReceiptManager.append(receipt)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Unified Integrity System")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # init
    p_init = subparsers.add_parser('init', help='Initialize baseline')
    p_init.add_argument('--anchor', action='store_true', help='Anchor to blockchain')
    p_init.set_defaults(func=cmd_init)
    
    # check
    p_check = subparsers.add_parser('check', help='Verify integrity')
    p_check.set_defaults(func=cmd_check)
    
    # start-session
    p_start = subparsers.add_parser('start-session', help='Start work session')
    p_start.add_argument('files', nargs='+', help='Files to work on')
    p_start.add_argument('--reason', help='Session reason')
    p_start.set_defaults(func=cmd_start_session)
    
    # verify-session
    p_verify = subparsers.add_parser('verify-session', help='Verify stable files')
    p_verify.set_defaults(func=cmd_verify_session)
    
    # end-session
    p_end = subparsers.add_parser('end-session', help='Finalize session')
    p_end.add_argument('--reason', help='Completion reason')
    p_end.add_argument('--anchor', action='store_true', help='Anchor to blockchain')
    p_end.set_defaults(func=cmd_end_session)
    
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    import sys
    sys.exit(main())
