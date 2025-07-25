import base64
import binascii
from typing import Optional, Tuple
from os import urandom
from django.conf import settings
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

KEY = binascii.unhexlify(settings.AES_SECRET_KEY) 

def encrypt_combined(number: int, uid: str) -> str:
    text = f"{number}::{uid}"
    iv = urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(text.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.urlsafe_b64encode(iv + ciphertext).decode()

def decrypt_combined(encoded: str) -> Optional[Tuple[int, str]]:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        if len(raw) < 17:
            return None

        iv, ciphertext = raw[:16], raw[16:]
        cipher = Cipher(algorithms.AES(KEY), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        text = unpadder.update(padded) + unpadder.finalize()

        number_str, uuid_str = text.decode().split("::", 1)
        return int(number_str), uuid_str
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
