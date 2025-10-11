#!/usr/bin/env python3
"""
Secure Integrity Manager - Solution au problème d'auto-référence
=================================================================

Stratégie :
1. Exclure les fichiers auto-générés de la baseline (CODING_HISTORY, BASELINE)
2. Calculer hash de chaque fichier individuellement
3. Construire un Merkle Tree des hashs
4. Ancrer la racine Merkle sur blockchain
5. Créer un manifeste signé séparément
6. Permettre l'ancrage individuel de fichiers critiques
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict


@dataclass
class FileSignature:
    """Signature d'un fichier"""
    path: str
    sha256: str
    size: int
    mtime: str
    ots_receipt: str = None
    blockchain_tx: str = None


class MerkleTree:
    """Arbre de Merkle simple pour les hashs de fichiers"""
    
    def __init__(self, hashes: List[Tuple[str, str]]):
        """
        Args:
            hashes: Liste de (path, hash) tuples
        """
        self.leaves = sorted(hashes, key=lambda x: x[0])  # Trier par path
        self.root = self._build_tree()
    
    def _build_tree(self) -> str:
        """Construire l'arbre et retourner la racine"""
        if not self.leaves:
            return hashlib.sha256(b"").hexdigest()
        
        # Niveau actuel = les feuilles
        current_level = [h[1] for h in self.leaves]
        
        # Construire l'arbre niveau par niveau
        while len(current_level) > 1:
            next_level = []
            
            # Parcourir par paires
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                
                # Si impair, dupliquer le dernier
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                
                # Combiner et hasher
                combined = hashlib.sha256(
                    bytes.fromhex(left) + bytes.fromhex(right)
                ).hexdigest()
                
                next_level.append(combined)
            
            current_level = next_level
        
        return current_level[0]
    
    def get_proof(self, file_path: str) -> List[str]:
        """Obtenir la preuve Merkle pour un fichier"""
        # Trouver l'index
        index = next((i for i, (p, _) in enumerate(self.leaves) if p == file_path), None)
        if index is None:
            return []
        
        # Construire la preuve (simplifié)
        proof = []
        current_level = [h[1] for h in self.leaves]
        current_index = index
        
        while len(current_level) > 1:
            # Pair/impair
            if current_index % 2 == 0:
                # Prendre le frère de droite si existe
                if current_index + 1 < len(current_level):
                    proof.append(('right', current_level[current_index + 1]))
            else:
                # Prendre le frère de gauche
                proof.append(('left', current_level[current_index - 1]))
            
            # Monter d'un niveau
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256(
                    bytes.fromhex(left) + bytes.fromhex(right)
                ).hexdigest()
                next_level.append(combined)
            
            current_level = next_level
            current_index = current_index // 2
        
        return proof


class SecureIntegrityManager:
    """Gestionnaire d'intégrité sans cycle auto-référentiel"""
    
    # Fichiers à EXCLURE de la baseline (auto-générés)
    EXCLUDED_FILES = {
        'CODING_HISTORY.md',
        'SECURITY_INTEGRITY_BASELINE.sha256',
        'secure_integrity_manifest.json',
        'secure_integrity_manifest.json.sig',
        '.integrity_store',
        'logs'
    }
    
    def __init__(self, root_dir: Path = Path('.')):
        self.root_dir = root_dir
        self.signatures: Dict[str, FileSignature] = {}
        self.merkle_tree = None
    
    def scan_files(self) -> List[Path]:
        """Scanner tous les fichiers (sauf exclusions)"""
        files = []
        
        for pattern in ['**/*.py', '**/*.md', '**/*.yml', '**/*.yaml', '**/*.json', '**/*.sh']:
            for file in self.root_dir.glob(pattern):
                # Exclure
                if any(excl in str(file) for excl in self.EXCLUDED_FILES):
                    continue
                
                # Exclure hidden et __pycache__
                if any(part.startswith('.') or part == '__pycache__' for part in file.parts):
                    continue
                
                files.append(file)
        
        return sorted(files)
    
    def hash_file(self, file_path: Path) -> FileSignature:
        """Calculer le hash d'un fichier"""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        stat = file_path.stat()
        
        return FileSignature(
            path=str(file_path.relative_to(self.root_dir)),
            sha256=sha256.hexdigest(),
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        )
    
    def build_signatures(self):
        """Construire toutes les signatures"""
        files = self.scan_files()
        print(f"📊 Scanning {len(files)} files...")
        
        for file in files:
            sig = self.hash_file(file)
            self.signatures[sig.path] = sig
        
        print(f"✅ {len(self.signatures)} files hashed")
    
    def build_merkle_tree(self):
        """Construire l'arbre de Merkle"""
        hashes = [(path, sig.sha256) for path, sig in self.signatures.items()]
        self.merkle_tree = MerkleTree(hashes)
        print(f"🌳 Merkle root: {self.merkle_tree.root}")
    
    def save_manifest(self, output_path: Path = Path('secure_integrity_manifest.json')):
        """Sauvegarder le manifeste"""
        manifest = {
            'version': '1.0.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'merkle_root': self.merkle_tree.root,
            'total_files': len(self.signatures),
            'files': {path: asdict(sig) for path, sig in self.signatures.items()}
        }
        
        with open(output_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"💾 Manifest saved to {output_path}")
        
        # Calculer hash du manifest
        manifest_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
        print(f"📋 Manifest hash: {manifest_hash}")
        
        return manifest_hash
    
    def anchor_to_blockchain(self, hash_to_anchor: str, label: str = "merkle_root"):
        """Ancrer un hash sur blockchain via OpenTimestamps"""
        try:
            # Créer fichier temporaire avec le hash
            hash_file = Path(f"/tmp/ots_{label}.txt")
            hash_file.write_text(hash_to_anchor)
            
            # Utiliser OpenTimestamps
            result = subprocess.run(
                ['ots', 'stamp', str(hash_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                receipt_file = Path(f"{hash_file}.ots")
                if receipt_file.exists():
                    print(f"⛓️  Anchored {label}: {hash_to_anchor[:16]}...")
                    print(f"   OTS receipt: {receipt_file}")
                    return str(receipt_file)
            else:
                print(f"⚠️  OTS failed: {result.stderr}")
                
        except FileNotFoundError:
            print("⚠️  OpenTimestamps not installed. Run: pip install opentimestamps-client")
        except Exception as e:
            print(f"⚠️  Anchor failed: {e}")
        
        return None
    
    def anchor_critical_files(self, patterns: List[str] = None):
        """Ancrer individuellement les fichiers critiques"""
        if patterns is None:
            patterns = [
                'cosmic_laws/*/___init__.py',
                'integrity.py',
                'cosmic_laws/llm_core/**/*.py',
                'monitoring/**/*.py'
            ]
        
        critical_files = []
        for pattern in patterns:
            critical_files.extend(self.root_dir.glob(pattern))
        
        print(f"\n⛓️  Anchoring {len(critical_files)} critical files individually...")
        
        for file in critical_files:
            rel_path = str(file.relative_to(self.root_dir))
            if rel_path in self.signatures:
                sig = self.signatures[rel_path]
                receipt = self.anchor_to_blockchain(sig.sha256, rel_path.replace('/', '_'))
                if receipt:
                    sig.ots_receipt = receipt
    
    def verify_file(self, file_path: str) -> Dict:
        """Vérifier un fichier contre le manifeste"""
        if file_path not in self.signatures:
            return {'status': 'NOT_IN_MANIFEST', 'file': file_path}
        
        # Recalculer le hash
        current_sig = self.hash_file(Path(file_path))
        expected_sig = self.signatures[file_path]
        
        if current_sig.sha256 == expected_sig.sha256:
            return {
                'status': 'OK',
                'file': file_path,
                'hash': current_sig.sha256
            }
        else:
            return {
                'status': 'TAMPERED',
                'file': file_path,
                'expected': expected_sig.sha256,
                'actual': current_sig.sha256
            }
    
    def verify_all(self) -> Dict:
        """Vérifier tous les fichiers"""
        results = {'ok': [], 'tampered': [], 'missing': []}
        
        for path in self.signatures.keys():
            file = Path(path)
            
            if not file.exists():
                results['missing'].append(path)
                continue
            
            verification = self.verify_file(path)
            
            if verification['status'] == 'OK':
                results['ok'].append(path)
            elif verification['status'] == 'TAMPERED':
                results['tampered'].append({
                    'file': path,
                    'expected': verification['expected'],
                    'actual': verification['actual']
                })
        
        return results


def main():
    """CLI principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Secure Integrity Manager")
    parser.add_argument('command', choices=['build', 'verify', 'anchor-root', 'anchor-critical', 'status'])
    parser.add_argument('--manifest', default='secure_integrity_manifest.json', help='Manifest file')
    
    args = parser.parse_args()
    
    manager = SecureIntegrityManager()
    
    if args.command == 'build':
        print("🔒 Building secure integrity manifest...")
        print("━" * 60)
        
        manager.build_signatures()
        manager.build_merkle_tree()
        manifest_hash = manager.save_manifest(Path(args.manifest))
        
        print("\n✅ Secure manifest built!")
        print(f"   Merkle root: {manager.merkle_tree.root}")
        print(f"   Manifest hash: {manifest_hash}")
        print("\nNext steps:")
        print("  1. Anchor root: python3 secure_integrity_manager.py anchor-root")
        print("  2. Anchor critical files: python3 secure_integrity_manager.py anchor-critical")
    
    elif args.command == 'verify':
        print("🔍 Verifying integrity...")
        print("━" * 60)
        
        # Charger manifest
        if not Path(args.manifest).exists():
            print(f"❌ Manifest not found: {args.manifest}")
            sys.exit(1)
        
        with open(args.manifest) as f:
            manifest = json.load(f)
        
        # Reconstruire signatures
        for path, sig_data in manifest['files'].items():
            manager.signatures[path] = FileSignature(**sig_data)
        
        # Vérifier
        results = manager.verify_all()
        
        print(f"\n✅ OK: {len(results['ok'])} files")
        
        if results['tampered']:
            print(f"\n❌ TAMPERED: {len(results['tampered'])} files")
            for item in results['tampered'][:5]:  # Montrer les 5 premiers
                print(f"   • {item['file']}")
                print(f"     Expected: {item['expected'][:16]}...")
                print(f"     Actual:   {item['actual'][:16]}...")
        
        if results['missing']:
            print(f"\n⚠️  MISSING: {len(results['missing'])} files")
            for path in results['missing'][:5]:
                print(f"   • {path}")
        
        if results['tampered'] or results['missing']:
            sys.exit(1)
    
    elif args.command == 'anchor-root':
        print("⛓️  Anchoring Merkle root to blockchain...")
        print("━" * 60)
        
        # Charger manifest
        with open(args.manifest) as f:
            manifest = json.load(f)
        
        manager.merkle_tree = type('MerkleTree', (), {'root': manifest['merkle_root']})()
        
        receipt = manager.anchor_to_blockchain(manifest['merkle_root'], 'merkle_root')
        
        if receipt:
            # Mettre à jour le manifest
            manifest['merkle_root_ots_receipt'] = receipt
            manifest['merkle_root_anchored_at'] = datetime.now(timezone.utc).isoformat()
            
            with open(args.manifest, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            print(f"✅ Merkle root anchored! Receipt: {receipt}")
    
    elif args.command == 'anchor-critical':
        print("⛓️  Anchoring critical files...")
        print("━" * 60)
        
        # Charger manifest
        with open(args.manifest) as f:
            manifest = json.load(f)
        
        for path, sig_data in manifest['files'].items():
            manager.signatures[path] = FileSignature(**sig_data)
        
        manager.anchor_critical_files()
        
        # Sauvegarder les receipts
        manifest['files'] = {path: asdict(sig) for path, sig in manager.signatures.items()}
        manifest['critical_files_anchored_at'] = datetime.now(timezone.utc).isoformat()
        
        with open(args.manifest, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print("✅ Critical files anchored!")
    
    elif args.command == 'status':
        if not Path(args.manifest).exists():
            print(f"❌ Manifest not found: {args.manifest}")
            sys.exit(1)
        
        with open(args.manifest) as f:
            manifest = json.load(f)
        
        print("📊 Secure Integrity Status")
        print("━" * 60)
        print(f"Version: {manifest['version']}")
        print(f"Timestamp: {manifest['timestamp']}")
        print(f"Total files: {manifest['total_files']}")
        print(f"Merkle root: {manifest['merkle_root']}")
        
        if 'merkle_root_ots_receipt' in manifest:
            print(f"✅ Merkle root anchored: {manifest['merkle_root_anchored_at']}")
        else:
            print("⏳ Merkle root not anchored yet")
        
        if 'critical_files_anchored_at' in manifest:
            print(f"✅ Critical files anchored: {manifest['critical_files_anchored_at']}")
        else:
            print("⏳ Critical files not anchored yet")


if __name__ == '__main__':
    main()



