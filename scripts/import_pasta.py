"""Rotina semanal: importa todos os exports do Google Trends de uma pasta e
agrupa as famílias.

Exemplos (na raiz do projeto):
  python scripts/import_pasta.py                       # usa EXPORTS_DIR do .env
  python scripts/import_pasta.py C:\\Users\\voce\\Downloads
  python scripts/import_pasta.py C:\\Users\\voce\\Downloads --mover
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.collectors.batch import DONE_FOLDER, FAILED, IMPORTED, PATTERN, import_folder  # noqa: E402
from radar_viral.collectors.file_import import CsvImportError  # noqa: E402
from radar_viral.config import load_settings  # noqa: E402
from radar_viral.processing.product_families import group_terms  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"Importa todos os arquivos {PATTERN} de uma pasta.")
    p.add_argument("pasta", nargs="?", type=Path, help="pasta dos exports (padrão: EXPORTS_DIR do .env)")
    p.add_argument("--mover", action="store_true",
                   help=f"move os arquivos importados/repetidos para a subpasta '{DONE_FOLDER}'")
    p.add_argument("--incluir-parcial", action="store_true", help="importa também o último período incompleto")
    p.add_argument("--sem-agrupar", action="store_true", help="não roda o agrupamento de famílias no final")
    p.add_argument("--simulado", action="store_true", help="marca TODOS os arquivos como SIMULADOS (teste)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        folder = args.pasta or settings.exports_dir
        if folder is None:
            print("[ERRO] Informe a pasta, ou defina EXPORTS_DIR no arquivo .env.")
            return 1
        engine = get_engine(settings.database_url)
    except ValueError as exc:
        print(f"[ERRO] {exc}")
        return 1
    try:
        return run(engine, folder, args, settings)
    except (CsvImportError, SchemaOutdatedError, ValueError) as exc:
        print(f"[ERRO] {exc}")
        return 1
    finally:
        engine.dispose()  # fecha as conexões com o banco ao terminar


def run(engine, folder, args, settings) -> int:
    init_db(engine)
    outcomes = import_folder(engine, folder, args.incluir_parcial, args.simulado, args.mover)

    print(f"Pasta: {folder}")
    if not outcomes:
        print(f"Nenhum arquivo {PATTERN} encontrado.")
        return 0

    for o in outcomes:
        extra = f" — {o.rows} valor(es)" if o.status == IMPORTED else ""
        extra += f", {o.skipped} do período parcial ignorado(s)" if o.skipped else ""
        print(f"  [{o.status.upper():<12}] {o.file}{extra}")
        if o.status != IMPORTED:
            print(f"                  {o.message}")
        if o.moved_to:
            print(f"                  movido para {DONE_FOLDER}{os.sep}")

    imported = sum(o.status == IMPORTED for o in outcomes)
    failed = sum(o.status == FAILED for o in outcomes)
    print(f"\nResumo: {imported} importado(s), {len(outcomes) - imported - failed} já importado(s), {failed} com erro.")

    if imported and not args.sem_agrupar:
        s = group_terms(engine, settings.family_similarity_threshold, include_simulated=args.simulado)
        print(f"Famílias: {s.joined_existing} termo(s) em famílias existentes, {s.new_families} família(s) nova(s).")
        if s.new_families:
            print("Revise com:  python scripts\\families.py listar")
    if imported:
        print("Se o painel estiver aberto, clique em 'Recarregar dados'.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
