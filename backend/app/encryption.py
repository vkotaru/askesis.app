"""Fernet encryption for sensitive data at rest (e.g., Google refresh tokens)."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Get or create a Fernet instance using ENCRYPTION_KEY (falls back to SECRET_KEY)."""
    global _fernet
    if _fernet is None:
        settings = get_settings()
        key_source = settings.encryption_key or settings.secret_key
        # Derive a valid 32-byte Fernet key from the source key
        key_bytes = hashlib.sha256(key_source.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        _fernet = Fernet(fernet_key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string, returning a base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to the original token."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # If decryption fails, the value may be a legacy plaintext token
        logger.warning("Failed to decrypt token — returning as plaintext (legacy)")
        return ciphertext


def get_refresh_token(user) -> str | None:
    """Get the decrypted refresh token for a user, or None if not set."""
    if not user.google_refresh_token:
        return None
    return decrypt_token(user.google_refresh_token)
