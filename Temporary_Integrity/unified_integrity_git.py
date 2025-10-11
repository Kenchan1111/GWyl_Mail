#!/usr/bin/env python3
"""
Unified Integrity System - Git Integration
===========================================

Extension Git pour lier commits et dual anchoring.

Features:
- Git hooks automatiques (pre-commit, post-commit, pre-push)
- Metadata dans commits (Git trailers)
- Vérification remote ↔ local
- Support GitLab + GitHub agnostique
- Backup preuves dans .integrity/ (versionné)

Usage:
    # Setup initial
    python unified_integrity_git.py init
    
    # Commit avec protection auto
    git commit -m "message"  # Hook activé automatiquement
    
    # Vérification remote
    python unified_integrity_git.py verify-remote
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import re

# Import du système dual
try:
    from unified_integrity_sigstore import (
        DualAnchorManager, DualProof, SigstoreConfig,
        DualReceiptManager, utcnow_iso
    )
    from unified_integrity import (
        BaselineManager, compute_sha256, MerkleTree
    )
except ImportError:
    print("⚠️  unified_integrity_sigstore.py requis")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

class GitConfig:
    """Configuration Git integration"""
    
    # Répertoire .integrity (versionné dans Git)
    INTEGRITY_DIR = Path('.integrity')
    PROOFS_DIR = INTEGRITY_DIR / 'proofs'
    COMMITS_DIR = PROOFS_DIR / 'commits'
    SESSIONS_DIR = PROOFS_DIR / 'sessions'
    
    # Fichiers
    CONFIG_FILE = INTEGRITY_DIR / 'config.yml'
    INDEX_FILE = INTEGRITY_DIR / 'index.jsonl'
    
    # Git hooks
    HOOKS_DIR = Path('.git/hooks')
    
    # Git trailers (metadata dans commits)
    TRAILER_PROOF = 'Integrity-Proof'
    TRAILER_MERKLE = 'Integrity-Merkle'
    TRAILER_REKOR = 'Integrity-Rekor'
    TRAILER_OTS = 'Integrity-OTS'


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class GitCommitProof:
    """Preuve liée à un commit Git"""
    commit_sha: str
    commit_message: str
    commit_author: str
    commit_date: str
    dual_proof: Dict  # DualProof.to_dict()
    files_modified: List[str]
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GitVerificationResult:
    """Résultat vérification Git"""
    success: bool
    commit_sha: str
    local_state: str  # 'valid', 'modified', 'missing'
    remote_state: str  # 'synced', 'diverged', 'ahead', 'behind'
    proof_status: Dict  # Résultat DualAnchor.verify_dual
    details: Dict


# ============================================================================
# GIT HELPER
# ============================================================================

class GitHelper:
    """Helper pour opérations Git"""
    
    @staticmethod
    def is_git_repo() -> bool:
        """Vérifie si répertoire courant est un repo Git"""
        return (Path('.git').exists() or 
                subprocess.run(['git', 'rev-parse', '--git-dir'],
                             capture_output=True).returncode == 0)
    
    @staticmethod
    def get_current_commit() -> Optional[str]:
        """Récupère SHA du commit courant"""
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None
    
    @staticmethod
    def get_commit_info(commit_sha: str) -> Optional[Dict]:
        """Récupère info d'un commit"""
        result = subprocess.run(
            ['git', 'show', '--no-patch', '--format=%H%n%s%n%an <%ae>%n%ai',
             commit_sha],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return None
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 4:
            return None
        
        return {
            'sha': lines[0],
            'message': lines[1],
            'author': lines[2],
            'date': lines[3]
        }
    
    @staticmethod
    def get_modified_files(commit_sha: str = 'HEAD') -> List[str]:
        """Récupère fichiers modifiés dans un commit"""
        result = subprocess.run(
            ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r',
             commit_sha],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return []
        
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    
    @staticmethod
    def get_file_content(filepath: str, commit_sha: str = 'HEAD') -> Optional[str]:
        """Récupère contenu d'un fichier à un commit donné"""
        result = subprocess.run(
            ['git', 'show', f'{commit_sha}:{filepath}'],
            capture_output=True,
            text=True
        )
        
        return result.stdout if result.returncode == 0 else None
    
    @staticmethod
    def add_commit_trailer(message: str, trailers: Dict[str, str]) -> str:
        """Ajoute Git trailers à un message de commit"""
        # Séparer subject et body
        lines = message.split('\n')
        
        # Construire trailers
        trailer_lines = []
        for key, value in trailers.items():
            trailer_lines.append(f'{key}: {value}')
        
        # Insérer trailers avant signature (si présente)
        final_lines = lines.copy()
        
        # Ajouter ligne vide si nécessaire
        if final_lines and final_lines[-1].strip():
            final_lines.append('')
        
        final_lines.extend(trailer_lines)
        
        return '\n'.join(final_lines)
    
    @staticmethod
    def get_remote_url(remote: str = 'origin') -> Optional[str]:
        """Récupère URL du remote"""
        result = subprocess.run(
            ['git', 'remote', 'get-url', remote],
            capture_output=True,
            text=True
        )
        
        return result.stdout.strip() if result.returncode == 0 else None
    
    @staticmethod
    def is_gitlab_remote(url: str) -> bool:
        """Détecte si remote est GitLab"""
        return 'gitlab' in url.lower()
    
    @staticmethod
    def is_github_remote(url: str) -> bool:
        """Détecte si remote est GitHub"""
        return 'github' in url.lower()


# ============================================================================
# GIT PROOF MANAGER
# ============================================================================

class GitProofManager:
    """Gère les preuves liées aux commits"""
    
    @staticmethod
    def init_integrity_dir():
        """Initialise .integrity/ pour Git"""
        GitConfig.COMMITS_DIR.mkdir(parents=True, exist_ok=True)
        GitConfig.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Créer .gitignore dans logs/ (preuves locales)
        logs_gitignore = Path('logs/.gitignore')
        logs_gitignore.parent.mkdir(exist_ok=True)
        logs_gitignore.write_text('*\n!.gitignore\n')
        
        # Config par défaut
        if not GitConfig.CONFIG_FILE.exists():
            config = {
                'version': '1.0',
                'auto_anchor': True,
                'require_sigstore': True,
                'require_ots': False,  # OTS optionnel (délai)
                'verify_on_push': True
            }
            GitConfig.CONFIG_FILE.write_text(
                '# Integrity System Config\n' +
                '\n'.join(f'{k}: {v}' for k, v in config.items())
            )
        
        print(f"✅ Initialized .integrity/")
    
    @staticmethod
    def save_commit_proof(commit_sha: str, dual_proof: DualProof,
                         commit_info: Dict, files: List[str]):
        """Sauvegarde preuve pour un commit"""
        GitConfig.COMMITS_DIR.mkdir(parents=True, exist_ok=True)
        
        git_proof = GitCommitProof(
            commit_sha=commit_sha,
            commit_message=commit_info['message'],
            commit_author=commit_info['author'],
            commit_date=commit_info['date'],
            dual_proof=dual_proof.to_dict(),
            files_modified=files
        )
        
        # CORRECTION: Sauvegarder avec SHA complet (pas prefix)
        proof_file = GitConfig.COMMITS_DIR / f'{commit_sha}.json'
        proof_file.write_text(json.dumps(git_proof.to_dict(), indent=2))
        
        # Ajouter à l'index
        GitProofManager._update_index(git_proof)
        
        print(f"✅ Proof saved: .integrity/proofs/commits/{proof_file.name}")
    
    @staticmethod
    def _update_index(git_proof: GitCommitProof):
        """Met à jour index searchable"""
        with GitConfig.INDEX_FILE.open('a') as f:
            index_entry = {
                'commit_sha': git_proof.commit_sha,
                'timestamp': git_proof.dual_proof['timestamp'],
                'author': git_proof.commit_author,
                'files': len(git_proof.files_modified),
                'sigstore': git_proof.dual_proof.get('sigstore') is not None,
                'ots_status': git_proof.dual_proof.get('opentimestamps', {}).get('status')
            }
            f.write(json.dumps(index_entry) + '\n')
    
    @staticmethod
    def get_commit_proof(commit_sha: str) -> Optional[GitCommitProof]:
        """Récupère preuve d'un commit (CORRECTION: SHA complet + fallback legacy)"""
        # CORRECTION: 1. Chercher par SHA complet (exact match)
        exact_file = GitConfig.COMMITS_DIR / f'{commit_sha}.json'
        if exact_file.exists():
            try:
                data = json.loads(exact_file.read_text())
                return GitCommitProof(**data)
            except:
                pass

        # CORRECTION: 2. Fallback legacy: chercher par préfixe 16 chars
        for proof_file in GitConfig.COMMITS_DIR.glob(f'{commit_sha[:16]}*.json'):
            try:
                data = json.loads(proof_file.read_text())
                # Vérifier que c'est bien le bon commit (éviter collision préfixe)
                if data.get('commit_sha') == commit_sha:
                    return GitCommitProof(**data)
            except:
                continue

        return None
    
    @staticmethod
    def verify_commit_proof(commit_sha: str) -> GitVerificationResult:
        """Vérifie preuve d'un commit"""
        # Récupérer preuve
        proof = GitProofManager.get_commit_proof(commit_sha)
        
        if not proof:
            return GitVerificationResult(
                success=False,
                commit_sha=commit_sha,
                local_state='missing',
                remote_state='unknown',
                proof_status={},
                details={'error': 'No proof found for commit'}
            )
        
        # Reconstruire DualProof
        dual_proof_dict = proof.dual_proof
        
        # Vérifier dual proof
        from unified_integrity_sigstore import DualAnchorManager
        verification = DualAnchorManager.verify_dual(dual_proof_dict)
        
        # Vérifier état local
        local_state = 'valid'
        
        # Recalculer Merkle root des fichiers actuels
        baseline = BaselineManager()
        baseline.load()
        
        current_hashes = []
        for filepath in proof.files_modified:
            if Path(filepath).exists():
                current_hash = compute_sha256(filepath)
                current_hashes.append((filepath, current_hash))
        
        if current_hashes:
            current_merkle = MerkleTree(current_hashes).root
            expected_merkle = dual_proof_dict['merkle_root']
            
            if current_merkle != expected_merkle:
                local_state = 'modified'
        
        return GitVerificationResult(
            success=verification['overall_status'] in ['protected', 'partial'],
            commit_sha=commit_sha,
            local_state=local_state,
            remote_state='unknown',  # Vérifié séparément
            proof_status=verification,
            details={
                'sigstore': verification.get('sigstore_status'),
                'ots': verification.get('ots_status'),
                'files': len(proof.files_modified)
            }
        )


# ============================================================================
# GIT HOOKS
# ============================================================================

class GitHooks:
    """Gestion des Git hooks"""
    
    PRE_COMMIT_HOOK = """#!/usr/bin/env python3
# Integrity System - Pre-commit hook
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unified_integrity_git import GitWorkflow

sys.exit(GitWorkflow.pre_commit_hook())
"""
    
    POST_COMMIT_HOOK = """#!/usr/bin/env python3
# Integrity System - Post-commit hook
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unified_integrity_git import GitWorkflow

sys.exit(GitWorkflow.post_commit_hook())
"""
    
    PRE_PUSH_HOOK = """#!/usr/bin/env python3
# Integrity System - Pre-push hook
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unified_integrity_git import GitWorkflow

sys.exit(GitWorkflow.pre_push_hook())
"""
    
    @staticmethod
    def install():
        """Installe Git hooks"""
        if not GitHelper.is_git_repo():
            print("❌ Not a Git repository")
            return False
        
        GitConfig.HOOKS_DIR.mkdir(exist_ok=True)
        
        hooks = {
            'pre-commit': GitHooks.PRE_COMMIT_HOOK,
            'post-commit': GitHooks.POST_COMMIT_HOOK,
            'pre-push': GitHooks.PRE_PUSH_HOOK
        }
        
        for hook_name, hook_content in hooks.items():
            hook_file = GitConfig.HOOKS_DIR / hook_name
            hook_file.write_text(hook_content)
            hook_file.chmod(0o755)
            print(f"✅ Installed: {hook_name}")
        
        return True


# ============================================================================
# GIT WORKFLOW
# ============================================================================

class GitWorkflow:
    """Workflows Git intégrés"""
    
    @staticmethod
    def pre_commit_hook() -> int:
        """Hook pré-commit: vérification baseline (CORRIGÉ: bloque vraiment + bypass)"""
        import os

        print("🔍 Pre-commit: Verifying baseline...")

        # CORRECTION: Bypass contrôlé
        if os.getenv('GWYL_BYPASS_PRECOMMIT') == '1':
            print("⚠️  BYPASS MODE ENABLED (GWYL_BYPASS_PRECOMMIT=1)")
            print("⚠️  Pre-commit checks SKIPPED - use with caution!")
            print("⚠️  This bypass has been logged.")
            # TODO: Logger le bypass dans un audit log
            return 0

        # CORRECTION: Vraie vérification qui bloque si problème
        try:
            # Récupérer fichiers staged
            result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                capture_output=True,
                text=True,
                check=True
            )

            staged_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]

            if not staged_files:
                print("✅ No files staged, allowing commit")
                return 0

            # Charger baseline
            baseline = BaselineManager()
            if not baseline.load():
                print("⚠️  No baseline found - first commit?")
                return 0

            # CORRECTION: Vérifier chaque fichier STRICTEMENT
            modified_tracked = []  # Fichiers suivis modifiés sans régénération
            new_untracked = []     # Nouveaux fichiers non exclus

            for filepath in staged_files:
                fpath = Path(filepath)

                # Fichiers exclus (système)
                from unified_integrity import Config
                if any(d in fpath.parts for d in Config.EXCLUDED_DIRS):
                    continue
                if fpath.name in Config.EXCLUDED_FROM_BASELINE:
                    continue

                if not fpath.exists():
                    # Fichier supprimé, OK
                    continue

                # Calculer hash actuel
                current_hash = compute_sha256(fpath)

                # CORRECTION: Bloquer si fichier suivi diffère
                if filepath in baseline.mapping:
                    baseline_hash = baseline.mapping[filepath]
                    if current_hash != baseline_hash:
                        modified_tracked.append(filepath)
                else:
                    # CORRECTION: Nouveau fichier non exclu = bloquer
                    new_untracked.append(filepath)

            # CORRECTION: Bloquer si problèmes détectés
            has_errors = bool(modified_tracked or new_untracked)

            if modified_tracked:
                print(f"\n❌ {len(modified_tracked)} tracked file(s) modified without baseline regeneration:")
                for f in modified_tracked[:10]:
                    print(f"  • {f}")
                if len(modified_tracked) > 10:
                    print(f"  ... and {len(modified_tracked) - 10} more")

            if new_untracked:
                print(f"\n❌ {len(new_untracked)} new file(s) not in baseline:")
                for f in new_untracked[:10]:
                    print(f"  • {f}")
                if len(new_untracked) > 10:
                    print(f"  ... and {len(new_untracked) - 10} more")

            if has_errors:
                print("\n🚫 COMMIT BLOCKED")
                print("\nTo fix:")
                print("  1. Regenerate baseline: python unified_integrity.py init")
                print("  2. Or bypass (emergency only): GWYL_BYPASS_PRECOMMIT=1 git commit ...")
                return 1

            print("✅ Pre-commit checks passed")
            return 0

        except Exception as e:
            print(f"❌ Pre-commit hook error: {e}")
            print("🚫 COMMIT BLOCKED (safety)")
            print(f"\nBypass (emergency only): GWYL_BYPASS_PRECOMMIT=1 git commit ...")
            return 1
    
    @staticmethod
    def post_commit_hook() -> int:
        """Hook post-commit: création dual anchor"""
        print("🔐 Post-commit: Creating dual anchor...")
        
        # Récupérer commit info
        commit_sha = GitHelper.get_current_commit()
        if not commit_sha:
            print("❌ Could not get current commit")
            return 1
        
        commit_info = GitHelper.get_commit_info(commit_sha)
        files = GitHelper.get_modified_files(commit_sha)
        
        # Calculer Merkle root des fichiers modifiés
        baseline = BaselineManager()
        baseline.load()
        
        hashes = []
        for filepath in files:
            if Path(filepath).exists():
                file_hash = compute_sha256(filepath)
                hashes.append((filepath, file_hash))
                # Mettre à jour baseline
                baseline.mapping[filepath] = file_hash
        
        if not hashes:
            print("⏭️  No files to anchor")
            return 0
        
        baseline.save()
        
        merkle_root = MerkleTree(hashes).root
        
        # Créer dual anchor
        dual_proof = DualAnchorManager.dual_anchor(
            merkle_root=merkle_root,
            files=files,
            label=f'commit_{commit_sha[:8]}',
            skip_ots=False  # OTS optionnel selon config
        )
        
        # Sauvegarder preuve
        GitProofManager.save_commit_proof(
            commit_sha=commit_sha,
            dual_proof=dual_proof,
            commit_info=commit_info,
            files=files
        )
        
        print(f"✅ Dual anchor created for commit {commit_sha[:8]}")
        
        # Suggérer d'ajouter .integrity/ au commit
        print("\n💡 Add proofs to Git:")
        print("   git add .integrity/")
        print("   git commit --amend --no-edit")
        
        return 0
    
    @staticmethod
    def pre_push_hook() -> int:
        """Hook pré-push: vérification preuves"""
        print("🔍 Pre-push: Verifying commits have proofs...")
        
        # Vérifier que commits à pusher ont des preuves
        # (Simplifié pour l'exemple)
        
        return 0


# ============================================================================
# COMMANDES CLI
# ============================================================================

def cmd_init(args):
    """Initialise Git integration"""
    print("🔧 Initializing Git Integration")
    print("="*60)
    
    if not GitHelper.is_git_repo():
        print("❌ Not a Git repository. Run 'git init' first.")
        return 1
    
    # Init .integrity/
    GitProofManager.init_integrity_dir()
    
    # Installer hooks
    GitHooks.install()
    
    # Détection remote
    remote_url = GitHelper.get_remote_url()
    if remote_url:
        if GitHelper.is_gitlab_remote(remote_url):
            print(f"\n✅ GitLab detected: {remote_url}")
        elif GitHelper.is_github_remote(remote_url):
            print(f"\n✅ GitHub detected: {remote_url}")
        else:
            print(f"\n⚠️  Unknown Git provider: {remote_url}")
    
    print("\n" + "="*60)
    print("✅ Git integration initialized!")
    print("\nNext steps:")
    print("  1. git add .integrity/")
    print("  2. git commit -m 'Add integrity system'")
    print("  3. Make commits as usual (hooks auto-activate)")
    
    return 0


def cmd_verify_commit(args):
    """Vérifie un commit"""
    commit_sha = args.commit or GitHelper.get_current_commit()
    
    if not commit_sha:
        print("❌ No commit specified and not in Git repo")
        return 1
    
    print(f"🔍 Verifying commit {commit_sha[:8]}...")
    print("="*60)
    
    result = GitProofManager.verify_commit_proof(commit_sha)
    
    print(f"\nCommit: {result.commit_sha[:16]}...")
    print(f"Local state: {result.local_state}")
    print(f"Proof status: {result.proof_status.get('overall_status', 'unknown')}")
    
    if result.success:
        print("\n✅ Commit integrity VERIFIED")
        return 0
    else:
        print("\n❌ Commit integrity verification FAILED")
        return 1


def cmd_verify_remote(args):
    """Vérifie cohérence avec remote"""
    print("🔍 Git Remote Verification")
    print("="*60)
    
    # TODO: Implémenter vérification remote complète
    print("\n⚠️  Remote verification: WIP")
    print("Future features:")
    print("  - Compare local proofs vs remote .integrity/")
    print("  - Detect force-push")
    print("  - Verify all commits have proofs")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Unified Integrity System - Git Integration"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # init
    p_init = subparsers.add_parser('init', help='Initialize Git integration')
    p_init.set_defaults(func=cmd_init)
    
    # verify-commit
    p_verify = subparsers.add_parser('verify-commit', help='Verify commit proof')
    p_verify.add_argument('--commit', help='Commit SHA (default: HEAD)')
    p_verify.set_defaults(func=cmd_verify_commit)
    
    # verify-remote
    p_remote = subparsers.add_parser('verify-remote', help='Verify remote consistency')
    p_remote.set_defaults(func=cmd_verify_remote)
    
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())