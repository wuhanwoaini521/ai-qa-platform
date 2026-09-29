from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class SecretStore:
    """Authenticated encryption for credentials persisted by API services."""

    def __init__(self, master_key: str | None = None) -> None:
        self.master_key = master_key or os.getenv("APP_SECRET_KEY", "qa-platform-super-secret-master-key-32b")
        self._in_memory_vault: dict[str, str] = {}
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(self.master_key.encode("utf-8")).digest())
        self._fernet = Fernet(derived_key)

    def encrypt_secret(self, raw_secret: str) -> str:
        if not raw_secret:
            return ""
        return "enc_" + self._fernet.encrypt(raw_secret.encode("utf-8")).decode("ascii")

    def decrypt_secret(self, encrypted_token: str) -> str:
        if not encrypted_token or not encrypted_token.startswith("enc_"):
            return encrypted_token
        try:
            return self._fernet.decrypt(encrypted_token[4:].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError):
            return ""

    @staticmethod
    def mask_secret(secret: str) -> str:
        """Returns a masked version of a sensitive secret for API responses."""
        if not secret:
            return ""
        if len(secret) <= 6:
            return "***"
        prefix = secret[:3]
        suffix = secret[-3:]
        return f"{prefix}***{suffix}"

    def store_secret(self, key: str, value: str) -> None:
        self._in_memory_vault[key] = self.encrypt_secret(value)

    def get_secret(self, key: str) -> str:
        enc = self._in_memory_vault.get(key, "")
        return self.decrypt_secret(enc)
