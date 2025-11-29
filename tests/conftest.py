from pathlib import Path

import pytest

from kairoscope.db import initialize_db


@pytest.fixture(autouse=True)
def setup_db_for_tests(tmp_path: Path):
    db_path = tmp_path / "test_kairoscope.db"

    if db_path.exists():
        db_path.unlink()

    initialize_db(db_path)

    yield db_path

    if db_path.exists():
        db_path.unlink()
