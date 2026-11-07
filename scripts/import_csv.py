"""Importa um CSV no formato padrão do Radar Viral.

Exemplos (na raiz do projeto):
  python scripts/import_csv.py dados.csv --fonte google_trends_manual
  python scripts/import_csv.py tests/fixtures/exemplo_simulado.csv --fonte teste --simulado
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.collectors.csv_importer import CsvImportError, import_csv  # noqa: E402
from radar_viral.config import load_settings  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Importa um CSV para o histórico do Radar Viral.")
    p.add_argument("arquivo", type=Path, help="caminho do arquivo .csv")
    p.add_argument("--fonte", required=True, help="código da fonte, ex.: google_trends_manual")
    p.add_argument("--nome-fonte", help="nome legível da fonte (opcional)")
    p.add_argument("--pais", help="código do país (padrão: DEFAULT_COUNTRY do .env)")
    p.add_argument("--decimal", choices=[",", "."], default=",", help="separador decimal (padrão: ,)")
    p.add_argument("--simulado", action="store_true", help="marca os dados como SIMULADOS (teste)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        engine = get_engine(settings.database_url)
        init_db(engine)
        result = import_csv(
            engine,
            args.arquivo,
            source_code=args.fonte,
            source_name=args.nome_fonte,
            country=(args.pais or settings.default_country),
            decimal_sep=args.decimal,
            simulated=args.simulado,
        )
    except (CsvImportError, SchemaOutdatedError, ValueError) as exc:
        print(f"[ERRO] {exc}")
        return 1

    aviso = " (SIMULADOS)" if args.simulado else ""
    print(f"Importação concluída: {result.rows_imported} linha(s){aviso} na coleta #{result.run_id}.")
    print(f"Fonte: {result.source_code} | SHA-256: {result.file_sha256[:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
