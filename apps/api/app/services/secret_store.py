from __future__ import annotations

import base64
import os


class SecretStore:
    """Enterprise secret store managing encrypted tokens, credentials, and safe masking."""

    def __init__(self, master_key: str | None = None) -> None:
        self.master_key = master_key or os.getenv("APP_SECRET_KEY", "qa-platform-super-secret-master-key-32b")
        self._in_memory_vault: dict[str, str] = {}

    def encrypt_secret(self, raw_secret: str) -> str:
        if not raw_secret:
            return ""
        # XOR + base64 encoding for portable storage
        key_bytes = self.master_key.encode("utf-8")
        raw_bytes = raw_secret.encode("utf-8")
        encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw_bytes))
        return "enc_" + base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def decrypt_secret(self, encrypted_token: str) -> str:
        if not encrypted_token or not encrypted_token.startswith("enc_"):
            return encrypted_token
        try:
            raw_b64 = encrypted_token[4:]
            encrypted = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
            key_bytes = self.master_key.encode("utf-8")
            decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted))
            return decrypted.decode("utf-8")
        except Exception:
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
