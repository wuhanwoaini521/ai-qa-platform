from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class FailureSnapshotCipher:
    """Encrypt ephemeral pytest transfers and platform-at-rest snapshot payloads."""

    EPHEMERAL_PREFIX = "ephemeral:v1:"
    AT_REST_PREFIX = "enc_"

    @staticmethod
    def generate_ephemeral_key() -> str:
        return Fernet.generate_key().decode("ascii")

    @classmethod
    def encrypt_ephemeral(cls, raw_value: str, key: str) -> str:
        if not raw_value:
            return ""
        token = Fernet(key.encode("ascii")).encrypt(raw_value.encode("utf-8")).decode("ascii")
        return cls.EPHEMERAL_PREFIX + token

    @classmethod
    def decrypt_ephemeral(cls, encrypted_value: str, key: str) -> str:
        if not encrypted_value.startswith(cls.EPHEMERAL_PREFIX):
            return ""
        try:
            return (
                Fernet(key.encode("ascii"))
                .decrypt(encrypted_value.removeprefix(cls.EPHEMERAL_PREFIX).encode("ascii"))
                .decode("utf-8")
            )
        except (InvalidToken, UnicodeDecodeError, ValueError):
            return ""

    @staticmethod
    def _master_fernet(master_key: str) -> Fernet:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode("utf-8")).digest())
        return Fernet(derived_key)

    @classmethod
    def encrypt_at_rest(cls, raw_value: str, master_key: str) -> str:
        if not raw_value:
            return ""
        token = cls._master_fernet(master_key).encrypt(raw_value.encode("utf-8")).decode("ascii")
        return cls.AT_REST_PREFIX + token

    @classmethod
    def decrypt_at_rest(cls, encrypted_value: str, master_key: str) -> str:
        if not encrypted_value.startswith(cls.AT_REST_PREFIX):
            return ""
        try:
            return (
                cls._master_fernet(master_key)
                .decrypt(encrypted_value.removeprefix(cls.AT_REST_PREFIX).encode("ascii"))
                .decode("utf-8")
            )
        except (InvalidToken, UnicodeDecodeError, ValueError):
            return ""
