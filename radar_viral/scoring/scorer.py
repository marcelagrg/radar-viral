"""Cálculo da pontuação de potencial de tendência.

pontuação = 100 × Σ (peso_i × nota_i) / Σ peso_i         (nota_i entre 0 e 1)

- Critérios sem dados: valor neutro OU excluídos (ver config).
- Confiança (0–100) é separada da pontuação: quanto do peso total tem dados
  reais × qualidade dos dados. Uma nota 70 com confiança 20 vale pouco.

IMPORTANTE: a pontuação resume sinais observados no passado. Não é uma
probabilidade de viralização.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from radar_viral.analysis.growth import WindowIndicators, classify, periods_for_window, window_indicators
from radar_viral.analysis.series import Series, build_series, latest_series_per_family, load_observations
from radar_viral.scoring.config import CRITERIA, ScoringConfig

GROWING = {"emergente", "em crescimento", "crescimento desacelerando"}


def normalize(value: float | None, lo: float, hi: float) -> float | None:
    """Escala linear limitada a [0, 1].  normalize(25, -50, 100) -> 0.5"""
    if value is None or np.isnan(value):
        return None
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def _mean(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return float(np.mean(known)) if known else None


# ---------------------------------------------------------------- critérios

def series_criteria(ind: WindowIndicators, cfg: ScoringConfig) -> dict[str, float | None]:
    """Notas 0–1 dos critérios que vêm de UMA série temporal."""
    if not ind.available:
        return {"velocidade": None, "aceleracao": None, "persistencia": None}
    r = cfg.ranges
    velocidade = _mean([
        normalize(ind.growth_pct, *r["crescimento_pct"]),
        normalize(ind.velocity_pct, *r["velocidade_pct_semana"]),
    ])
    aceleracao = normalize(ind.acceleration_pp, *r["aceleracao_pp"])
    # Persistência: sobe de forma contínua (consistência) E continua perto do
    # pico (1 + queda/100: -40% do pico -> 0,6). Pico passageiro tira nota baixa.
    near_peak = None if ind.peak_drop_pct is None else 1 + ind.peak_drop_pct / 100
    persistencia = _mean([ind.consistency, near_peak])
    return {"velocidade": velocidade, "aceleracao": aceleracao, "persistencia": persistencia}


def data_quality(s: Series, ind: WindowIndicators) -> float:
    """Qualidade dos dados de 0 a 1 = suficiência × completude × força do sinal.

    - suficiência: pontos / (4 × períodos da janela); 1 = duas comparações completas
    - completude: 1 − lacunas / (pontos + lacunas)
    - força do sinal: 0,5 quando a base é baixa
    """
    n = periods_for_window(ind.window_days, s.period_days)
    if not ind.available or not n:
        return 0.0
    points = len(s.data)
    sufficiency = min(1.0, points / (4 * n))
    completeness = 1 - s.gaps / (points + s.gaps)
    strength = 0.5 if ind.low_base else 1.0
    return sufficiency * completeness * strength


# ---------------------------------------------------------------- pontuação

@dataclass
class ScoreResult:
    family: str
    country: str
    score: float
    confidence: float
    classification: str
    sources: list[str]
    criteria: dict[str, float | None]        # nota 0–1 (None = sem dados)
    contributions: dict[str, float]          # pontos que cada critério somou
    missing: list[str] = field(default_factory=list)
    quality: float = 0.0


def combine(criteria: dict[str, float | None], cfg: ScoringConfig) -> tuple[float, dict[str, float], list[str], float]:
    """Aplica os pesos. Devolve (pontuação, contribuições, ausentes, cobertura)."""
    weights = cfg.weights
    total = sum(weights.values())
    active = {c: w for c, w in weights.items() if w > 0}
    missing = [c for c in active if criteria.get(c) is None]
    coverage = sum(w for c, w in active.items() if c not in missing) / total

    if cfg.missing_strategy == "renormalizar":
        used = {c: w for c, w in active.items() if c not in missing}
        denom = sum(used.values())
        if denom == 0:
            return 0.0, {c: 0.0 for c in active}, missing, 0.0
        contributions = {c: (100 * w * criteria[c] / denom if c in used else 0.0) for c, w in active.items()}
    else:  # neutro
        contributions = {
            c: 100 * w * (criteria[c] if c not in missing else cfg.neutral_value) / total
            for c, w in active.items()
        }
    return sum(contributions.values()), contributions, missing, coverage


def score_group(family: str, country: str, series: list[Series], cfg: ScoringConfig) -> ScoreResult:
    """Pontua uma família num país, usando todas as suas séries (uma por fonte)."""
    per_source = []
    for s in series:
        ind = window_indicators(s.data, cfg.main_window, s.period_days, s.metric)
        per_source.append((s, ind, series_criteria(ind, cfg), classify(ind)))

    criteria: dict[str, float | None] = {c: None for c in CRITERIA}
    for name in ("velocidade", "aceleracao", "persistencia"):
        criteria[name] = _mean([crit[name] for _, _, crit, _ in per_source])

    sources = sorted({s.source_code for s, *_ in per_source})
    if len(sources) >= 2:  # só faz sentido comparar plataformas com 2+ fontes
        growing = {s.source_code for s, _, _, cls in per_source if cls in GROWING}
        criteria["multiplataforma"] = len(growing) / len(sources)
    # engajamento, intencao_compra, concorrencia, sazonalidade, potencial_comercial:
    # sem fonte de dados ainda -> permanecem None (ver docs/pontuacao.md)

    score, contributions, missing, coverage = combine(criteria, cfg)
    # Classificação textual: a da série com mais pontos
    main = max(per_source, key=lambda t: len(t[0].data))
    # Teto: um pico que já passou não pode parecer promissor. O corte aparece
    # como uma "contribuição" negativa, para que a soma das linhas do
    # detalhamento continue igual à pontuação.
    cap = cfg.caps.get("pico_passageiro", 100.0)
    if main[3] == "pico passageiro" and score > cap:
        contributions["teto_pico_passageiro"] = cap - score
        score = cap
    quality = _mean([data_quality(s, ind) for s, ind, _, _ in per_source]) or 0.0
    return ScoreResult(
        family=family,
        country=country,
        score=round(score, 1),
        confidence=round(100 * coverage * quality, 1),
        classification=main[3],
        sources=sources,
        criteria=criteria,
        contributions={c: round(v, 2) for c, v in contributions.items()},
        missing=missing,
        quality=round(quality, 3),
    )


def score_all(engine: Engine, cfg: ScoringConfig, include_simulated: bool = False) -> list[ScoreResult]:
    series = latest_series_per_family(build_series(load_observations(engine, include_simulated)))
    groups: dict[tuple[str, str], list[Series]] = {}
    for s in series:
        groups.setdefault((s.family_name, s.country), []).append(s)
    results = [score_group(f, c, ss, cfg) for (f, c), ss in groups.items()]
    return sorted(results, key=lambda r: (-r.score, -r.confidence, r.family))


def results_to_frame(results: list[ScoreResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        row = {
            "familia": r.family, "pais": r.country, "pontuacao": r.score, "confianca": r.confidence,
            "classificacao": r.classification, "fontes": ", ".join(r.sources),
            "qualidade_dados": r.quality, "criterios_sem_dados": ", ".join(r.missing),
        }
        for c in CRITERIA:
            row[f"nota_{c}"] = r.criteria.get(c)
            row[f"pontos_{c}"] = r.contributions.get(c)
        row["teto_pico_passageiro"] = r.contributions.get("teto_pico_passageiro", 0.0)
        rows.append(row)
    return pd.DataFrame(rows)
