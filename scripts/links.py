"""Links de compra das famílias de produto (Amazon, Shopee, Mercado Livre).

Exemplos (na raiz do projeto):
  python scripts/links.py adicionar "playstation" shopee "https://shopee.com.br/..." --rotulo "PS5 Slim"
  python scripts/links.py listar
  python scripts/links.py listar --familia playstation
  python scripts/links.py remover 3
  python scripts/links.py buscar "mini aspirador portátil"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.config import load_settings  # noqa: E402
from radar_viral.marketplaces import MARKETPLACES, save_link, search_links  # noqa: E402
from radar_viral.storage import repository as repo  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Links de compra das famílias de produto.")
    sub = p.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("adicionar", help="adiciona um link a uma família")
    a.add_argument("familia", help="nome exato da família (veja 'families.py listar')")
    a.add_argument("marketplace", choices=list(MARKETPLACES))
    a.add_argument("url")
    a.add_argument("--rotulo", help="descrição curta, ex.: 'kit com 2'")
    lst = sub.add_parser("listar", help="lista os links")
    lst.add_argument("--familia", help="só desta família")
    r = sub.add_parser("remover", help="remove um link pelo número (#)")
    r.add_argument("id", type=int)
    b = sub.add_parser("buscar", help="mostra links de busca nos marketplaces (não salva nada)")
    b.add_argument("termo")
    return p


def family_id_or_error(engine, name: str) -> int:
    fid = repo.get_family_id(engine, name)
    if fid is None:
        raise ValueError(f"família não encontrada: {name!r} (confira com 'python scripts\\families.py listar')")
    return fid


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.comando == "buscar":  # não precisa de banco
            for name, url in search_links(args.termo).items():
                print(f"{name:<14} {url}")
            return 0
        engine = get_engine(load_settings().database_url)
        init_db(engine)
        if args.comando == "adicionar":
            link_id = save_link(engine, family_id_or_error(engine, args.familia), args.marketplace, args.url, args.rotulo)
            print(f"Link #{link_id} adicionado a '{args.familia}' ({MARKETPLACES[args.marketplace].name}).")
        elif args.comando == "listar":
            fid = family_id_or_error(engine, args.familia) if args.familia else None
            links = repo.list_links(engine, fid)
            if not links:
                print("Nenhum link cadastrado.")
            for link in links:
                rotulo = f" — {link['label']}" if link["label"] else ""
                print(f"#{link['id']:<4} {link['family_name']} | {MARKETPLACES[link['marketplace']].name}{rotulo}\n      {link['url']}")
        elif args.comando == "remover":
            repo.delete_link(engine, args.id)
            print(f"Link #{args.id} removido.")
    except (ValueError, SchemaOutdatedError) as exc:
        print(f"[ERRO] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
