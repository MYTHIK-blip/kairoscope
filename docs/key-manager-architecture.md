# Key Manager Architectural Design for Kairoscope

**Date:** 2025-11-29

## 1. Overview
-   **Context:** To enhance Kairoscope's security and flexibility, particularly for industry and civic use cases, there is a critical need to move beyond simple file-based key storage to support hardware-backed keystores.
-   **Goal:** Implement a pluggable `KeyManager` interface that abstracts cryptographic key operations, allowing Kairoscope to seamlessly integrate various key storage backends (e.g., file, TPM, PKCS#11, Secure Enclave).
-   **Current Status:** The `KeyManager` Abstract Base Class and the `FileKeyBackend` implementation have been completed, refactoring the existing file-based key management.
-   **Benefits:**
    -   **Enhanced Security:** Private keys can be generated and stored in hardware, making them non-extractable and resistant to software attacks.
    -   **Flexibility:** Users can choose the key backend that best suits their security requirements and operational environment.
    -   **Testability:** Easier to mock key operations for testing purposes.
    -   **Future-Proofing:** Simplifies integration of new key technologies.

## 2. Core `KeyManager` Interface (Abstract Base Class)

A new Abstract Base Class (ABC) named `KeyManager` will be defined. All concrete key backend implementations must inherit from this ABC and implement its methods.

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Union
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes

class KeyManager(ABC):
    """
    Abstract Base Class for managing cryptographic keys.
    All key backends must implement this interface.
    """

    @abstractmethod
    def generate_key_pair(self, curve: str = "P384", label: str = None) -> Tuple[str, str]:
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
        Returns the SHA256 fingerprint of the public key, used as the agent ID.
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
    def verify_signature(self, key_id: str, signature: bytes, data: bytes) -> bool:
        """
        Verifies a signature against the data using the public key associated with key_id.
        """
        pass

    @abstractmethod
    def get_algorithm(self, key_id: str) -> str:
        """
        Returns the signing algorithm used by the key (e.g., "ES384").
        """
        pass

    @abstractmethod
    def list_keys(self) -> List[Dict[str, str]]:
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
```

## 3. Concrete Backend Implementations

### 3.1. `FileKeyBackend` (Adapting Existing Logic)
-   **Description:** This backend will encapsulate the current file-based key management logic found in `provenance.py`.
-   **Key Storage:** Keys are stored as PEM files (`kairoscope.key`, `kairoscope.pub`) in the filesystem.
-   **`key_id`:** Could be a simple label (e.g., "default-file-key") or derived from the public key fingerprint.
-   **Dependencies:** `cryptography`.

### 3.2. `TPMKeyBackend` (using `tpm2-pytss`)
-   **Description:** Integrates with a TPM 2.0 module for hardware-backed key operations.
-   **`generate_key_pair`:** Uses `tpm2-pytss` to create ECC P-384 keys within the TPM. The `key_id` would be a persistent TPM handle or a unique identifier assigned by the backend.
-   **`sign_digest`:** Delegates to `tpm2-pytss`'s `ESAPI.sign()` method, ensuring the private key never leaves the TPM.
-   **`get_public_key`:** Retrieves the public key from the TPM.
-   **Configuration:** Requires access to the TPM device (e.g., `/dev/tpmrm0`).
-   **Dependencies:** `tpm2-pytss`.

### 3.3. `PKCS11KeyBackend` (using `python-pkcs11`)
-   **Description:** Integrates with any PKCS#11 compliant device (e.g., HSMs, smart cards, SoftHSMv2).
-   **`generate_key_pair`:** Uses `python-pkcs11` to create ECC P-384 keys on the PKCS#11 token. The `key_id` could be the key's `CKA_LABEL` or `CKA_ID`.
-   **`sign_digest`:** Delegates to the PKCS#11 private key object's `sign()` method.
-   **`get_public_key`:** Retrieves the public key from the token.
-   **Configuration:** Requires path to the PKCS#11 library, token label, and user PIN.
-   **Dependencies:** `python-pkcs11`.

### 3.4. `OSKeyringBackend` (using `keyring` - Optional Fallback)
-   **Description:** Provides a software-backed key storage using the operating system's native keyring service.
-   **`generate_key_pair`:** Generates keys using `cryptography` and stores them encrypted in the OS keyring.
-   **Trade-offs:** Offers better protection than plain files but lacks hardware isolation. Suitable for less critical keys or as a user-friendly fallback.
-   **Dependencies:** `keyring`, `cryptography`.

## 4. Refactoring `provenance.py`

The `provenance.py` module will be refactored to become the orchestrator of key operations, delegating to an instance of the chosen `KeyManager` backend.

-   The module will no longer directly handle key file I/O or `cryptography` key generation/loading.
-   It will maintain a reference to the currently active `KeyManager` instance.
-   Functions like `get_keypair()`, `sign_bytes()`, `get_public_key_fingerprint()`, and `create_assertion()` will be updated to call the corresponding methods on the active `KeyManager` instance.

## 5. Integration with `cli.py`

The Command-Line Interface (`cli.py`) will be extended to allow users to manage and select key backends.

-   **New CLI Group:** A new `kairoscope key` command group will be introduced.
    -   `kairoscope key generate --backend <type> --label <name> [--curve P384]`: Generates a new key pair using the specified backend and assigns a label.
    -   `kairoscope key list`: Lists all keys managed by all configured backends, showing their `key_id`, `label`, `type`, and `backend`.
    -   `kairoscope key set-default <key_id>`: Sets a specific key as the default for signing operations. This default will be stored in a configuration file (e.g., `policy.yaml` or a new `config.yaml`).
    -   `kairoscope key delete <key_id>`: Deletes a key from its backend.
-   **Existing Commands:**
    -   `kairoscope sign <artifact_hash> [--key-id <id>]`: The `sign` command will use the default key if `--key-id` is not provided.
    -   `kairoscope capture`: Will not directly interact with keys, but the subsequent `sign` operation will use the configured key.

## 6. Impact on Provenance Data

-   The `create_assertion` function will be updated to include additional metadata within the C2PA-like assertion:
    -   `key_id`: The unique identifier of the key used for signing.
    -   `key_backend_type`: The type of key backend used (e.g., "file", "tpm", "pkcs11").
    -   This metadata enhances the verifiability of the assertion by providing context about the key's origin and protection level.

## 7. Error Handling and Fallbacks

-   Robust error handling will be implemented for scenarios where a chosen backend is unavailable, misconfigured, or fails during a cryptographic operation.
-   The `FileKeyBackend` will serve as a default fallback if no hardware backend is configured or available, ensuring basic functionality while clearly indicating the lower security posture.
-   Clear error messages will guide users on how to resolve issues with key backends.
