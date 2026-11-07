"""Testes dos indicadores. Séries montadas aqui são SIMULADAS."""

import numpy as np
import pandas as pd
import pytest

from radar_viral.analysis import growth as g


def weekly(values, start="2026-01-04"):
    return pd.Series([float(v) for v in values], index=pd.date_range(start, periods=len(values), freq="7D"))


@pytest.mark.parametrize(
    "window, period, expected",
    [(7, 7, 1), (14, 7, 2), (30, 7, 4), (90, 7, 13), (30, 1, 30), (7, 30, None), (30, None, None)],
)
def test_janela_em_periodos(window, period, expected):
    assert g.periods_for_window(window, period) == expected


def test_velocidade_exemplo_da_documentacao():
    # 10, 12, 14: sobe 2/semana; média 12 -> 16,67% por semana
    assert g.relative_slope(np.array([10.0, 12, 14]), 7) == pytest.approx(16.667, rel=1e-3)
    assert g.relative_slope(np.array([10.0, 12]), 7) is None  # < 3 pontos


def test_crescimento_simples():
    ind = g.window_indicators(weekly([10, 10, 10, 10, 20, 20, 20, 20]), 30, 7, "google_trends_0_100")
    assert ind.periods == 4 and ind.available
    assert ind.growth_pct == pytest.approx(100.0)
    assert ind.previous_mean == 10 and ind.current_mean == 20


def test_dados_insuficientes():
    ind = g.window_indicators(weekly([10, 20, 30]), 30, 7)
    assert not ind.available and g.classify(ind) == "dados insuficientes"


def test_emergente():
    serie = weekly([10, 10, 11, 10, 12, 16, 22, 30])  # crescente e acelerando
    ind = g.window_indicators(serie, 30, 7, "google_trends_0_100")
    assert ind.acceleration_pp > 0 and ind.consistency == 1.0
    assert g.classify(ind) == "emergente"


def test_crescimento_desacelerando():
    serie = weekly([10, 14, 18, 22, 24, 25, 25.5, 26])  # ainda acima, mas freando
    ind = g.window_indicators(serie, 30, 7, "google_trends_0_100")
    assert ind.growth_pct > 10 and ind.acceleration_pp < 0
    assert g.classify(ind) == "crescimento desacelerando"


def test_pico_passageiro_nao_e_tendencia():
    serie = weekly([20, 20, 20, 20, 25, 100, 40, 30])  # explodiu e caiu
    ind = g.window_indicators(serie, 30, 7, "google_trends_0_100")
    assert ind.growth_pct > 0 and ind.peak_drop_pct <= -40
    assert g.classify(ind) == "pico passageiro"


def test_queda_e_estavel():
    assert g.classify(g.window_indicators(weekly([40, 40, 40, 40, 30, 28, 26, 25]), 30, 7, "x")) == "em queda"
    assert g.classify(g.window_indicators(weekly([30, 31, 29, 30, 30, 31, 30, 29]), 30, 7, "x")) == "estável"


def test_base_baixa_nao_vira_emergente():
    serie = weekly([0.5, 0.5, 0.5, 0.5, 1, 2, 3, 4])  # "+400%" sobre quase nada
    ind = g.window_indicators(serie, 30, 7, "google_trends_0_100")
    assert ind.growth_pct > 300 and ind.low_base
    assert g.classify(ind) == "base baixa"


def test_surgiu_do_zero():
    ind = g.window_indicators(weekly([0, 0, 0, 0, 5, 10, 15, 20]), 30, 7, "search_volume")
    assert ind.growth_pct is None
    # base 0 < mínimo -> "base baixa" tem prioridade sobre "surgiu do zero"
    assert g.classify(ind) == "base baixa"


def test_janela_menor_que_frequencia():
    mensal = pd.Series([10.0, 20, 30, 40], index=pd.date_range("2026-01-01", periods=4, freq="MS"))
    assert not g.window_indicators(mensal, 7, 30).available


def test_estatisticas_gerais():
    stats = g.overall_stats(weekly([10, 50, 100, 80]))
    assert stats["pico"] == 100 and stats["ultimo_vs_pico_pct"] == pytest.approx(-20.0)
    assert stats["sazonalidade"].startswith("indisponível")
