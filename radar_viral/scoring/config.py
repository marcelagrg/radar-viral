"""Leitura e validação de config/pontuacao.toml.

TOML é um formato de configuração legível por humanos; o Python 3.11+ lê
com o módulo tomllib, sem instalar nada.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from radar_viral.analysis.growth import WINDOWS_DAYS
from radar_viral.config import PROJECT_ROOT

DEFAULT_PATH = PROJECT_ROOT / "config" / "pontuacao.toml"

CRITERIA = (
    "velocidade",
    "aceleracao",
    "persistencia",
    "multiplataforma",
    "engajamento",
    "intencao_compra",
    "concorrencia",
    "sazonalidade",
    "potencial_comercial",
)
NORMALIZATIONS = ("crescimento_pct", "velocidade_pct_semana", "aceleracao_pp")
STRATEGIES = ("neutro", "renormalizar")
CAPS = ("pico_passageiro",)


class ScoringConfigError(ValueError):
    """Arquivo de configuração da pontuação inválido."""


@dataclass(frozen=True)
class ScoringConfig:
    main_window: int
    missing_strategy: str
    neutral_value: float
    weights: dict[str, float]
    ranges: dict[str, tuple[float, float]]
    caps: dict[str, float]


def load_scoring_config(path: Path | None = None) -> ScoringConfig:
    path = Path(path or DEFAULT_PATH)
    if not path.is_file():
        raise ScoringConfigError(f"arquivo de configuração não encontrado: {path}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ScoringConfigError(f"erro de sintaxe em {path.name}: {exc}") from None
    return parse_scoring_config(raw)


def parse_scoring_config(raw: dict) -> ScoringConfig:
    """Valida o conteúdo já lido (separado para facilitar os testes)."""
    geral = raw.get("geral", {})
    window = geral.get("janela_principal", 90)
    if window not in WINDOWS_DAYS:
        raise ScoringConfigError(f"janela_principal deve ser uma de {WINDOWS_DAYS}, não {window!r}")
    strategy = geral.get("criterios_ausentes", "neutro")
    if strategy not in STRATEGIES:
        raise ScoringConfigError(f"criterios_ausentes deve ser um de {STRATEGIES}, não {strategy!r}")
    neutral = geral.get("valor_neutro", 0.5)
    if not isinstance(neutral, (int, float)) or not 0 <= neutral <= 1:
        raise ScoringConfigError("valor_neutro deve ser um número entre 0 e 1")

    weights_raw = raw.get("pesos", {})
    unknown = set(weights_raw) - set(CRITERIA)
    if unknown:
        raise ScoringConfigError(
            f"critério(s) desconhecido(s) em [pesos]: {', '.join(sorted(unknown))}. "
            f"Válidos: {', '.join(CRITERIA)}"
        )
    weights = {}
    for name in CRITERIA:
        w = weights_raw.get(name, 0)
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w < 0:
            raise ScoringConfigError(f"peso de {name!r} deve ser um número >= 0")
        weights[name] = float(w)
    if sum(weights.values()) == 0:
        raise ScoringConfigError("pelo menos um peso deve ser maior que zero")

    ranges = {}
    norm_raw = raw.get("normalizacao", {})
    for name in NORMALIZATIONS:
        r = norm_raw.get(name)
        if not isinstance(r, dict) or "min" not in r or "max" not in r:
            raise ScoringConfigError(f"[normalizacao.{name}] precisa de 'min' e 'max'")
        lo, hi = float(r["min"]), float(r["max"])
        if lo >= hi:
            raise ScoringConfigError(f"[normalizacao.{name}]: min deve ser menor que max")
        ranges[name] = (lo, hi)

    caps_raw = raw.get("tetos", {})
    unknown = set(caps_raw) - set(CAPS)
    if unknown:
        raise ScoringConfigError(f"teto(s) desconhecido(s): {', '.join(sorted(unknown))}")
    caps = {}
    for name in CAPS:
        v = caps_raw.get(name, 100)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 100:
            raise ScoringConfigError(f"teto {name!r} deve ser um número entre 0 e 100")
        caps[name] = float(v)

    return ScoringConfig(window, strategy, float(neutral), weights, ranges, caps)
