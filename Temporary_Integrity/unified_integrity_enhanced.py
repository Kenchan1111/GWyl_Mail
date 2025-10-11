#!/usr/bin/env python3
"""
Unified Integrity System - Enhanced Verification
================================================

Ajoute les vérifications manquantes pour un système d'intégrité complet :
1. Vérification de chaîne complète (SHA → Merkle → Sigstore → OTS → Git)
2. Cohérence des timestamps
3. Cohérence des identités (Git ↔ Sigstore)
4. Protection contre rollback OTS
5. Vérification topologie Git
6. Alerting automatique

Usage:
    # Vérification complète
    python unified_integrity_enhanced.py verify-full-chain

    # Audit complet
    python unified_integrity_enhanced.py audit-all

    # Monitoring continu
    python unified_integrity_enhanced.py monitor --interval 60
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import des modules existants
try:
    from unified_integrity import (
        Config, BaselineManager, compute_sha256, MerkleTree, utcnow_iso
    )
    from unified_integrity_sigstore import (
        SigstoreManager, DualAnchorManager, DualReceiptManager,
        SigstoreConfig
    )
    from unified_integrity_git import (
        GitHelper, GitProofManager, GitConfig
    )
except ImportError as e:
    print(f"⚠️  Modules requis manquants: {e}")
    print("   Assurez-vous que unified_integrity*.py sont dans le même répertoire")
    sys.exit(1)


# ============================================================================
# CONFIGURATION ENHANCED
# ============================================================================

class EnhancedConfig:
    """Configuration des vérifications avancées"""

    # Tolérance temporelle (secondes)
    TIMESTAMP_TOLERANCE = 300  # 5 minutes

    # Alerting
    ALERTING_CONFIG = Path('.integrity/alerting.yml')
    ALERT_LOG = Path('logs/alerts.jsonl')

    # Révocations
    REVOCATIONS_LOG = Path('.integrity/revocations.jsonl')

    # Audit
    AUDIT_LOG = Path('logs/audit.jsonl')


# ============================================================================
# ENUMS ET DATA CLASSES
# ============================================================================

class VerificationLevel(Enum):
    """Niveaux de vérification"""
    BASIC = "basic"           # SHA-256 uniquement
    STANDARD = "standard"     # SHA + Merkle
    FULL = "full"            # SHA + Merkle + Sigstore + OTS
    PARANOID = "paranoid"    # Full + Git + Identity + Timestamps


class AlertSeverity(Enum):
    """Sévérité des alertes"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ChainVerificationResult:
    """Résultat de vérification de chaîne complète"""
    success: bool
    level: VerificationLevel
    layers: Dict[str, bool]  # {'sha256': True, 'merkle': True, ...}
    issues: List[str]
    timestamp: str
    details: Dict

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'level': self.level.value
        }


@dataclass
class TimestampCoherenceResult:
    """Résultat vérification cohérence timestamps"""
    coherent: bool
    git_timestamp: str
    sigstore_timestamp: str
    ots_timestamp: Optional[str]
    max_delta_seconds: float
    tolerance_seconds: int
    issues: List[str]


@dataclass
class IdentityCoherenceResult:
    """Résultat vérification cohérence identités"""
    coherent: bool
    git_author: str
    git_email: str
    sigstore_identity: str
    match: bool
    issues: List[str]


@dataclass
class Alert:
    """Alerte système"""
    timestamp: str
    severity: AlertSeverity
    type: str
    message: str
    details: Dict
    commit_sha: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'severity': self.severity.value
        }


# ============================================================================
# FULL CHAIN VERIFIER
# ============================================================================

class FullChainVerifier:
    """Vérificateur de chaîne complète d'intégrité"""

    @staticmethod
    def verify_full_chain(
        commit_sha: Optional[str] = None,
        level: VerificationLevel = VerificationLevel.FULL
    ) -> ChainVerificationResult:
        """
        Vérifie la chaîne complète d'intégrité

        Layers:
        1. SHA-256: Fichiers actuels vs baseline
        2. Merkle: Reconstruction Merkle root
        3. Sigstore: Signature Merkle root
        4. OTS: Preuve OTS Merkle root
        5. Git: Metadata commit
        6. Identity: Git author == Sigstore identity
        7. Timestamps: Cohérence temporelle
        """
        layers = {}
        issues = []
        details = {}

        # Récupérer commit SHA
        if not commit_sha:
            commit_sha = GitHelper.get_current_commit()
            if not commit_sha:
                return ChainVerificationResult(
                    success=False,
                    level=level,
                    layers={},
                    issues=["Not in a Git repository"],
                    timestamp=utcnow_iso(),
                    details={}
                )

        # === LAYER 1: SHA-256 ===
        try:
            baseline = BaselineManager()
            baseline.load()
            verification = baseline.verify()

            if verification['mismatch'] or verification['missing']:
                layers['sha256'] = False
                issues.append(f"SHA-256: {len(verification['mismatch'])} mismatches, "
                            f"{len(verification['missing'])} missing files")
            else:
                layers['sha256'] = True

            details['sha256'] = {
                'ok': len(verification['ok']),
                'mismatch': len(verification['mismatch']),
                'missing': len(verification['missing'])
            }
        except Exception as e:
            layers['sha256'] = False
            issues.append(f"SHA-256 verification failed: {e}")

        if level == VerificationLevel.BASIC:
            return ChainVerificationResult(
                success=layers.get('sha256', False),
                level=level,
                layers=layers,
                issues=issues,
                timestamp=utcnow_iso(),
                details=details
            )

        # === LAYER 2: MERKLE ===
        try:
            # Récupérer preuve commit
            git_proof = GitProofManager.get_commit_proof(commit_sha)

            if git_proof:
                expected_merkle = git_proof.dual_proof['merkle_root']

                # CORRECTION CRITIQUE: Recalculer Merkle UNIQUEMENT sur les fichiers du commit
                # (pas toute la baseline, sinon faux négatif systématique)
                files_in_proof = git_proof.dual_proof.get('files', git_proof.files_modified)

                if files_in_proof:
                    # Construire Merkle sur les MÊMES fichiers que ceux ancrés
                    proof_hashes = []
                    for filepath in files_in_proof:
                        if filepath in baseline.mapping:
                            proof_hashes.append((filepath, baseline.mapping[filepath]))
                        elif Path(filepath).exists():
                            # Fichier pas dans baseline mais existe (nouveau fichier)
                            current_hash = compute_sha256(Path(filepath))
                            proof_hashes.append((filepath, current_hash))

                    if proof_hashes:
                        current_merkle = MerkleTree(proof_hashes).root
                    else:
                        current_merkle = None
                        issues.append("No files to compute Merkle root")
                else:
                    # Fallback: toute la baseline (ancien comportement)
                    file_hashes = [(p, h) for p, h in baseline.mapping.items()]
                    current_merkle = MerkleTree(file_hashes).root

                if current_merkle and current_merkle == expected_merkle:
                    layers['merkle'] = True
                elif current_merkle:
                    layers['merkle'] = False
                    issues.append(f"Merkle mismatch: expected {expected_merkle[:16]}... "
                                f"got {current_merkle[:16]}...")
                else:
                    layers['merkle'] = False

                details['merkle'] = {
                    'current': current_merkle,
                    'expected': expected_merkle,
                    'match': current_merkle == expected_merkle if current_merkle else False,
                    'files_checked': len(files_in_proof) if files_in_proof else 'all'
                }
            else:
                layers['merkle'] = False
                issues.append("No Git proof found for commit")
        except Exception as e:
            layers['merkle'] = False
            issues.append(f"Merkle verification failed: {e}")

        if level == VerificationLevel.STANDARD:
            return ChainVerificationResult(
                success=all(layers.values()),
                level=level,
                layers=layers,
                issues=issues,
                timestamp=utcnow_iso(),
                details=details
            )

        # === LAYER 3: SIGSTORE ===
        if git_proof and git_proof.dual_proof.get('sigstore'):
            try:
                sigstore_data = git_proof.dual_proof['sigstore']

                sig_result = SigstoreManager.verify(
                    sig_path=sigstore_data['sig_path'],
                    cert_path=sigstore_data['cert_path'],
                    data=git_proof.dual_proof['merkle_root']
                )

                layers['sigstore'] = sig_result.success
                if not sig_result.success:
                    issues.append(f"Sigstore verification failed: {sig_result.details.get('error')}")

                details['sigstore'] = sig_result.details
            except Exception as e:
                layers['sigstore'] = False
                issues.append(f"Sigstore verification error: {e}")
        else:
            layers['sigstore'] = False
            issues.append("No Sigstore proof available")

        # === LAYER 4: OTS ===
        if git_proof and git_proof.dual_proof.get('opentimestamps'):
            try:
                ots_data = git_proof.dual_proof['opentimestamps']
                ots_proof_path = Path(ots_data['proof_path'])

                if ots_proof_path.exists():
                    if ots_data['status'] == 'confirmed':
                        # Vérifier preuve OTS
                        result = subprocess.run(
                            ['ots', 'verify', str(ots_proof_path)],
                            capture_output=True,
                            text=True
                        )

                        layers['ots'] = result.returncode == 0
                        if result.returncode != 0:
                            issues.append(f"OTS verification failed: {result.stderr}")

                        details['ots'] = {
                            'status': 'confirmed',
                            'bitcoin_block': ots_data.get('bitcoin_block'),
                            'verified': result.returncode == 0
                        }
                    else:
                        layers['ots'] = None  # Pending, pas d'erreur
                        details['ots'] = {'status': 'pending'}
                else:
                    layers['ots'] = False
                    issues.append(f"OTS proof file missing: {ots_proof_path}")
            except Exception as e:
                layers['ots'] = False
                issues.append(f"OTS verification error: {e}")
        else:
            layers['ots'] = False
            issues.append("No OTS proof available")

        if level == VerificationLevel.FULL:
            # Considérer OTS pending comme succès partiel
            success = (layers.get('sha256', False) and
                      layers.get('merkle', False) and
                      layers.get('sigstore', False))

            return ChainVerificationResult(
                success=success,
                level=level,
                layers=layers,
                issues=issues,
                timestamp=utcnow_iso(),
                details=details
            )

        # === LAYER 5+6+7: PARANOID (Git + Identity + Timestamps) ===
        if level == VerificationLevel.PARANOID and git_proof:
            # Git metadata
            commit_info = GitHelper.get_commit_info(commit_sha)
            if commit_info:
                layers['git'] = True
                details['git'] = commit_info
            else:
                layers['git'] = False
                issues.append("Could not retrieve Git commit info")

            # Identity coherence
            identity_result = FullChainVerifier.verify_identity_coherence(git_proof)
            layers['identity'] = identity_result.coherent
            if not identity_result.coherent:
                issues.extend(identity_result.issues)
            details['identity'] = asdict(identity_result)

            # Timestamp coherence
            timestamp_result = FullChainVerifier.verify_timestamp_coherence(git_proof)
            layers['timestamps'] = timestamp_result.coherent
            if not timestamp_result.coherent:
                issues.extend(timestamp_result.issues)
            details['timestamps'] = asdict(timestamp_result)

        # Succès global
        success = all(v for k, v in layers.items() if v is not None and k not in ['ots'])

        return ChainVerificationResult(
            success=success,
            level=level,
            layers=layers,
            issues=issues,
            timestamp=utcnow_iso(),
            details=details
        )

    @staticmethod
    def verify_identity_coherence(git_proof) -> IdentityCoherenceResult:
        """Vérifie que Git author == Sigstore identity"""
        # Extraire email Git
        git_author_full = git_proof.commit_author
        email_match = re.search(r'<(.+?)>', git_author_full)
        git_email = email_match.group(1) if email_match else ""

        git_author_name = git_author_full.split('<')[0].strip()

        # Extraire identité Sigstore
        sigstore_identity = ""
        if git_proof.dual_proof.get('sigstore'):
            sigstore_identity = git_proof.dual_proof['sigstore'].get('cert_subject', '')

        # Comparer
        match = git_email.lower() == sigstore_identity.lower()

        issues = []
        if not match:
            issues.append(
                f"Identity mismatch: Git author '{git_email}' != "
                f"Sigstore identity '{sigstore_identity}'"
            )

        return IdentityCoherenceResult(
            coherent=match,
            git_author=git_author_name,
            git_email=git_email,
            sigstore_identity=sigstore_identity,
            match=match,
            issues=issues
        )

    @staticmethod
    def verify_timestamp_coherence(
        git_proof,
        tolerance_seconds: int = EnhancedConfig.TIMESTAMP_TOLERANCE
    ) -> TimestampCoherenceResult:
        """Vérifie la cohérence des timestamps (Git, Sigstore, OTS)"""

        def parse_timestamp(ts_str: str) -> datetime:
            """Parse timestamp ISO ou Git format"""
            try:
                # Try ISO format
                return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            except:
                # Try Git format (YYYY-MM-DD HH:MM:SS +ZZZZ)
                try:
                    return datetime.strptime(ts_str[:19], '%Y-%m-%d %H:%M:%S')
                except:
                    return None

        # Extraire timestamps
        git_ts_str = git_proof.commit_date
        git_ts = parse_timestamp(git_ts_str)

        sigstore_ts_str = git_proof.dual_proof.get('sigstore', {}).get('timestamp', '')
        sigstore_ts = parse_timestamp(sigstore_ts_str)

        ots_ts_str = git_proof.dual_proof.get('opentimestamps', {}).get('timestamp')
        ots_ts = parse_timestamp(ots_ts_str) if ots_ts_str else None

        # Calculer deltas
        timestamps = [ts for ts in [git_ts, sigstore_ts, ots_ts] if ts]

        if len(timestamps) < 2:
            return TimestampCoherenceResult(
                coherent=False,
                git_timestamp=git_ts_str,
                sigstore_timestamp=sigstore_ts_str,
                ots_timestamp=ots_ts_str,
                max_delta_seconds=0,
                tolerance_seconds=tolerance_seconds,
                issues=["Insufficient timestamps to compare"]
            )

        # Max delta
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        max_delta = (max_ts - min_ts).total_seconds()

        coherent = max_delta <= tolerance_seconds

        issues = []
        if not coherent:
            issues.append(
                f"Timestamp delta ({max_delta:.0f}s) exceeds tolerance ({tolerance_seconds}s)"
            )
            issues.append(f"  Git:      {git_ts_str}")
            issues.append(f"  Sigstore: {sigstore_ts_str}")
            if ots_ts_str:
                issues.append(f"  OTS:      {ots_ts_str}")

        return TimestampCoherenceResult(
            coherent=coherent,
            git_timestamp=git_ts_str,
            sigstore_timestamp=sigstore_ts_str,
            ots_timestamp=ots_ts_str,
            max_delta_seconds=max_delta,
            tolerance_seconds=tolerance_seconds,
            issues=issues
        )


# ============================================================================
# OTS ROLLBACK PROTECTION
# ============================================================================

class OTSRollbackProtector:
    """Protection contre suppression/dégradation des preuves OTS"""

    @staticmethod
    def verify_ots_integrity() -> List[str]:
        """Vérifie que toutes les preuves OTS déclarées existent"""
        issues = []

        # Vérifier dual_receipts.jsonl
        if not SigstoreConfig.DUAL_RECEIPTS.exists():
            return issues

        with SigstoreConfig.DUAL_RECEIPTS.open('r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    receipt = json.loads(line)

                    if receipt.get('opentimestamps'):
                        ots_data = receipt['opentimestamps']
                        proof_path = Path(ots_data['proof_path'])

                        if not proof_path.exists():
                            issues.append(
                                f"Missing OTS proof at line {line_num}: {proof_path}"
                            )
                except Exception as e:
                    issues.append(f"Error parsing receipt line {line_num}: {e}")

        return issues

    @staticmethod
    def create_ots_backup(backup_dir: Path = Path('backups/ots')):
        """Crée une sauvegarde des preuves OTS"""
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'ots_backup_{timestamp}.tar.gz'

        # Tar.gz des preuves OTS
        subprocess.run([
            'tar', '-czf', str(backup_file),
            '-C', str(SigstoreConfig.PROOFS_DIR.parent),
            str(SigstoreConfig.PROOFS_DIR.name)
        ], check=True)

        return backup_file


# ============================================================================
# GIT TOPOLOGY VERIFIER
# ============================================================================

class GitTopologyVerifier:
    """Vérificateur de topologie Git (chaîne continue de preuves)"""

    @staticmethod
    def verify_continuous_chain(
        from_commit: Optional[str] = None,
        to_commit: Optional[str] = None
    ) -> Dict:
        """
        Vérifie que tous les commits entre from_commit et to_commit ont des preuves
        """
        if not to_commit:
            to_commit = GitHelper.get_current_commit()

        if not from_commit:
            # Trouver premier commit avec preuve
            from_commit = GitTopologyVerifier._find_first_proof_commit()

        # Récupérer tous les commits
        result = subprocess.run(
            ['git', 'rev-list', f'{from_commit}..{to_commit}'],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                'success': False,
                'error': f"Git rev-list failed: {result.stderr}"
            }

        commits = [c.strip() for c in result.stdout.split('\n') if c.strip()]

        # Vérifier chaque commit
        missing_proofs = []
        broken_chains = []

        for commit_sha in commits:
            proof = GitProofManager.get_commit_proof(commit_sha)

            if not proof:
                missing_proofs.append(commit_sha)
            else:
                # Vérifier que le parent a aussi une preuve
                parent_result = subprocess.run(
                    ['git', 'rev-parse', f'{commit_sha}^'],
                    capture_output=True,
                    text=True
                )

                if parent_result.returncode == 0:
                    parent_sha = parent_result.stdout.strip()
                    parent_proof = GitProofManager.get_commit_proof(parent_sha)

                    if not parent_proof:
                        broken_chains.append({
                            'commit': commit_sha,
                            'parent': parent_sha,
                            'reason': 'parent has no proof'
                        })

        return {
            'success': len(missing_proofs) == 0 and len(broken_chains) == 0,
            'total_commits': len(commits),
            'missing_proofs': missing_proofs,
            'broken_chains': broken_chains
        }

    @staticmethod
    def _find_first_proof_commit() -> Optional[str]:
        """Trouve le premier commit avec une preuve"""
        if not GitConfig.COMMITS_DIR.exists():
            return None

        # Récupérer tous les commits avec preuves
        proof_files = list(GitConfig.COMMITS_DIR.glob('*.json'))

        if not proof_files:
            return None

        # Récupérer le commit SHA du plus ancien proof
        oldest_proof = min(proof_files, key=lambda p: p.stat().st_mtime)

        try:
            data = json.loads(oldest_proof.read_text())
            return data['commit_sha']
        except:
            return None


# ============================================================================
# ALERTING SYSTEM
# ============================================================================

class AlertingSystem:
    """Système d'alerting multi-canal"""

    @staticmethod
    def load_config() -> Dict:
        """Charge la configuration d'alerting"""
        if not EnhancedConfig.ALERTING_CONFIG.exists():
            # Config par défaut
            return {
                'enabled': False,
                'channels': {
                    'email': None,
                    'slack_webhook': None,
                    'log_file': True
                },
                'triggers': {
                    'mismatch_detected': AlertSeverity.CRITICAL.value,
                    'missing_proof': AlertSeverity.WARNING.value,
                    'identity_mismatch': AlertSeverity.CRITICAL.value,
                    'timestamp_incoherent': AlertSeverity.WARNING.value,
                    'ots_missing': AlertSeverity.WARNING.value,
                    'broken_chain': AlertSeverity.CRITICAL.value
                }
            }

        # TODO: Parser YAML (nécessite PyYAML)
        return {'enabled': False}

    @staticmethod
    def send_alert(alert: Alert):
        """Envoie une alerte selon la configuration"""
        config = AlertingSystem.load_config()

        if not config.get('enabled', False):
            # Toujours logger
            AlertingSystem._log_alert(alert)
            return

        channels = config.get('channels', {})

        # Email
        if channels.get('email'):
            AlertingSystem._send_email(alert, channels['email'])

        # Slack
        if channels.get('slack_webhook'):
            AlertingSystem._send_slack(alert, channels['slack_webhook'])

        # Log file
        if channels.get('log_file', True):
            AlertingSystem._log_alert(alert)

    @staticmethod
    def _log_alert(alert: Alert):
        """Log une alerte dans le fichier"""
        EnhancedConfig.ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)

        with EnhancedConfig.ALERT_LOG.open('a') as f:
            f.write(json.dumps(alert.to_dict()) + '\n')

    @staticmethod
    def _send_email(alert: Alert, email_config: Dict):
        """Envoie alerte par email"""
        # TODO: Implémenter envoi email
        pass

    @staticmethod
    def _send_slack(alert: Alert, webhook_url: str):
        """Envoie alerte sur Slack"""
        # TODO: Implémenter webhook Slack
        pass


# ============================================================================
# AUDIT SYSTEM
# ============================================================================

class AuditSystem:
    """Système d'audit complet"""

    @staticmethod
    def run_full_audit() -> Dict:
        """Exécute un audit complet du système"""
        audit_results = {
            'timestamp': utcnow_iso(),
            'checks': {}
        }

        print("🔍 AUDIT COMPLET DU SYSTÈME D'INTÉGRITÉ")
        print("=" * 70)
        print()

        # 1. Full chain verification
        print("1️⃣  Vérification chaîne complète...")
        chain_result = FullChainVerifier.verify_full_chain(
            level=VerificationLevel.PARANOID
        )
        audit_results['checks']['full_chain'] = chain_result.to_dict()

        if chain_result.success:
            print("   ✅ Chaîne d'intégrité VALIDE")
        else:
            print("   ❌ Chaîne d'intégrité COMPROMISE")
            for issue in chain_result.issues:
                print(f"      • {issue}")
        print()

        # 2. OTS integrity
        print("2️⃣  Vérification intégrité OTS...")
        ots_issues = OTSRollbackProtector.verify_ots_integrity()
        audit_results['checks']['ots_integrity'] = {
            'success': len(ots_issues) == 0,
            'issues': ots_issues
        }

        if len(ots_issues) == 0:
            print("   ✅ Preuves OTS intactes")
        else:
            print(f"   ⚠️  {len(ots_issues)} preuves OTS manquantes")
            for issue in ots_issues[:5]:
                print(f"      • {issue}")
        print()

        # 3. Git topology
        print("3️⃣  Vérification topologie Git...")
        topology_result = GitTopologyVerifier.verify_continuous_chain()
        audit_results['checks']['git_topology'] = topology_result

        if topology_result.get('success', False):
            print(f"   ✅ Chaîne Git continue ({topology_result['total_commits']} commits)")
        else:
            print("   ⚠️  Chaîne Git incomplète")
            if topology_result.get('missing_proofs'):
                print(f"      • {len(topology_result['missing_proofs'])} commits sans preuve")
            if topology_result.get('broken_chains'):
                print(f"      • {len(topology_result['broken_chains'])} ruptures de chaîne")
        print()

        # 4. Alerting health
        print("4️⃣  Vérification système d'alerting...")
        alert_config = AlertingSystem.load_config()
        audit_results['checks']['alerting'] = {
            'enabled': alert_config.get('enabled', False),
            'channels': list(alert_config.get('channels', {}).keys())
        }

        if alert_config.get('enabled'):
            print("   ✅ Alerting activé")
        else:
            print("   ⚠️  Alerting désactivé")
        print()

        # 5. Statistiques globales
        print("📊 STATISTIQUES")
        print("-" * 70)

        baseline = BaselineManager()
        baseline.load()
        print(f"   Fichiers trackés: {len(baseline.mapping)}")

        if GitConfig.COMMITS_DIR.exists():
            proof_count = len(list(GitConfig.COMMITS_DIR.glob('*.json')))
            print(f"   Commits avec preuves: {proof_count}")

        if EnhancedConfig.ALERT_LOG.exists():
            with EnhancedConfig.ALERT_LOG.open('r') as f:
                alert_count = sum(1 for _ in f)
            print(f"   Alertes totales: {alert_count}")

        print()

        # Score global
        total_checks = len(audit_results['checks'])
        passed_checks = sum(1 for c in audit_results['checks'].values()
                          if c.get('success', False))
        score = (passed_checks / total_checks * 100) if total_checks > 0 else 0

        print("=" * 70)
        print(f"SCORE GLOBAL: {score:.0f}% ({passed_checks}/{total_checks} checks passed)")
        print("=" * 70)

        audit_results['score'] = score

        # Sauvegarder audit
        EnhancedConfig.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with EnhancedConfig.AUDIT_LOG.open('a') as f:
            f.write(json.dumps(audit_results) + '\n')

        return audit_results


# ============================================================================
# CLI COMMANDS
# ============================================================================

def cmd_verify_full_chain(args):
    """Vérifie la chaîne complète"""
    level = VerificationLevel[args.level.upper()]

    result = FullChainVerifier.verify_full_chain(
        commit_sha=args.commit,
        level=level
    )

    print("🔍 VÉRIFICATION CHAÎNE COMPLÈTE")
    print("=" * 70)
    print(f"Level: {result.level.value}")
    print(f"Commit: {args.commit or 'HEAD'}")
    print()

    print("Layers:")
    for layer, status in result.layers.items():
        if status is True:
            icon = "✅"
        elif status is False:
            icon = "❌"
        else:
            icon = "⏳"
        print(f"  {icon} {layer}")

    print()

    if result.issues:
        print("Issues:")
        for issue in result.issues:
            print(f"  • {issue}")
        print()

    if result.success:
        print("✅ VÉRIFICATION RÉUSSIE")
        return 0
    else:
        print("❌ VÉRIFICATION ÉCHOUÉE")

        # Envoyer alerte
        alert = Alert(
            timestamp=utcnow_iso(),
            severity=AlertSeverity.CRITICAL,
            type='chain_verification_failed',
            message='Full chain verification failed',
            details=result.to_dict(),
            commit_sha=args.commit
        )
        AlertingSystem.send_alert(alert)

        return 1


def cmd_audit_all(args):
    """Audit complet"""
    results = AuditSystem.run_full_audit()

    if results['score'] >= 80:
        return 0
    else:
        return 1


def cmd_verify_ots_integrity(args):
    """Vérifie intégrité OTS"""
    print("🔍 Vérification intégrité OTS")
    print("=" * 70)

    issues = OTSRollbackProtector.verify_ots_integrity()

    if len(issues) == 0:
        print("✅ Toutes les preuves OTS sont présentes")
        return 0
    else:
        print(f"⚠️  {len(issues)} preuves OTS manquantes:")
        for issue in issues:
            print(f"  • {issue}")

        # Alerte
        alert = Alert(
            timestamp=utcnow_iso(),
            severity=AlertSeverity.WARNING,
            type='ots_proofs_missing',
            message=f'{len(issues)} OTS proofs missing',
            details={'issues': issues}
        )
        AlertingSystem.send_alert(alert)

        return 1


def cmd_verify_git_topology(args):
    """Vérifie topologie Git"""
    print("🔍 Vérification topologie Git")
    print("=" * 70)

    result = GitTopologyVerifier.verify_continuous_chain(
        from_commit=args.from_commit,
        to_commit=args.to_commit
    )

    if result.get('success'):
        print(f"✅ Chaîne continue ({result['total_commits']} commits)")
        return 0
    else:
        print("❌ Chaîne incomplète")

        if result.get('missing_proofs'):
            print(f"\n{len(result['missing_proofs'])} commits sans preuve:")
            for sha in result['missing_proofs'][:10]:
                print(f"  • {sha}")

        if result.get('broken_chains'):
            print(f"\n{len(result['broken_chains'])} ruptures de chaîne:")
            for item in result['broken_chains'][:10]:
                print(f"  • {item['commit'][:8]} → {item['parent'][:8]} : {item['reason']}")

        return 1


def cmd_monitor(args):
    """Monitoring continu"""
    import time

    print("👀 MONITORING CONTINU")
    print("=" * 70)
    print(f"Intervalle: {args.interval}s")
    print("(Ctrl+C pour arrêter)")
    print()

    try:
        while True:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Vérification...")

            result = FullChainVerifier.verify_full_chain(
                level=VerificationLevel.FULL
            )

            if result.success:
                print(f"[{timestamp}] ✅ OK")
            else:
                print(f"[{timestamp}] ❌ PROBLÈME DÉTECTÉ")
                for issue in result.issues:
                    print(f"           • {issue}")

                # Alerte
                alert = Alert(
                    timestamp=utcnow_iso(),
                    severity=AlertSeverity.CRITICAL,
                    type='monitor_alert',
                    message='Integrity issue detected during monitoring',
                    details=result.to_dict()
                )
                AlertingSystem.send_alert(alert)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring arrêté")
        return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Integrity System - Advanced Verification"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # verify-full-chain
    p_verify = subparsers.add_parser('verify-full-chain',
                                     help='Verify full integrity chain')
    p_verify.add_argument('--commit', help='Commit SHA (default: HEAD)')
    p_verify.add_argument('--level', default='full',
                         choices=['basic', 'standard', 'full', 'paranoid'],
                         help='Verification level')
    p_verify.set_defaults(func=cmd_verify_full_chain)

    # audit-all
    p_audit = subparsers.add_parser('audit-all', help='Run full system audit')
    p_audit.set_defaults(func=cmd_audit_all)

    # verify-ots-integrity
    p_ots = subparsers.add_parser('verify-ots-integrity',
                                  help='Verify OTS proofs integrity')
    p_ots.set_defaults(func=cmd_verify_ots_integrity)

    # verify-git-topology
    p_topo = subparsers.add_parser('verify-git-topology',
                                   help='Verify Git commit chain')
    p_topo.add_argument('--from-commit', help='Start commit')
    p_topo.add_argument('--to-commit', help='End commit (default: HEAD)')
    p_topo.set_defaults(func=cmd_verify_git_topology)

    # monitor
    p_monitor = subparsers.add_parser('monitor',
                                      help='Continuous monitoring')
    p_monitor.add_argument('--interval', type=int, default=60,
                          help='Check interval in seconds')
    p_monitor.set_defaults(func=cmd_monitor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
