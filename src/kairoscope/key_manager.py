from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes


class KeyManager(ABC):
    """
    Abstract Base Class for managing cryptographic keys.
    All key backends must implement this interface.
    """

    @abstractmethod
    def generate_key_pair(self, curve: str = "P384", label: str | None = None) -> tuple[str, str]:
        """
        Generates a new ECC key pair (P-384 by default) within the backend.
        Returns a tuple of (key_id, public_key_pem).
        The key_id is a unique identifier for the key within the backend.
        """
        pass

    @abstractmethod
    def get_public_key(self, key_id: str) -> PublicKeyTypes:
        """
        Retrieves the public key object for a given key identifier.
        """
        pass

    @abstractmethod
    def get_public_key_pem(self, key_id: str) -> str:
        """
        Retrieves the public key in PEM format for a given key identifier.
        """
        pass

    @abstractmethod
    def get_public_key_fingerprint(self, key_id: str) -> str:
        """
        Returns the SHA256 fingerprint of the public key for a given key_id.
        """
        pass

    @abstractmethod
    def sign_digest(self, key_id: str, digest: bytes) -> bytes:
        """
        Signs a pre-hashed digest (e.g., SHA256 of artifact content)
        using the private key associated with key_id.
        The private key must remain within the backend.
        """
        pass

    @abstractmethod
    def verify_signature(self, key_id: str, signature: bytes, digest: bytes) -> bool:
        """
        Verifies a signature against the digest using the public key associated with key_id.
        """
        pass

    @abstractmethod
    def get_algorithm(self, key_id: str) -> str:
        """
        Returns the signing algorithm used by the key (e.g., "ES384").
        """
        pass

    @abstractmethod
    def list_keys(self) -> list[dict[str, str]]:
        """
        Lists available keys managed by this backend, returning a list of dictionaries
        with key details (e.g., {'id': '...', 'label': '...', 'type': 'ECC', 'backend': '...'}).
        """
        pass

    @abstractmethod
    def delete_key(self, key_id: str) -> None:
        """
        Deletes a key from the backend.
        """
        pass


KEY_PASSWORD = None  # For simplicity in v0.1; use env var or KMS in production.


class FileKeyBackend(KeyManager):
    """
    KeyManager implementation for file-based key storage using cryptography library.
    """

    def __init__(self, key_dir: Path | None = None):
        self.key_dir = key_dir if key_dir is not None else Path.cwd()
        self._private_key: PrivateKeyTypes | None = None
        self._public_key: PublicKeyTypes | None = None
        self._key_id: str | None = None  # The fingerprint of the managed key

    def _get_private_key_path(self) -> Path:
        return self.key_dir / "kairoscope.key"

    def _get_public_key_path(self) -> Path:
        return self.key_dir / "kairoscope.pub"

    def _load_or_generate_keypair(self) -> PrivateKeyTypes:
        """
        Loads an existing private key or generates a new one.
        Sets self._key_id to the fingerprint of the loaded/generated key.
        """
        if self._private_key:
            return self._private_key

        private_key_path = self._get_private_key_path()
        public_key_path = self._get_public_key_path()

        if private_key_path.exists():
            with open(private_key_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(), password=KEY_PASSWORD
                )
        else:
            # Using ECC for smaller key sizes and good performance.
            self._private_key = ec.generate_private_key(ec.SECP384R1())
            pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            with open(private_key_path, "wb") as f:
                f.write(pem)

            # Also save public key for convenience
            public_pem = self._private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            with open(public_key_path, "wb") as f:
                f.write(public_pem)

        # Set the key_id after loading/generating the key
        self._key_id = self._calculate_fingerprint_from_public_key(self._private_key.public_key())
        return self._private_key

    def _calculate_fingerprint_from_public_key(self, public_key: PublicKeyTypes) -> str:
        """Helper to calculate fingerprint from a public key object."""
        der_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashes.Hash(hashes.SHA256())
        digest.update(der_bytes)
        return f"sha256:{digest.finalize().hex()}"

    def generate_key_pair(self, curve: str = "P384", label: str | None = None) -> tuple[str, str]:
        # For FileKeyBackend, we only manage one key pair for now.
        # This method will ensure it exists and return its details.
        self._load_or_generate_keypair()  # Ensure key is loaded/generated and _key_id is set
        if self._key_id is None:
            raise RuntimeError("Key ID not set after loading/generating key pair.")
        key_id = self._key_id
        public_key_pem = self.get_public_key_pem(key_id)
        return key_id, public_key_pem

    def get_public_key(self, key_id: str) -> PublicKeyTypes:
        private_key = self._load_or_generate_keypair()
        if self._key_id != key_id:
            raise ValueError(f"Key with ID {key_id} not managed by this FileKeyBackend instance.")
        return private_key.public_key()

    def get_public_key_pem(self, key_id: str) -> str:
        public_key = self.get_public_key(key_id)
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def get_public_key_fingerprint(self, key_id: str) -> str:
        # For FileKeyBackend, the key_id IS the fingerprint
        if self._key_id != key_id:
            raise ValueError(f"Key with ID {key_id} not managed by this FileKeyBackend instance.")
        return self._key_id

    def sign_digest(self, key_id: str, digest: bytes) -> bytes:
        private_key = self._load_or_generate_keypair()
        if self._key_id != key_id:
            raise ValueError(f"Key with ID {key_id} not managed by this FileKeyBackend instance.")
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            return private_key.sign(digest, ec.ECDSA(hashes.SHA256()))
        elif isinstance(private_key, rsa.RSAPrivateKey):
            return private_key.sign(
                digest,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        raise TypeError("Unsupported private key type for signing")

    def verify_signature(self, key_id: str, signature: bytes, digest: bytes) -> bool:
        public_key = self.get_public_key(key_id)
        try:
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(signature, digest, ec.ECDSA(hashes.SHA256()))
            elif isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(
                    signature,
                    digest,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256(),
                )
            else:
                return False
            return True
        except Exception:
            return False

    def get_algorithm(self, key_id: str) -> str:
        private_key = self._load_or_generate_keypair()
        if self._key_id != key_id:
            raise ValueError(f"Key with ID {key_id} not managed by this FileKeyBackend instance.")
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            return "ES384"  # Assuming P384 for ECC
        elif isinstance(private_key, rsa.RSAPrivateKey):
            return "PS256"  # Assuming RSA PSS with SHA256
        return "UNKNOWN"

    def list_keys(self) -> list[dict[str, str]]:
        private_key_path = self._get_private_key_path()
        if private_key_path.exists():
            self._load_or_generate_keypair()  # Ensure key is loaded/generated and _key_id is set
            if self._key_id is None:
                raise RuntimeError("Key ID not set after loading/generating key pair.")
            key_id = self._key_id
            return [
                {
                    "id": key_id,
                    "label": "default-file-key",
                    "type": "ECC",  # Assuming ECC for now
                    "backend": "file",
                    "public_key_pem": self.get_public_key_pem(key_id),
                }
            ]
        return []

    def delete_key(self, key_id: str) -> None:
        # For FileKeyBackend, we only manage one key pair.
        # This method will delete the key files if the key_id matches.
        if self._key_id != key_id:
            raise ValueError(f"Key with ID {key_id} not managed by this FileKeyBackend instance.")

        private_key_path = self._get_private_key_path()
        public_key_path = self._get_public_key_path()
        if private_key_path.exists():
            private_key_path.unlink()
        if public_key_path.exists():
            public_key_path.unlink()
        self._private_key = None
        self._public_key = None
        self._key_id = None
