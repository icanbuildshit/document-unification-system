"""
Authentication Agent for JWT-based authentication, following auth_master.md specifications.

Implements a complete authentication system with:
- JWT token generation and validation (RS256)
- Risk-based analysis for MFA decisions
- Session management
- Audit logging
"""

import os
import time
import json
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union

import jwt
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, Field

from src.utils.orchestrator_logging import setup_logger

# Initialize logger
logger = setup_logger("auth_agent")

# Error codes as defined in auth_master.md
ERROR_CODES = {
    "AUTH-001": "Bad credentials",
    "AUTH-002": "MFA required",
    "AUTH-003": "Token expired",
    "AUTH-004": "Token revoked",
    "AUTH-005": "Scope violation",
}


class TokenPayload(BaseModel):
    """JWT token payload schema"""
    sub: str
    aud: str = "lendr.dashboard"
    iss: str = "auth.lendr.local"
    iat: int = Field(default_factory=lambda: int(time.time()))
    exp: int
    scope: List[str]
    ctx: Dict[str, Any]


class SessionData(BaseModel):
    """Session data stored in Redis"""
    user_id: str
    refresh_token_id: str
    refresh_token_exp: int
    device_fingerprint: str
    active: bool = True
    risk_score: int
    last_accessed: int = Field(default_factory=lambda: int(time.time()))
    scope: List[str]
    metadata: Dict[str, Any] = {}


class AuthResult(BaseModel):
    """Result of authentication operations"""
    success: bool
    message: str
    error_code: Optional[str] = None
    tokens: Optional[Dict[str, str]] = None
    requires_mfa: bool = False


class CredentialGuard:
    """Validates credentials (passwords, API keys, etc.)"""
    
    def validate_credentials(self, username: str, password: str) -> bool:
        """
        Validate user credentials.
        
        In a production environment, this should validate against a secure
        user store (e.g., a database with properly hashed passwords).
        
        For this implementation, we're using a simple mock approach.
        """
        # TODO: Replace with actual credential validation logic
        # This is just a mock implementation for demonstration
        mock_users = {
            "test@example.com": "password123",
            "admin@example.com": "admin123"
        }
        
        return username in mock_users and mock_users[username] == password


class RiskAnalyzer:
    """Analyzes session risk factors to determine if MFA is required"""
    
    def calculate_risk_score(self, 
                             username: str, 
                             ip_address: str, 
                             user_agent: str, 
                             device_fingerprint: str, 
                             geolocation: Optional[Dict[str, float]] = None,
                             behavioral_data: Optional[Dict[str, Any]] = None) -> int:
        """
        Calculate a risk score from 0-100 based on various factors.
        Higher scores indicate higher risk.
        
        Args:
            username: User's email or identifier
            ip_address: Client IP address
            user_agent: Browser/client user agent string
            device_fingerprint: Device identifier
            geolocation: Dict with lat/long coordinates (optional)
            behavioral_data: Typing patterns, mouse movements, etc. (optional)
            
        Returns:
            Integer risk score from 0-100
        """
        # Start with a baseline risk
        score = 30
        
        # TODO: Implement actual risk scoring based on:
        # - Geo-velocity (rapid location changes)
        # - Time-of-day abnormality
        # - Device fingerprint familiarity
        # - Behavioral biometrics
        # - Known fraud signals
        
        # For now, using a simple random factor for demonstration
        import random
        # Add some randomness to simulate different risk levels
        score += random.randint(-20, 40)
        
        # Ensure score stays in valid range
        return max(0, min(score, 100))
    
    def requires_mfa(self, risk_score: int, device_recognized: bool) -> bool:
        """
        Determine if MFA is required based on risk score and device recognition.
        
        Args:
            risk_score: Calculated risk score (0-100)
            device_recognized: Whether device has been seen before
            
        Returns:
            Boolean indicating if MFA should be required
        """
        # Step-up MFA when risk_score ≥ 60 or unfamiliar device fingerprint
        return risk_score >= 60 or not device_recognized


class SessionBroker:
    """Manages JWT token generation, validation, and session state"""
    
    def __init__(self, redis_url=None):
        """
        Initialize session broker with a connection to Redis.
        
        Args:
            redis_url: Redis connection string, defaults to localhost
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url)
        self.access_token_ttl = 15 * 60  # 15 minutes in seconds
        self.refresh_token_ttl = 24 * 60 * 60  # 24 hours in seconds
        
        # In production, load keys from secure storage
        # For demo purposes, generate new keys if needed
        self._load_or_generate_keys()
    
    def _load_or_generate_keys(self):
        """Load RSA keys from environment or generate new ones"""
        # In production, keys should be loaded from secure storage
        # For now, generate new keys for demonstration
        if not hasattr(self, "private_key"):
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            self.public_key = self.private_key.public_key()
            
            # Export keys to PEM format
            self.private_key_pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            self.public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
    
    def generate_tokens(self, user_id: str, scope: List[str], context: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate a new JWT access token and refresh token pair.
        
        Args:
            user_id: Unique user identifier
            scope: List of permission scopes
            context: Additional context information
            
        Returns:
            Dict containing access_token and refresh_token
        """
        # Generate a unique ID for the refresh token
        refresh_token_id = str(uuid.uuid4())
        
        # Current timestamp
        now = int(time.time())
        
        # Create access token payload
        access_payload = TokenPayload(
            sub=user_id,
            iat=now,
            exp=now + self.access_token_ttl,
            scope=scope,
            ctx=context
        )
        
        # Create refresh token payload (simpler, but with longer expiry)
        refresh_payload = {
            "sub": user_id,
            "jti": refresh_token_id,  # Unique token ID
            "iat": now,
            "exp": now + self.refresh_token_ttl,
            "type": "refresh"
        }
        
        # Sign tokens with RS256
        access_token = jwt.encode(
            access_payload.dict(),
            self.private_key_pem,
            algorithm="RS256"
        )
        
        refresh_token = jwt.encode(
            refresh_payload,
            self.private_key_pem,
            algorithm="RS256"
        )
        
        # Store refresh token metadata in Redis
        session_data = SessionData(
            user_id=user_id,
            refresh_token_id=refresh_token_id,
            refresh_token_exp=now + self.refresh_token_ttl,
            device_fingerprint=context.get("device_fingerprint", "unknown"),
            risk_score=context.get("risk", 0),
            scope=scope
        )
        
        # Store in Redis, with TTL matching refresh token expiry
        self.redis_client.setex(
            f"refresh_token:{refresh_token_id}",
            self.refresh_token_ttl,
            session_data.json()
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self.access_token_ttl,
            "token_type": "Bearer"
        }
    
    def validate_access_token(self, token: str) -> Tuple[bool, Dict, Optional[str]]:
        """
        Validate an access token and return its decoded payload if valid.
        
        Args:
            token: JWT access token
            
        Returns:
            Tuple of (is_valid, payload, error_code)
        """
        try:
            # Decode and verify the token
            payload = jwt.decode(
                token,
                self.public_key_pem,
                algorithms=["RS256"],
                options={"verify_signature": True}
            )
            
            # Check if token has expired
            if payload.get("exp", 0) < time.time():
                return False, {}, "AUTH-003"
            
            # Additional checks could be implemented here (revocation, etc.)
            
            return True, payload, None
            
        except jwt.ExpiredSignatureError:
            return False, {}, "AUTH-003"
        except jwt.InvalidTokenError:
            return False, {}, "AUTH-004"
    
    def refresh_tokens(self, refresh_token: str) -> Union[Dict[str, str], None]:
        """
        Validate a refresh token and issue a new token pair if valid.
        Old refresh token is revoked.
        
        Args:
            refresh_token: JWT refresh token
            
        Returns:
            Dict with new token pair or None if invalid
        """
        try:
            # Decode token without verifying expiration (we'll check manually)
            payload = jwt.decode(
                refresh_token,
                self.public_key_pem,
                algorithms=["RS256"],
                options={"verify_signature": True}
            )
            
            # Check token type
            if payload.get("type") != "refresh":
                return None
            
            # Get token identifier
            token_id = payload.get("jti")
            user_id = payload.get("sub")
            
            if not token_id or not user_id:
                return None
            
            # Check if token exists in Redis
            token_key = f"refresh_token:{token_id}"
            session_data_json = self.redis_client.get(token_key)
            
            if not session_data_json:
                # Token not found or expired
                return None
            
            # Parse session data
            session_data = SessionData.parse_raw(session_data_json)
            
            # Check if token has been revoked
            if not session_data.active:
                return None
            
            # Revoke the old token
            self.redis_client.delete(token_key)
            
            # Create a context from the session data
            context = {
                "device_fingerprint": session_data.device_fingerprint,
                "risk": session_data.risk_score,
                "ua": session_data.metadata.get("user_agent", "unknown"),
                "ip": session_data.metadata.get("ip_address", "unknown")
            }
            
            # Generate new token pair
            return self.generate_tokens(user_id, session_data.scope, context)
            
        except (jwt.InvalidTokenError, json.JSONDecodeError):
            return None
    
    def revoke_session(self, access_token: str) -> bool:
        """
        Revoke a user's session based on their access token.
        
        Args:
            access_token: JWT access token
            
        Returns:
            Boolean indicating success
        """
        valid, payload, _ = self.validate_access_token(access_token)
        
        if not valid:
            return False
        
        user_id = payload.get("sub")
        
        if not user_id:
            return False
        
        # In a real system, you'd want to:
        # 1. Find all refresh tokens for this user
        # 2. Mark them as revoked or delete them
        
        # For this implementation, we'll scan for keys matching this user
        # Note: Scanning in Redis can be expensive in production
        refresh_token_pattern = "refresh_token:*"
        cursor = 0
        revoked_count = 0
        
        while True:
            cursor, keys = self.redis_client.scan(cursor, refresh_token_pattern)
            
            for key in keys:
                try:
                    session_data_json = self.redis_client.get(key)
                    if session_data_json:
                        session_data = SessionData.parse_raw(session_data_json)
                        
                        if session_data.user_id == user_id:
                            # Either delete or mark as inactive
                            self.redis_client.delete(key)
                            revoked_count += 1
                except:
                    # If any error occurs, continue with other keys
                    continue
            
            if cursor == 0:
                break
        
        return revoked_count > 0


class AuditScribe:
    """Records authentication events to secure, immutable audit logs"""
    
    def __init__(self, log_path=None, hmac_key=None):
        """
        Initialize the audit logger with path and HMAC key.
        
        Args:
            log_path: Path to the audit log file
            hmac_key: Secret key for signing log entries
        """
        self.log_path = log_path or os.getenv("AUDIT_LOG_PATH", "/mnt/e/sort/output/audit/audit_trail.jsonl")
        
        # In production, this key should be loaded from secure storage
        self.hmac_key = hmac_key or os.getenv("AUDIT_HMAC_KEY", "default-hmac-key").encode()
        
        # Ensure the log directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
    
    def log_event(self, 
                  user_id: str,
                  ip_address: str,
                  action: str,
                  result: str,
                  error_code: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an authentication event with a secure signature.
        
        Args:
            user_id: User identifier (anonymized if needed)
            ip_address: Client IP address (can be partially redacted)
            action: Action performed (login, logout, etc.)
            result: Result of the action (success, deny, etc.)
            error_code: Error code if applicable
            metadata: Additional contextual information
        """
        # Create timestamp
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Redact IP for privacy (keeping first two octets)
        ip_parts = ip_address.split('.')
        if len(ip_parts) == 4:
            redacted_ip = f"{ip_parts[0]}.{ip_parts[1]}.x.x"
        else:
            redacted_ip = "0.0.0.x.x"
        
        # Build log entry
        log_entry = {
            "ts": timestamp,
            "uid": user_id,
            "ip": redacted_ip,
            "action": action,
            "result": result
        }
        
        # Add error code if present
        if error_code:
            log_entry["err"] = error_code
        
        # Add metadata if present (excluding sensitive fields)
        if metadata:
            # Filter out any potentially sensitive fields
            safe_metadata = {k: v for k, v in metadata.items() 
                            if k not in ["password", "token", "secret", "credential"]}
            
            # Merge safely without overwriting core fields
            for key, value in safe_metadata.items():
                if key not in log_entry:
                    log_entry[key] = value
        
        # Compute HMAC signature for log integrity
        log_json = json.dumps(log_entry, sort_keys=True)
        signature = hmac.new(
            self.hmac_key,
            log_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Add signature to log entry
        log_entry["signature"] = signature
        
        # Write to log file (append mode)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Also log to standard logger for visibility
        logger.info(f"Auth event: {action} for user {user_id} - {result}")


class AuthAgent:
    """
    Agent for handling authentication flow according to auth_master.md.
    
    Coordinates credential validation, risk analysis, MFA decisions,
    token management, and audit logging.
    """
    
    def __init__(self, redis_url=None, audit_log_path=None):
        """
        Initialize the Authentication Agent with its components.
        
        Args:
            redis_url: Redis connection string
            audit_log_path: Path to the audit log file
        """
        self.credential_guard = CredentialGuard()
        self.risk_analyzer = RiskAnalyzer()
        self.session_broker = SessionBroker(redis_url)
        self.audit_scribe = AuditScribe(audit_log_path)
        
        logger.info("Authentication Agent initialized")
    
    def login(self, 
              username: str, 
              password: str, 
              ip_address: str, 
              user_agent: str,
              device_fingerprint: str,
              scope: List[str] = None) -> AuthResult:
        """
        Authenticate a user and issue tokens if successful.
        
        Args:
            username: User's email or username
            password: User's password (will be redacted in logs)
            ip_address: Client IP address
            user_agent: Client user agent string
            device_fingerprint: Unique device identifier
            scope: Requested permission scopes
            
        Returns:
            AuthResult object with result status and tokens if successful
        """
        # Default scope if none provided
        if not scope:
            scope = ["default"]
        
        # Audit context (excluding password)
        audit_ctx = {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "device_fingerprint": device_fingerprint
        }
        
        # Step 1: Validate credentials
        if not self.credential_guard.validate_credentials(username, password):
            # Log failed attempt
            self.audit_scribe.log_event(
                user_id=username,
                ip_address=ip_address,
                action="login",
                result="deny",
                error_code="AUTH-001",
                metadata=audit_ctx
            )
            
            return AuthResult(
                success=False,
                message="Invalid credentials",
                error_code="AUTH-001"
            )
        
        # Step 2: Calculate risk score
        risk_score = self.risk_analyzer.calculate_risk_score(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint
        )
        
        # Determine if MFA is required
        # For simplicity, assume device is recognized if fingerprint is not empty
        device_recognized = bool(device_fingerprint and device_fingerprint != "unknown")
        requires_mfa = self.risk_analyzer.requires_mfa(risk_score, device_recognized)
        
        # Step 3: Check if MFA is required
        if requires_mfa:
            # In a real system, you would initiate the MFA challenge here
            self.audit_scribe.log_event(
                user_id=username,
                ip_address=ip_address,
                action="mfa_required",
                result="pending",
                error_code="AUTH-002",
                metadata=audit_ctx
            )
            
            return AuthResult(
                success=False,
                message="Multi-factor authentication required",
                error_code="AUTH-002",
                requires_mfa=True
            )
        
        # Step 4: Generate tokens
        context = {
            "risk": risk_score,
            "ip": ip_address,
            "ua": user_agent,
            "device_fingerprint": device_fingerprint
        }
        
        tokens = self.session_broker.generate_tokens(username, scope, context)
        
        # Log successful login
        self.audit_scribe.log_event(
            user_id=username,
            ip_address=ip_address,
            action="login",
            result="success",
            metadata=audit_ctx
        )
        
        return AuthResult(
            success=True,
            message="Authentication successful",
            tokens=tokens
        )
    
    def verify_token(self, access_token: str) -> AuthResult:
        """
        Verify an access token and return its claims if valid.
        
        Args:
            access_token: JWT access token
            
        Returns:
            AuthResult indicating if token is valid
        """
        valid, payload, error_code = self.session_broker.validate_access_token(access_token)
        
        if not valid:
            return AuthResult(
                success=False,
                message=ERROR_CODES.get(error_code, "Invalid token"),
                error_code=error_code
            )
        
        return AuthResult(
            success=True,
            message="Token valid",
            tokens={"payload": payload}
        )
    
    def refresh(self, refresh_token: str, ip_address: str, user_agent: str) -> AuthResult:
        """
        Refresh a token pair using a valid refresh token.
        
        Args:
            refresh_token: JWT refresh token
            ip_address: Client IP address 
            user_agent: Client user agent string
            
        Returns:
            AuthResult with new tokens if successful
        """
        new_tokens = self.session_broker.refresh_tokens(refresh_token)
        
        if not new_tokens:
            # Log failed refresh
            self.audit_scribe.log_event(
                user_id="unknown",  # We don't know the user at this point
                ip_address=ip_address,
                action="refresh",
                result="deny",
                error_code="AUTH-004",
                metadata={"user_agent": user_agent}
            )
            
            return AuthResult(
                success=False,
                message="Invalid or expired refresh token",
                error_code="AUTH-004"
            )
        
        # Extract user ID from new access token to log the event
        try:
            # Decode without verification since we just created it
            payload = jwt.decode(
                new_tokens["access_token"],
                options={"verify_signature": False}
            )
            user_id = payload.get("sub", "unknown")
        except:
            user_id = "unknown"
        
        # Log successful refresh
        self.audit_scribe.log_event(
            user_id=user_id,
            ip_address=ip_address,
            action="refresh",
            result="success",
            metadata={"user_agent": user_agent}
        )
        
        return AuthResult(
            success=True,
            message="Tokens refreshed successfully",
            tokens=new_tokens
        )
    
    def logout(self, access_token: str, ip_address: str, user_agent: str) -> AuthResult:
        """
        Revoke a user's session and invalidate their tokens.
        
        Args:
            access_token: JWT access token
            ip_address: Client IP address
            user_agent: Client user agent string
            
        Returns:
            AuthResult indicating logout success
        """
        # First validate the token to get the user ID
        valid, payload, _ = self.session_broker.validate_access_token(access_token)
        
        if not valid:
            return AuthResult(
                success=False,
                message="Invalid token",
                error_code="AUTH-004"
            )
        
        user_id = payload.get("sub", "unknown")
        
        # Revoke the session
        revoked = self.session_broker.revoke_session(access_token)
        
        # Log the logout event
        self.audit_scribe.log_event(
            user_id=user_id,
            ip_address=ip_address,
            action="logout",
            result="success" if revoked else "failure",
            metadata={"user_agent": user_agent}
        )
        
        return AuthResult(
            success=revoked,
            message="Logout successful" if revoked else "Logout failed"
        )
    
    def verify_mfa(self, 
                   username: str, 
                   mfa_code: str, 
                   ip_address: str, 
                   user_agent: str,
                   device_fingerprint: str,
                   scope: List[str] = None) -> AuthResult:
        """
        Verify an MFA challenge and issue tokens if successful.
        
        Args:
            username: User's email or username
            mfa_code: MFA verification code
            ip_address: Client IP address
            user_agent: Client user agent string
            device_fingerprint: Unique device identifier
            scope: Requested permission scopes
            
        Returns:
            AuthResult with tokens if MFA was successful
        """
        # Default scope if none provided
        if not scope:
            scope = ["default"]
        
        # Audit context
        audit_ctx = {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "device_fingerprint": device_fingerprint
        }
        
        # TODO: Implement actual MFA verification
        # For this demo, we'll accept any 6-digit code
        valid_mfa = len(mfa_code) == 6 and mfa_code.isdigit()
        
        if not valid_mfa:
            # Log failed MFA attempt
            self.audit_scribe.log_event(
                user_id=username,
                ip_address=ip_address,
                action="mfa_verify",
                result="deny",
                error_code="AUTH-002",
                metadata=audit_ctx
            )
            
            return AuthResult(
                success=False,
                message="Invalid MFA code",
                error_code="AUTH-002",
                requires_mfa=True
            )
        
        # Calculate risk score (should be cached from initial login attempt)
        risk_score = self.risk_analyzer.calculate_risk_score(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint
        )
        
        # Generate tokens
        context = {
            "risk": risk_score,
            "ip": ip_address,
            "ua": user_agent,
            "device_fingerprint": device_fingerprint,
            "mfa_verified": True
        }
        
        tokens = self.session_broker.generate_tokens(username, scope, context)
        
        # Log successful MFA verification
        self.audit_scribe.log_event(
            user_id=username,
            ip_address=ip_address,
            action="mfa_verify",
            result="success",
            metadata=audit_ctx
        )
        
        return AuthResult(
            success=True,
            message="MFA verification successful",
            tokens=tokens
        )