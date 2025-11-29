import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kairoscope.cli import cli
from kairoscope.db import get_all_events, initialize_db, insert_event
from kairoscope.policy import get_policy_file
from kairoscope.provenance import get_public_key_fingerprint


# Mock timestamp for deterministic ledger entries
@pytest.fixture(autouse=True)
def mock_timestamp():
    with patch("kairoscope.cli._get_timestamp", return_value="2025-09-21T12:00:00.000Z"):
        yield


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    # Change the current working directory to a temporary one for each test
    # This ensures that artifacts/, dist/, kairoscope.key, etc., are created in isolation
    original_cwd = Path.cwd()
    Path.cwd = lambda: tmp_path

    # Set the KAIROSCOPE_DB_PATH environment variable for the test
    db_path = tmp_path / "test_kairoscope.db"
    os.environ["KAIROSCOPE_DB_PATH"] = str(db_path)

    # Ensure directories are created for the test run
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    (tmp_path / "dist").mkdir(exist_ok=True)

    initialize_db(db_path)  # Initialize the database with the temporary path
    yield db_path  # Yield db_path so tests can use it

    # Clean up the database file and environment variable after each test
    if db_path.exists():
        db_path.unlink()
    del os.environ["KAIROSCOPE_DB_PATH"]

    # Restore original cwd after test
    Path.cwd = lambda: original_cwd


def _capture_and_sign_artifact(
    runner: CliRunner, tmp_path: Path, content: bytes, db_path: Path
) -> str:
    test_file_path = tmp_path / "test_input.txt"
    test_file_path.write_bytes(content)

    runner.invoke(cli, ["capture", str(test_file_path)])
    content_hash = hashlib.sha256(content).hexdigest()
    runner.invoke(cli, ["sign", content_hash])
    return content_hash


def test_export_command_blocked_by_policy(
    runner: CliRunner, tmp_path: Path, setup_test_environment: Path
):
    db_path = setup_test_environment
    test_file_content = b"Unauthorized content."
    test_file_path = tmp_path / "unauthorized.txt"
    test_file_path.write_bytes(test_file_content)

    # Capture the artifact, but DO NOT sign it
    result_capture = runner.invoke(cli, ["capture", str(test_file_path)])
    assert result_capture.exit_code == 0

    content_hash = hashlib.sha256(test_file_content).hexdigest()

    # Attempt to export without signing
    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    checksums_file = tmp_path / "dist" / "SHA256SUMS"

    result_export = runner.invoke(
        cli, ["export", "--output", str(output_tarball), "--checksums", str(checksums_file)]
    )
    assert result_export.exit_code != 0  # Expect a non-zero exit code for failure
    assert "Export blocked: Not all artifacts have valid signatures." in result_export.stderr

    # Assert that no tarball or checksums file was created
    assert not output_tarball.exists()
    assert not checksums_file.exists()

    # Assert that no export event was added to the ledger
    events = get_all_events(db_path)
    # Only the capture event should be present
    assert len(events) == 1
    capture_event = events[0]
    assert capture_event["action"] == "capture"
    assert capture_event["artifact_hash"] == content_hash


def test_policy_config_command(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    # Ensure policy.yaml exists (it should be created by the fixture or manually)
    policy_file = get_policy_file()
    policy_file.write_text(
        "governance_model: Custom\ncontrols:\n  - TestControl\nexistential_rules:\n  - name: test_rule\n    min_witnesses: 1\nuniversal_rules: []\nthreshold_rules: []\n"
    )

    result = runner.invoke(cli, ["policy", "config"])
    assert result.exit_code == 0
    assert "governance_model: Custom" in result.output
    assert "min_witnesses: 1" in result.output


def test_export_command_universal_rule(
    runner: CliRunner, tmp_path: Path, setup_test_environment: Path
):
    db_path = setup_test_environment
    test_file_content = b"Content for universal rule test."
    _capture_and_sign_artifact(runner, tmp_path, test_file_content, db_path)

    # Define a policy that requires a 'ledger' validator, which is not explicitly met here
    policy_file = get_policy_file()
    policy_file.write_text(
        """
    governance_model: Custom
    universal_rules:
      - name: require_ledger_validation
        required_validators: [ledger]
    existential_rules:
      - name: default_export_policy
        min_witnesses: 1
    threshold_rules: []
"""
    )

    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    checksums_file = tmp_path / "dist" / "SHA256SUMS"

    result_export = runner.invoke(
        cli, ["export", "--output", str(output_tarball), "--checksums", str(checksums_file)]
    )
    assert result_export.exit_code != 0
    assert "Export blocked" in result_export.stderr
    assert not output_tarball.exists()


def test_export_command_threshold_rule(
    runner: CliRunner, tmp_path: Path, setup_test_environment: Path
):
    db_path = setup_test_environment
    test_file_content = b"Content for threshold rule test."
    content_hash = _capture_and_sign_artifact(runner, tmp_path, test_file_content, db_path)

    # Simulate a second attestor
    second_attestor_fingerprint = "sha256:second_attestor_fingerprint"
    insert_event(
        {
            "ts": "2025-09-21T12:01:00.000Z",
            "action": "sign",
            "by": second_attestor_fingerprint,
            "artifact_hash": content_hash,
            "artifact_signature": "00" * 64,  # A dummy 64-byte hex string for testing the count
            "c2pa_assertion": "dummy_assertion",
        },
        db_path,
    )

    # Define a policy that requires 2 out of 2 attestors
    policy_file = get_policy_file()
    policy_file.write_text(
        f"""
governance_model: Custom
universal_rules: []
existential_rules:
  - name: default_export_policy
    min_witnesses: 1
threshold_rules:
  - name: two_attestors_required
    k: 2
    n: 2
    attestors: [{get_public_key_fingerprint()}, {second_attestor_fingerprint}]
"""
    )

    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    checksums_file = tmp_path / "dist" / "SHA256SUMS"

    result_export = runner.invoke(
        cli, ["export", "--output", str(output_tarball), "--checksums", str(checksums_file)]
    )
    assert result_export.exit_code != 0
    assert "Export blocked" in result_export.stderr
    assert not output_tarball.exists()
