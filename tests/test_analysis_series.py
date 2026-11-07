"""Montagem de séries a partir do banco. Usa o trecho REAL do Google Trends
(tests/fixtures) e dados SIMULADOS."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from radar_viral.analysis import series as sr
from radar_viral.analysis.report import growth_table
from radar_viral.collectors.google_trends_csv import import_google_trends
from radar_viral.models import ObservationIn
from radar_viral.processing.product_families import group_terms
from radar_viral.storage import repository as repo

REAL = Path(__file__).parent / "fixtures" / "google_trends" / "time_series_BR_20251107-0805_20261107-0805.csv"


def seed_trends_run(engine, values, terms=("[SIMULADO] fone",), start=date(2026, 1, 4)):
    """Simula uma exportação do Google Trends (uma coleta, escala relativa)."""
    src = repo.get_or_create_source(engine, "google_trends", "Google Trends")
    run = repo.start_run(engine, src, "BR")
    items = [
        ObservationIn(term=t, reference_date=start + timedelta(weeks=i), popularity_value=v,
                      popularity_metric="google_trends_0_100", is_simulated=True)
        for t in terms for i, v in enumerate(values)
    ]
    repo.add_observations(engine, run, items)
    repo.finish_run(engine, run, "success")
    return run


def test_frequencia_inferida():
    semanal = pd.DatetimeIndex(pd.date_range("2026-01-04", periods=5, freq="7D"))
    diaria = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=5, freq="D"))
    assert sr.infer_period_days(semanal) == 7 and sr.infer_period_days(diaria) == 1
    assert sr.infer_period_days(semanal[:1]) is None


def test_lacunas():
    datas = pd.DatetimeIndex(["2026-01-04", "2026-01-11", "2026-01-25"])  # falta 18/01
    assert sr.count_gaps(datas, 7) == 1


def test_trecho_real_vira_uma_serie(engine):
    import_google_trends(engine, REAL)
    group_terms(engine, threshold=0.45)
    series = sr.build_series(sr.load_observations(engine))
    assert len(series) == 1
    s = series[0]
    assert s.family_name == "playstation" and s.frequency == "semanal" and s.gaps == 0
    assert s.data.tolist() == [59, 68, 99, 100, 83]


def test_exportacoes_diferentes_nao_se_misturam(engine):
    """Duas exportações = duas escalas = duas séries."""
    seed_trends_run(engine, [10, 20, 30])
    seed_trends_run(engine, [50, 60, 70], start=date(2026, 1, 18))
    series = sr.build_series(sr.load_observations(engine, include_simulated=True))
    assert len(series) == 2
    latest = sr.latest_series_per_family(series)
    assert len(latest) == 1 and latest[0].data.tolist() == [50, 60, 70]


def test_termos_da_mesma_familia_sao_somados(engine):
    seed_trends_run(engine, [10, 20], terms=("[SIMULADO] fone bluetooth", "[SIMULADO] fones bluetooth"))
    group_terms(engine, threshold=0.45, include_simulated=True)
    [s] = sr.build_series(sr.load_observations(engine, include_simulated=True))
    assert s.data.tolist() == [20, 40] and len(s.terms) == 2


def test_tabela_completa(engine):
    seed_trends_run(engine, [10, 10, 11, 10, 12, 16, 22, 30])
    table = growth_table(engine, main_window=30, include_simulated=True)
    row = table.iloc[0]
    assert row["classificacao"] == "emergente"
    assert row["status_7d"] != "dados insuficientes"
    assert row["status_90d"] == "dados insuficientes"
    assert row["familia"].endswith("(sem família)")


def test_janela_invalida(engine):
    with pytest.raises(ValueError):
        growth_table(engine, main_window=45)


def test_banco_vazio(engine):
    assert growth_table(engine).empty
