import hashlib
import hmac
import os


def hash_senha(senha: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        _, salt, h = armazenado.split("$")
        novo = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(novo.hex(), h)
    except Exception:
        return False
