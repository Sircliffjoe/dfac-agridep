import hashlib
import base64
from django.conf import settings
from cryptography.fernet import Fernet

def get_fernet() -> Fernet:
    """Returns a configured Fernet cipher instance."""
    raw_key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '')
    # Ensure key is 32 url-safe base64-encoded bytes
    if not raw_key:
        raw_key = base64.urlsafe_b64encode(b'default_dev_key_32_bytes_long!!').decode()
    try:
        return Fernet(raw_key.encode('utf-8'))
    except Exception:
        # Fallback for key format variations in development
        padded = raw_key.ljust(32, '=')[:32]
        return Fernet(base64.urlsafe_b64encode(padded.encode('utf-8')))

def encrypt_value(value: str) -> str:
    """Encrypts a plaintext string to an encrypted ciphertext string."""
    if not value:
        return ""
    fernet = get_fernet()
    return fernet.encrypt(value.encode('utf-8')).decode('utf-8')

def decrypt_value(token: str) -> str:
    """Decrypts a ciphertext string back to plaintext."""
    if not token:
        return ""
    try:
        fernet = get_fernet()
        return fernet.decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception:
        return "[Decryption Error]"

def hash_deterministic(value: str) -> str:
    """
    Computes a deterministic SHA-256 hash (e.g. for NIN or Phone)
    allowing exact-match duplicate detection without decrypting database records.
    """
    if not value:
        return ""
    normalized = value.strip().upper()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
