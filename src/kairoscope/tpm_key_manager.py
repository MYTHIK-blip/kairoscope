from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from tpm2_pytss.constants import (
    TPM2_ALG,
    TPM2_HT,
    TPM2_RC,
    TPM2_RH,
    TPM2_ST,
)

# Import tpm2_pytss components
from tpm2_pytss.ESAPI import ESAPI
from tpm2_pytss.exceptions import TPM2_Exception

from kairoscope.key_manager import KeyManager


class TpmKeyBackend(KeyManager):
    """
    KeyManager implementation for TPM-backed key storage using tpm2-pytss.
    """

    def __init__(self, tcti_name: str = "tabrmd"):
        self.tcti_name = tcti_name
        self._esapi: ESAPI | None = None
        self._connect_esapi()

    def _connect_esapi(self):
        """Establishes a connection to the TPM."""
        if self._esapi is None:
            try:
                self._esapi = ESAPI(self.tcti_name)
            except TPM2_Exception as e:
                raise RuntimeError(
                    f"Failed to connect to TPM using TCTI '{self.tcti_name}': {e}"
                ) from e

    def _get_esapi(self) -> ESAPI:
        """Returns the connected TPM instance, ensuring it's connected."""
        if self._esapi is None:
            self._connect_esapi()
        if self._esapi is None:  # Should not happen if _connect_esapi raises on failure
            raise RuntimeError("TPM connection not established.")
        return self._esapi

    def _calculate_fingerprint_from_public_key(self, public_key_pem: bytes) -> str:
        """Helper to calculate SHA256 fingerprint from a public key PEM."""
        public_key = serialization.load_pem_public_key(public_key_pem)
        der_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashes.Hash(hashes.SHA256())
        digest.update(der_bytes)
        return f"sha256:{digest.finalize().hex()}"

    def generate_key_pair(self, curve: str = "P384", label: str | None = None) -> tuple[str, str]:
        esapi = self._get_esapi()

        # Define key parameters for ECC P384
        in_sensitive = esapi.TPM2B_SENSITIVE_CREATE(
            userAuth=b"",
            data=b"",
        )
        in_public = esapi.TPM2B_PUBLIC(
            type=TPM2_ALG.ECC,
            nameAlg=TPM2_ALG.SHA256,
            objectAttributes=(
                esapi.TPMA_OBJECT.FIXEDTPM
                | esapi.TPMA_OBJECT.FIXEDPARENT
                | esapi.TPMA_OBJECT.SENSITIVEDATAORIGIN
                | esapi.TPMA_OBJECT.USERWITHAUTH
                | esapi.TPMA_OBJECT.SIGN
                | esapi.TPMA_OBJECT.NOCPDA
            ),
            parameters=esapi.TPMS_ECC_PARMS(
                scheme=esapi.TPMS_SIG_SCHEME_ECDSA(hashAlg=TPM2_ALG.SHA256),
                curveID=TPM2_ALG.ECC_NIST_P384,  # Use P384 curve
                kdf=esapi.TPMS_KDF_SCHEME_NULL(),
            ),
            unique=esapi.TPMS_ECC_POINT(),
        )

        # Create the key in the TPM
        try:
            create_result = esapi.create(
                parentHandle=TPM2_RH.OWNER,
                inSensitive=in_sensitive,
                inPublic=in_public,
                outsideInfo=b"",
                creationPCR=esapi.TPM2B_PCR_SELECTION(),
            )
            private_handle = esapi.load(
                parentHandle=TPM2_RH.OWNER,
                inPrivate=create_result.outPrivate,
                inPublic=create_result.outPublic,
            )

            # Make the key persistent
            persistent_handle = esapi.evictcontrol(
                auth=TPM2_RH.OWNER,
                objectHandle=private_handle.handle,
                persistentHandle=TPM2_HT.PERSISTENT
                | 0x00000001,  # Use a fixed persistent handle for now
            ).persistentHandle

            # Read the public part of the key
            read_pub_result = esapi.readpublic(objectHandle=persistent_handle)
            public_key_pem = read_pub_result.outPublic.to_pem()
            key_id = self._calculate_fingerprint_from_public_key(public_key_pem)

            # Store the key_id and persistent handle mapping (e.g., in a simple dict or config file)
            # For now, we'll just return the key_id and PEM.
            # In a real scenario, you'd manage persistent handles and their associated key_ids.

            return key_id, public_key_pem.decode("utf-8")

        except TPM2_Exception as e:
            raise RuntimeError(f"Failed to generate TPM key pair: {e}") from e

    def get_public_key(self, key_id: str) -> PublicKeyTypes:
        esapi = self._get_esapi()
        # This is a simplified approach. In a real system, you'd map key_id to persistent handle.
        # For now, we assume the key_id corresponds to a known persistent handle.
        # We'll use the fixed handle used in generate_key_pair for demonstration.
        persistent_handle = TPM2_HT.PERSISTENT | 0x00000001

        try:
            read_pub_result = esapi.readpublic(objectHandle=persistent_handle)
            public_key_pem = read_pub_result.outPublic.to_pem()

            # Verify that the key_id matches the fingerprint of the retrieved public key
            if self._calculate_fingerprint_from_public_key(public_key_pem) != key_id:
                raise ValueError(f"Key ID mismatch for persistent handle {persistent_handle}")

            return serialization.load_pem_public_key(public_key_pem)
        except TPM2_Exception as e:
            raise RuntimeError(f"Failed to retrieve public key from TPM: {e}") from e

    def get_public_key_pem(self, key_id: str) -> str:
        esapi = self._get_esapi()
        persistent_handle = TPM2_HT.PERSISTENT | 0x00000001

        try:
            read_pub_result = esapi.readpublic(objectHandle=persistent_handle)
            public_key_pem = read_pub_result.outPublic.to_pem()

            if self._calculate_fingerprint_from_public_key(public_key_pem) != key_id:
                raise ValueError(f"Key ID mismatch for persistent handle {persistent_handle}")

            return public_key_pem.decode("utf-8")
        except TPM2_Exception as e:
            raise RuntimeError(f"Failed to retrieve public key PEM from TPM: {e}") from e

    def get_public_key_fingerprint(self, key_id: str) -> str:
        # For TPM keys, the key_id is the fingerprint
        # We should verify that the key exists and its fingerprint matches
        self.get_public_key(key_id)  # This will raise an error if key_id is not found or mismatched
        return key_id

    def sign_digest(self, key_id: str, digest: bytes) -> bytes:
        esapi = self._get_esapi()
        persistent_handle = TPM2_HT.PERSISTENT | 0x00000001

        # Load the persistent key into the transient area for signing
        try:
            load_result = esapi.load(
                parentHandle=TPM2_RH.OWNER,
                inPrivate=esapi.TPM2B_PRIVATE(),  # Not needed for persistent key
                inPublic=esapi.readpublic(objectHandle=persistent_handle).outPublic,
            )
            key_handle = load_result.handle

            # Sign the digest
            sign_result = esapi.sign(
                keyHandle=key_handle,
                digest=esapi.TPM2B_DIGEST(digest),
                inScheme=esapi.TPMT_SIG_SCHEME(
                    scheme=TPM2_ALG.ECDSA, details=esapi.TPMU_SIG_SCHEME(hashAlg=TPM2_ALG.SHA256)
                ),
                validation=esapi.TPMT_TK_HASHCHECK(
                    tag=TPM2_ST.HASHCHECK, hierarchy=TPM2_RH.NULL, digest=b""
                ),
            )

            # Unload the key from transient area
            esapi.flushcontext(flushHandle=key_handle)

            # Convert the signature to a format compatible with cryptography library (ASN.1 DER)
            # tpm2-pytss returns r and s components. We need to encode them.
            r = sign_result.signature.signature.signatureR.buffer
            s = sign_result.signature.signature.signatureS.buffer

            # Pad r and s with leading zeros if necessary to match expected length (P384 is 48 bytes)
            # This is a simplification; proper ASN.1 DER encoding should be used.
            # For now, assuming fixed length for P384 (48 bytes for r and s)
            # r_padded = r.rjust(48, b"\x00")
            # s_padded = s.rjust(48, b"\x00")

            # This is a very basic attempt at DER encoding for ECDSA.
            # A more robust solution would use a dedicated ASN.1 library or cryptography's internal methods.
            # For P384, r and s are 48 bytes.
            # Sequence header: 0x30
            # Length of sequence: (length of r_int + length of s_int + 4 bytes for type/length of each)
            # Integer type: 0x02
            # Length of integer: length of r_int
            # r_int bytes
            # Integer type: 0x02
            # Length of integer: length of s_int
            # s_int bytes

            # Example for P384 (48 bytes for r and s)
            # r_len = len(r_padded)
            # s_len = len(s_padded)
            # total_len = r_len + s_len + 4 # 2 for type, 2 for length
            # der_signature = b'\x30' + total_len.to_bytes(1, 'big') + \
            #                 b'\x02' + r_len.to_bytes(1, 'big') + r_padded + \
            #                 b'\x02' + s_len.to_bytes(1, 'big') + s_padded

            # For now, return a concatenated r and s, which `cryptography` might not directly accept for verification
            # This will need proper ASN.1 DER encoding for compatibility with `cryptography`'s verify method.
            # For testing purposes, we might need to adjust the verify_signature method in FileKeyBackend
            # or implement a TPM-specific verification.

            # For now, returning raw r and s concatenated. This will likely fail cryptography's verification.
            # TODO: Implement proper ASN.1 DER encoding for ECDSA signature.
            return r + s

        except TPM2_Exception as e:
            raise RuntimeError(f"Failed to sign digest with TPM: {e}") from e

    def verify_signature(self, key_id: str, signature: bytes, digest: bytes) -> bool:
        # For TPM-generated signatures, verification can be done using the public key
        # and the cryptography library, provided the signature format is compatible (ASN.1 DER).
        # Since sign_digest currently returns concatenated r+s, this will likely fail.
        # TODO: Adjust this once sign_digest returns proper DER.
        public_key = self.get_public_key(key_id)

        # Assuming signature is r + s concatenation for now, need to split and re-encode for cryptography
        # This is a placeholder and will need to be updated once sign_digest produces DER.
        # For P384, r and s are 48 bytes each.
        r = signature[:48]
        s = signature[48:]

        # Re-encode r and s into ASN.1 DER for cryptography's verify method
        # This is a simplified encoding and might not be fully compliant for all cases.
        # A proper ASN.1 DER encoder should be used.
        try:
            from cryptography.hazmat.primitives.asymmetric import utils
            from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

            if isinstance(public_key, EllipticCurvePublicKey):
                # Convert r and s to integers
                r_int = int.from_bytes(r, "big")
                s_int = int.from_bytes(s, "big")

                # Create an ECDSA signature object
                ecdsa_signature = utils.encode_dss_signature(r_int, s_int)

                public_key.verify(ecdsa_signature, digest, ec.ECDSA(hashes.SHA256()))
                return True
            else:
                return False
        except Exception:
            return False

    def get_algorithm(self, key_id: str) -> str:
        # Assuming P384 ECC for now
        self.get_public_key(key_id)  # Ensure key exists
        return "ES384"

    def list_keys(self) -> list[dict[str, str]]:
        esapi = self._get_esapi()
        keys = []
        # This is a simplified listing. In a real system, you'd iterate through
        # persistent handles or a managed list of keys.
        # For now, we check if our fixed persistent handle exists.
        persistent_handle = TPM2_HT.PERSISTENT | 0x00000001
        try:
            read_pub_result = esapi.readpublic(objectHandle=persistent_handle)
            public_key_pem = read_pub_result.outPublic.to_pem()
            key_id = self._calculate_fingerprint_from_public_key(public_key_pem)
            keys.append(
                {
                    "id": key_id,
                    "label": "default-tpm-key",
                    "type": "ECC",
                    "backend": "tpm",
                    "public_key_pem": public_key_pem.decode("utf-8"),
                }
            )
        except TPM2_Exception as e:
            if e.rc == TPM2_RC.HANDLE:  # Handle not found
                pass
            else:
                raise RuntimeError(f"Failed to list TPM keys: {e}") from e
        return keys

    def delete_key(self, key_id: str) -> None:
        esapi = self._get_esapi()
        persistent_handle = TPM2_HT.PERSISTENT | 0x00000001

        # Verify key_id before deleting
        if (
            self._calculate_fingerprint_from_public_key(self.get_public_key_pem(key_id).encode())
            != key_id
        ):
            raise ValueError(f"Key ID mismatch for persistent handle {persistent_handle}")

        try:
            esapi.evictcontrol(
                auth=TPM2_RH.OWNER,
                objectHandle=persistent_handle,
                persistentHandle=TPM2_RH.NULL,  # Evict the persistent handle
            )
        except TPM2_Exception as e:
            if e.rc == TPM2_RC.HANDLE:  # Key not found, already deleted
                pass
            else:
                raise RuntimeError(f"Failed to delete TPM key: {e}") from e
