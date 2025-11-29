import hashlib
import json
import os
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kairoscope.cli import cli
from kairoscope.db import get_all_events, get_artifact_metadata_by_hash, initialize_db


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


def test_capture_command(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_file_content = b"Hello, Kairoscope!"
    test_file_path = tmp_path / "test_input.txt"
    test_file_path.write_bytes(test_file_content)

    content_hash = hashlib.sha256(test_file_content).hexdigest()
    artifact_path = tmp_path / "artifacts" / content_hash

    # First capture
    result = runner.invoke(cli, ["capture", str(test_file_path)])
    assert result.exit_code == 0
    assert artifact_path.exists()  # Raw artifact file still exists

    # Verify artifact metadata in DB
    retrieved_artifact = get_artifact_metadata_by_hash(content_hash, db_path)
    assert retrieved_artifact is not None
    assert retrieved_artifact["hash"] == content_hash
    assert retrieved_artifact["kind"] == "capture"

    # Verify ledger entry in DB
    events = get_all_events(db_path)
    assert len(events) == 1
    capture_event = events[0]
    assert capture_event["action"] == "capture"
    assert capture_event["artifact_hash"] == content_hash

    # Test idempotency
    result_idempotent = runner.invoke(cli, ["capture", str(test_file_path)])
    assert result_idempotent.exit_code == 0
    assert "Artifact already exists" in result_idempotent.output
    assert len(get_all_events(db_path)) == 1  # No new ledger entry


def test_sign_command(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_file_content = b"Hello, Kairoscope!"
    test_file_path = tmp_path / "test_input.txt"
    test_file_path.write_bytes(test_file_content)

    # Capture first
    runner.invoke(cli, ["capture", str(test_file_path)])
    content_hash = hashlib.sha256(test_file_content).hexdigest()

    # Sign the artifact
    result = runner.invoke(cli, ["sign", content_hash])
    assert result.exit_code == 0

    # Verify artifact metadata in DB
    updated_record = get_artifact_metadata_by_hash(content_hash, db_path)
    assert updated_record is not None  # Ensure it's not None before accessing
    assert "c2pa_assertion" in updated_record
    assert updated_record["hash"] == content_hash

    # Verify ledger entry in DB
    events = get_all_events(db_path)
    assert len(events) == 2  # Capture + Sign
    sign_event = events[1]
    assert sign_event["action"] == "sign"
    assert sign_event["artifact_hash"] == content_hash
    assert "artifact_signature" in sign_event
    assert "c2pa_assertion" in sign_event

    # Test idempotency
    result_idempotent = runner.invoke(cli, ["sign", content_hash])
    assert result_idempotent.exit_code == 0
    assert "already signed" in result_idempotent.output
    assert len(get_all_events(db_path)) == 2  # No new ledger entry


def test_export_command_happy_path(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_file_content = b"Hello, Kairoscope!"
    test_file_path = tmp_path / "test_input.txt"
    test_file_path.write_bytes(test_file_content)

    # Capture and Sign
    runner.invoke(cli, ["capture", str(test_file_path)])
    content_hash = hashlib.sha256(test_file_content).hexdigest()
    runner.invoke(cli, ["sign", content_hash])

    # Export
    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    checksums_file = tmp_path / "dist" / "SHA256SUMS"

    result = runner.invoke(
        cli, ["export", "--output", str(output_tarball), "--checksums", str(checksums_file)]
    )
    assert result.exit_code == 0
    assert output_tarball.exists()
    assert checksums_file.exists()
    assert f"Exported to {output_tarball}" in result.output

    # Verify tarball contents
    with tarfile.open(output_tarball, "r:gz") as tar:
        tar_members = [m.name for m in tar.getmembers()]
        assert f"artifacts/{content_hash}" in tar_members

        # Verify content of the artifact inside the tarball
        extracted_artifact = tar.extractfile(f"artifacts/{content_hash}")
        assert extracted_artifact is not None
        assert extracted_artifact.read() == test_file_content

    # Verify checksums file
    checksum_line = checksums_file.read_text().strip()
    tarball_hash = hashlib.sha256(output_tarball.read_bytes()).hexdigest()
    assert checksum_line == f"{tarball_hash} {output_tarball.name}"

    events = get_all_events(db_path)
    assert len(events) == 3  # Capture + Sign + Export
    export_event = events[2]
    assert export_event["action"] == "export"
    assert export_event["tarball_hash"] == tarball_hash
    assert content_hash in export_event["artifacts_exported"]


def test_ledger_command_show(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_file_content = b"Hello, Kairoscope!"
    test_file_path = tmp_path / "test_input.txt"
    test_file_path.write_bytes(test_file_content)

    runner.invoke(cli, ["capture", str(test_file_path)])
    content_hash = hashlib.sha256(test_file_content).hexdigest()
    runner.invoke(cli, ["sign", content_hash])

    result = runner.invoke(cli, ["ledger", "--show"])
    assert result.exit_code == 0
    events = get_all_events(db_path)
    assert len(events) == 2
    assert json.dumps(events[0], sort_keys=True) in result.output
    assert json.dumps(events[1], sort_keys=True) in result.output


def test_ledger_command_empty(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    # The fixture already initializes a fresh DB, so it should be empty
    result = runner.invoke(cli, ["ledger", "--show"])
    assert result.exit_code == 0
    assert "Ledger is empty." in result.output


def test_capture_from_stdin(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_content = b"Content from stdin."
    content_hash = hashlib.sha256(test_content).hexdigest()
    artifact_path = tmp_path / "artifacts" / content_hash

    result = runner.invoke(cli, ["capture"], input=test_content)
    assert result.exit_code == 0
    assert artifact_path.exists()

    # Verify artifact metadata in DB
    retrieved_artifact = get_artifact_metadata_by_hash(content_hash, db_path)
    assert retrieved_artifact is not None
    assert retrieved_artifact["hash"] == content_hash
    assert retrieved_artifact["kind"] == "capture"

    # Verify ledger entry in DB
    events = get_all_events(db_path)
    assert len(events) == 1
    capture_event = events[0]
    assert capture_event["action"] == "capture"
    assert capture_event["artifact_hash"] == content_hash
