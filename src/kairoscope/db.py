import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def get_db_path() -> Path:
    db_path_str = os.environ.get("KAIROSCOPE_DB_PATH")
    if db_path_str:
        return Path(db_path_str)
    return Path.cwd() / "kairoscope.db"


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def initialize_db(db_path: Path) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create events table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            by TEXT NOT NULL,
            artifact_hash TEXT,
            artifact_id TEXT,
            artifact_signature TEXT,
            c2pa_assertion TEXT,
            exported_tarball TEXT,
            tarball_hash TEXT,
            artifacts_exported TEXT, -- Stored as JSON string
            sbom_generated INTEGER, -- Boolean (0 or 1)
            slsa_generated INTEGER, -- Boolean (0 or 1)
            raw_event_json TEXT NOT NULL -- Original event JSON for flexibility
        )
    """
    )

    # Create artifacts table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY, -- artifact_id (UUID)
            kind TEXT NOT NULL,
            uri TEXT NOT NULL,
            hash TEXT UNIQUE NOT NULL,
            c2pa_assertion TEXT,
            raw_metadata_json TEXT NOT NULL -- Original artifact metadata JSON for flexibility
        )
    """
    )

    conn.commit()
    conn.close()


def insert_event(event: dict[str, Any], db_path: Path) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO events (
            timestamp, action, by, artifact_hash, artifact_id, artifact_signature,
            c2pa_assertion, exported_tarball, tarball_hash, artifacts_exported,
            sbom_generated, slsa_generated, raw_event_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            event.get("ts"),
            event.get("action"),
            event.get("by"),
            event.get("artifact_hash"),
            event.get("artifact_id"),
            event.get("artifact_signature"),
            event.get("c2pa_assertion"),
            event.get("exported_tarball"),
            event.get("tarball_hash"),
            (
                json.dumps(event.get("artifacts_exported"))
                if event.get("artifacts_exported")
                else None
            ),
            int(event.get("sbom_generated", False)),
            int(event.get("slsa_generated", False)),
            json.dumps(event),
        ),
    )
    conn.commit()
    conn.close()


def get_all_events(db_path: Path) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_event_json FROM events ORDER BY timestamp ASC")
    events = [json.loads(row["raw_event_json"]) for row in cursor.fetchall()]
    conn.close()
    return events


def insert_artifact_metadata(metadata: dict[str, Any], db_path: Path) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO artifacts (
            id, kind, uri, hash, c2pa_assertion, raw_metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            metadata.get("id"),
            metadata.get("kind"),
            metadata.get("uri"),
            metadata.get("hash"),
            metadata.get("c2pa_assertion"),
            json.dumps(metadata),
        ),
    )
    conn.commit()
    conn.close()


def get_artifact_metadata_by_hash(artifact_hash: str, db_path: Path) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_metadata_json FROM artifacts WHERE hash = ?", (artifact_hash,))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row["raw_metadata_json"]) if row else None


def get_artifact_metadata_by_id(artifact_id: str, db_path: Path) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_metadata_json FROM artifacts WHERE id = ?", (artifact_id,))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row["raw_metadata_json"]) if row else None


def get_all_artifact_hashes(db_path: Path) -> list[str]:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT hash FROM artifacts")
    hashes = [row["hash"] for row in cursor.fetchall()]
    conn.close()
    return hashes
