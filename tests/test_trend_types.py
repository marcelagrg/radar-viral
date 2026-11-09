"""Tipos de tendência. Todas as séries aqui são SIMULADAS (formatos típicos)."""

import tomllib

import pandas as pd
import pytest

from radar_viral.analysis import trend_types as tt


def w(values, freq="7D"):
    return pd.Series([float(v) for v in values], index=pd.date_range("2026-01-04", periods=len(values), freq=freq))


def kind(values, period=7, cfg=None):
    freq = f"{period}D"
    return tt.classify_trend_type(w(values, freq), period, "google_trends_0_100", cfg)


def test_sustentada_em_alta():
    t = kind([20] * 30 + [40, 38, 42, 41, 39, 44, 43, 40, 42, 45, 41, 43])
    assert (t.tipo, t.fase) == (tt.SUSTENTADA, tt.FASE_EM_ALTA)
    assert t.semanas_em_alta == 12 and t.linha_de_base == 20
    assert t.inicio_alta == pd.Timestamp("2026-01-04") + pd.Timedelta(weeks=30)


def test_sustentada_tolera_uma_semana_de_queda():
    t = kind([20] * 30 + [40, 41, 25, 42, 40, 43, 41, 44, 42, 40])  # 25 no meio
    assert t.tipo == tt.SUSTENTADA and t.semanas_em_alta == 10


def test_sustentada_perdendo_forca():
    t = kind([20] * 30 + [40, 45, 50, 60, 55, 50, 45, 40, 35, 30])
    assert (t.tipo, t.fase) == (tt.SUSTENTADA, tt.FASE_PERDENDO_FORCA)
    assert t.queda_do_pico_pct == pytest.approx(-50)


def test_alta_longa_desde_o_meio_do_ano():
    """A média da série inteira (30) esconderia esta alta; a linha de base local não."""
    t = kind([20] * 26 + [40] * 26)
    assert t.tipo == tt.SUSTENTADA and t.semanas_em_alta == 26 and t.ganho_pct == pytest.approx(100)


def test_subita_em_alta():
    t = kind([20] * 30 + [25, 60, 62])
    assert (t.tipo, t.fase) == (tt.SUBITA, tt.FASE_EM_ALTA)


def test_subita_ja_caindo():
    t = kind([20] * 30 + [25, 70, 50, 35])
    assert (t.tipo, t.fase) == (tt.SUBITA, tt.FASE_CAINDO)


def test_pico_que_ja_voltou_a_base():
    t = kind([20] * 30 + [80, 40, 22, 21, 20, 20])
    assert (t.tipo, t.fase) == (tt.SUBITA, tt.FASE_CAINDO) and t.pico == 80


def test_alta_lenta_e_curta_nao_e_subita():
    """+50% em 3 semanas, mas sem chegar ao dobro: ainda não é nenhum dos tipos."""
    t = kind([20] * 30 + [30, 31, 32])
    assert t.tipo == tt.SEM_TIPO


def test_alta_subita_que_durou_vira_sustentada():
    t = kind([20] * 30 + [60] * 9)
    assert t.tipo == tt.SUSTENTADA


@pytest.mark.parametrize("values", [[20, 21, 19, 20] * 10, [50 - i for i in range(40)]])
def test_sem_tendencia(values):
    assert kind(values).tipo == tt.SEM_TIPO


def test_base_baixa_nao_gera_alarme():
    """De 1 para 3 é '3×', mas no Trends abaixo de 5 é ruído: a base mínima é 5."""
    assert kind([1] * 30 + [3, 3, 3]).tipo == tt.SEM_TIPO


def test_dados_curtos_ou_mensais():
    assert kind([20] * 8).tipo == tt.INSUFICIENTE
    assert tt.classify_trend_type(w([20] * 40, "30D"), 30).tipo == tt.INSUFICIENTE


def test_dados_diarios_convertem_semanas():
    """30 dias de dados diários: base de 12 semanas = 84 dias -> insuficiente."""
    assert kind([20] * 30, period=1).tipo == tt.INSUFICIENTE
    t = kind([20] * 90 + [60] * 10, period=1)  # 90 dias de base, alta há 10 dias
    assert t.tipo == tt.SUBITA and t.semanas_em_alta == pytest.approx(10 / 7)


def test_config_padrao_e_ajustes():
    cfg = tt.load_trend_config()
    assert cfg == tt.TrendConfig()  # arquivo e valores padrão coincidem
    raw = tomllib.loads(tt.DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["sustentada"]["semanas_minimas"] = 12
    strict = tt.parse_trend_config(raw)
    serie = [20] * 30 + [40] * 10
    assert kind(serie).tipo == tt.SUSTENTADA
    assert kind(serie, cfg=strict).tipo != tt.SUSTENTADA  # 10 semanas < 12


@pytest.mark.parametrize(
    "section, key, value",
    [("sustentada", "semanas_minimas", 0), ("sustentada", "semanas_minimas", 8.5),
     ("subita", "multiplicador_minimo", 1), ("alta", "fracao_minima_acima", 0.2),
     ("linha_de_base", "semanas", True)],
)
def test_config_invalida(section, key, value):
    raw = tomllib.loads(tt.DEFAULT_PATH.read_text(encoding="utf-8"))
    raw[section][key] = value
    with pytest.raises(tt.TrendConfigError, match=key):
        tt.parse_trend_config(raw)
