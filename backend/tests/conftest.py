from pathlib import Path

import pytest

from intellidocpro.envfile import load_env_file


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    """Point the server SQLite store at a per-test database."""
    monkeypatch.setenv("INTELLIDOCPRO_DB", str(tmp_path / "test.db"))

# Load engine credentials from backend/.env for integration tests.
# Placeholder (REPLACE_ME) values never enter the environment.
load_env_file(Path(__file__).parent.parent / ".env")
