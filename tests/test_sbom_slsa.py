import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kairoscope.cli import cli
from kairoscope.db import get_all_events, initialize_db


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


def test_export_with_sbom(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    _capture_and_sign_artifact(runner, tmp_path, b"Content for SBOM test.", db_path)

    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    sbom_output_path = tmp_path / "dist" / "kairoscope-v0.1.0.tar.sbom.json"

    result = runner.invoke(
        cli,
        [
            "export",
            "--output",
            str(output_tarball),
            "--checksums",
            str(tmp_path / "dist" / "SHA256SUMS"),
            "--sbom",
        ],
    )
    assert result.exit_code == 0
    assert output_tarball.exists()
    assert sbom_output_path.exists()

    # Verify SBOM content (basic check for project SBOM)
    sbom_content = json.loads(sbom_output_path.read_text())
    assert sbom_content["bomFormat"] == "CycloneDX"
    assert sbom_content["specVersion"] == "1.6"
    # We expect components to be present, but not necessarily specific names as it's a project SBOM
    assert len(sbom_content["components"]) > 0

    # Verify ledger entry
    events = get_all_events(db_path)
    export_event = events[-1]
    assert export_event["action"] == "export"
    assert export_event["sbom_generated"] is True
    assert export_event["slsa_generated"] is False


def test_export_with_slsa(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_content = b"Content for SLSA test."
    _capture_and_sign_artifact(runner, tmp_path, test_content, db_path)

    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    slsa_output_path = tmp_path / "dist" / "kairoscope-v0.1.0.tar.slsa.json"

    result = runner.invoke(
        cli,
        [
            "export",
            "--output",
            str(output_tarball),
            "--checksums",
            str(tmp_path / "dist" / "SHA256SUMS"),
            "--slsa",
        ],
    )
    assert result.exit_code == 0
    assert output_tarball.exists()
    assert slsa_output_path.exists()

    # Verify SLSA content
    slsa_content = json.loads(slsa_output_path.read_text())
    assert slsa_content["_type"] == "https://in-toto.io/Statement/v0.1"
    assert slsa_content["predicateType"] == "https://slsa.dev/provenance/v0.2"
    assert slsa_content["subject"][0]["name"] == output_tarball.name
    assert (
        slsa_content["subject"][0]["digest"]["sha256"]
        == hashlib.sha256(output_tarball.read_bytes()).hexdigest()
    )

    # Verify ledger entry
    events = get_all_events(db_path)
    export_event = events[-1]
    assert export_event["action"] == "export"
    assert export_event["sbom_generated"] is False
    assert export_event["slsa_generated"] is True


def test_export_with_sbom_and_slsa(runner: CliRunner, tmp_path: Path, setup_test_environment: Path):
    db_path = setup_test_environment
    test_content = b"Content for both SBOM and SLSA test."
    _capture_and_sign_artifact(runner, tmp_path, test_content, db_path)

    output_tarball = tmp_path / "dist" / "kairoscope-v0.1.0.tar.gz"
    sbom_output_path = tmp_path / "dist" / "kairoscope-v0.1.0.tar.sbom.json"
    slsa_output_path = tmp_path / "dist" / "kairoscope-v0.1.0.tar.slsa.json"

    result = runner.invoke(
        cli,
        [
            "export",
            "--output",
            str(output_tarball),
            "--checksums",
            str(tmp_path / "dist" / "SHA256SUMS"),
            "--sbom",
            "--slsa",
        ],
    )
    assert result.exit_code == 0
    assert output_tarball.exists()
    assert sbom_output_path.exists()
    assert slsa_output_path.exists()

    # Verify SBOM content (basic check)
    sbom_content = json.loads(sbom_output_path.read_text())
    assert sbom_content["bomFormat"] == "CycloneDX"
    assert sbom_content["specVersion"] == "1.6"
    assert len(sbom_content["components"]) > 0

    # Verify SLSA content (basic check)
    slsa_content = json.loads(slsa_output_path.read_text())
    assert slsa_content["_type"] == "https://in-toto.io/Statement/v0.1"
    assert slsa_content["predicateType"] == "https://slsa.dev/provenance/v0.2"
    assert (
        slsa_content["subject"][0]["digest"]["sha256"]
        == hashlib.sha256(output_tarball.read_bytes()).hexdigest()
    )

    # Verify ledger entry
    events = get_all_events(db_path)
    export_event = events[-1]
    assert export_event["action"] == "export"
    assert export_event["sbom_generated"] is True
    assert export_event["slsa_generated"] is True
