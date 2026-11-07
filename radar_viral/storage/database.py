"""Conexão com o banco de dados."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, inspect

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


class SchemaOutdatedError(RuntimeError):
    """O banco existente foi criado por uma versão antiga do esquema."""


def check_schema(engine: Engine) -> None:
    """Compara as colunas do banco real com as definidas em schema.py.

    create_all() cria tabelas novas, mas NÃO adiciona colunas a tabelas que
    já existem. Sem esta checagem, o erro só apareceria lá na frente, numa
    mensagem confusa do tipo "no such column".
    """
    inspector = inspect(engine)
    missing = []
    for table in metadata.sorted_tables:
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{col.name}" for col in table.columns if col.name not in existing]
    if missing:
        raise SchemaOutdatedError(
            "O banco foi criado por uma versão anterior do Radar Viral e não tem as colunas: "
            + ", ".join(missing)
        )


def init_db(engine: Engine) -> list[str]:
    """Cria as tabelas que ainda não existem e devolve os nomes das tabelas.

    create_all é seguro para rodar várias vezes: não apaga nem altera
    tabelas existentes. (Para alterar tabelas já criadas, usaremos
    migrações no futuro — ver docs/arquitetura.md.)
    """
    metadata.create_all(engine)
    check_schema(engine)
    return sorted(metadata.tables.keys())
