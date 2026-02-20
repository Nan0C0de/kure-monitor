import base64
import hashlib
import os
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet = None


def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive a valid Fernet key from an arbitrary string.

    If *raw_key* is already a valid Fernet key (url-safe base64 of 32 bytes)
    it is returned as-is.  Otherwise a SHA-256 digest is computed and encoded
    to produce a deterministic, valid Fernet key.
    """
    try:
        decoded = base64.urlsafe_b64decode(raw_key)
        if len(decoded) == 32:
            return raw_key.encode()
    except Exception:
        pass

    # Derive 32 bytes deterministically and url-safe-b64 encode
    digest = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY environment variable is required for API key encryption"
            )
        _fernet = Fernet(_derive_fernet_key(key))
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string and return the Fernet token as a string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token string and return the plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
