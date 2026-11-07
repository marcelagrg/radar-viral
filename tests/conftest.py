"""Configurações compartilhadas pelos testes (fixtures do pytest)."""

import pytest

from radar_viral.storage.database import get_engine, init_db


@pytest.fixture
def engine(tmp_path):
    """Banco SQLite temporário e novo para cada teste — nunca usa o banco real."""
    eng = get_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    init_db(eng)
    yield eng
    eng.dispose()
