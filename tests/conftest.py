"""Point the DB at a throwaway file before any repository call."""

import pytest

from chess_llm.db import init_db


@pytest.fixture(scope="session", autouse=True)
def _temp_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    init_db(f"sqlite:///{db_file}")
    yield
