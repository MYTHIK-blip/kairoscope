import hashlib
import json
from pathlib import Path


def generate_slsa_attestation(artifact_path: Path, output_path: Path, predicate: dict) -> None:
    """
    Generates a SLSA attestation for the given artifact path.
    """
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    attestation_content = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "subject": [{"name": artifact_path.name, "digest": {"sha256": artifact_hash}}],
        "predicate": predicate,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(attestation_content, f, indent=2)
