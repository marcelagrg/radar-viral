"""Conexão com o banco de dados."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event

from radar_viral.storage.schema import metadata


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    # Por padrão o SQLite IGNORA chaves estrangeiras. Este comando liga a
    # verificação em cada nova conexão (o PostgreSQL já faz isso sempre).
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(database_url: str, echo: bool = False) -> Engine:
    """Cria o "engine": o objeto que gerencia as conexões com o banco.

    echo=True imprime todo SQL executado — útil para aprender e depurar.
    """
    engine = create_engine(database_url, echo=echo)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def init_db(engine: Engine) -> list[str]:
    """Cria as tabelas que ainda não existem e devolve os nomes das tabelas.

    create_all é seguro para rodar várias vezes: não apaga nem altera
    tabelas existentes. (Para alterar tabelas já criadas, usaremos
    migrações no futuro — ver docs/arquitetura.md.)
    """
    metadata.create_all(engine)
    return sorted(metadata.tables.keys())
