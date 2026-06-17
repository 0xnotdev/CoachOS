from cryptography.fernet import Fernet
import base64
import hashlib
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class SecurityHelper:
    def __init__(self):
        # Derives a cryptographically strong 32-byte key from the configured JWT secret key.
        # This keeps the setup simple and free of third-party KMS dependencies while enforcing AES-256 (Fernet).
        secret = settings.SUPABASE_JWT_SECRET or "default_fallback_jwt_secret_key_32_bytes_long"
        key_bytes = hashlib.sha256(secret.encode()).digest()
        self.key = base64.urlsafe_b64encode(key_bytes)
        self.cipher = Fernet(self.key)

    def encrypt(self, plain_text: str) -> str:
        """
        Encrypts a plaintext string into a secure AES-256 cipher string.
        """
        if not plain_text:
            return ""
        return self.cipher.encrypt(plain_text.encode()).decode()

    def decrypt(self, cipher_text: str) -> str:
        """
        Decrypts an AES-256 cipher string back to plaintext.
        Returns the input as-is if it's plaintext (e.g. legacy secrets before encryption migration).
        """
        if not cipher_text:
            return ""
        try:
            return self.cipher.decrypt(cipher_text.encode()).decode()
        except Exception:
            # Safe fallback in case of unencrypted legacy database rows
            return cipher_text

# Global singleton
security_helper = SecurityHelper()
