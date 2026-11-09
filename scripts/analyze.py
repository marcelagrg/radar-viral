"""Indicadores de crescimento por família de produto.

Exemplos (na raiz do projeto):
  python scripts/analyze.py
  python scripts/analyze.py --janela 30 --familia playstation --detalhe
  python scripts/analyze.py --csv data/indicadores.csv
"""

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.analysis.growth import WINDOWS_DAYS  # noqa: E402
from radar_viral.analysis.report import growth_table  # noqa: E402
from radar_viral.config import load_settings  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402


def fmt(value, suffix="", digits=1, signed=True):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:+.{digits}f}{suffix}" if signed else f"{value:.{digits}f}{suffix}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Indicadores de crescimento do Radar Viral.")
    p.add_argument("--janela", type=int, choices=WINDOWS_DAYS, default=90, help="janela principal (dias)")
    p.add_argument("--familia", help="filtra famílias cujo nome contém este texto")
    p.add_argument("--detalhe", action="store_true", help="mostra todas as janelas")
    p.add_argument("--todas-coletas", action="store_true", help="uma linha por exportação, não só a mais recente")
    p.add_argument("--incluir-simulados", action="store_true", help="inclui dados SIMULADOS")
    p.add_argument("--csv", type=Path, help="salva a tabela completa neste arquivo .csv")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        engine = get_engine(load_settings().database_url)
        init_db(engine)
        table = growth_table(engine, args.janela, args.incluir_simulados, args.todas_coletas)
    except (ValueError, SchemaOutdatedError) as exc:
        print(f"[ERRO] {exc}")
        return 1

    if table.empty:
        print("Nenhuma série com valores numéricos. Importe dados primeiro.")
        return 0
    if args.familia:
        table = table[table["familia"].str.contains(args.familia, case=False, regex=False)]
        if table.empty:
            print(f"Nenhuma família contém {args.familia!r}.")
            return 0

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig + ';' + vírgula decimal: abre corretamente no Excel em português
        table.to_csv(args.csv, index=False, sep=";", decimal=",", encoding="utf-8-sig")
        print(f"Tabela salva em {args.csv} ({len(table)} linha(s)).")

    j = args.janela
    for _, r in table.iterrows():
        coleta = f", coleta #{r['coleta']}" if r["coleta"] is not None and not math.isnan(r["coleta"]) else ""
        print(f"\n■ {r['familia']}  [{r['fonte']}, {r['pais']}{coleta}]")
        print(f"  {r['pontos']} pontos ({r['frequencia']}) de {r['inicio']} a {r['fim']}; lacunas: {r['lacunas']}")
        print(f"  Pico {fmt(r['pico'], signed=False)} em {r['data_pico']}; último valor "
              f"{fmt(r['ultimo'], signed=False)} ({fmt(r['ultimo_vs_pico_pct'], '%')} vs. pico)")
        print(f"  Janela {j}d: crescimento {fmt(r[f'crescimento_{j}d'], '%')}, "
              f"velocidade {fmt(r[f'velocidade_{j}d'], '%/sem')}, "
              f"aceleração {fmt(r[f'aceleracao_{j}d'], ' p.p.')}, "
              f"consistência {fmt(r[f'consistencia_{j}d'], digits=2, signed=False)}")
        print(f"  Classificação: {r['classificacao'].upper()}")
        print(f"  Tipo de tendência: {r['tipo']} — {r['tipo_explicacao']}")
        if args.detalhe:
            for w in WINDOWS_DAYS:
                print(f"    {w:>2}d: {r[f'status_{w}d']:<26} crescimento {fmt(r[f'crescimento_{w}d'], '%')}")
        print(f"  Sazonalidade: {r['sazonalidade']}")
    print("\nAtenção: classificações descrevem o comportamento passado; não são previsões.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
