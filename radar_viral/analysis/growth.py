"""Indicadores de crescimento de uma série temporal.

Todas as funções recebem uma pd.Series (índice = data, valores = número) e
são PURAS: não acessam o banco. Isso facilita testar e reutilizar.

JANELAS: "30 dias" vira um número de PERÍODOS conforme a frequência dos dados.
Dados semanais: 7d = 1 semana, 14d = 2, 30d ≈ 4, 90d ≈ 13. Se a janela for
menor que o intervalo entre pontos (7 dias com dados mensais), o indicador
não é calculado — não inventamos pontos.

Comparação sempre entre a janela ATUAL (últimos N períodos) e a ANTERIOR
(os N períodos imediatamente antes).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

WINDOWS_DAYS = (7, 14, 30, 90)

# Abaixo disso (na média da janela anterior), variações percentuais enganam:
# ir de 0,5 para 3 numa escala 0–100 é "+500%", mas é ruído.
MIN_BASE = {"google_trends_0_100": 5.0}
DEFAULT_MIN_BASE = 1.0

# Regras de classificação (todas em pontos percentuais). Mantidas visíveis e
# simples de propósito; serão calibradas quando houver mais dados reais.
RULES = {
    "emergente_crescimento_min": 30.0,   # crescimento da janela >= 30%
    "emergente_consistencia_min": 0.6,   # >= 60% dos períodos subindo
    "crescimento_min": 10.0,             # >= 10% = em crescimento
    "queda_max": -10.0,                  # <= -10% = em queda
    "pico_queda_max": -40.0,             # caiu >= 40% desde o pico da janela
}


@dataclass
class WindowIndicators:
    window_days: int
    periods: int | None           # quantos pontos a janela tem
    available: bool               # há dados para janela atual + anterior?
    current_mean: float | None
    previous_mean: float | None
    growth_pct: float | None      # crescimento percentual da média
    velocity_pct: float | None    # inclinação da janela atual, em % da média por semana
    acceleration_pp: float | None # velocidade atual - anterior (pontos percentuais/semana)
    consistency: float | None     # fração dos períodos da janela que subiram ou ficaram iguais
    peak_drop_pct: float | None   # último valor vs. pico da janela atual
    low_base: bool                # base pequena demais para confiar no percentual

    def as_dict(self) -> dict:
        return asdict(self)


def periods_for_window(window_days: int, period_days: int | None) -> int | None:
    if not period_days or window_days < period_days:
        return None
    return max(1, round(window_days / period_days))


def relative_slope(values: np.ndarray, period_days: int) -> float | None:
    """Inclinação da reta que melhor se ajusta aos pontos (mínimos quadrados),
    expressa em % da média por semana. Precisa de pelo menos 3 pontos.

    Exemplo: valores 10, 12, 14 (semanais) -> sobe 2 por semana; média 12 ->
    velocidade = 2/12 = 16,7% por semana.
    """
    if len(values) < 3:
        return None
    mean = float(np.mean(values))
    if mean == 0:
        return None
    slope_per_period = np.polyfit(np.arange(len(values)), values, deg=1)[0]
    return float(slope_per_period / mean * 100 * (7 / period_days))


def window_indicators(
    data: pd.Series, window_days: int, period_days: int | None, metric: str | None = None
) -> WindowIndicators:
    n = periods_for_window(window_days, period_days)
    empty = WindowIndicators(window_days, n, False, None, None, None, None, None, None, None, False)
    if n is None or len(data) < 2 * n:
        return empty

    values = data.to_numpy(dtype=float)
    current, previous = values[-n:], values[-2 * n : -n]
    cur_mean, prev_mean = float(current.mean()), float(previous.mean())
    min_base = MIN_BASE.get(metric or "", DEFAULT_MIN_BASE)

    growth = None if prev_mean == 0 else (cur_mean - prev_mean) / prev_mean * 100
    velocity = relative_slope(current, period_days)
    prev_velocity = relative_slope(previous, period_days)
    acceleration = None if velocity is None or prev_velocity is None else velocity - prev_velocity

    # Consistência: das variações período a período (incluindo a entrada na
    # janela), quantas foram >= 0? Mede se o crescimento é contínuo ou aos saltos.
    steps = np.diff(values[-(n + 1) :])
    consistency = float((steps >= 0).mean()) if len(steps) else None

    peak = float(current.max())
    peak_drop = None if peak == 0 else (current[-1] - peak) / peak * 100

    return WindowIndicators(
        window_days=window_days,
        periods=n,
        available=True,
        current_mean=cur_mean,
        previous_mean=prev_mean,
        growth_pct=growth,
        velocity_pct=velocity,
        acceleration_pp=acceleration,
        consistency=consistency,
        peak_drop_pct=peak_drop,
        low_base=prev_mean < min_base,
    )


def all_windows(data: pd.Series, period_days: int | None, metric: str | None = None) -> list[WindowIndicators]:
    return [window_indicators(data, w, period_days, metric) for w in WINDOWS_DAYS]


def classify(ind: WindowIndicators) -> str:
    """Classificação textual de UMA janela. Não é previsão: descreve o passado."""
    r = RULES
    if not ind.available:
        return "dados insuficientes"
    if ind.low_base:
        return "base baixa"
    if ind.growth_pct is None:
        return "surgiu do zero"
    g, acc, cons, drop = ind.growth_pct, ind.acceleration_pp, ind.consistency, ind.peak_drop_pct
    if g > 0 and drop is not None and drop <= r["pico_queda_max"]:
        return "pico passageiro"
    if g >= r["emergente_crescimento_min"] and (cons or 0) >= r["emergente_consistencia_min"] and (acc is None or acc > 0):
        return "emergente"
    if g >= r["crescimento_min"]:
        return "em crescimento" if acc is None or acc >= 0 else "crescimento desacelerando"
    if g <= r["queda_max"]:
        return "em queda"
    return "estável"


def overall_stats(data: pd.Series) -> dict:
    """Visão de longo prazo: popularidade ao longo de todo o período."""
    values = data.to_numpy(dtype=float)
    peak_pos = int(values.argmax())
    return {
        "pontos": len(values),
        "inicio": data.index[0].date(),
        "fim": data.index[-1].date(),
        "media": float(values.mean()),
        "pico": float(values.max()),
        "data_pico": data.index[peak_pos].date(),
        "ultimo": float(values[-1]),
        "ultimo_vs_pico_pct": None if values.max() == 0 else (values[-1] - values.max()) / values.max() * 100,
        # Sazonalidade exige pelo menos 2 ciclos completos (2 anos) para
        # separar "padrão anual" de "acaso". Não calculamos antes disso.
        "sazonalidade": "indisponível (requer 2 anos de dados)"
        if (data.index[-1] - data.index[0]).days < 730
        else "a implementar",
    }
