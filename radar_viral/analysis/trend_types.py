"""Tipos de tendência (Etapa 11): sustentada, alta súbita (e sazonal, futura).

Diferente das classificações da Etapa 5 (que comparam duas janelas), aqui se
olha o FORMATO da série inteira: quando a alta começou, quanto subiu, há
quanto tempo dura e se continua perto do pico.

Funções puras (sem banco). Limites em config/tendencias.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from radar_viral.analysis.growth import DEFAULT_MIN_BASE, MIN_BASE
from radar_viral.config import PROJECT_ROOT

DEFAULT_PATH = PROJECT_ROOT / "config" / "tendencias.toml"

SUSTENTADA = "tendência sustentada"
SUBITA = "alta súbita"
SEM_TIPO = "sem tendência definida"
INSUFICIENTE = "dados insuficientes"
FASE_EM_ALTA, FASE_CAINDO, FASE_PERDENDO_FORCA = "em alta", "já caindo", "perdendo força"


class TrendConfigError(ValueError):
    """config/tendencias.toml inválido."""


@dataclass(frozen=True)
class TrendConfig:
    base_weeks: int = 12
    above_base_pct: float = 50.0
    min_fraction_above: float = 0.8
    sustained_min_weeks: int = 8
    sustained_max_drop_pct: float = 30.0
    sudden_multiplier: float = 2.0
    sudden_max_weeks: int = 3
    falling_drop_pct: float = 40.0


def load_trend_config(path: Path | None = None) -> TrendConfig:
    path = Path(path or DEFAULT_PATH)
    if not path.is_file():
        raise TrendConfigError(f"arquivo de configuração não encontrado: {path}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TrendConfigError(f"erro de sintaxe em {path.name}: {exc}") from None
    return parse_trend_config(raw)


def parse_trend_config(raw: dict) -> TrendConfig:
    def get(section, key, default, kind, lo, hi):
        value = raw.get(section, {}).get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise TrendConfigError(f"[{section}] {key} deve ser um número entre {lo} e {hi}")
        if kind is int and value != int(value):
            raise TrendConfigError(f"[{section}] {key} deve ser um número inteiro")
        return kind(value)

    return TrendConfig(
        base_weeks=get("linha_de_base", "semanas", 12, int, 2, 104),
        above_base_pct=get("alta", "acima_da_base_pct", 50, float, 1, 1000),
        min_fraction_above=get("alta", "fracao_minima_acima", 0.8, float, 0.5, 1),
        sustained_min_weeks=get("sustentada", "semanas_minimas", 8, int, 1, 104),
        sustained_max_drop_pct=get("sustentada", "queda_maxima_do_pico_pct", 30, float, 0, 100),
        sudden_multiplier=get("subita", "multiplicador_minimo", 2.0, float, 1.01, 100),
        sudden_max_weeks=get("subita", "semanas_para_atingir", 3, int, 1, 52),
        falling_drop_pct=get("subita", "queda_fase_caindo_pct", 40, float, 1, 100),
    )


@dataclass
class TrendType:
    tipo: str
    fase: str | None = None
    explicacao: str = ""
    linha_de_base: float | None = None
    inicio_alta: pd.Timestamp | None = None
    semanas_em_alta: float | None = None
    ganho_pct: float | None = None        # média das últimas semanas vs. linha de base
    pico: float | None = None
    data_pico: pd.Timestamp | None = None
    queda_do_pico_pct: float | None = None


def _periods(weeks: float, period_days: int) -> int:
    return max(1, round(weeks * 7 / period_days))


def find_elevated_start(values: np.ndarray, base_n: int, factor: float, min_frac: float, floor: float):
    """Índice onde começa o período de alta que vai até o fim da série (ou None).

    Para cada início candidato k: base = mediana dos base_n pontos anteriores
    (nunca menor que 'floor'); o período k..fim é "alta" se o ponto k e pelo
    menos min_frac dos pontos estão >= factor × base. Fica o k mais antigo
    válido — ou seja, o período de alta mais longo.
    Devolve (k, base) ou (None, None).
    """
    n = len(values)
    best = (None, None)
    for k in range(n - 1, base_n - 1, -1):  # do fim para o começo
        base = max(float(np.median(values[k - base_n : k])), floor)
        threshold = factor * base
        window = values[k:]
        if values[k] >= threshold and (window >= threshold).mean() >= min_frac:
            best = (k, base)
    return best


def classify_trend_type(
    data: pd.Series, period_days: int | None, metric: str | None = None, cfg: TrendConfig | None = None
) -> TrendType:
    cfg = cfg or TrendConfig()
    if not period_days or period_days > 7:
        return TrendType(INSUFICIENTE, explicacao="requer dados semanais ou diários (export de 12 meses ou 30 dias)")
    values = data.to_numpy(dtype=float)
    base_n = _periods(cfg.base_weeks, period_days)
    min_weeks = cfg.sustained_min_weeks
    if len(values) < base_n + 2:
        weeks_needed = cfg.base_weeks + 2 * period_days / 7
        return TrendType(INSUFICIENTE, explicacao=f"precisa de pelo menos ~{weeks_needed:.0f} semanas de dados")

    floor = MIN_BASE.get(metric or "", DEFAULT_MIN_BASE)  # evita "+300%" sobre quase nada
    factor = 1 + cfg.above_base_pct / 100
    k, base = find_elevated_start(values, base_n, factor, cfg.min_fraction_above, floor)
    dates = data.index
    recent_n = min(_periods(min_weeks, period_days), len(values))

    if k is not None:
        elevated = values[k:]
        peak_pos = int(np.argmax(elevated))
        peak = float(elevated[peak_pos])
        drop = (values[-1] - peak) / peak * 100
        weeks_up = len(elevated) * period_days / 7
        gain = (float(np.mean(values[-recent_n:])) / base - 1) * 100
        common = dict(linha_de_base=base, inicio_alta=dates[k], semanas_em_alta=weeks_up, ganho_pct=gain,
                      pico=peak, data_pico=dates[k + peak_pos], queda_do_pico_pct=drop)
        reach = values[k : k + _periods(cfg.sudden_max_weeks, period_days)]
        sudden = reach.max() >= cfg.sudden_multiplier * base

        if weeks_up >= min_weeks:
            # Sua definição ("continua em alta") é a fase "em alta". Se já caiu mais
            # que o permitido desde o pico, a alta foi duradoura mas está perdendo força.
            fase = FASE_EM_ALTA if drop >= -cfg.sustained_max_drop_pct else FASE_PERDENDO_FORCA
            return TrendType(SUSTENTADA, fase=fase, explicacao=(
                f"em alta há {weeks_up:.0f} semanas (desde {dates[k]:%d/%m/%Y}); "
                f"{gain:+.0f}% acima da linha de base ({base:.1f}); {abs(drop):.0f}% abaixo do pico"), **common)
        if sudden and weeks_up < min_weeks:
            fase = FASE_CAINDO if drop <= -cfg.falling_drop_pct else FASE_EM_ALTA
            return TrendType(SUBITA, fase=fase, explicacao=(
                f"chegou a {reach.max() / base:.1f}× a linha de base ({base:.1f}) em até "
                f"{cfg.sudden_max_weeks} semanas, a partir de {dates[k]:%d/%m/%Y}; "
                f"em alta há {weeks_up:.0f} semana(s); {abs(drop):.0f}% abaixo do pico"), **common)

    # Pico súbito que JÁ VOLTOU para perto da base (não há período de alta no fim):
    # olha as últimas semanas contra a base anterior a elas.
    if len(values) >= base_n + recent_n:
        recent = values[-recent_n:]
        base_before = max(float(np.median(values[-(recent_n + base_n) : -recent_n])), floor)
        peak_pos = int(np.argmax(recent))
        peak = float(recent[peak_pos])
        drop = (values[-1] - peak) / peak * 100 if peak else 0.0
        if peak >= cfg.sudden_multiplier * base_before and drop <= -cfg.falling_drop_pct:
            when = dates[len(values) - recent_n + peak_pos]
            return TrendType(SUBITA, fase=FASE_CAINDO, linha_de_base=base_before, pico=peak, data_pico=when,
                             queda_do_pico_pct=drop, explicacao=(
                                 f"pico de {peak / base_before:.1f}× a linha de base ({base_before:.1f}) "
                                 f"em {when:%d/%m/%Y}; já caiu {abs(drop):.0f}% desde então"))

    return TrendType(SEM_TIPO, explicacao="sem alta sustentada nem súbita em relação à linha de base")
