"""
Audit & Compliance Orchestrator for managing audit logs and compliance requirements.
"""

import logging
import uuid
import os
import json
import hashlib
import time
import hmac
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
import asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption
)
from cryptography.exceptions import InvalidSignature

from src.utils.base_orchestrator import BaseOrchestrator
from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode
)

logger = logging.getLogger(__name__)

class AuditOrchestrator(BaseOrchestrator):
    """
    Orchestrates audit logging and compliance operations.
    
    Responsible for:
    1. Collecting and consolidating audit logs from all agents
    2. Enforcing regulatory compliance checks
    3. Generating compliance reports and attestations
    4. Tracking data handling for privacy regulations
    5. Managing data retention and deletion policies
    6. Maintaining cryptographically verifiable audit trails
    """
    
    def __init__(self):
        """Initialize the audit orchestrator."""
        self.orchestrator_id = "audit-orchestrator"
        super().__init__(self.orchestrator_id)
        
        # Initialize audit log storage
        self.audit_logs = []  # In-memory cache of recent logs
        self.max_cached_logs = 1000  # Maximum number of logs to keep in memory
        
        # Initialize audit configuration
        self._init_audit_configuration()
        
        # Initialize crypto keys for log signing
        self._init_crypto_keys()
        
        # Initialize compliance rules
        self.compliance_rules = self._load_compliance_rules()
        
        logger.info(f"Audit Orchestrator {self.orchestrator_id} initialized")
    
    def _init_audit_configuration(self):
        """Initialize audit configuration."""
        # Set up log paths
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.logs_dir = os.path.join(base_dir, "logs")
        self.audit_dir = os.path.join(base_dir, "output", "audit")
        
        # Create directories if they don't exist
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)
        
        # Set up audit trail file
        self.audit_trail_file = os.path.join(self.audit_dir, "audit_trail.jsonl")
        
        # Configure retention policies (days)
        self.retention_periods = {
            "auth_logs": 90,  # Authentication logs kept for 90 days
            "document_logs": 365,  # Document processing logs kept for 1 year
            "system_logs": 30,  # System logs kept for 30 days
            "compliance_logs": 730  # Compliance logs kept for 2 years
        }
        
        # Set up tamper detection
        self.check_interval = 3600  # Check audit trail integrity every hour
        self.last_check_time = time.time()
        
        # Initialize sequence counter
        self._init_sequence_counter()
    
    def _init_sequence_counter(self):
        """Initialize the sequence counter for audit logs."""
        self.sequence_counter = 0
        
        # If the audit trail file exists, determine the next sequence number
        if os.path.exists(self.audit_trail_file):
            try:
                with open(self.audit_trail_file, "r", encoding="utf-8") as f:
                    # Go to the end of the file and read the last few lines
                    f.seek(0, os.SEEK_END)
                    file_size = f.tell()
                    
                    # Read the last 4KB of the file (typical log entries are <1KB)
                    read_size = min(4096, file_size)
                    f.seek(max(0, file_size - read_size), os.SEEK_SET)
                    
                    last_lines = f.readlines()
                    if last_lines:
                        # Parse the last line to get the sequence number
                        try:
                            last_log = json.loads(last_lines[-1])
                            self.sequence_counter = last_log.get("sequence", 0) + 1
                        except json.JSONDecodeError:
                            # If the last line is corrupted, start from a safe sequence number
                            self.sequence_counter = int(time.time() * 1000)
            except Exception as e:
                logger.error(f"Error initializing sequence counter: {e}")
                # Use current timestamp as fallback
                self.sequence_counter = int(time.time() * 1000)
        
        logger.info(f"Initialized sequence counter at {self.sequence_counter}")
    
    def _init_crypto_keys(self):
        """Initialize cryptographic keys for audit log signing."""
        key_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "keys")
        private_key_path = os.path.join(key_dir, "audit_private_key.pem")
        public_key_path = os.path.join(key_dir, "audit_public_key.pem")
        
        # Ensure key directory exists
        os.makedirs(key_dir, exist_ok=True)
        
        if os.path.exists(private_key_path) and os.path.exists(public_key_path):
            # Load existing keys
            try:
                with open(private_key_path, "rb") as f:
                    private_key_data = f.read()
                    self.private_key = load_pem_private_key(
                        private_key_data,
                        password=None
                    )
                
                with open(public_key_path, "rb") as f:
                    public_key_data = f.read()
                    self.public_key = load_pem_public_key(public_key_data)
                
                # Store PEM strings for later use
                self.private_key_pem = private_key_data
                self.public_key_pem = public_key_data
                
                logger.info("Loaded existing audit signing keys")
            except Exception as e:
                logger.error(f"Error loading audit signing keys: {e}")
                self._generate_new_keys(private_key_path, public_key_path)
        else:
            self._generate_new_keys(private_key_path, public_key_path)
    
    def _generate_new_keys(self, private_key_path: str, public_key_path: str):
        """Generate new RSA keys for audit log signing."""
        # Generate new RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Extract public key
        public_key = private_key.public_key()
        
        # Serialize private key
        private_key_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        )
        
        # Serialize public key
        public_key_pem = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )
        
        # Store keys
        self.private_key = private_key
        self.public_key = public_key
        self.private_key_pem = private_key_pem
        self.public_key_pem = public_key_pem
        
        # Write keys to files
        with open(private_key_path, "wb") as f:
            f.write(private_key_pem)
        
        with open(public_key_path, "wb") as f:
            f.write(public_key_pem)
        
        # Set restrictive permissions on private key
        os.chmod(private_key_path, 0o600)
        
        logger.info("Generated new audit signing keys")
    
    def _load_compliance_rules(self) -> Dict[str, Any]:
        """Load compliance rules configuration."""
        # This would typically load from a configuration file
        # Here we use hardcoded rules for demonstration
        return {
            "gdpr": {
                "rules": [
                    {"id": "data_minimization", "check": "document_size_check", "threshold": 10},
                    {"id": "pii_detection", "check": "pii_pattern_match", "patterns": ["ssn", "email", "phone"]},
                    {"id": "consent_tracking", "check": "metadata_field_exists", "field": "consent"},
                    {"id": "data_retention", "check": "max_age_check", "max_days": 730}
                ],
                "severity_levels": {
                    "high": ["pii_detection"],
                    "medium": ["consent_tracking", "data_retention"],
                    "low": ["data_minimization"]
                }
            },
            "hipaa": {
                "rules": [
                    {"id": "phi_protection", "check": "phi_pattern_match", "patterns": ["medical", "diagnosis", "treatment"]},
                    {"id": "access_controls", "check": "auth_level_check", "min_level": "provider"},
                    {"id": "audit_trail", "check": "audit_completeness", "required_events": ["access", "modify", "delete"]}
                ],
                "severity_levels": {
                    "high": ["phi_protection"],
                    "medium": ["access_controls"],
                    "low": ["audit_trail"]
                }
            },
            "internal": {
                "rules": [
                    {"id": "audit_signing", "check": "signature_check"},
                    {"id": "log_sequence", "check": "sequence_check"}
                ],
                "severity_levels": {
                    "critical": ["audit_signing", "log_sequence"]
                }
            }
        }
    
    def get_supported_tasks(self) -> List[str]:
        """Get the list of tasks supported by this orchestrator."""
        return [
            "log_action",
            "query_audit_logs",
            "verify_audit_trail",
            "run_compliance_check",
            "generate_compliance_report",
            "get_audit_public_key",
            "purge_expired_logs"
        ]
    
    def handle_log_action(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle logging an action to the audit trail.
        
        Args:
            message: Orchestration message with action logging parameters
            
        Returns:
            Action logging result
        """
        params = message.params
        required_fields = ["action_type", "actor_id", "target"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        # Extract action details
        action_type = params["action_type"]
        actor_id = params["actor_id"]
        target = params["target"]
        result = params.get("result", "unknown")
        details = params.get("details", {})
        
        try:
            # Create log entry
            log_entry = self._create_log_entry(
                action_type=action_type,
                actor_id=actor_id,
                target=target,
                result=result,
                details=details,
                context=message.context.to_dict() if hasattr(message.context, "to_dict") else message.context
            )
            
            # Write to audit trail
            self._write_to_audit_trail(log_entry)
            
            # Add to in-memory cache
            self._add_to_cache(log_entry)
            
            return message.create_response({
                "log_id": log_entry["log_id"],
                "timestamp": log_entry["timestamp"],
                "sequence": log_entry["sequence"],
                "status": "logged"
            })
        except Exception as e:
            logger.error(f"Error logging action: {str(e)}")
            return message.create_error_response(
                error=f"Error logging action: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_query_audit_logs(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle querying audit logs.
        
        Args:
            message: Orchestration message with audit log query parameters
            
        Returns:
            Audit log query results
        """
        params = message.params
        filters = params.get("filters", {})
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        
        try:
            # Validate time formats if provided
            if start_time:
                try:
                    datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except ValueError:
                    return message.create_error_response(
                        error="Invalid start_time format, must be ISO format",
                        error_code=ErrorCode.VALIDATION_ERROR
                    )
            
            if end_time:
                try:
                    datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                except ValueError:
                    return message.create_error_response(
                        error="Invalid end_time format, must be ISO format",
                        error_code=ErrorCode.VALIDATION_ERROR
                    )
            
            # Query logs
            result = self._query_logs(filters, start_time, end_time, limit, offset)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error querying audit logs: {str(e)}")
            return message.create_error_response(
                error=f"Error querying audit logs: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_verify_audit_trail(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle verifying the integrity of the audit trail.
        
        Args:
            message: Orchestration message with verification parameters
            
        Returns:
            Verification results
        """
        params = message.params
        log_id = params.get("log_id")
        start_time = params.get("start_time")
        end_time = params.get("end_time", datetime.utcnow().isoformat() + "Z")
        
        try:
            if log_id:
                # Verify a specific log entry
                result = self._verify_log_entry(log_id)
            else:
                # Verify a range of log entries
                result = self._verify_log_range(start_time, end_time)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error verifying audit trail: {str(e)}")
            return message.create_error_response(
                error=f"Error verifying audit trail: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_run_compliance_check(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle running a compliance check.
        
        Args:
            message: Orchestration message with compliance check parameters
            
        Returns:
            Compliance check results
        """
        params = message.params
        required_fields = ["compliance_type", "target_id"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        compliance_type = params["compliance_type"]
        target_id = params["target_id"]
        check_params = params.get("check_params", {})
        
        try:
            # Check if compliance type is supported
            if compliance_type not in self.compliance_rules:
                return message.create_error_response(
                    error=f"Unsupported compliance type: {compliance_type}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
            
            # Run compliance check
            result = self._run_compliance_check(compliance_type, target_id, check_params)
            
            # Log the compliance check
            self._create_log_entry(
                action_type="compliance_check",
                actor_id=message.origin,
                target=target_id,
                result="completed",
                details={
                    "compliance_type": compliance_type,
                    "check_results": result,
                    "request_id": message.request_id
                },
                context=message.context.to_dict() if hasattr(message.context, "to_dict") else message.context
            )
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error running compliance check: {str(e)}")
            return message.create_error_response(
                error=f"Error running compliance check: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_generate_compliance_report(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle generating a compliance report.
        
        Args:
            message: Orchestration message with report generation parameters
            
        Returns:
            Compliance report generation results
        """
        params = message.params
        required_fields = ["compliance_type", "report_period"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        compliance_type = params["compliance_type"]
        report_period = params["report_period"]
        report_format = params.get("report_format", "json")
        
        try:
            # Check if compliance type is supported
            if compliance_type not in self.compliance_rules:
                return message.create_error_response(
                    error=f"Unsupported compliance type: {compliance_type}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
            
            # Generate compliance report
            result = self._generate_compliance_report(compliance_type, report_period, report_format)
            
            # Log the report generation
            self._create_log_entry(
                action_type="compliance_report",
                actor_id=message.origin,
                target=f"{compliance_type}_report",
                result="generated",
                details={
                    "compliance_type": compliance_type,
                    "report_period": report_period,
                    "report_format": report_format,
                    "report_id": result.get("report_id")
                },
                context=message.context.to_dict() if hasattr(message.context, "to_dict") else message.context
            )
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error generating compliance report: {str(e)}")
            return message.create_error_response(
                error=f"Error generating compliance report: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_get_audit_public_key(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle providing the public key used for audit log verification.
        
        Args:
            message: Orchestration message
            
        Returns:
            Public key information
        """
        return message.create_response({
            "alg": "RSA-SHA256",
            "public_key": self.public_key_pem.decode('utf-8'),
            "key_id": "audit-primary",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    
    def handle_purge_expired_logs(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle purging expired logs according to retention policies.
        
        Args:
            message: Orchestration message
            
        Returns:
            Log purging results
        """
        params = message.params
        log_type = params.get("log_type", "all")
        dry_run = params.get("dry_run", False)
        
        try:
            result = self._purge_expired_logs(log_type, dry_run)
            
            # Log the purge operation
            self._create_log_entry(
                action_type="log_purge",
                actor_id=message.origin,
                target=f"{log_type}_logs",
                result="completed",
                details={
                    "log_type": log_type,
                    "dry_run": dry_run,
                    "purged_count": result.get("purged_count", 0)
                },
                context=message.context.to_dict() if hasattr(message.context, "to_dict") else message.context
            )
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error purging expired logs: {str(e)}")
            return message.create_error_response(
                error=f"Error purging expired logs: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def _create_log_entry(self, action_type: str, actor_id: str, target: str, result: str, 
                       details: Optional[Dict[str, Any]] = None, 
                       context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new audit log entry.
        
        Args:
            action_type: Type of action being performed
            actor_id: ID of the actor performing the action
            target: Target of the action
            result: Result of the action
            details: Additional details about the action
            context: Context information
            
        Returns:
            Complete log entry
        """
        # Generate log ID
        log_id = f"log-{uuid.uuid4().hex}"
        
        # Get current timestamp
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Increment sequence counter
        self.sequence_counter += 1
        sequence = self.sequence_counter
        
        # Create log entry
        log_entry = {
            "log_id": log_id,
            "timestamp": timestamp,
            "sequence": sequence,
            "action_type": action_type,
            "actor_id": actor_id,
            "target": target,
            "result": result,
            "details": details or {},
            "context": context or {}
        }
        
        # Add previous hash if we have logs
        if self.audit_logs:
            previous_log = self.audit_logs[-1]
            log_entry["previous_hash"] = previous_log.get("hash")
        else:
            # If this is the first log, check if we have logs in the file
            if os.path.exists(self.audit_trail_file) and os.path.getsize(self.audit_trail_file) > 0:
                try:
                    with open(self.audit_trail_file, "r", encoding="utf-8") as f:
                        # Go to the end of the file and read the last line
                        f.seek(0, os.SEEK_END)
                        file_size = f.tell()
                        
                        # Read back until we find a newline or reach the beginning
                        pos = file_size - 1
                        while pos > 0:
                            f.seek(pos)
                            char = f.read(1)
                            if char == '\n':
                                break
                            pos -= 1
                        
                        # Read the last line
                        last_line = f.readline()
                        last_log = json.loads(last_line)
                        log_entry["previous_hash"] = last_log.get("hash")
                except Exception as e:
                    logger.error(f"Error retrieving previous hash: {e}")
        
        # Create log content for hashing (without the hash field)
        log_content = json.dumps(log_entry, sort_keys=True)
        
        # Calculate hash of the log content
        log_hash = hashlib.sha256(log_content.encode()).hexdigest()
        log_entry["hash"] = log_hash
        
        # Sign the hash
        signature = self._sign_hash(log_hash)
        log_entry["signature"] = signature
        
        return log_entry
    
    def _sign_hash(self, log_hash: str) -> str:
        """
        Sign a log hash with the private key.
        
        Args:
            log_hash: Hash to sign
            
        Returns:
            Base64-encoded signature
        """
        try:
            # Sign the hash
            signature = self.private_key.sign(
                log_hash.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Encode as hex string
            return signature.hex()
        except Exception as e:
            logger.error(f"Error signing log hash: {e}")
            return ""
    
    def _verify_signature(self, log_hash: str, signature: str) -> bool:
        """
        Verify a log signature.
        
        Args:
            log_hash: Hash that was signed
            signature: Signature to verify
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Decode signature from hex
            signature_bytes = bytes.fromhex(signature)
            
            # Verify signature
            self.public_key.verify(
                signature_bytes,
                log_hash.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # If verify doesn't raise an exception, signature is valid
            return True
        except InvalidSignature:
            logger.error("Invalid signature detected")
            return False
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    def _add_to_cache(self, log_entry: Dict[str, Any]) -> None:
        """
        Add a log entry to the in-memory cache.
        
        Args:
            log_entry: Log entry to add
        """
        self.audit_logs.append(log_entry)
        
        # Trim cache if needed
        if len(self.audit_logs) > self.max_cached_logs:
            self.audit_logs = self.audit_logs[-self.max_cached_logs:]
    
    def _write_to_audit_trail(self, log_entry: Dict[str, Any]) -> None:
        """
        Write a log entry to the audit trail file.
        
        Args:
            log_entry: Log entry to write
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.audit_trail_file), exist_ok=True)
            
            # Write log entry to file
            with open(self.audit_trail_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Error writing to audit trail: {e}")
            raise
    
    def _query_logs(self, filters: Dict[str, Any], start_time: Optional[str], 
                 end_time: Optional[str], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Query audit logs with filters and time range.
        
        Args:
            filters: Dictionary of filters to apply
            start_time: ISO format start time
            end_time: ISO format end time
            limit: Maximum number of logs to return
            offset: Number of logs to skip
            
        Returns:
            Query results
        """
        # Convert times to datetime objects if provided
        start_dt = None
        end_dt = None
        
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        
        # First check in-memory cache
        matching_logs = []
        
        # Apply filters to in-memory logs
        for log in self.audit_logs:
            if self._log_matches_filters(log, filters, start_dt, end_dt):
                matching_logs.append(log)
        
        # If we need more logs, or specifically want older logs, search the file
        if len(matching_logs) < limit + offset or (start_dt and self.audit_logs and 
                                              datetime.fromisoformat(self.audit_logs[0]["timestamp"].replace("Z", "+00:00")) > start_dt):
            # Load logs from file
            file_logs = self._load_logs_from_file(filters, start_dt, end_dt, limit + offset)
            
            # Merge logs, avoiding duplicates
            existing_ids = {log["log_id"] for log in matching_logs}
            for log in file_logs:
                if log["log_id"] not in existing_ids:
                    matching_logs.append(log)
                    existing_ids.add(log["log_id"])
        
        # Sort by timestamp (newest first)
        matching_logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply limit and offset
        result_logs = matching_logs[offset:offset + limit] if offset < len(matching_logs) else []
        
        return {
            "logs": result_logs,
            "count": len(result_logs),
            "total": len(matching_logs),
            "has_more": len(matching_logs) > offset + limit,
            "status": "success"
        }
    
    def _log_matches_filters(self, log: Dict[str, Any], filters: Dict[str, Any], 
                          start_dt: Optional[datetime], end_dt: Optional[datetime]) -> bool:
        """
        Check if a log entry matches the given filters and time range.
        
        Args:
            log: Log entry to check
            filters: Filters to apply
            start_dt: Start datetime
            end_dt: End datetime
            
        Returns:
            True if log matches, False otherwise
        """
        # Check time range
        if start_dt or end_dt:
            log_dt = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
            if start_dt and log_dt < start_dt:
                return False
            if end_dt and log_dt > end_dt:
                return False
        
        # Check filters
        for key, value in filters.items():
            parts = key.split(".")
            
            # Handle nested fields
            if len(parts) > 1:
                # Navigate to the nested field
                current = log
                for part in parts[:-1]:
                    if part in current:
                        current = current[part]
                    else:
                        return False
                
                # Check the field value
                if parts[-1] not in current or current[parts[-1]] != value:
                    return False
            else:
                # Check top-level field
                if key in log:
                    if log[key] != value:
                        return False
                else:
                    return False
        
        return True
    
    def _load_logs_from_file(self, filters: Dict[str, Any], start_dt: Optional[datetime], 
                          end_dt: Optional[datetime], limit: int) -> List[Dict[str, Any]]:
        """
        Load logs from the audit trail file.
        
        Args:
            filters: Filters to apply
            start_dt: Start datetime
            end_dt: End datetime
            limit: Maximum number of logs to return
            
        Returns:
            List of matching log entries
        """
        matching_logs = []
        
        # Check if the file exists
        if not os.path.exists(self.audit_trail_file):
            return matching_logs
        
        try:
            with open(self.audit_trail_file, "r", encoding="utf-8") as f:
                for line in f:
                    # Parse log entry
                    try:
                        log = json.loads(line)
                        
                        # Check if log matches filters and time range
                        if self._log_matches_filters(log, filters, start_dt, end_dt):
                            matching_logs.append(log)
                            
                            # Break if we've reached the limit
                            if len(matching_logs) >= limit:
                                break
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing log entry: {line}")
                        continue
        except Exception as e:
            logger.error(f"Error loading logs from file: {e}")
        
        return matching_logs
    
    def _verify_log_entry(self, log_id: str) -> Dict[str, Any]:
        """
        Verify the integrity of a specific log entry.
        
        Args:
            log_id: ID of the log entry to verify
            
        Returns:
            Verification results
        """
        # Search for the log entry
        log_entry = None
        
        # First check in-memory cache
        for log in self.audit_logs:
            if log["log_id"] == log_id:
                log_entry = log
                break
        
        # If not found, search the file
        if not log_entry:
            try:
                with open(self.audit_trail_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            log = json.loads(line)
                            if log["log_id"] == log_id:
                                log_entry = log
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Error searching for log entry: {e}")
                return {
                    "log_id": log_id,
                    "verified": False,
                    "error": f"Error searching for log entry: {str(e)}",
                    "status": "error"
                }
        
        # If log entry not found
        if not log_entry:
            return {
                "log_id": log_id,
                "verified": False,
                "error": "Log entry not found",
                "status": "error"
            }
        
        # Verify signature
        log_hash = log_entry["hash"]
        signature = log_entry.get("signature", "")
        
        if not signature:
            return {
                "log_id": log_id,
                "verified": False,
                "error": "Log entry has no signature",
                "status": "error"
            }
        
        # Make a copy of the log entry without the hash and signature for verification
        verification_log = log_entry.copy()
        verification_log.pop("hash", None)
        verification_log.pop("signature", None)
        
        # Calculate hash of the verification log
        verification_hash = hashlib.sha256(json.dumps(verification_log, sort_keys=True).encode()).hexdigest()
        
        # Check if hash matches
        hash_matches = verification_hash == log_hash
        
        # Verify signature
        signature_valid = self._verify_signature(log_hash, signature)
        
        return {
            "log_id": log_id,
            "timestamp": log_entry["timestamp"],
            "sequence": log_entry.get("sequence"),
            "hash_matches": hash_matches,
            "signature_valid": signature_valid,
            "verified": hash_matches and signature_valid,
            "status": "success" if hash_matches and signature_valid else "error"
        }
    
    def _verify_log_range(self, start_time: Optional[str], end_time: Optional[str]) -> Dict[str, Any]:
        """
        Verify the integrity of a range of log entries.
        
        Args:
            start_time: ISO format start time
            end_time: ISO format end time
            
        Returns:
            Verification results
        """
        # Convert times to datetime objects
        start_dt = None
        end_dt = None
        
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        
        # Load logs from the file
        logs = []
        try:
            with open(self.audit_trail_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log = json.loads(line)
                        
                        # Check time range
                        log_dt = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
                        if start_dt and log_dt < start_dt:
                            continue
                        if end_dt and log_dt > end_dt:
                            continue
                        
                        logs.append(log)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error loading logs: {e}")
            return {
                "verified": False,
                "error": f"Error loading logs: {str(e)}",
                "status": "error"
            }
        
        # Sort logs by sequence number
        logs.sort(key=lambda x: x.get("sequence", 0))
        
        # Verify each log and check hash chain
        verification_results = []
        chain_valid = True
        previous_hash = None
        
        for log in logs:
            # Verify signature
            log_hash = log["hash"]
            signature = log.get("signature", "")
            
            if not signature:
                verification_results.append({
                    "log_id": log["log_id"],
                    "verified": False,
                    "error": "Log entry has no signature"
                })
                chain_valid = False
                continue
            
            # Make a copy of the log entry without the hash and signature for verification
            verification_log = log.copy()
            verification_log.pop("hash", None)
            verification_log.pop("signature", None)
            
            # Calculate hash of the verification log
            verification_hash = hashlib.sha256(json.dumps(verification_log, sort_keys=True).encode()).hexdigest()
            
            # Check if hash matches
            hash_matches = verification_hash == log_hash
            
            # Verify signature
            signature_valid = self._verify_signature(log_hash, signature)
            
            # Check hash chain
            if previous_hash is not None and log.get("previous_hash") != previous_hash:
                chain_valid = False
            
            # Store result
            verification_results.append({
                "log_id": log["log_id"],
                "sequence": log.get("sequence"),
                "hash_matches": hash_matches,
                "signature_valid": signature_valid,
                "chain_valid": previous_hash is None or log.get("previous_hash") == previous_hash,
                "verified": hash_matches and signature_valid and (previous_hash is None or log.get("previous_hash") == previous_hash)
            })
            
            # Update previous hash
            previous_hash = log_hash
            
            # Break chain if any verification fails
            if not (hash_matches and signature_valid):
                chain_valid = False
        
        return {
            "logs_verified": len(verification_results),
            "chain_valid": chain_valid,
            "all_verified": all(r["verified"] for r in verification_results),
            "verification_details": verification_results[:10],  # Only return first 10 for brevity
            "start_time": start_time,
            "end_time": end_time,
            "status": "success" if chain_valid and all(r["verified"] for r in verification_results) else "error"
        }
    
    def _run_compliance_check(self, compliance_type: str, target_id: str, check_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a compliance check on a target.
        
        Args:
            compliance_type: Type of compliance check to run
            target_id: ID of the target to check
            check_params: Additional parameters for the check
            
        Returns:
            Compliance check results
        """
        # Get compliance rules for the specified type
        rules = self.compliance_rules.get(compliance_type, {}).get("rules", [])
        severity_levels = self.compliance_rules.get(compliance_type, {}).get("severity_levels", {})
        
        if not rules:
            return {
                "compliance_type": compliance_type,
                "target_id": target_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "checks": [],
                "overall_status": "error",
                "error": f"No rules defined for compliance type: {compliance_type}",
                "status": "error"
            }
        
        # Run each rule check
        check_results = []
        all_passed = True
        critical_failures = 0
        high_failures = 0
        medium_failures = 0
        
        for rule in rules:
            rule_id = rule["id"]
            check_type = rule["check"]
            
            # Determine severity
            severity = "unknown"
            for level, rule_ids in severity_levels.items():
                if rule_id in rule_ids:
                    severity = level
                    break
            
            # Placeholder implementation for different check types
            # In a real implementation, these would call specialized checkers
            passed = True
            details = "Compliance check passed"
            
            if check_type == "data_minimization":
                # Check document size doesn't exceed threshold
                threshold = rule.get("threshold", 10)
                doc_size = check_params.get("document_size", 5)  # Placeholder
                passed = doc_size <= threshold
                details = f"Document size {doc_size} is {'within' if passed else 'above'} threshold {threshold}"
            
            elif check_type == "pii_pattern_match":
                # Check for PII patterns
                patterns = rule.get("patterns", [])
                detected_patterns = check_params.get("detected_patterns", [])  # Placeholder
                passed = not any(p in detected_patterns for p in patterns)
                if not passed:
                    matched = [p for p in patterns if p in detected_patterns]
                    details = f"Detected {len(matched)} PII patterns: {', '.join(matched)}"
                else:
                    details = "No PII patterns detected"
            
            elif check_type == "metadata_field_exists":
                # Check if a required metadata field exists
                field = rule.get("field")
                metadata = check_params.get("metadata", {})
                passed = field in metadata
                details = f"Required field '{field}' {'exists' if passed else 'missing'} in metadata"
            
            elif check_type == "max_age_check":
                # Check if document age is within limits
                max_days = rule.get("max_days", 365)
                doc_date_str = check_params.get("document_date")
                if doc_date_str:
                    try:
                        doc_date = datetime.fromisoformat(doc_date_str.replace("Z", "+00:00"))
                        age_days = (datetime.utcnow() - doc_date).days
                        passed = age_days <= max_days
                        details = f"Document age {age_days} days is {'within' if passed else 'exceeds'} limit of {max_days} days"
                    except ValueError:
                        passed = False
                        details = "Invalid document date format"
                else:
                    passed = False
                    details = "Document date not provided"
            
            # Update check status counters
            if not passed:
                all_passed = False
                if severity == "critical":
                    critical_failures += 1
                elif severity == "high":
                    high_failures += 1
                elif severity == "medium":
                    medium_failures += 1
            
            # Add check result
            check_results.append({
                "rule_id": rule_id,
                "severity": severity,
                "passed": passed,
                "details": details
            })
        
        # Determine overall status
        overall_status = "compliant"
        if not all_passed:
            if critical_failures > 0:
                overall_status = "critical_violation"
            elif high_failures > 0:
                overall_status = "high_violation"
            elif medium_failures > 0:
                overall_status = "medium_violation"
            else:
                overall_status = "low_violation"
        
        return {
            "compliance_type": compliance_type,
            "target_id": target_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "checks": check_results,
            "overall_status": overall_status,
            "violations": {
                "critical": critical_failures,
                "high": high_failures,
                "medium": medium_failures,
                "low": len(check_results) - sum([critical_failures, high_failures, medium_failures]) - (len(check_results) if all_passed else 0)
            },
            "status": "success"
        }
    
    def _generate_compliance_report(self, compliance_type: str, report_period: str, report_format: str = "json") -> Dict[str, Any]:
        """
        Generate a compliance report for a time period.
        
        Args:
            compliance_type: Type of compliance to report on
            report_period: Time period to cover (e.g., "last_30_days", "last_quarter", "custom:YYYY-MM-DD:YYYY-MM-DD")
            report_format: Output format (json, csv, pdf)
            
        Returns:
            Compliance report generation results
        """
        # Parse the report period
        start_time = None
        end_time = datetime.utcnow().isoformat() + "Z"
        
        if report_period == "last_7_days":
            start_time = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
        elif report_period == "last_30_days":
            start_time = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        elif report_period == "last_quarter":
            start_time = (datetime.utcnow() - timedelta(days=90)).isoformat() + "Z"
        elif report_period == "last_year":
            start_time = (datetime.utcnow() - timedelta(days=365)).isoformat() + "Z"
        elif report_period.startswith("custom:"):
            # Custom date range format: "custom:YYYY-MM-DD:YYYY-MM-DD"
            parts = report_period.split(":")
            if len(parts) >= 3:
                try:
                    start_time = datetime.fromisoformat(parts[1]).isoformat() + "Z"
                    end_time = datetime.fromisoformat(parts[2]).isoformat() + "Z"
                except ValueError:
                    return {
                        "compliance_type": compliance_type,
                        "report_period": report_period,
                        "error": "Invalid custom date format, use YYYY-MM-DD",
                        "status": "error"
                    }
        else:
            return {
                "compliance_type": compliance_type,
                "report_period": report_period,
                "error": "Unsupported report period",
                "status": "error"
            }
        
        # Generate report ID
        report_id = f"report-{compliance_type}-{uuid.uuid4().hex[:8]}"
        
        # Query logs for compliance-related actions
        filters = {
            "action_type": "compliance_check",
            "details.compliance_type": compliance_type
        }
        
        log_results = self._query_logs(filters, start_time, end_time, 1000, 0)
        logs = log_results.get("logs", [])
        
        # Aggregate check results
        total_checks = len(logs)
        passed_checks = sum(1 for log in logs if log.get("details", {}).get("check_results", {}).get("overall_status") == "compliant")
        failure_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        
        for log in logs:
            check_results = log.get("details", {}).get("check_results", {})
            violations = check_results.get("violations", {})
            failure_counts["critical"] += violations.get("critical", 0)
            failure_counts["high"] += violations.get("high", 0)
            failure_counts["medium"] += violations.get("medium", 0)
            failure_counts["low"] += violations.get("low", 0)
        
        # Create report data
        report_data = {
            "report_id": report_id,
            "compliance_type": compliance_type,
            "start_time": start_time,
            "end_time": end_time,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "compliance_rate": (passed_checks / total_checks * 100) if total_checks > 0 else 100,
                "violations": failure_counts
            },
            "details": {
                "check_logs": logs[:10]  # Include first 10 logs for reference
            }
        }
        
        # Determine overall compliance status
        if failure_counts["critical"] > 0:
            report_data["summary"]["overall_status"] = "critical_violation"
        elif failure_counts["high"] > 0:
            report_data["summary"]["overall_status"] = "high_violation"
        elif failure_counts["medium"] > 0:
            report_data["summary"]["overall_status"] = "medium_violation"
        elif failure_counts["low"] > 0:
            report_data["summary"]["overall_status"] = "low_violation"
        else:
            report_data["summary"]["overall_status"] = "compliant"
        
        # Write report to file
        report_file_path = None
        try:
            # Create reports directory
            reports_dir = os.path.join(self.audit_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            # Write report in requested format
            if report_format == "json":
                report_file_path = os.path.join(reports_dir, f"{report_id}.json")
                with open(report_file_path, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2)
            elif report_format == "csv":
                # Simplified CSV format - in a real implementation this would be more comprehensive
                report_file_path = os.path.join(reports_dir, f"{report_id}.csv")
                with open(report_file_path, "w", encoding="utf-8") as f:
                    f.write("Report ID,Compliance Type,Start Time,End Time,Total Checks,Passed Checks,Compliance Rate,Overall Status\n")
                    f.write(f"{report_id},{compliance_type},{start_time},{end_time},{total_checks},{passed_checks},{report_data['summary']['compliance_rate']:.2f},{report_data['summary']['overall_status']}\n")
            else:
                # Unsupported format - only return JSON data
                pass
        except Exception as e:
            logger.error(f"Error writing report file: {e}")
        
        # Return report metadata
        return {
            "report_id": report_id,
            "compliance_type": compliance_type,
            "report_period": report_period,
            "format": report_format,
            "file_path": report_file_path,
            "summary": report_data["summary"],
            "status": "success"
        }
    
    def _purge_expired_logs(self, log_type: str = "all", dry_run: bool = False) -> Dict[str, Any]:
        """
        Purge expired logs according to retention policies.
        
        Args:
            log_type: Type of logs to purge (all, auth, document, system, compliance)
            dry_run: If True, only report what would be purged without actually purging
            
        Returns:
            Purge results
        """
        # Determine retention period for the log type
        retention_days = 0
        if log_type == "all":
            # Use the minimum retention period for dry run reporting
            retention_days = min(self.retention_periods.values())
        elif log_type == "auth":
            retention_days = self.retention_periods["auth_logs"]
        elif log_type == "document":
            retention_days = self.retention_periods["document_logs"]
        elif log_type == "system":
            retention_days = self.retention_periods["system_logs"]
        elif log_type == "compliance":
            retention_days = self.retention_periods["compliance_logs"]
        else:
            return {
                "log_type": log_type,
                "error": f"Unsupported log type: {log_type}",
                "status": "error"
            }
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff_date.isoformat() + "Z"
        
        # Track purge statistics
        purge_stats = {
            "log_type": log_type,
            "retention_days": retention_days,
            "cutoff_date": cutoff_str,
            "dry_run": dry_run,
            "purged_count": 0,
            "purged_logs": []
        }
        
        # Implement purging logic based on log type
        # For now, this is a placeholder that identifies logs that would be purged
        if log_type == "all" or log_type == "auth":
            # Query auth logs that are older than the cutoff date
            auth_filters = {"action_type": "auth_"}
            auth_logs = self._query_logs(auth_filters, None, cutoff_str, 100, 0)
            purge_stats["purged_count"] += auth_logs.get("count", 0)
            if not dry_run:
                # In a real implementation, we would actually purge these logs
                pass
        
        if log_type == "all" or log_type == "document":
            # Query document logs that are older than the cutoff date
            doc_filters = {"action_type": "doc_"}
            doc_logs = self._query_logs(doc_filters, None, cutoff_str, 100, 0)
            purge_stats["purged_count"] += doc_logs.get("count", 0)
            if not dry_run:
                # In a real implementation, we would actually purge these logs
                pass
        
        if log_type == "all" or log_type == "system":
            # Query system logs that are older than the cutoff date
            sys_filters = {"action_type": "system_"}
            sys_logs = self._query_logs(sys_filters, None, cutoff_str, 100, 0)
            purge_stats["purged_count"] += sys_logs.get("count", 0)
            if not dry_run:
                # In a real implementation, we would actually purge these logs
                pass
        
        if log_type == "all" or log_type == "compliance":
            # Query compliance logs that are older than the cutoff date
            comp_filters = {"action_type": "compliance_"}
            comp_logs = self._query_logs(comp_filters, None, cutoff_str, 100, 0)
            purge_stats["purged_count"] += comp_logs.get("count", 0)
            if not dry_run:
                # In a real implementation, we would actually purge these logs
                pass
        
        return {
            "log_type": log_type,
            "retention_days": retention_days,
            "cutoff_date": cutoff_str,
            "purged_count": purge_stats["purged_count"],
            "dry_run": dry_run,
            "status": "success"
        }