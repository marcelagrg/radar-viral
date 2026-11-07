"""Cria o banco de dados e as tabelas do Radar Viral.

Uso (na raiz do projeto):  python scripts/init_db.py
"""

import sys
from pathlib import Path

# Permite rodar o script diretamente, encontrando o pacote radar_viral.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.config import load_settings  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def main() -> int:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"[ERRO] Configuração inválida: {exc}")
        return 1

    engine = get_engine(settings.database_url)
    try:
        tables = init_db(engine)
    except SchemaOutdatedError as exc:
        print(f"[ERRO] {exc}")
        print("Se o banco ainda não tem dados reais, apague o arquivo .db e rode este script de novo.")
        return 1
    print(f"Banco: {settings.database_url}")
    print(f"Tabelas disponíveis: {', '.join(tables)}")
    print("Banco inicializado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
