"""
Authentication and Authorization Module for Lab Notebook Services

Implements Bearer token auth, Slack signature verification, and HMAC validation
for cross-service communication.
"""

import hashlib
import hmac
import time
import secrets
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
import jwt
import logging

logger = logging.getLogger(__name__)


class AuthManager:
    """Centralized authentication and authorization manager"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize auth manager with configuration
        
        Args:
            config: Dict containing auth configuration including:
                - bearer_token: Main API bearer token
                - slack_signing_secret: Slack app signing secret
                - hmac_secret: Secret for cross-service HMAC signatures
                - jwt_secret: Secret for JWT token generation (optional)
                - token_expiry_hours: JWT token expiry time (default 24)
        """
        self.bearer_token = config.get('bearer_token')
        self.slack_signing_secret = config.get('slack_signing_secret')
        self.hmac_secret = config.get('hmac_secret')
        self.jwt_secret = config.get('jwt_secret', secrets.token_urlsafe(32))
        self.token_expiry_hours = config.get('token_expiry_hours', 24)
        
        if not self.bearer_token:
            raise ValueError("Bearer token is required for authentication")
    
    def verify_bearer_token(self, token: str) -> bool:
        """
        Verify bearer token from Authorization header
        
        Args:
            token: Bearer token string
            
        Returns:
            bool: True if token is valid
        """
        if not token:
            return False
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(token, self.bearer_token)
    
    def verify_slack_signature(self, 
                              signature: str, 
                              timestamp: str, 
                              body: bytes) -> bool:
        """
        Verify Slack request signature
        
        Args:
            signature: X-Slack-Signature header value
            timestamp: X-Slack-Request-Timestamp header value
            body: Raw request body
            
        Returns:
            bool: True if signature is valid
        """
        if not all([signature, timestamp, body, self.slack_signing_secret]):
            return False
        
        # Check timestamp to prevent replay attacks (5 minute window)
        try:
            ts = float(timestamp)
            if abs(time.time() - ts) > 300:  # 5 minutes
                logger.warning(f"Slack request timestamp too old: {timestamp}")
                return False
        except (ValueError, TypeError):
            logger.error(f"Invalid Slack timestamp: {timestamp}")
            return False
        
        # Construct base string for signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        
        # Calculate expected signature
        expected_sig = 'v0=' + hmac.new(
            self.slack_signing_secret.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison
        return hmac.compare_digest(expected_sig, signature)
    
    def generate_hmac_signature(self, payload: bytes) -> str:
        """
        Generate HMAC signature for cross-service communication
        
        Args:
            payload: Request body as bytes
            
        Returns:
            str: HMAC signature in format "sha256=<hex>"
        """
        if not self.hmac_secret:
            raise ValueError("HMAC secret not configured")
        
        signature = hmac.new(
            self.hmac_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def verify_hmac_signature(self, signature: str, payload: bytes) -> bool:
        """
        Verify HMAC signature for cross-service communication
        
        Args:
            signature: X-Signature header value
            payload: Request body as bytes
            
        Returns:
            bool: True if signature is valid
        """
        if not signature or not self.hmac_secret:
            return False
        
        expected_sig = self.generate_hmac_signature(payload)
        return hmac.compare_digest(expected_sig, signature)
    
    def generate_jwt_token(self, 
                          user_id: str, 
                          claims: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate JWT token for session management
        
        Args:
            user_id: User identifier
            claims: Additional claims to include in token
            
        Returns:
            str: JWT token
        """
        payload = {
            'user_id': user_id,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            'jti': secrets.token_urlsafe(16)  # JWT ID for revocation support
        }
        
        if claims:
            payload.update(claims)
        
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Dict containing token claims if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None


# Flask decorators for authentication
def require_bearer_auth(auth_manager: AuthManager):
    """
    Flask decorator to require bearer token authentication
    
    Args:
        auth_manager: AuthManager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            
            if not auth_manager.verify_bearer_token(auth_header):
                return jsonify({
                    'status': 'error',
                    'code': 'E_SECURITY',
                    'message': 'Invalid or missing bearer token'
                }), 401
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_slack_signature(auth_manager: AuthManager):
    """
    Flask decorator to verify Slack request signatures
    
    Args:
        auth_manager: AuthManager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Slack-Signature', '')
            timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
            
            if not auth_manager.verify_slack_signature(
                signature, timestamp, request.get_data()
            ):
                return jsonify({
                    'status': 'error',
                    'code': 'E_SECURITY',
                    'message': 'Invalid Slack signature'
                }), 401
            
            # Store verified Slack user ID in g for use in view
            try:
                data = request.get_json(force=True)
                g.slack_user_id = data.get('user', {}).get('id')
            except:
                pass
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_hmac_signature(auth_manager: AuthManager):
    """
    Flask decorator to verify HMAC signatures for cross-service calls
    
    Args:
        auth_manager: AuthManager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Signature', '')
            
            if not auth_manager.verify_hmac_signature(
                signature, request.get_data()
            ):
                return jsonify({
                    'status': 'error',
                    'code': 'E_SECURITY',
                    'message': 'Invalid HMAC signature'
                }), 401
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


class TokenStore:
    """Simple in-memory token store for revocation support"""
    
    def __init__(self):
        self.revoked_tokens = set()
        self.token_metadata = {}
    
    def revoke_token(self, jti: str):
        """Revoke a token by its JWT ID"""
        self.revoked_tokens.add(jti)
        if jti in self.token_metadata:
            del self.token_metadata[jti]
    
    def is_revoked(self, jti: str) -> bool:
        """Check if a token is revoked"""
        return jti in self.revoked_tokens
    
    def store_metadata(self, jti: str, metadata: Dict[str, Any]):
        """Store metadata about a token"""
        self.token_metadata[jti] = {
            **metadata,
            'created_at': datetime.utcnow().isoformat()
        }
    
    def cleanup_expired(self):
        """Remove expired tokens from revocation list"""
        # This would be called periodically to clean up old entries
        current_time = datetime.utcnow()
        for jti in list(self.revoked_tokens):
            if jti in self.token_metadata:
                created = datetime.fromisoformat(self.token_metadata[jti]['created_at'])
                if (current_time - created).days > 30:  # Keep for 30 days
                    self.revoked_tokens.remove(jti)
                    del self.token_metadata[jti]