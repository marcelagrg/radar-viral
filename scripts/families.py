"""Famílias de produtos: agrupar, listar e corrigir.

Exemplos (na raiz do projeto):
  python scripts/families.py agrupar
  python scripts/families.py agrupar --limiar 0.6 --refazer
  python scripts/families.py listar
  python scripts/families.py mover "aspirador de mesa USB" "mini aspirador portátil"
  python scripts/families.py renomear "mini aspirador portátil" "Mini aspirador"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.config import load_settings  # noqa: E402
from radar_viral.processing.product_families import group_terms  # noqa: E402
from radar_viral.storage import repository as repo  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Famílias de produtos do Radar Viral.")
    sub = p.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("agrupar", help="agrupa os termos ainda sem família")
    a.add_argument("--limiar", type=float, help="similaridade mínima 0–1 (padrão: .env)")
    a.add_argument("--refazer", action="store_true", help="recalcula as atribuições automáticas")
    a.add_argument("--incluir-simulados", action="store_true", help="inclui termos SIMULADOS")

    sub.add_parser("listar", help="mostra as famílias e seus termos")

    m = sub.add_parser("mover", help="move um termo para uma família (cria se não existir)")
    m.add_argument("termo")
    m.add_argument("familia")

    r = sub.add_parser("renomear", help="renomeia uma família")
    r.add_argument("antigo")
    r.add_argument("novo")
    return p


def cmd_agrupar(engine, args, settings) -> None:
    threshold = args.limiar if args.limiar is not None else settings.family_similarity_threshold
    s = group_terms(engine, threshold, rebuild=args.refazer, include_simulated=args.incluir_simulados)
    print(f"Limiar de similaridade: {threshold}")
    print(f"Termos analisados: {s.terms_total} (já tinham família: {s.already_assigned})")
    print(f"Entraram em famílias existentes: {s.joined_existing}")
    print(f"Famílias novas: {s.new_families} ({s.terms_in_new_families} termo(s))")
    print("Revise com:  python scripts\\families.py listar")


def cmd_listar(engine) -> None:
    families = repo.list_families(engine)
    if not families:
        print("Nenhuma família ainda. Rode:  python scripts\\families.py agrupar")
        return
    for fam in families:
        print(f"\n[{fam['id']}] {fam['name']}  ({len(fam['terms'])} termo(s))")
        for t in fam["terms"]:
            tag = "manual" if t["method"] == "manual" else f"auto {t['similarity']:.2f}"
            print(f"     - {t['term']}  ({tag})")


def cmd_mover(engine, args) -> None:
    if args.termo not in repo.list_distinct_terms(engine, include_simulated=True):
        raise ValueError(f"termo não encontrado nas observações: {args.termo!r} (confira com 'listar')")
    family_id = repo.get_family_id(engine, args.familia)
    created = family_id is None
    if created:
        family_id = repo.create_family(engine, args.familia, created_by="manual")
    repo.assign_term(engine, args.termo, family_id, method="manual")
    repo.delete_empty_families(engine)
    print(f"'{args.termo}' agora pertence a '{args.familia}'" + (" (família criada)." if created else "."))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        engine = get_engine(settings.database_url)
        init_db(engine)
        if args.comando == "agrupar":
            cmd_agrupar(engine, args, settings)
        elif args.comando == "listar":
            cmd_listar(engine)
        elif args.comando == "mover":
            cmd_mover(engine, args)
        elif args.comando == "renomear":
            repo.rename_family(engine, args.antigo, args.novo)
            print(f"Família renomeada para '{args.novo}'.")
    except (ValueError, SchemaOutdatedError) as exc:
        print(f"[ERRO] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
