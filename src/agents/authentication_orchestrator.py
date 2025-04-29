"""
Authentication Orchestrator for managing user identity and access control.
"""

import logging
import uuid
import os
import json
import time
import redis
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from src.utils.base_orchestrator import BaseOrchestrator
from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode
)

logger = logging.getLogger(__name__)

class AuthenticationOrchestrator(BaseOrchestrator):
    """
    Orchestrates user authentication and access control operations.
    
    Responsible for:
    1. Managing user identity and access verification
    2. Coordinating token issuance, refreshing, and revocation
    3. Handling session state management
    4. Enforcing multi-factor authentication rules
    5. Maintaining authentication audit logs
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the authentication orchestrator.
        
        Args:
            redis_url: Optional Redis URL for session storage
        """
        self.orchestrator_id = "auth-orchestrator"
        super().__init__(self.orchestrator_id)
        
        # Initialize session storage (Redis if available, otherwise in-memory)
        self._init_session_storage(redis_url)
        
        # Generate or load encryption keys
        self._init_crypto_keys()
        
        # Load user database (placeholder - would be DB in production)
        self.users = self._load_user_database()
        
        # Define token TTLs
        self.access_token_ttl = 3600  # 1 hour
        self.refresh_token_ttl = 2592000  # 30 days
        
        # Initialize blacklisted tokens set
        self.blacklisted_tokens = set()
        
        logger.info(f"Authentication Orchestrator {self.orchestrator_id} initialized")
    
    def _init_session_storage(self, redis_url: Optional[str]):
        """Initialize session storage."""
        self.use_redis = redis_url is not None
        
        if self.use_redis:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("Connected to Redis for session storage")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                self.use_redis = False
                self.sessions = {}
        else:
            logger.info("Using in-memory session storage")
            self.sessions = {}
    
    def _init_crypto_keys(self):
        """Initialize cryptographic keys for JWT signing."""
        key_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "keys")
        private_key_path = os.path.join(key_dir, "jwt_private_key.pem")
        public_key_path = os.path.join(key_dir, "jwt_public_key.pem")
        
        # Ensure key directory exists
        os.makedirs(key_dir, exist_ok=True)
        
        if os.path.exists(private_key_path) and os.path.exists(public_key_path):
            # Load existing keys
            with open(private_key_path, "rb") as f:
                self.private_key_pem = f.read()
            
            with open(public_key_path, "rb") as f:
                self.public_key_pem = f.read()
                
            logger.info("Loaded existing JWT keys")
        else:
            # Generate new RSA key pair
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Extract public key
            public_key = private_key.public_key()
            
            # Serialize private key to PEM
            self.private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            # Serialize public key to PEM
            self.public_key_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            # Write keys to files
            with open(private_key_path, "wb") as f:
                f.write(self.private_key_pem)
            
            with open(public_key_path, "wb") as f:
                f.write(self.public_key_pem)
            
            # Set restrictive permissions on private key
            os.chmod(private_key_path, 0o600)
            
            logger.info("Generated new JWT keys")
    
    def _load_user_database(self) -> Dict[str, Dict[str, Any]]:
        """Load user database (placeholder implementation)."""
        # This would be replaced with a real database in production
        return {
            "user-789": {
                "id": "user-789",
                "name": "Demo User",
                "email": "demo@example.com",
                "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$hashhashhashhashhashhash",  # This is a placeholder
                "roles": ["standard"],
                "permissions": ["doc:read", "doc:write"],
                "mfa_enabled": False,
                "mfa_methods": []
            },
            "admin-123": {
                "id": "admin-123",
                "name": "Admin User",
                "email": "admin@example.com",
                "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$hashhashhashhashhashhash",  # This is a placeholder
                "roles": ["admin"],
                "permissions": ["doc:read", "doc:write", "doc:admin", "system:admin"],
                "mfa_enabled": True,
                "mfa_methods": ["totp"]
            }
        }
    
    def get_supported_tasks(self) -> List[str]:
        """Get the list of tasks supported by this orchestrator."""
        return [
            "authenticate",
            "validate_token",
            "refresh_token",
            "revoke_token",
            "validate_access",
            "start_mfa",
            "verify_mfa",
            "get_public_key"
        ]
    
    def handle_authenticate(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle authentication request.
        
        Args:
            message: Orchestration message with authentication parameters
            
        Returns:
            Authentication result
        """
        params = message.params
        required_fields = ["username", "password"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        # Extract credentials
        username = params["username"]
        password = params["password"]
        
        # In a real implementation, we would verify the password hash
        # For now, we'll just check if the user exists
        user_id = None
        for uid, user in self.users.items():
            if user["email"] == username:
                user_id = uid
                break
        
        if not user_id:
            return message.create_error_response(
                error="Invalid username or password",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
        
        user = self.users[user_id]
        
        # Check if MFA is required
        if user.get("mfa_enabled", False):
            # Generate MFA session
            mfa_session_id = str(uuid.uuid4())
            mfa_expires_at = datetime.utcnow() + timedelta(minutes=10)
            
            mfa_session = {
                "session_id": mfa_session_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": mfa_expires_at.isoformat() + "Z",
                "completed": False,
                "mfa_methods": user.get("mfa_methods", [])
            }
            
            # Store MFA session
            self._store_session(f"mfa:{mfa_session_id}", mfa_session)
            
            # Return MFA required response
            return message.create_response({
                "status": "mfa_required",
                "mfa_session_id": mfa_session_id,
                "mfa_methods": user.get("mfa_methods", []),
                "expires_in": 600  # 10 minutes
            })
        
        # If no MFA required, generate tokens
        token_pair = self._generate_tokens(user_id, user.get("roles", []), user.get("permissions", []))
        
        # Create session
        session_id = token_pair["session_id"]
        expires_at = datetime.utcnow() + timedelta(seconds=self.access_token_ttl)
        
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": expires_at.isoformat() + "Z",
            "auth_level": user.get("roles", ["guest"])[0],
            "refresh_token_id": token_pair["refresh_token_id"],
            "ip_address": params.get("ip_address", "unknown"),
            "user_agent": params.get("user_agent", "unknown"),
        }
        
        # Store session
        self._store_session(f"session:{session_id}", session)
        
        # Return token response
        return message.create_response({
            "user_id": user_id,
            "session_id": session_id,
            "access_token": token_pair["access_token"],
            "refresh_token": token_pair["refresh_token"],
            "token_type": "Bearer",
            "expires_in": self.access_token_ttl,
            "auth_level": session["auth_level"],
            "permissions": user.get("permissions", []),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success"
        })
    
    def handle_validate_token(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle token validation request.
        
        Args:
            message: Orchestration message with token validation parameters
            
        Returns:
            Token validation result
        """
        params = message.params
        
        if "token" not in params:
            return message.create_error_response(
                error="Missing required field: token",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        token = params["token"]
        validation_result = self._validate_token(token)
        
        if validation_result["valid"]:
            return message.create_response(validation_result)
        else:
            return message.create_error_response(
                error=validation_result["error"],
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
    
    def handle_refresh_token(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle token refresh request.
        
        Args:
            message: Orchestration message with token refresh parameters
            
        Returns:
            Token refresh result
        """
        params = message.params
        
        if "refresh_token" not in params:
            return message.create_error_response(
                error="Missing required field: refresh_token",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        refresh_token = params["refresh_token"]
        
        try:
            # Verify refresh token
            payload = jwt.decode(
                refresh_token,
                self.public_key_pem,
                algorithms=["RS256"],
                options={"verify_signature": True}
            )
            
            # Check token type
            if payload.get("type") != "refresh":
                return message.create_error_response(
                    error="Invalid token type",
                    error_code=ErrorCode.AUTHENTICATION_ERROR
                )
            
            # Check if token is blacklisted
            token_id = payload.get("jti")
            if token_id in self.blacklisted_tokens:
                return message.create_error_response(
                    error="Token has been revoked",
                    error_code=ErrorCode.AUTHENTICATION_ERROR
                )
            
            # Get user
            user_id = payload.get("sub")
            if not user_id or user_id not in self.users:
                return message.create_error_response(
                    error="Invalid user",
                    error_code=ErrorCode.AUTHENTICATION_ERROR
                )
            
            user = self.users[user_id]
            
            # Generate new tokens
            token_pair = self._generate_tokens(user_id, user.get("roles", []), user.get("permissions", []))
            
            # Blacklist old refresh token
            self.blacklisted_tokens.add(token_id)
            
            # Create or update session
            session_id = token_pair["session_id"]
            expires_at = datetime.utcnow() + timedelta(seconds=self.access_token_ttl)
            
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z",
                "auth_level": user.get("roles", ["guest"])[0],
                "refresh_token_id": token_pair["refresh_token_id"],
                "ip_address": params.get("ip_address", "unknown"),
                "user_agent": params.get("user_agent", "unknown"),
            }
            
            # Store session
            self._store_session(f"session:{session_id}", session)
            
            # Return new token pair
            return message.create_response({
                "user_id": user_id,
                "session_id": session_id,
                "access_token": token_pair["access_token"],
                "refresh_token": token_pair["refresh_token"],
                "token_type": "Bearer",
                "expires_in": self.access_token_ttl,
                "auth_level": session["auth_level"],
                "permissions": user.get("permissions", []),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "success"
            })
            
        except jwt.ExpiredSignatureError:
            return message.create_error_response(
                error="Refresh token expired",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
        except jwt.InvalidTokenError as e:
            return message.create_error_response(
                error=f"Invalid refresh token: {str(e)}",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
    
    def handle_revoke_token(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle token revocation request.
        
        Args:
            message: Orchestration message with token revocation parameters
            
        Returns:
            Token revocation result
        """
        params = message.params
        
        if "token" not in params and "session_id" not in params:
            return message.create_error_response(
                error="Missing required field: token or session_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        if "session_id" in params:
            # Revoke by session ID
            session_id = params["session_id"]
            session_key = f"session:{session_id}"
            
            # Get session
            session = self._get_session(session_key)
            if not session:
                return message.create_error_response(
                    error="Session not found",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND
                )
            
            # Blacklist refresh token
            refresh_token_id = session.get("refresh_token_id")
            if refresh_token_id:
                self.blacklisted_tokens.add(refresh_token_id)
            
            # Delete session
            self._delete_session(session_key)
            
            return message.create_response({
                "status": "success",
                "message": "Session revoked successfully",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
        else:
            # Revoke by token
            token = params["token"]
            
            try:
                # Verify token to get token ID
                payload = jwt.decode(
                    token,
                    self.public_key_pem,
                    algorithms=["RS256"],
                    options={"verify_signature": True}
                )
                
                token_id = payload.get("jti")
                if not token_id:
                    return message.create_error_response(
                        error="Invalid token: missing token ID",
                        error_code=ErrorCode.VALIDATION_ERROR
                    )
                
                # Blacklist token
                self.blacklisted_tokens.add(token_id)
                
                # If it's a refresh token, revoke the associated session
                if payload.get("type") == "refresh":
                    user_id = payload.get("sub")
                    
                    # Find and delete any sessions with this refresh token
                    if self.use_redis:
                        # For Redis we would need to scan for sessions
                        pass
                    else:
                        # For in-memory storage
                        for session_key, session in list(self.sessions.items()):
                            if (session.get("refresh_token_id") == token_id and 
                                session.get("user_id") == user_id):
                                self._delete_session(session_key)
                
                return message.create_response({
                    "status": "success",
                    "message": "Token revoked successfully",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                
            except jwt.ExpiredSignatureError:
                # Token already expired, consider it revoked
                return message.create_response({
                    "status": "success",
                    "message": "Token already expired",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
            except jwt.InvalidTokenError as e:
                return message.create_error_response(
                    error=f"Invalid token: {str(e)}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
    
    def handle_validate_access(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle access validation request.
        
        Args:
            message: Orchestration message with access validation parameters
            
        Returns:
            Access validation result
        """
        params = message.params
        required_fields = ["user_id", "resource", "action"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        user_id = params["user_id"]
        resource = params["resource"]
        action = params["action"]
        
        # Check if user exists
        if user_id not in self.users:
            return message.create_response({
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "access_granted": False,
                "auth_level": "none",
                "reason": "user_not_found",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
        
        user = self.users[user_id]
        
        # Determine permission required based on action and resource
        # This is a simple implementation - in practice would use a more sophisticated
        # permission system like attribute-based access control (ABAC)
        permission_required = f"{resource.split(':')[0]}:{action}"
        
        # Check if user has the required permission
        has_permission = permission_required in user.get("permissions", [])
        
        result = {
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "access_granted": has_permission,
            "auth_level": user.get("roles", ["guest"])[0],
            "permissions": user.get("permissions", []),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if not has_permission:
            result["reason"] = "permission_denied"
        
        return message.create_response(result)
    
    def handle_start_mfa(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle MFA initialization request.
        
        Args:
            message: Orchestration message with MFA parameters
            
        Returns:
            MFA initialization result
        """
        params = message.params
        
        if "user_id" not in params:
            return message.create_error_response(
                error="Missing required field: user_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        user_id = params["user_id"]
        
        # Check if user exists
        if user_id not in self.users:
            return message.create_error_response(
                error="User not found",
                error_code=ErrorCode.RESOURCE_NOT_FOUND
            )
        
        user = self.users[user_id]
        
        # Check if MFA is enabled for user
        if not user.get("mfa_enabled", False):
            return message.create_error_response(
                error="MFA not enabled for user",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
        
        # Generate MFA session
        mfa_session_id = str(uuid.uuid4())
        mfa_expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        mfa_session = {
            "session_id": mfa_session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": mfa_expires_at.isoformat() + "Z",
            "completed": False,
            "mfa_methods": user.get("mfa_methods", [])
        }
        
        # Store MFA session
        self._store_session(f"mfa:{mfa_session_id}", mfa_session)
        
        # Return MFA session info
        return message.create_response({
            "mfa_session_id": mfa_session_id,
            "mfa_methods": user.get("mfa_methods", []),
            "expires_in": 600,  # 10 minutes
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    
    def handle_verify_mfa(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle MFA verification request.
        
        Args:
            message: Orchestration message with MFA verification parameters
            
        Returns:
            MFA verification result
        """
        params = message.params
        required_fields = ["mfa_session_id", "method", "code"]
        
        # Validate input
        for field in required_fields:
            if field not in params:
                return message.create_error_response(
                    error=f"Missing required field: {field}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        mfa_session_id = params["mfa_session_id"]
        method = params["method"]
        code = params["code"]
        
        # Get MFA session
        mfa_session = self._get_session(f"mfa:{mfa_session_id}")
        if not mfa_session:
            return message.create_error_response(
                error="MFA session not found or expired",
                error_code=ErrorCode.RESOURCE_NOT_FOUND
            )
        
        # Check if session is expired
        expires_at = datetime.fromisoformat(mfa_session["expires_at"].replace("Z", "+00:00"))
        if expires_at < datetime.utcnow():
            self._delete_session(f"mfa:{mfa_session_id}")
            return message.create_error_response(
                error="MFA session expired",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
        
        # Check if method is supported for this user
        if method not in mfa_session.get("mfa_methods", []):
            return message.create_error_response(
                error=f"MFA method {method} not enabled for user",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
        
        # Verify MFA code
        # This is a placeholder - in a real implementation, we would verify the code
        # based on the method (TOTP, SMS, etc.)
        if method == "totp" and code == "123456":  # Placeholder check
            # Mark MFA session as completed
            mfa_session["completed"] = True
            self._store_session(f"mfa:{mfa_session_id}", mfa_session)
            
            # Get user
            user_id = mfa_session["user_id"]
            user = self.users[user_id]
            
            # Generate tokens
            token_pair = self._generate_tokens(user_id, user.get("roles", []), user.get("permissions", []))
            
            # Create session
            session_id = token_pair["session_id"]
            expires_at = datetime.utcnow() + timedelta(seconds=self.access_token_ttl)
            
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z",
                "auth_level": user.get("roles", ["guest"])[0],
                "refresh_token_id": token_pair["refresh_token_id"],
                "ip_address": params.get("ip_address", "unknown"),
                "user_agent": params.get("user_agent", "unknown"),
                "mfa_verified": True,
                "mfa_method": method
            }
            
            # Store session
            self._store_session(f"session:{session_id}", session)
            
            # Return token response
            return message.create_response({
                "user_id": user_id,
                "session_id": session_id,
                "access_token": token_pair["access_token"],
                "refresh_token": token_pair["refresh_token"],
                "token_type": "Bearer",
                "expires_in": self.access_token_ttl,
                "auth_level": session["auth_level"],
                "permissions": user.get("permissions", []),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "success"
            })
        else:
            return message.create_error_response(
                error="Invalid MFA code",
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )
    
    def handle_get_public_key(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle public key request.
        
        Returns the public key used for token verification.
        
        Args:
            message: Orchestration message
            
        Returns:
            Public key information
        """
        return message.create_response({
            "alg": "RS256",
            "public_key": self.public_key_pem.decode('utf-8'),
            "key_id": "primary",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    
    def _generate_tokens(self, user_id: str, roles: List[str], permissions: List[str]) -> Dict[str, str]:
        """
        Generate JWT access and refresh tokens.
        
        Args:
            user_id: User ID
            roles: User roles
            permissions: User permissions
            
        Returns:
            Dictionary containing tokens and related information
        """
        # Generate session ID and refresh token ID
        session_id = str(uuid.uuid4())
        refresh_token_id = str(uuid.uuid4())
        
        # Get current time
        now = int(time.time())
        
        # Create access token payload
        access_payload = {
            "sub": user_id,
            "sid": session_id,
            "roles": roles,
            "perms": permissions,
            "iat": now,
            "exp": now + self.access_token_ttl,
            "jti": str(uuid.uuid4())
        }
        
        # Create refresh token payload
        refresh_payload = {
            "sub": user_id,
            "sid": session_id,
            "iat": now,
            "exp": now + self.refresh_token_ttl,
            "jti": refresh_token_id,
            "type": "refresh"
        }
        
        # Sign tokens with RS256
        access_token = jwt.encode(
            access_payload,
            self.private_key_pem,
            algorithm="RS256"
        )
        
        refresh_token = jwt.encode(
            refresh_payload,
            self.private_key_pem,
            algorithm="RS256"
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "session_id": session_id,
            "refresh_token_id": refresh_token_id
        }
    
    def _validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a JWT token.
        
        Args:
            token: JWT token to validate
            
        Returns:
            Validation result
        """
        try:
            # Verify token signature and claims
            payload = jwt.decode(
                token,
                self.public_key_pem,
                algorithms=["RS256"]
            )
            
            # Check if token is blacklisted
            token_id = payload.get("jti")
            if token_id in self.blacklisted_tokens:
                return {
                    "valid": False,
                    "error": "token_revoked",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            
            # Check if it's an access token (not a refresh token)
            if payload.get("type") == "refresh":
                return {
                    "valid": False,
                    "error": "invalid_token_type",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            
            # Get user
            user_id = payload.get("sub")
            if not user_id or user_id not in self.users:
                return {
                    "valid": False,
                    "error": "user_not_found",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            
            # Get session
            session_id = payload.get("sid")
            if session_id:
                session = self._get_session(f"session:{session_id}")
                if not session:
                    return {
                        "valid": False,
                        "error": "session_not_found",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
            
            # Token is valid
            return {
                "valid": True,
                "user_id": user_id,
                "session_id": session_id,
                "roles": payload.get("roles", []),
                "permissions": payload.get("perms", []),
                "expires_at": datetime.fromtimestamp(payload["exp"]).isoformat() + "Z",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except jwt.ExpiredSignatureError:
            return {
                "valid": False,
                "error": "token_expired",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except jwt.InvalidTokenError as e:
            return {
                "valid": False,
                "error": f"invalid_token: {str(e)}",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def _store_session(self, key: str, session: Dict[str, Any]) -> None:
        """
        Store a session in the session storage.
        
        Args:
            key: Session key
            session: Session data
        """
        if self.use_redis:
            try:
                # Convert to JSON and store in Redis
                session_json = json.dumps(session)
                
                # If it's a temporary session (like MFA), set an expiry
                if key.startswith("mfa:"):
                    # Extract expiry from session
                    expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
                    ttl = int((expires_at - datetime.utcnow()).total_seconds())
                    if ttl > 0:
                        self.redis_client.setex(key, ttl, session_json)
                    else:
                        # Session already expired
                        return
                else:
                    # For regular sessions, use a longer TTL (e.g., 2 days)
                    self.redis_client.setex(key, 172800, session_json)
            except Exception as e:
                logger.error(f"Failed to store session in Redis: {str(e)}")
                # Fallback to in-memory storage
                self.sessions[key] = session
        else:
            # Store in-memory
            self.sessions[key] = session
    
    def _get_session(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a session from the session storage.
        
        Args:
            key: Session key
            
        Returns:
            Session data or None if not found
        """
        if self.use_redis:
            try:
                session_json = self.redis_client.get(key)
                if session_json:
                    return json.loads(session_json)
                return None
            except Exception as e:
                logger.error(f"Failed to get session from Redis: {str(e)}")
                # Fallback to in-memory storage
                return self.sessions.get(key)
        else:
            # Get from in-memory storage
            return self.sessions.get(key)
    
    def _delete_session(self, key: str) -> None:
        """
        Delete a session from the session storage.
        
        Args:
            key: Session key
        """
        if self.use_redis:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.error(f"Failed to delete session from Redis: {str(e)}")
                # Fallback to in-memory storage
                if key in self.sessions:
                    del self.sessions[key]
        else:
            # Delete from in-memory storage
            if key in self.sessions:
                del self.sessions[key]