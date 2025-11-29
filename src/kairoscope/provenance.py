"""
Hanldes cryptographic operations for KAIROSCOPE.

- Key pair generation, loading.
- Signing and verification of data.
- Creation of C2PA-like assertions.
"""

import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes


def get_key_path() -> Path:
    return Path.cwd() / "kairoscope.key"


def get_public_key_path() -> Path:
    return Path.cwd() / "kairoscope.pub"


KEY_PASSWORD = None  # For simplicity in v0.1; use env var or KMS in production.


def get_keypair() -> PrivateKeyTypes:
    """
    Loads an existing private key or generates a new one.

    For Bronze, we use an unencrypted local key file. This is not secure for
    production but satisfies the offline-first, deterministic requirement.
    """
    if get_key_path().exists():
        with open(get_key_path(), "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=KEY_PASSWORD)
    else:
        # Using ECC for smaller key sizes and good performance.
        private_key = ec.generate_private_key(ec.SECP384R1())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(get_key_path(), "wb") as f:
            f.write(pem)

        # Also save public key for convenience
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with open(get_public_key_path(), "wb") as f:
            f.write(public_pem)

    return private_key


def get_public_key(private_key: PrivateKeyTypes | None = None) -> PublicKeyTypes:
    """Returns the public key from a private key or loads it from the filesystem."""
    if private_key:
        return private_key.public_key()
    if get_public_key_path().exists():
        with open(get_public_key_path(), "rb") as f:
            return serialization.load_pem_public_key(f.read())
    # If public key file is missing, regenerate from private key
    priv_key = get_keypair()
    return priv_key.public_key()


def get_public_key_fingerprint() -> str:
    """Returns the SHA256 fingerprint of the public key, used as the agent ID."""
    public_key = get_public_key()
    der_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashes.Hash(hashes.SHA256())
    digest.update(der_bytes)
    return f"sha256:{digest.finalize().hex()}"


def sign_bytes(data: bytes, private_key: PrivateKeyTypes) -> bytes:
    """Signs a byte string using the provided private key."""
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    elif isinstance(private_key, rsa.RSAPrivateKey):
        return private_key.sign(
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    raise TypeError("Unsupported private key type")


def verify_signature(
    signature: bytes, data: bytes, public_key: PublicKeyTypes | None = None
) -> bool:
    """Verifies a signature against the data and public key."""
    key_to_use = public_key or get_public_key()
    try:
        if isinstance(key_to_use, ec.EllipticCurvePublicKey):
            key_to_use.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        elif isinstance(key_to_use, rsa.RSAPrivateKey):
            key_to_use.verify(
                signature,
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        else:
            return False
        return True
    except Exception:
        return False


def create_assertion(artifact_hash: str, signature_hex: str) -> str:
    """
    Creates a minimal, C2PA-like JSON assertion.

    This is a simplified, local-only construct for Bronze. It binds the
    artifact hash to a signature and the identity of the signer.
    """
    assertion = {
        "alg": "ES384" if isinstance(get_keypair(), ec.EllipticCurvePrivateKey) else "PS256",
        "hash": artifact_hash,
        "signature": signature_hex,
        "signer": get_public_key_fingerprint(),
    }
    # Using compact, sorted JSON for deterministic output.
    return json.dumps(assertion, sort_keys=True, separators=(",", ":"))
