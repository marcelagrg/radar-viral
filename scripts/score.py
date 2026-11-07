"""Ranking de potencial de tendência (0–100).

Exemplos (na raiz do projeto):
  python scripts/score.py
  python scripts/score.py --detalhe --familia playstation
  python scripts/score.py --config config/meus_pesos.toml --csv data/ranking.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar_viral.config import load_settings  # noqa: E402
from radar_viral.scoring.config import CRITERIA, ScoringConfigError, load_scoring_config  # noqa: E402
from radar_viral.scoring.scorer import results_to_frame, score_all  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402

LABELS = {
    "velocidade": "Velocidade", "aceleracao": "Aceleração", "persistencia": "Persistência",
    "multiplataforma": "Multiplataforma", "engajamento": "Engajamento",
    "intencao_compra": "Intenção de compra", "concorrencia": "Concorrência",
    "sazonalidade": "Sazonalidade", "potencial_comercial": "Potencial comercial",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pontuação de potencial de tendência.")
    p.add_argument("--config", type=Path, help="arquivo de pesos (padrão: config/pontuacao.toml)")
    p.add_argument("--pais", help="filtra por país, ex.: BR")
    p.add_argument("--familia", help="filtra famílias cujo nome contém este texto")
    p.add_argument("--top", type=int, default=20, help="quantas famílias mostrar (padrão 20)")
    p.add_argument("--detalhe", action="store_true", help="mostra a contribuição de cada critério")
    p.add_argument("--incluir-simulados", action="store_true", help="inclui dados SIMULADOS")
    p.add_argument("--csv", type=Path, help="salva o ranking completo neste .csv")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_scoring_config(args.config)
        engine = get_engine(load_settings().database_url)
        init_db(engine)
        results = score_all(engine, cfg, args.incluir_simulados)
    except (ScoringConfigError, SchemaOutdatedError, ValueError) as exc:
        print(f"[ERRO] {exc}")
        return 1

    if args.pais:
        results = [r for r in results if r.country == args.pais.upper()]
    if args.familia:
        results = [r for r in results if args.familia.lower() in r.family.lower()]
    if not results:
        print("Nada para pontuar. Importe dados e rode 'families.py agrupar'.")
        return 0

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        results_to_frame(results).to_csv(args.csv, index=False, sep=";", decimal=",", encoding="utf-8-sig")
        print(f"Ranking salvo em {args.csv} ({len(results)} linha(s)).")

    print(f"Janela {cfg.main_window}d | critérios sem dados: {cfg.missing_strategy}"
          f"{f' ({cfg.neutral_value})' if cfg.missing_strategy == 'neutro' else ''}\n")
    print(f"{'#':>3}  {'Pontuação':>9}  {'Confiança':>9}  {'Classificação':<26} Família")
    for pos, r in enumerate(results[: args.top], start=1):
        print(f"{pos:>3}  {r.score:>9.1f}  {r.confidence:>9.1f}  {r.classification:<26} {r.family} [{r.country}]")
        if args.detalhe:
            total = sum(cfg.weights.values())
            for c in CRITERIA:
                w = cfg.weights[c]
                if w == 0:
                    continue
                nota = r.criteria.get(c)
                nota_txt = "sem dados" if nota is None else f"nota {nota:.2f}"
                print(f"       {LABELS[c]:<20} peso {w / total:>5.0%}  {nota_txt:<10} -> {r.contributions[c]:>5.1f} pts")
            if "teto_pico_passageiro" in r.contributions:
                cap = cfg.caps["pico_passageiro"]
                print(f"       {f'Teto pico passageiro ({cap:.0f})':<38} -> {r.contributions['teto_pico_passageiro']:>5.1f} pts")
            print(f"       Qualidade dos dados: {r.quality:.2f} | fontes: {', '.join(r.sources)}")
    print("\nA pontuação resume sinais observados; NÃO é probabilidade de viralização.")
    print("Confiança baixa = poucos critérios com dados ou dados fracos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
