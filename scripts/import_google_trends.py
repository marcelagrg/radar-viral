"""Importa o CSV exportado do Google Trends ("Interesse ao longo do tempo").

Exemplos (na raiz do projeto):
  python scripts/import_google_trends.py C:\\Downloads\\time_series_BR_20251107-0805_20261107-0805.csv
  python scripts/import_google_trends.py arquivo_renomeado.csv --pais BR --fim 2026-11-07
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.collectors.file_import import CsvImportError  # noqa: E402
from radar_viral.collectors.google_trends_csv import import_google_trends  # noqa: E402
from radar_viral.config import load_settings  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def iso_date(text: str):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"data inválida {text!r}; use AAAA-MM-DD") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Importa um export CSV do Google Trends.")
    p.add_argument("arquivo", type=Path, help="caminho do arquivo .csv baixado do Google Trends")
    p.add_argument("--pais", help="país (só necessário se o arquivo foi renomeado)")
    p.add_argument("--fim", type=iso_date, help="data final da consulta, AAAA-MM-DD (arquivo renomeado)")
    p.add_argument("--incluir-parcial", action="store_true",
                   help="importa também o último período, mesmo que incompleto")
    p.add_argument("--simulado", action="store_true", help="marca os dados como SIMULADOS (teste)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        engine = get_engine(load_settings().database_url)
        init_db(engine)
        result = import_google_trends(
            engine, args.arquivo, country=args.pais, period_end=args.fim,
            include_partial=args.incluir_parcial, simulated=args.simulado,
        )
    except (CsvImportError, SchemaOutdatedError, ValueError) as exc:
        print(f"[ERRO] {exc}")
        return 1

    aviso = " (SIMULADOS)" if args.simulado else ""
    print(f"Importação concluída: {result.rows_imported} valor(es){aviso} na coleta #{result.run_id}.")
    if result.rows_skipped:
        print(f"Último período ignorado por estar incompleto ({result.rows_skipped} valor(es)). "
              "Use --incluir-parcial para importá-lo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
