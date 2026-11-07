"""Monta séries temporais (uma por família de produto) a partir do banco.

O QUE É UMA SÉRIE AQUI
Uma sequência de (data, valor) que pode ser comparada consigo mesma.

Regra crucial: valores RELATIVOS (Google Trends 0–100) só são comparáveis
dentro da MESMA exportação — o 100 de um arquivo não é o 100 de outro.
Por isso, para métricas relativas, cada coleta (run) vira uma série
separada. Métricas absolutas (ex.: volume de buscas) podem juntar coletas.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine, select

from radar_viral.storage.schema import observations, product_families, sources, term_families

RELATIVE_METRICS = {"google_trends_0_100"}
FREQUENCIES = {1: "diária", 7: "semanal", 30: "mensal"}


@dataclass
class Series:
    family_id: int | None
    family_name: str
    source_code: str
    country: str
    metric: str
    run_id: int | None          # preenchido só para métricas relativas
    terms: list[str]
    data: pd.Series             # índice = data (Timestamp), valores = float
    period_days: int | None     # 1, 7, 30... (None se há só 1 ponto)
    gaps: int                   # períodos faltando entre a primeira e a última data

    @property
    def frequency(self) -> str:
        if self.period_days is None:
            return "indefinida"
        return FREQUENCIES.get(self.period_days, f"a cada {self.period_days} dias")


def load_observations(engine: Engine, include_simulated: bool = False) -> pd.DataFrame:
    """Observações com valor numérico + família, como DataFrame do Pandas."""
    query = (
        select(
            observations.c.run_id,
            observations.c.country,
            observations.c.term,
            observations.c.reference_date,
            observations.c.collected_at,
            observations.c.popularity_value,
            observations.c.popularity_metric,
            observations.c.search_volume,
            sources.c.code.label("source_code"),
            term_families.c.family_id,
            product_families.c.name.label("family_name"),
        )
        .join(sources, sources.c.id == observations.c.source_id)
        # outerjoin = LEFT JOIN: mantém termos que ainda não têm família
        .outerjoin(term_families, term_families.c.term == observations.c.term)
        .outerjoin(product_families, product_families.c.id == term_families.c.family_id)
    )
    if not include_simulated:
        query = query.where(observations.c.is_simulated.is_(False))
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    if df.empty:
        return df

    # Valor analisado: popularidade se existir; senão, volume de buscas.
    df["metric"] = df["popularity_metric"].where(df["popularity_value"].notna(), "search_volume")
    df["value"] = df["popularity_value"].fillna(df["search_volume"])
    df = df[df["value"].notna()].copy()
    # Data do ponto: data de referência; para coletas "ao vivo", a data da coleta.
    collected = pd.to_datetime(df["collected_at"], utc=True).dt.tz_localize(None).dt.normalize()
    df["date"] = pd.to_datetime(df["reference_date"]).fillna(collected)
    df["family_name"] = df["family_name"].fillna(df["term"] + " (sem família)")
    return df


def infer_period_days(dates: pd.DatetimeIndex) -> int | None:
    """Intervalo típico entre pontos (mediana), arredondado para 1/7/30 dias."""
    if len(dates) < 2:
        return None
    median = pd.Series(dates).diff().dt.days.median()
    for known in (1, 7, 30):
        if abs(median - known) <= (0 if known == 1 else 3):
            return known
    return int(round(median))


def count_gaps(dates: pd.DatetimeIndex, period_days: int | None) -> int:
    if period_days is None or period_days == 30 or len(dates) < 2:
        return 0  # meses têm tamanhos diferentes; não estimamos lacunas
    expected = (dates[-1] - dates[0]).days // period_days + 1
    return max(0, expected - len(dates))


def build_series(df: pd.DataFrame) -> list[Series]:
    """Agrupa as observações em séries comparáveis.

    Dentro de uma série, valores de vários termos da mesma família na mesma
    data são SOMADOS. Para o Google Trends isso só vale porque termos da
    mesma exportação compartilham a mesma escala.
    """
    if df.empty:
        return []
    df = df.copy()
    df["series_run"] = df["run_id"].where(df["metric"].isin(RELATIVE_METRICS), -1)
    keys = ["family_name", "source_code", "country", "metric", "series_run"]
    result = []
    for key, group in df.groupby(keys, sort=True, dropna=False):
        family_name, source_code, country, metric, series_run = key
        data = group.groupby("date")["value"].sum().sort_index().astype(float)
        dates = pd.DatetimeIndex(data.index)
        period = infer_period_days(dates)
        fam_ids = group["family_id"].dropna().unique()
        result.append(
            Series(
                family_id=int(fam_ids[0]) if len(fam_ids) else None,
                family_name=family_name,
                source_code=source_code,
                country=country,
                metric=metric,
                run_id=None if series_run == -1 else int(series_run),
                terms=sorted(group["term"].unique()),
                data=data,
                period_days=period,
                gaps=count_gaps(dates, period),
            )
        )
    return result


def latest_series_per_family(series: list[Series]) -> list[Series]:
    """Para cada família/fonte/país/métrica, fica a série mais recente
    (para o Google Trends, a exportação com a data final mais nova)."""
    best: dict[tuple, Series] = {}
    for s in series:
        key = (s.family_name, s.source_code, s.country, s.metric)
        current = best.get(key)
        if current is None or (s.data.index[-1], s.run_id or 0) > (current.data.index[-1], current.run_id or 0):
            best[key] = s
    return sorted(best.values(), key=lambda s: s.family_name)
