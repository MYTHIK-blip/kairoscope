"""
Hanldes cryptographic operations for KAIROSCOPE.

- Key pair generation, loading.
- Signing and verification of data.
- Creation of C2PA-like assertions.
"""

import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes

from kairoscope.key_manager import FileKeyBackend, KeyManager

# Initialize the default key manager (FileKeyBackend for now)
_key_manager: KeyManager | None = None


def set_key_manager(manager: KeyManager) -> None:
    """Sets the active KeyManager instance."""
    global _key_manager
    _key_manager = manager


def get_active_key_manager() -> KeyManager:
    """Returns the active KeyManager instance, raising an error if not set."""
    if _key_manager is None:
        raise RuntimeError("KeyManager has not been initialized. Call set_key_manager first.")
    return _key_manager


# For simplicity in v0.1; use env var or KMS in production.
# This is now handled within FileKeyBackend but kept for consistency if needed elsewhere.
KEY_PASSWORD = None


def get_keypair() -> PrivateKeyTypes:
    """
    Loads an existing private key or generates a new one using the active KeyManager.
    Note: This function now returns the private key object from the FileKeyBackend
    for compatibility with existing code that expects it. In a multi-backend
    scenario, this would typically return a key_id.
    """
    manager = get_active_key_manager()
    # For FileKeyBackend, generate_key_pair ensures the key exists and returns its ID.
    # We then retrieve the actual private key object for compatibility.
    key_id, _ = manager.generate_key_pair()
    # This is a temporary workaround to get the actual private key object
    # from FileKeyBackend, as other backends won't expose it.
    # Future refactoring will pass key_id instead of private_key objects.
    if isinstance(manager, FileKeyBackend):
        return manager._load_or_generate_keypair()
    raise NotImplementedError(
        "get_keypair() is only fully supported for FileKeyBackend in this transition phase."
    )


def get_public_key(private_key: PrivateKeyTypes | None = None) -> PublicKeyTypes:
    """Returns the public key from a private key or loads it from the active KeyManager."""
    manager = get_active_key_manager()
    if private_key:
        return private_key.public_key()
    # If no private_key is provided, assume we need the public key of the default key.
    key_id, _ = manager.generate_key_pair()  # Ensure default key exists
    return manager.get_public_key(key_id)


def get_public_key_fingerprint() -> str:
    """Returns the SHA256 fingerprint of the public key from the active KeyManager."""
    manager = get_active_key_manager()
    key_id, _ = manager.generate_key_pair()  # Ensure default key exists
    return manager.get_public_key_fingerprint(key_id)


def sign_bytes(data: bytes) -> bytes:
    """
    Signs a byte string using the active KeyManager.
    The data is first hashed before being passed to the KeyManager's sign_digest method.
    """
    manager = get_active_key_manager()
    key_id, _ = manager.generate_key_pair()  # Ensure default key exists

    # Hash the data before signing the digest
    hasher = hashes.Hash(hashes.SHA256())
    hasher.update(data)
    digest = hasher.finalize()

    return manager.sign_digest(key_id, digest)


def verify_signature(
    signature: bytes, data: bytes, public_key: PublicKeyTypes | None = None
) -> bool:
    """Verifies a signature against the data using the public key associated with key_id."""
    manager = get_active_key_manager()
    key_id, _ = manager.generate_key_pair()  # Ensure default key exists

    # Hash the data to create a digest for verification
    hasher = hashes.Hash(hashes.SHA256())
    hasher.update(data)
    digest = hasher.finalize()

    return manager.verify_signature(key_id, signature, digest)


def create_assertion(artifact_hash: str, signature_hex: str) -> str:
    """
    Creates a minimal, C2PA-like JSON assertion.
    This now includes key_id and key_backend_type from the active KeyManager.
    """
    manager = get_active_key_manager()
    key_id, _ = manager.generate_key_pair()  # Ensure default key exists
    assertion = {
        "alg": manager.get_algorithm(key_id),
        "hash": artifact_hash,
        "signature": signature_hex,
        "signer": manager.get_public_key_fingerprint(key_id),
        "key_id": key_id,
        "key_backend_type": manager.__class__.__name__.replace("KeyBackend", "").lower(),
    }
    # Using compact, sorted JSON for deterministic output.
    return json.dumps(assertion, sort_keys=True, separators=(",", ":"))
