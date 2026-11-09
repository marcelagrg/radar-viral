"""Junta séries + indicadores numa tabela (DataFrame) pronta para exibir/exportar."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine

from radar_viral.analysis.growth import WINDOWS_DAYS, all_windows, classify, overall_stats
from radar_viral.analysis.trend_types import classify_trend_type, load_trend_config
from radar_viral.analysis.series import build_series, latest_series_per_family, load_observations


def growth_table(
    engine: Engine, main_window: int = 90, include_simulated: bool = False, all_runs: bool = False
) -> pd.DataFrame:
    """Uma linha por série, com indicadores de todas as janelas.

    Colunas de janela usam sufixos: crescimento_30d, velocidade_30d...
    'classificacao' usa a janela principal (main_window).
    """
    if main_window not in WINDOWS_DAYS:
        raise ValueError(f"janela principal deve ser uma de {WINDOWS_DAYS}")
    series = build_series(load_observations(engine, include_simulated))
    if not all_runs:
        series = latest_series_per_family(series)
    trend_cfg = load_trend_config()
    rows = []
    for s in series:
        row = {
            "familia": s.family_name,
            "familia_id": s.family_id,
            "fonte": s.source_code,
            "pais": s.country,
            "metrica": s.metric,
            "coleta": s.run_id,
            "frequencia": s.frequency,
            "lacunas": s.gaps,
            "termos": ", ".join(s.terms),
            **overall_stats(s.data),
        }
        main = None
        for ind in all_windows(s.data, s.period_days, s.metric):
            d = f"_{ind.window_days}d"
            row["crescimento" + d] = ind.growth_pct
            row["velocidade" + d] = ind.velocity_pct
            row["aceleracao" + d] = ind.acceleration_pp
            row["consistencia" + d] = ind.consistency
            row["status" + d] = classify(ind)
            if ind.window_days == main_window:
                main = ind
        t = classify_trend_type(s.data, s.period_days, s.metric, trend_cfg)
        row["tipo"] = f"{t.tipo} ({t.fase})" if t.fase else t.tipo
        row["tipo_explicacao"] = t.explicacao
        row["janela_principal"] = f"{main_window}d"
        row["classificacao"] = classify(main) if main else "janela inválida"
        rows.append(row)
    return pd.DataFrame(rows)
