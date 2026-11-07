"""Monta tudo o que o painel exibe, a partir do banco.

Fica separado do Streamlit (dashboard/app.py) por dois motivos:
1. pode ser testado com pytest, sem abrir navegador;
2. se um dia o painel for trocado por outra ferramenta, esta parte continua.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

import pandas as pd
from sqlalchemy import Engine

from radar_viral.analysis.growth import WINDOWS_DAYS, all_windows, classify, window_indicators
from radar_viral.analysis.series import Series, build_series, latest_series_per_family, load_observations
from radar_viral.scoring.config import ScoringConfig
from radar_viral.scoring.scorer import ScoreResult, score_series
from radar_viral.storage import repository as repo

# Agrupamento das classificações para as abas do painel
TAB_GROUPS = {
    "Emergentes": {"emergente"},
    "Em crescimento": {"em crescimento"},
    "Em desaceleração": {"crescimento desacelerando", "em queda", "pico passageiro"},
}

METRIC_LABELS = {
    "google_trends_0_100": "Interesse relativo (0–100, Google Trends)",
    "search_volume": "Volume de buscas",
}

Key = tuple[str, str]  # (família, país)


@dataclass
class DashboardData:
    ranking: pd.DataFrame
    scores: dict[Key, ScoreResult]
    latest: dict[Key, list[Series]]        # série mais recente por fonte
    all_series: dict[Key, list[Series]]    # todas as exportações (escalas diferentes!)
    links: dict[Key, str]
    categories: pd.DataFrame
    last_update: datetime | None
    main_window: int
    sources: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    has_simulated: bool = False


def _family_categories(df: pd.DataFrame) -> dict[Key, str]:
    """Categoria de cada família = a mais frequente entre as suas observações."""
    with_cat = df[df["category_name"].notna() & (df["category_name"] != "")]
    if with_cat.empty:
        return {}
    mode = with_cat.groupby(["family_name", "country"])["category_name"].agg(lambda s: s.mode().iloc[0])
    return {k: v for k, v in mode.items()}


def _latest_links(df: pd.DataFrame) -> dict[Key, str]:
    """Link original mais recente de cada família (para conferir na fonte)."""
    with_url = df[df["url"].notna()].sort_values("date")
    return {k: g["url"].iloc[-1] for k, g in with_url.groupby(["family_name", "country"])}


def load_dashboard(
    engine: Engine, cfg: ScoringConfig, main_window: int | None = None, include_simulated: bool = False
) -> DashboardData:
    cfg = replace(cfg, main_window=main_window or cfg.main_window)
    df = load_observations(engine, include_simulated)
    last_update = repo.last_successful_run_at(engine)
    empty = DashboardData(pd.DataFrame(), {}, {}, {}, {}, pd.DataFrame(), last_update, cfg.main_window)
    if df.empty:
        return empty

    every = build_series(df)
    latest_list = latest_series_per_family(every)
    results = score_series(latest_list, cfg)

    latest: dict[Key, list[Series]] = {}
    for s in latest_list:
        latest.setdefault((s.family_name, s.country), []).append(s)
    all_series: dict[Key, list[Series]] = {}
    for s in every:
        all_series.setdefault((s.family_name, s.country), []).append(s)
    links = _latest_links(df)
    categories = _family_categories(df)

    rows = []
    for r in results:
        key = (r.family, r.country)
        main = max(latest[key], key=lambda s: len(s.data))
        ind = window_indicators(main.data, cfg.main_window, main.period_days, main.metric)
        rows.append({
            "familia": r.family,
            "pais": r.country,
            "pontuacao": r.score,
            "confianca": r.confidence,
            "classificacao": r.classification,
            "crescimento_pct": ind.growth_pct,
            "categoria": categories.get(key),
            "fontes": ", ".join(r.sources),
            "ultima_data": main.data.index[-1].date(),
            "link": links.get(key),
        })
    ranking = _numeric(pd.DataFrame(rows), ["pontuacao", "confianca", "crescimento_pct"])

    return DashboardData(
        ranking=ranking,
        scores={(r.family, r.country): r for r in results},
        latest=latest,
        all_series=all_series,
        links=links,
        categories=category_summary(ranking),
        last_update=last_update,
        main_window=cfg.main_window,
        sources=sorted(df["source_code"].unique()),
        countries=sorted(df["country"].unique()),
        has_simulated=include_simulated,
    )


def _numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """None -> NaN em colunas numéricas: o Pandas trata NaN como número ausente
    (a coluna fica float, não 'object'), e as tabelas não exibem o texto 'None'."""
    for col in columns:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def filter_ranking(
    ranking: pd.DataFrame,
    countries: list[str] | None = None,
    sources: list[str] | None = None,
    classifications: list[str] | None = None,
    categories: list[str] | None = None,
    min_score: float = 0,
    min_confidence: float = 0,
    search: str = "",
) -> pd.DataFrame:
    """Aplica os filtros da barra lateral. Lista vazia/None = sem filtro."""
    if ranking.empty:
        return ranking
    mask = (ranking["pontuacao"] >= min_score) & (ranking["confianca"] >= min_confidence)
    if countries:
        mask &= ranking["pais"].isin(countries)
    if sources:
        mask &= ranking["fontes"].apply(lambda f: any(s in f.split(", ") for s in sources))
    if classifications:
        mask &= ranking["classificacao"].isin(classifications)
    if categories:
        mask &= ranking["categoria"].isin(categories)
    if search.strip():
        mask &= ranking["familia"].str.contains(search.strip(), case=False, regex=False)
    return ranking[mask].reset_index(drop=True)


def category_summary(ranking: pd.DataFrame) -> pd.DataFrame:
    """Categorias com mais sinais de crescimento. Vazio se nenhuma fonte informa categoria."""
    if ranking.empty or ranking["categoria"].isna().all():
        return pd.DataFrame()
    growing = TAB_GROUPS["Emergentes"] | TAB_GROUPS["Em crescimento"]
    df = ranking[ranking["categoria"].notna()].copy()
    df["crescendo"] = df["classificacao"].isin(growing)
    out = (
        df.groupby("categoria")
        .agg(familias=("familia", "count"), em_crescimento=("crescendo", "sum"), pontuacao_media=("pontuacao", "mean"))
        .reset_index()
        .sort_values(["em_crescimento", "pontuacao_media"], ascending=False)
    )
    out["pontuacao_media"] = out["pontuacao_media"].round(1)
    return out.reset_index(drop=True)


def windows_table(s: Series) -> pd.DataFrame:
    """Comparação entre períodos: uma linha por janela (7/14/30/90 dias)."""
    rows = []
    for ind in all_windows(s.data, s.period_days, s.metric):
        rows.append({
            "janela": f"{ind.window_days} dias",
            "semanas_ou_pontos": ind.periods,
            "media_atual": ind.current_mean,
            "media_anterior": ind.previous_mean,
            "crescimento_pct": ind.growth_pct,
            "velocidade_pct_sem": ind.velocity_pct,
            "aceleracao_pp": ind.acceleration_pp,
            "consistencia": ind.consistency,
            "classificacao": classify(ind),
        })
    return _numeric(pd.DataFrame(rows), ["media_atual", "media_anterior", "crescimento_pct",
                                         "velocidade_pct_sem", "aceleracao_pp", "consistencia"])


def contributions_table(result: ScoreResult, cfg: ScoringConfig) -> pd.DataFrame:
    total = sum(cfg.weights.values())
    rows = [
        {
            "criterio": c,
            "peso_pct": 100 * w / total,
            "nota": result.criteria.get(c),
            "pontos": result.contributions.get(c, 0.0),
            "sem_dados": c in result.missing,
        }
        for c, w in cfg.weights.items() if w > 0
    ]
    if "teto_pico_passageiro" in result.contributions:
        rows.append({"criterio": "teto: pico passageiro", "peso_pct": None, "nota": None,
                     "pontos": result.contributions["teto_pico_passageiro"], "sem_dados": False})
    return _numeric(pd.DataFrame(rows), ["peso_pct", "nota", "pontos"])


def series_frame(s: Series, start=None, end=None) -> pd.DataFrame:
    df = pd.DataFrame({"data": s.data.index, "valor": s.data.to_numpy()})
    if start is not None:
        df = df[df["data"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["data"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


__all__ = ["WINDOWS_DAYS", "load_dashboard", "filter_ranking", "windows_table", "contributions_table",
           "series_frame", "category_summary", "TAB_GROUPS", "METRIC_LABELS", "DashboardData"]
