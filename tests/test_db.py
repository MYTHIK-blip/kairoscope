from pathlib import Path

from kairoscope.db import (
    get_all_artifact_hashes,
    get_all_events,
    get_artifact_metadata_by_hash,
    get_artifact_metadata_by_id,
    get_db_connection,
    insert_artifact_metadata,
    insert_event,
)


def test_db_initialization(setup_db_for_tests: Path):
    db_path = setup_db_for_tests
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "events" in tables
    assert "artifacts" in tables

    conn.close()


def test_insert_and_get_event(setup_db_for_tests: Path):
    db_path = setup_db_for_tests
    event_data = {
        "ts": "2025-09-21T10:00:00.000Z",
        "action": "capture",
        "by": "test_agent",
        "artifact_hash": "test_hash_123",
        "artifact_id": "test_id_456",
        "raw_event_json": "{}",
    }
    insert_event(event_data, db_path)

    events = get_all_events(db_path)
    assert len(events) == 1
    retrieved_event = events[0]
    assert retrieved_event["action"] == "capture"
    assert retrieved_event["artifact_hash"] == "test_hash_123"

    # Test with more complex event data
    export_event_data = {
        "ts": "2025-09-21T11:00:00.000Z",
        "action": "export",
        "by": "test_agent",
        "exported_tarball": "/tmp/test.tar.gz",
        "tarball_hash": "tar_hash_789",
        "artifacts_exported": ["hash1", "hash2"],
        "sbom_generated": True,
        "slsa_generated": False,
    }
    insert_event(export_event_data, db_path)

    events = get_all_events(db_path)
    assert len(events) == 2
    retrieved_export_event = events[1]
    assert retrieved_export_event["action"] == "export"
    assert retrieved_export_event["tarball_hash"] == "tar_hash_789"
    assert retrieved_export_event["artifacts_exported"] == ["hash1", "hash2"]
    assert retrieved_export_event["sbom_generated"] is True
    assert retrieved_export_event["slsa_generated"] is False


def test_insert_and_get_artifact_metadata(setup_db_for_tests: Path):
    db_path = setup_db_for_tests
    metadata = {
        "id": "artifact_uuid_1",
        "kind": "capture",
        "uri": "file://path/to/artifact1",
        "hash": "hash_val_1",
        "c2pa_assertion": "assertion_data_1",
        "raw_metadata_json": "{}",
    }
    insert_artifact_metadata(metadata, db_path)

    retrieved_by_hash = get_artifact_metadata_by_hash("hash_val_1", db_path)
    assert retrieved_by_hash is not None
    if retrieved_by_hash:
        assert retrieved_by_hash["id"] == "artifact_uuid_1"
        assert retrieved_by_hash["kind"] == "capture"

    retrieved_by_id = get_artifact_metadata_by_id("artifact_uuid_1", db_path)
    assert retrieved_by_id is not None
    if retrieved_by_id:
        assert retrieved_by_id["hash"] == "hash_val_1"

    # Test update (INSERT OR REPLACE)
    updated_metadata = metadata.copy()
    updated_metadata["c2pa_assertion"] = "new_assertion_data"
    insert_artifact_metadata(updated_metadata, db_path)

    retrieved_updated = get_artifact_metadata_by_hash("hash_val_1", db_path)
    assert retrieved_updated is not None
    if retrieved_updated:
        assert retrieved_updated["c2pa_assertion"] == "new_assertion_data"


def test_get_all_artifact_hashes(setup_db_for_tests: Path):
    db_path = setup_db_for_tests
    insert_artifact_metadata({"id": "id1", "kind": "k", "uri": "u", "hash": "h1"}, db_path)
    insert_artifact_metadata({"id": "id2", "kind": "k", "uri": "u", "hash": "h2"}, db_path)

    hashes = get_all_artifact_hashes(db_path)
    assert len(hashes) == 2
    assert "h1" in hashes
    assert "h2" in hashes
