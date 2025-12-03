# Hardware Keystores Surface Scan for Kairoscope Integration

**Date:** 2025-11-29

## 1. TPM 2.0 (Trusted Platform Module)
-   **Python Bindings:** `tpm2-pytss` (official Python wrapper for `tpm2-tss` stack).
-   **Capabilities:** Supports ECC key generation, signing, and secure storage (sealing) of keys. Keys can be bound to specific platform configurations.
-   **Notes:** Requires explicit scheme setup for ECDSA. ECC curve support is device-dependent and needs verification for P-384.

## 2. HSMs (Hardware Security Modules - PKCS#11)
-   **Python Wrappers:** `python-pkcs11`, `py-hsm`. These libraries provide interfaces to devices supporting the PKCS#11 standard.
-   **Supported Operations:** Comprehensive support for various cryptographic operations including RSA, ECDSA key generation, signing, and key rotation.
-   **Cloud Integration:** Cloud HSM services (e.g., AWS CloudHSM, Azure Key Vault) often expose a PKCS#11 interface, allowing for integration via these modules.

## 3. Secure Enclaves (e.g., Intel SGX, ARM TrustZone)
-   **SDKs/APIs:** Open Enclave SDK, Gramine, SCONE. Python support is typically via FFI (Foreign Function Interface) or specific SDKs.
-   **Use Cases:** Provide a trusted execution environment for sensitive code and data, enabling attestation, secure storage, and enclave-protected signing.
-   **Limitations:** High operational complexity, significant development overhead, and runtime support for Python within enclaves can be challenging.

## 4. OS-level Keyrings (e.g., macOS Keychain, Windows Credential Locker, Linux Secret Service)
-   **Library:** Python `keyring` library provides a cross-platform interface.
-   **Platforms:** Integrates with native OS credential stores.
-   **Trade-offs:** Software-backed, meaning keys are protected by OS mechanisms but not by dedicated hardware isolation. Suitable for general secrets management but does not offer the same hardware-grade protection as TPMs or HSMs. Can serve as a fallback or for less critical keys.

## 5. Key Management Operations
-   **Hardware-bound Private Keys:** A critical feature is the ability to generate and use private keys that are non-extractable from the hardware.
-   **Signing:** The hardware performs the signing operation internally, returning only the digital signature to the application, never exposing the private key.
-   **Public Key Retrieval:** Standard and generally straightforward across all options.
-   **Rotation/Revocation:** Mechanisms are often vendor-specific or require careful implementation at the application layer, especially for hardware-bound keys.
-   **ECC Curve Support:** Deep research is required to confirm explicit support for P-384 (used for ES384 signatures) within chosen hardware/libraries.

## 6. Security Guarantees
-   **TPM/HSM:** Offer strong hardware isolation, protecting keys from software attacks and often from physical tampering. Provide hardware-rooted trust.
-   **Secure Enclaves:** Offer runtime protection for code and data, ensuring confidentiality and integrity even on a compromised host OS. Support remote attestation.
-   **OS Keyrings:** Rely on the security of the underlying operating system. Keys are encrypted at rest but can be vulnerable if the OS is compromised.

## 7. Architectural Impact
-   **Proposal:** Implement a `KeyManager` interface within Kairoscope's `provenance.py` module. This interface would allow for pluggable backends (e.g., `FileKeyBackend`, `TPMKeyBackend`, `PKCS11KeyBackend`, `EnclaveKeyBackend`).
-   **CLI Changes:** The `cli.py` would need modifications to allow users to select and manage the active key backend (e.g., `kairoscope keygen --backend tpm`).
-   **Provenance:** Metadata about the key backend used for signing should be included in the C2PA-like assertions to enhance the verifiability of the provenance chain.

## 8. Deployment & Compatibility
-   **Linux:** Generally offers the strongest support for TPM, PKCS#11 (via various drivers), and Intel SGX.
-   **Windows/macOS:** PKCS#11 modules are available. Windows has TPM support, but Python integration might require specific libraries. macOS has Secure Enclave, but direct Python access is limited, often requiring native code wrappers.
-   **Mobile:** ARM TrustZone variants are common, but Python integration is complex. Fallback to OS-level software keystores (e.g., Android Keystore) is more feasible.
-   **Air-gapped Builds:** Prefer on-device TPM/HSM solutions. Cloud HSMs are not suitable for air-gapped environments.
-   **Fallback:** An OS keyring or the existing file-based keystore should remain as a fallback option, with clear risk labeling for users.
