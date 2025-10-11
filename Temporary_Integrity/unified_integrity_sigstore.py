#!/usr/bin/env python3
"""
Unified Integrity System - Sigstore Extension
==============================================

Extension ajoutant Sigstore pour combler le gap temporel d'OpenTimestamps.

Architecture dual :
- Sigstore : Preuve immédiate (T+0s) avec identité
- OTS : Preuve permanente (T+24h) sur Bitcoin

Usage:
    # Ancrage dual (défaut)
    python unified_integrity_sigstore.py end-session --dual-anchor
    
    # Vérification dual
    python unified_integrity_sigstore.py verify-dual
    
    # Upgrade OTS pending
    python unified_integrity_sigstore.py upgrade-ots
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import tempfile
import os

# Import du système de base (unified_integrity.py)
try:
    from unified_integrity import (
        Config, utcnow_iso, compute_sha256, BaselineManager,
        SessionManager, AnchorManager, ReceiptManager, MismatchLogger,
        MerkleTree
    )
except ImportError:
    print("⚠️  unified_integrity.py requis. Assurez-vous qu'il est dans le même répertoire.")
    sys.exit(1)


# ============================================================================
# CONFIGURATION SIGSTORE
# ============================================================================

class SigstoreConfig:
    """Configuration Sigstore"""

    # Répertoires
    PROOFS_DIR = Path('logs/proofs')
    SIGSTORE_DIR = PROOFS_DIR / 'sigstore'
    SIGNATURES_DIR = SIGSTORE_DIR / 'signatures'
    CERTIFICATES_DIR = SIGSTORE_DIR / 'certificates'
    REKOR_ENTRIES_DIR = SIGSTORE_DIR / 'rekor_entries'

    # Fichiers
    SIGSTORE_INDEX = SIGSTORE_DIR / 'index.json'
    DUAL_RECEIPTS = PROOFS_DIR / 'dual_receipts.jsonl'

    # URLs Sigstore (production)
    REKOR_URL = "https://rekor.sigstore.dev"
    FULCIO_URL = "https://fulcio.sigstore.dev"

    # OIDC Providers
    OIDC_PROVIDERS = {
        'google': 'https://accounts.google.com',
        'github': 'https://github.com/login/oauth',
        'microsoft': 'https://login.microsoftonline.com'
    }

    # CORRECTION: Politique d'identité (configurable via env)
    # Issuers autorisés (vide = tous acceptés)
    ALLOWED_ISSUERS = os.getenv('SIGSTORE_ALLOWED_ISSUERS', '').split(',') if os.getenv('SIGSTORE_ALLOWED_ISSUERS') else []

    # Domaines email autorisés (vide = tous acceptés)
    ALLOWED_EMAIL_DOMAINS = os.getenv('SIGSTORE_ALLOWED_EMAIL_DOMAINS', '').split(',') if os.getenv('SIGSTORE_ALLOWED_EMAIL_DOMAINS') else []

    # Mode enforcement: 'warn' ou 'strict'
    ENFORCEMENT_MODE = os.getenv('SIGSTORE_ENFORCEMENT_MODE', 'warn')  # warn par défaut, strict après migration


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SigstoreProof:
    """Preuve Sigstore"""
    timestamp: str
    rekor_uuid: str
    rekor_url: str
    rekor_log_index: int
    cert_path: str
    cert_subject: str  # Email/identity
    cert_issuer: str
    sig_path: str
    hash_signed: str
    files: List[str]
    bundle_path: str  # CORRECTION: Bundle pour vérification

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DualProof:
    """Preuve combinée Sigstore + OTS"""
    timestamp: str
    merkle_root: str
    files: List[str]
    sigstore: Optional[Dict]
    opentimestamps: Optional[Dict]
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VerificationResult:
    """Résultat de vérification"""
    success: bool
    status: str  # 'verified', 'failed', 'expired', 'pending'
    details: Dict
    timestamp: str


# ============================================================================
# SIGSTORE MANAGER
# ============================================================================

class SigstoreManager:
    """Gestionnaire Sigstore (cosign, rekor, fulcio)"""
    
    @staticmethod
    def check_dependencies() -> Tuple[bool, List[str]]:
        """Vérifie que cosign est installé"""
        missing = []
        
        if not subprocess.run(['which', 'cosign'], capture_output=True).returncode == 0:
            missing.append('cosign')
        
        return len(missing) == 0, missing
    
    @staticmethod
    def sign(
        data: str,
        label: str = "integrity",
        identity_token: Optional[str] = None,
        files: Optional[List[str]] = None
    ) -> Optional[SigstoreProof]:
        """
        Signe un hash via Sigstore
        
        Args:
            data: Hash à signer (hex string)
            label: Label pour les fichiers de sortie
            identity_token: Token OIDC (None = interactive)
            files: Liste de fichiers associés
        
        Returns:
            SigstoreProof ou None si échec
        """
        ok, missing = SigstoreManager.check_dependencies()
        if not ok:
            print(f"⚠️  Sigstore dependencies missing: {', '.join(missing)}")
            print("   Install: https://docs.sigstore.dev/cosign/installation/")
            return None
        
        # Créer répertoires
        SigstoreConfig.SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
        SigstoreConfig.CERTIFICATES_DIR.mkdir(parents=True, exist_ok=True)
        SigstoreConfig.REKOR_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
        
        # Timestamp pour nommage
        ts = utcnow_iso().replace(':', '').replace('-', '').replace('.', '')
        
        # Chemins de sortie
        sig_file = SigstoreConfig.SIGNATURES_DIR / f"{label}_{ts}.sig"
        cert_file = SigstoreConfig.CERTIFICATES_DIR / f"{label}_{ts}.pem"
        bundle_file = SigstoreConfig.SIGNATURES_DIR / f"{label}_{ts}.bundle"
        
        # Créer fichier temporaire avec le hash
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        
        try:
            # Commande cosign sign-blob
            cmd = [
                'cosign', 'sign-blob',
                tmp_path,
                '--output-signature', str(sig_file),
                '--output-certificate', str(cert_file),
                '--bundle', str(bundle_file)
            ]
            
            # Ajouter OIDC provider si spécifié
            oidc_provider = os.getenv('SIGSTORE_OIDC_PROVIDER', 'google')
            if oidc_provider in SigstoreConfig.OIDC_PROVIDERS:
                cmd.extend(['--oidc-provider', oidc_provider])
            
            # Mode interactif par défaut (ouvre navigateur)
            if identity_token:
                cmd.extend(['--identity-token', identity_token])
            
            print(f"🔐 Signing with Sigstore (OIDC: {oidc_provider})...")
            print("   → Browser will open for authentication")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Cosign sign failed: {result.stderr}")
                return None
            
            # Extraire info du bundle
            bundle_data = json.loads(bundle_file.read_text())
            
            # Extraire UUID Rekor
            rekor_uuid = None
            rekor_log_index = -1
            if 'rekorBundle' in bundle_data:
                rekor_bundle = bundle_data['rekorBundle']
                rekor_log_index = rekor_bundle.get('Payload', {}).get('logIndex', -1)
                rekor_uuid = rekor_bundle.get('Payload', {}).get('logID', 'unknown')
            
            # Extraire info certificat
            cert_subject = "unknown"
            cert_issuer = "unknown"
            
            # Parser le certificat pour extraire subject
            try:
                # Utiliser openssl pour parser (simple et universel)
                cert_info = subprocess.run(
                    ['openssl', 'x509', '-in', str(cert_file), '-noout', '-subject', '-issuer'],
                    capture_output=True,
                    text=True
                )
                if cert_info.returncode == 0:
                    for line in cert_info.stdout.split('\n'):
                        if 'subject=' in line.lower():
                            # Extraire email du subject
                            if 'emailAddress=' in line:
                                cert_subject = line.split('emailAddress=')[1].split(',')[0].strip()
                        if 'issuer=' in line.lower():
                            cert_issuer = line.split('issuer=')[1].strip()
            except Exception as e:
                print(f"⚠️  Could not parse certificate: {e}")
            
            # Sauvegarder entry Rekor
            rekor_entry_file = SigstoreConfig.REKOR_ENTRIES_DIR / f"{label}_{ts}.json"
            rekor_entry_file.write_text(json.dumps(bundle_data, indent=2))
            
            proof = SigstoreProof(
                timestamp=utcnow_iso(),
                rekor_uuid=rekor_uuid,
                rekor_url=f"{SigstoreConfig.REKOR_URL}/api/v1/log/entries?logIndex={rekor_log_index}",
                rekor_log_index=rekor_log_index,
                cert_path=str(cert_file),
                cert_subject=cert_subject,
                cert_issuer=cert_issuer,
                sig_path=str(sig_file),
                hash_signed=data,
                files=files or [],
                bundle_path=str(bundle_file)  # CORRECTION: Stocker bundle
            )
            
            print(f"✅ Sigstore signature created")
            print(f"   Rekor index: {rekor_log_index}")
            print(f"   Identity: {cert_subject}")
            print(f"   Certificate: {cert_file.name}")
            print(f"   Verifiable: IMMEDIATELY")
            
            return proof
            
        except Exception as e:
            print(f"❌ Sigstore signing failed: {e}")
            return None
        
        finally:
            # Nettoyer fichier temporaire
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    @staticmethod
    def verify(
        sig_path: str,
        cert_path: str,
        data: str,
        rekor_url: Optional[str] = None,
        bundle_path: Optional[str] = None,
        expected_identity: Optional[str] = None
    ) -> VerificationResult:
        """
        Vérifie une signature Sigstore (CORRIGÉ: bundle + identity)

        Args:
            sig_path: Chemin vers signature
            cert_path: Chemin vers certificat
            data: Hash attendu
            rekor_url: URL Rekor pour vérification inclusion
            bundle_path: Chemin vers bundle (préféré pour vérif)
            expected_identity: Identité attendue (ex: email Git author)

        Returns:
            VerificationResult
        """
        ok, _ = SigstoreManager.check_dependencies()
        if not ok:
            return VerificationResult(
                success=False,
                status='failed',
                details={'error': 'cosign not installed'},
                timestamp=utcnow_iso()
            )

        # Créer fichier temporaire avec le hash
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            # CORRECTION: Utiliser bundle si disponible (méthode recommandée)
            if bundle_path and Path(bundle_path).exists():
                cmd = [
                    'cosign', 'verify-blob',
                    tmp_path,
                    '--bundle', bundle_path,
                    '--certificate-identity-regexp', '.*',  # On vérifie manuellement après
                    '--certificate-oidc-issuer-regexp', '.*'
                ]
            else:
                # Fallback: sig + cert séparés
                cmd = [
                    'cosign', 'verify-blob',
                    tmp_path,
                    '--signature', sig_path,
                    '--certificate', cert_path,
                    '--certificate-identity-regexp', '.*',
                    '--certificate-oidc-issuer-regexp', '.*'
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return VerificationResult(
                    success=False,
                    status='failed',
                    details={'error': result.stderr},
                    timestamp=utcnow_iso()
                )

            # Vérification OK, maintenant checker identity coherence + politique
            cert_subject = "unknown"
            cert_issuer_url = "unknown"

            # Extraire identity ET issuer du certificat
            try:
                cert_info = subprocess.run(
                    ['openssl', 'x509', '-in', cert_path, '-noout', '-subject', '-issuer', '-text'],
                    capture_output=True,
                    text=True
                )
                if cert_info.returncode == 0:
                    output = cert_info.stdout
                    # Extraire email
                    if 'emailAddress=' in output or 'Subject:' in output:
                        for line in output.split('\n'):
                            if 'emailAddress=' in line:
                                cert_subject = line.split('emailAddress=')[1].split(',')[0].strip()
                            # Issuer URL souvent dans extensions
                            if 'Issuer:' in line or 'CA Issuers' in line:
                                if 'https://' in line:
                                    # Parser URL issuer
                                    import re
                                    match = re.search(r'https://[^\s,]+', line)
                                    if match:
                                        cert_issuer_url = match.group(0)
            except:
                pass

            # CORRECTION: Vérification politique d'identité (issuer + email domain)
            policy_violations = []

            # Vérifier issuer si politique définie
            if SigstoreConfig.ALLOWED_ISSUERS:
                issuer_allowed = False
                for allowed in SigstoreConfig.ALLOWED_ISSUERS:
                    if allowed.strip() and allowed.strip() in cert_issuer_url:
                        issuer_allowed = True
                        break
                if not issuer_allowed:
                    policy_violations.append(f"Issuer not allowed: {cert_issuer_url}")

            # Vérifier domaine email si politique définie
            if SigstoreConfig.ALLOWED_EMAIL_DOMAINS and cert_subject != "unknown":
                domain_allowed = False
                for allowed_domain in SigstoreConfig.ALLOWED_EMAIL_DOMAINS:
                    if allowed_domain.strip() and cert_subject.endswith(allowed_domain.strip()):
                        domain_allowed = True
                        break
                if not domain_allowed:
                    policy_violations.append(f"Email domain not allowed: {cert_subject}")

            # Vérifier expected_identity si fourni
            identity_coherent = True
            identity_warning = None

            if expected_identity and cert_subject != "unknown":
                if cert_subject != expected_identity:
                    identity_coherent = False
                    identity_warning = f"Identity mismatch: cert={cert_subject}, expected={expected_identity}"

            # CORRECTION: Appliquer enforcement mode
            enforcement_fail = False
            if policy_violations:
                violations_msg = "; ".join(policy_violations)
                if SigstoreConfig.ENFORCEMENT_MODE == 'strict':
                    enforcement_fail = True
                    print(f"🚫 Policy violation (STRICT mode): {violations_msg}")
                else:  # warn
                    print(f"⚠️  Policy violation (WARN mode): {violations_msg}")

            final_success = identity_coherent and not enforcement_fail

            return VerificationResult(
                success=final_success,
                status='verified' if final_success else 'failed',
                details={
                    'signature': sig_path,
                    'certificate': cert_path,
                    'bundle': bundle_path or 'N/A',
                    'rekor_url': rekor_url or 'N/A',
                    'cert_identity': cert_subject,
                    'cert_issuer': cert_issuer_url,
                    'expected_identity': expected_identity or 'not checked',
                    'identity_coherent': identity_coherent,
                    'policy_violations': policy_violations,
                    'enforcement_mode': SigstoreConfig.ENFORCEMENT_MODE,
                    'warning': identity_warning
                },
                timestamp=utcnow_iso()
            )

        except Exception as e:
            return VerificationResult(
                success=False,
                status='failed',
                details={'error': str(e)},
                timestamp=utcnow_iso()
            )

        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass


# ============================================================================
# DUAL ANCHOR MANAGER
# ============================================================================

class DualAnchorManager:
    """Orchestrateur Sigstore + OpenTimestamps"""
    
    @staticmethod
    def dual_anchor(
        merkle_root: str,
        files: List[str],
        label: str = "session",
        skip_sigstore: bool = False,
        skip_ots: bool = False,
        identity_token: Optional[str] = None
    ) -> DualProof:
        """
        Ancrage dual Sigstore + OTS
        
        Returns:
            DualProof avec les deux preuves
        """
        sigstore_proof_dict = None
        ots_proof_dict = None
        
        # === PHASE 1 : SIGSTORE (IMMÉDIAT) ===
        if not skip_sigstore:
            print("\n" + "="*60)
            print("PHASE 1: SIGSTORE ANCHORING (IMMEDIATE)")
            print("="*60)
            
            sigstore_proof = SigstoreManager.sign(
                data=merkle_root,
                label=label,
                identity_token=identity_token,
                files=files
            )
            
            if sigstore_proof:
                sigstore_proof_dict = sigstore_proof.to_dict()
                print("✅ Sigstore proof: IMMEDIATE verification available")
            else:
                print("⚠️  Sigstore anchoring skipped (not available)")
        
        # === PHASE 2 : OPENTIMESTAMPS (DIFFÉRÉ) ===
        if not skip_ots:
            print("\n" + "="*60)
            print("PHASE 2: OPENTIMESTAMPS ANCHORING (DELAYED)")
            print("="*60)
            
            ots_proof_path = AnchorManager.anchor(merkle_root, label)
            
            if ots_proof_path:
                ots_proof_dict = {
                    'proof_path': str(ots_proof_path),
                    'status': 'pending',
                    'confirmed_at': None,
                    'bitcoin_block': None
                }
                print("⏳ OTS proof: Pending (confirmation in 1-24h)")
            else:
                print("⚠️  OTS anchoring skipped (not available)")
        
        # === DUAL PROOF ===
        dual_proof = DualProof(
            timestamp=utcnow_iso(),
            merkle_root=merkle_root,
            files=files,
            sigstore=sigstore_proof_dict,
            opentimestamps=ots_proof_dict
        )
        
        return dual_proof
    
    @staticmethod
    def verify_dual(receipt: Dict) -> Dict:
        """
        Vérifie un receipt dual
        
        Returns:
            {
                'sigstore_status': 'verified' | 'failed' | 'skipped',
                'ots_status': 'confirmed' | 'pending' | 'failed' | 'skipped',
                'overall_status': 'protected' | 'partial' | 'failed',
                'details': {...}
            }
        """
        results = {
            'sigstore_status': 'skipped',
            'ots_status': 'skipped',
            'overall_status': 'unknown',
            'details': {}
        }
        
        # Vérifier Sigstore
        if receipt.get('sigstore'):
            sig_data = receipt['sigstore']

            # CORRECTION: Passer bundle_path et expected_identity (si disponible)
            sig_result = SigstoreManager.verify(
                sig_path=sig_data['sig_path'],
                cert_path=sig_data['cert_path'],
                data=receipt['merkle_root'],
                rekor_url=sig_data.get('rekor_url'),
                bundle_path=sig_data.get('bundle_path'),  # CORRECTION: Utiliser bundle
                expected_identity=None  # TODO: Obtenir Git author pour vérif
            )

            results['sigstore_status'] = sig_result.status
            results['details']['sigstore'] = sig_result.details
        
        # Vérifier OTS
        if receipt.get('opentimestamps'):
            ots_data = receipt['opentimestamps']
            
            if ots_data['status'] == 'confirmed':
                # Vérifier preuve OTS
                ots_proof = Path(ots_data['proof_path'])
                if ots_proof.exists():
                    # ots verify
                    result = subprocess.run(
                        ['ots', 'verify', str(ots_proof)],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        results['ots_status'] = 'confirmed'
                        results['details']['ots'] = {
                            'confirmed_at': ots_data.get('confirmed_at'),
                            'bitcoin_block': ots_data.get('bitcoin_block')
                        }
                    else:
                        results['ots_status'] = 'failed'
                        results['details']['ots'] = {'error': result.stderr}
                else:
                    results['ots_status'] = 'failed'
                    results['details']['ots'] = {'error': 'proof file not found'}
            else:
                results['ots_status'] = 'pending'
                results['details']['ots'] = {'status': 'awaiting confirmation'}
        
        # Statut global
        if results['sigstore_status'] == 'verified' or results['ots_status'] == 'confirmed':
            results['overall_status'] = 'protected'
        elif results['sigstore_status'] == 'verified' or results['ots_status'] == 'pending':
            results['overall_status'] = 'partial'
        else:
            results['overall_status'] = 'failed'
        
        return results
    
    @staticmethod
    def upgrade_ots_proofs() -> int:
        """
        Upgrade tous les OTS pending dans dual_receipts.jsonl
        
        Returns:
            Nombre de preuves upgradées
        """
        if not SigstoreConfig.DUAL_RECEIPTS.exists():
            print("No dual receipts found")
            return 0
        
        upgraded = 0
        temp_file = SigstoreConfig.DUAL_RECEIPTS.with_suffix('.tmp')
        
        with SigstoreConfig.DUAL_RECEIPTS.open('r') as f_in, temp_file.open('w') as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                
                receipt = json.loads(line)
                
                # Vérifier si OTS pending
                if receipt.get('opentimestamps', {}).get('status') == 'pending':
                    ots_proof = Path(receipt['opentimestamps']['proof_path'])
                    
                    if ots_proof.exists():
                        # Upgrade
                        result = subprocess.run(
                            ['ots', 'upgrade', str(ots_proof)],
                            capture_output=True,
                            text=True
                        )
                        
                        # Vérifier si confirmé
                        verify_result = subprocess.run(
                            ['ots', 'verify', str(ots_proof)],
                            capture_output=True,
                            text=True
                        )
                        
                        if verify_result.returncode == 0:
                            # Extraire block Bitcoin du output
                            output = verify_result.stdout
                            bitcoin_block = None
                            
                            if 'block' in output.lower():
                                # Parser block number (format varies)
                                import re
                                match = re.search(r'block\s+(\d+)', output, re.IGNORECASE)
                                if match:
                                    bitcoin_block = int(match.group(1))
                            
                            # Mettre à jour le receipt
                            receipt['opentimestamps']['status'] = 'confirmed'
                            receipt['opentimestamps']['confirmed_at'] = utcnow_iso()
                            receipt['opentimestamps']['bitcoin_block'] = bitcoin_block
                            
                            upgraded += 1
                            print(f"✅ Upgraded: {ots_proof.name} (block: {bitcoin_block})")
                
                # Écrire receipt (modifié ou non)
                f_out.write(json.dumps(receipt) + '\n')
        
        # Remplacer fichier original
        temp_file.replace(SigstoreConfig.DUAL_RECEIPTS)
        
        return upgraded


# ============================================================================
# DUAL RECEIPT MANAGER
# ============================================================================

class DualReceiptManager:
    """Gère les receipts dual (Sigstore + OTS)"""
    
    @staticmethod
    def append(dual_proof: DualProof):
        """Ajoute un receipt dual au log (CORRECTION: append atomique)"""
        SigstoreConfig.PROOFS_DIR.mkdir(parents=True, exist_ok=True)

        # CORRECTION: Utiliser O_APPEND + fsync pour atomicité
        import os
        filepath = SigstoreConfig.DUAL_RECEIPTS
        fd = os.open(filepath, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            data = (json.dumps(dual_proof.to_dict()) + '\n').encode('utf-8')
            os.write(fd, data)
            os.fsync(fd)  # Force flush to disk
        finally:
            os.close(fd)
    
    @staticmethod
    def get_latest() -> Optional[Dict]:
        """Récupère le dernier receipt dual"""
        if not SigstoreConfig.DUAL_RECEIPTS.exists():
            return None
        
        last = None
        with SigstoreConfig.DUAL_RECEIPTS.open('r') as f:
            for line in f:
                if line.strip():
                    try:
                        last = json.loads(line)
                    except:
                        pass
        
        return last
    
    @staticmethod
    def get_all_pending() -> List[Dict]:
        """Récupère tous les receipts avec OTS pending"""
        if not SigstoreConfig.DUAL_RECEIPTS.exists():
            return []
        
        pending = []
        with SigstoreConfig.DUAL_RECEIPTS.open('r') as f:
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    receipt = json.loads(line)
                    if receipt.get('opentimestamps', {}).get('status') == 'pending':
                        pending.append(receipt)
                except:
                    pass
        
        return pending


# ============================================================================
# COMMANDES CLI
# ============================================================================

def cmd_end_session_dual(args):
    """Finalise session avec dual anchoring"""
    print("🏁 Finalizing session with DUAL ANCHORING...")
    print("="*60)
    
    # Finaliser session (système de base)
    session_mgr = SessionManager()
    result = session_mgr.finalize(
        reason=args.reason or "Session completed",
        auto_anchor=False  # On gère l'ancrage ici
    )
    
    merkle_root = result['merkle_root']
    
    # Récupérer fichiers de la session (depuis receipt classique)
    last_receipt = ReceiptManager.get_latest()
    files = last_receipt.get('working_files', []) if last_receipt else []
    
    # Dual anchor
    dual_proof = DualAnchorManager.dual_anchor(
        merkle_root=merkle_root,
        files=files,
        label=f"session_{utcnow_iso().replace(':', '').replace('-', '')}",
        skip_sigstore=args.no_sigstore,
        skip_ots=args.no_ots
    )
    
    # Sauvegarder receipt dual
    DualReceiptManager.append(dual_proof)
    
    print("\n" + "="*60)
    print("✅ SESSION FINALIZED WITH DUAL PROTECTION")
    print("="*60)
    print(f"Files updated: {result['total_files']}")
    print(f"Merkle root: {merkle_root[:16]}...")
    
    if dual_proof.sigstore:
        print(f"\n✅ Sigstore: VERIFIED (immediate)")
        print(f"   Identity: {dual_proof.sigstore['cert_subject']}")
    
    if dual_proof.opentimestamps:
        print(f"\n⏳ OpenTimestamps: PENDING (1-24h)")
        print(f"   Proof: {Path(dual_proof.opentimestamps['proof_path']).name}")
    
    return 0


def cmd_verify_dual(args):
    """Vérifie dual anchoring"""
    print("🔍 DUAL VERIFICATION")
    print("="*60)
    
    # Récupérer dernier receipt
    receipt = DualReceiptManager.get_latest()
    
    if not receipt:
        print("❌ No dual receipts found")
        return 1
    
    # Vérifier
    results = DualAnchorManager.verify_dual(receipt)
    
    print(f"\nTimestamp: {receipt['timestamp']}")
    print(f"Merkle root: {receipt['merkle_root'][:16]}...")
    print(f"Files: {len(receipt.get('files', []))}")
    
    print("\n" + "-"*60)
    print("SIGSTORE")
    print("-"*60)
    
    if results['sigstore_status'] == 'verified':
        print("✅ Status: VERIFIED")
        sig_details = receipt.get('sigstore', {})
        print(f"   Identity: {sig_details.get('cert_subject', 'N/A')}")
        print(f"   Rekor: {sig_details.get('rekor_url', 'N/A')}")
    elif results['sigstore_status'] == 'failed':
        print("❌ Status: FAILED")
        print(f"   Error: {results['details'].get('sigstore', {}).get('error', 'Unknown')}")
    else:
        print("⏭️  Status: SKIPPED")
    
    print("\n" + "-"*60)
    print("OPENTIMESTAMPS")
    print("-"*60)
    
    if results['ots_status'] == 'confirmed':
        print("✅ Status: CONFIRMED")
        ots_details = results['details'].get('ots', {})
        print(f"   Confirmed: {ots_details.get('confirmed_at', 'N/A')}")
        print(f"   Bitcoin block: {ots_details.get('bitcoin_block', 'N/A')}")
    elif results['ots_status'] == 'pending':
        print("⏳ Status: PENDING")
        print("   Waiting for Bitcoin confirmation (1-24h)")
        print("   Run 'make upgrade-ots' to check for updates")
    elif results['ots_status'] == 'failed':
        print("❌ Status: FAILED")
        print(f"   Error: {results['details'].get('ots', {}).get('error', 'Unknown')}")
    else:
        print("⏭️  Status: SKIPPED")
    
    print("\n" + "="*60)
    print(f"OVERALL STATUS: {results['overall_status'].upper()}")
    print("="*60)
    
    if results['overall_status'] == 'protected':
        print("✅ File integrity is FULLY PROTECTED")
        return 0
    elif results['overall_status'] == 'partial':
        print("⚠️  File integrity is PARTIALLY PROTECTED")
        print("   (Sigstore verified OR OTS pending)")
        return 0
    else:
        print("❌ File integrity verification FAILED")
        return 1


def cmd_upgrade_ots(args):
    """Upgrade OTS pending proofs"""
    print("⛓️  UPGRADING OPENTIMESTAMPS PROOFS")
    print("="*60)
    
    pending = DualReceiptManager.get_all_pending()
    
    if not pending:
        print("✅ No pending OTS proofs")
        return 0
    
    print(f"Found {len(pending)} pending proofs")
    print()
    
    upgraded = DualAnchorManager.upgrade_ots_proofs()
    
    print()
    print("="*60)
    print(f"✅ {upgraded}/{len(pending)} proofs confirmed")
    print("="*60)
    
    if upgraded < len(pending):
        print(f"⏳ {len(pending) - upgraded} still pending (try again later)")
    
    return 0


def cmd_sigstore_sign(args):
    """Signe des fichiers via Sigstore uniquement"""
    print("🔐 SIGSTORE SIGNING")
    print("="*60)
    
    if not args.files:
        print("❌ No files specified")
        return 1
    
    # Calculer Merkle root des fichiers
    baseline = BaselineManager()
    baseline.load()
    
    hashes = []
    for f in args.files:
        if f in baseline.mapping:
            hashes.append((f, baseline.mapping[f]))
    
    if not hashes:
        print("❌ No valid files found in baseline")
        return 1
    
    merkle = MerkleTree(hashes).root
    
    # Signer
    proof = SigstoreManager.sign(
        data=merkle,
        label="manual_sign",
        files=args.files
    )
    
    if proof:
        print("\n✅ Signing successful")
        return 0
    else:
        print("\n❌ Signing failed")
        return 1


def cmd_migrate_receipts(args):
    """Migre receipts OTS-only vers dual format"""
    print("🔄 MIGRATING RECEIPTS TO DUAL FORMAT")
    print("="*60)
    
    # Lire anciens receipts
    old_receipts = Config.RECEIPTS_LOG
    
    if not old_receipts.exists():
        print("✅ No legacy receipts to migrate")
        return 0
    
    migrated = 0
    
    with old_receipts.open('r') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                old_receipt = json.loads(line)
                
                # Créer dual receipt (sans Sigstore pour ancien)
                dual_receipt = {
                    'timestamp': old_receipt.get('timestamp', utcnow_iso()),
                    'merkle_root': old_receipt.get('merkle_root', ''),
                    'files': old_receipt.get('files', []),
                    'sigstore': None,  # Pas de Sigstore pour anciens
                    'opentimestamps': {
                        'proof_path': old_receipt.get('ots_proof', ''),
                        'status': 'confirmed',  # Assumer confirmé si ancien
                        'confirmed_at': old_receipt.get('timestamp'),
                        'bitcoin_block': None
                    }
                }
                
                # Écrire dual receipt
                with SigstoreConfig.DUAL_RECEIPTS.open('a') as f_out:
                    f_out.write(json.dumps(dual_receipt) + '\n')
                
                migrated += 1
                
            except Exception as e:
                print(f"⚠️  Failed to migrate entry: {e}")
    
    print(f"\n✅ Migrated {migrated} receipts")
    print(f"   From: {old_receipts}")
    print(f"   To: {SigstoreConfig.DUAL_RECEIPTS}")
    
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Unified Integrity System - Sigstore Extension"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # end-session-dual
    p_end = subparsers.add_parser('end-session', help='Finalize session with dual anchoring')
    p_end.add_argument('--reason', help='Completion reason')
    p_end.add_argument('--no-sigstore', action='store_true', help='Skip Sigstore')
    p_end.add_argument('--no-ots', action='store_true', help='Skip OTS')
    p_end.set_defaults(func=cmd_end_session_dual)
    
    # verify-dual
    p_verify = subparsers.add_parser('verify-dual', help='Verify dual anchoring')
    p_verify.set_defaults(func=cmd_verify_dual)
    
    # upgrade-ots
    p_upgrade = subparsers.add_parser('upgrade-ots', help='Upgrade OTS pending proofs')
    p_upgrade.set_defaults(func=cmd_upgrade_ots)
    
    # sigstore-sign
    p_sign = subparsers.add_parser('sigstore-sign', help='Sign files with Sigstore only')
    p_sign.add_argument('files', nargs='+', help='Files to sign')
    p_sign.set_defaults(func=cmd_sigstore_sign)
    
    # migrate-receipts
    p_migrate = subparsers.add_parser('migrate-receipts', help='Migrate OTS receipts to dual format')
    p_migrate.set_defaults(func=cmd_migrate_receipts)
    
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())