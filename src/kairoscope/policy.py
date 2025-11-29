from collections import defaultdict
from pathlib import Path

import jsonschema
import yaml

from kairoscope.db import get_all_events
from kairoscope.provenance import get_public_key, verify_signature

ONTOLOGY_SCHEMA_FILE = Path(__file__).parent.parent.parent / "ontology" / "kairoscope.schema.yaml"


def get_policy_file() -> Path:
    return Path.cwd() / "policy.yaml"


def load_policy_config() -> dict:
    """Loads the policy configuration from policy.yaml and validates it against the schema."""
    policy_file = get_policy_file()
    if not policy_file.exists():
        # Return a default policy if the file doesn't exist
        default_policy = {
            "governance_model": "Custom",
            "controls": ["Default control: Ensure all artifacts are signed before export"],
            "existential_rules": [{"name": "default_export_policy", "min_witnesses": 1}],
            "universal_rules": [],
            "threshold_rules": [],
        }
        # Validate default policy against schema
        with open(ONTOLOGY_SCHEMA_FILE) as f:
            schema = yaml.safe_load(f)
        jsonschema.validate(instance=default_policy, schema=schema["properties"]["Policy"])
        return default_policy

    with open(policy_file) as f:
        policy_config = yaml.safe_load(f)

    # Validate loaded policy against schema
    with open(ONTOLOGY_SCHEMA_FILE) as f:
        schema = yaml.safe_load(f)
    jsonschema.validate(instance=policy_config, schema=schema["properties"]["Policy"])

    return policy_config


def check_existential_rule(artifact_hashes: list[str], rule: dict, db_path: Path) -> bool:
    """
    Enforces the existential rule: export is permitted only if >= min_witnesses valid signatures
    exist for each artifact in the provided set.
    """
    min_witnesses = rule.get("min_witnesses", 1)
    public_key = get_public_key()
    events = get_all_events(db_path)

    artifact_signatures_count: defaultdict[str, int] = defaultdict(int)

    for event in events:
        if event.get("action") == "sign":
            artifact_hash = event.get("artifact_hash")
            artifact_signature_hex = event.get("artifact_signature")
            if artifact_hash and artifact_signature_hex:
                artifact_signature = bytes.fromhex(artifact_signature_hex)
                is_valid = verify_signature(
                    artifact_signature, artifact_hash.encode("utf-8"), public_key
                )
                if is_valid:
                    artifact_signatures_count[artifact_hash] += 1

    for h in artifact_hashes:
        if artifact_signatures_count[h] < min_witnesses:
            return False
    return True


def check_universal_rule(artifact_hashes: list[str], rule: dict, db_path: Path) -> bool:
    """
    Enforces the Universal rule: all specified validators must pass for each artifact.
    For now, focuses on 'signature' and 'ledger' (absence of refutation).
    """
    required_validators = rule.get("required_validators", [])
    public_key = get_public_key()
    events = get_all_events(db_path)

    # Collect valid signatures for each artifact
    signed_artifacts = set()
    for event in events:
        if event.get("action") == "sign":
            artifact_hash = event.get("artifact_hash")
            artifact_signature_hex = event.get("artifact_signature")
            if artifact_hash and artifact_signature_hex:
                artifact_signature = bytes.fromhex(artifact_signature_hex)
                is_valid = verify_signature(
                    artifact_signature, artifact_hash.encode("utf-8"), public_key
                )
                if is_valid:
                    signed_artifacts.add(artifact_hash)

    for h in artifact_hashes:
        if "signature" in required_validators and h not in signed_artifacts:
            return False
        # Placeholder for 'ledger' (absence of refutation)
        # For now, assume no refutation events exist.
        # Future: check for 'refute' events for this artifact_hash
        if "ledger" in required_validators:
            # For the purpose of this test, if 'ledger' is required and no refutation logic is implemented,
            # we consider it as not met, causing the universal rule to fail.
            # A proper implementation would check for actual ledger validation/refutation events.
            return False

    return True


def check_threshold_rule(artifact_hashes: list[str], rule: dict, db_path: Path) -> bool:
    """
    Enforces the Threshold rule: requires k out of n attestations from specified attestors.
    """
    k = rule.get("k")
    n = rule.get("n")
    attestors = rule.get("attestors", [])

    if k is None or n is None or not attestors:
        # Rule is malformed or incomplete, treat as failure
        return False

    public_key = get_public_key()  # Assuming a single public key for verification for now
    events = get_all_events(db_path)

    artifact_attestations_count: defaultdict[str, defaultdict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )  # artifact_hash -> attestor_id -> count

    for event in events:
        if event.get("action") == "sign":
            artifact_hash = event.get("artifact_hash")
            attestor_id = event.get("by")  # 'by' field stores the public key fingerprint
            artifact_signature_hex = event.get("artifact_signature")

            if (
                artifact_hash
                and attestor_id
                and isinstance(attestor_id, str)
                and attestor_id in attestors
                and artifact_signature_hex
            ):
                artifact_signature = bytes.fromhex(artifact_signature_hex)
                is_valid = verify_signature(
                    artifact_signature, artifact_hash.encode("utf-8"), public_key
                )
                if is_valid:
                    artifact_attestations_count[artifact_hash][attestor_id] += 1

    for h in artifact_hashes:
        valid_attestations_for_artifact = 0
        for attestor_id_raw in attestors:
            if attestor_id_raw is None:
                continue
            attestor_id_str: str = str(attestor_id_raw)
            if (
                artifact_attestations_count[h][attestor_id_str] > 0
            ):  # Count each attestor once per artifact
                valid_attestations_for_artifact += 1

        if valid_attestations_for_artifact < k:
            return False
    return True


def can_export(artifact_hashes: list[str], db_path: Path) -> bool:
    """
    Determines if export is permitted based on the loaded policy configuration.
    All enabled rules (existential, universal, threshold) must pass.
    """
    policy_config = load_policy_config()

    # Check Existential Rules
    for rule in policy_config.get("existential_rules", []):
        if not check_existential_rule(artifact_hashes, rule, db_path):
            return False

    # Check Universal Rules
    for rule in policy_config.get("universal_rules", []):
        if not check_universal_rule(artifact_hashes, rule, db_path):
            return False

    # Check Threshold Rules
    for rule in policy_config.get("threshold_rules", []):
        if not check_threshold_rule(artifact_hashes, rule, db_path):
            return False

    return True
