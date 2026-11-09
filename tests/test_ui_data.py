"""Camada de dados do painel. Usa o trecho REAL do Google Trends e dados SIMULADOS."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from radar_viral.collectors.google_trends_csv import import_google_trends
from radar_viral.models import ObservationIn
from radar_viral.processing.product_families import group_terms
from radar_viral.scoring.config import load_scoring_config
from radar_viral.storage import repository as repo
from radar_viral.ui import data as ui

REAL = Path(__file__).parent / "fixtures" / "google_trends" / "time_series_BR_20251107-0805_20261107-0805.csv"


def seed(engine, term, values, category=None, source="google_trends"):
    src = repo.get_or_create_source(engine, source, source)
    run = repo.start_run(engine, src, "BR")
    repo.add_observations(engine, run, [
        ObservationIn(term=term, reference_date=date(2026, 1, 4) + timedelta(weeks=i), popularity_value=v,
                      popularity_metric="google_trends_0_100", category_name=category, is_simulated=True,
                      url="https://exemplo.invalid/simulado")
        for i, v in enumerate(values)
    ])
    repo.finish_run(engine, run, "success")


@pytest.fixture
def cfg():
    return load_scoring_config()


def test_banco_vazio(engine, cfg):
    d = ui.load_dashboard(engine, cfg)
    assert d.ranking.empty and d.last_update is None


def test_dados_reais(engine, cfg):
    import_google_trends(engine, REAL)
    group_terms(engine, threshold=0.45)
    d = ui.load_dashboard(engine, cfg, main_window=14)
    row = d.ranking.iloc[0]
    assert row["familia"] == "playstation" and row["ultima_data"] == date(2025, 11, 30)
    assert row["link"].startswith("https://trends.google.com.br/trends/explore?")
    assert d.last_update is not None and d.sources == ["google_trends"]
    assert d.categories.empty  # o Google Trends não informa categoria


def test_simulados_so_quando_pedidos(engine, cfg):
    seed(engine, "[SIMULADO] a", [10, 10, 11, 10, 12, 16, 22, 30])
    assert ui.load_dashboard(engine, cfg).ranking.empty
    assert len(ui.load_dashboard(engine, cfg, include_simulated=True).ranking) == 1


def test_filtros(engine, cfg):
    seed(engine, "[SIMULADO] fone", [10, 10, 11, 10, 12, 16, 22, 30], category="Eletrônicos")
    seed(engine, "[SIMULADO] garrafa", [30, 31, 29, 30, 30, 31, 30, 29], category="Casa")
    d = ui.load_dashboard(engine, cfg, main_window=30, include_simulated=True)
    r = d.ranking
    assert len(ui.filter_ranking(r)) == 2
    assert ui.filter_ranking(r, search="FONE")["familia"].tolist() == ["[SIMULADO] fone (sem família)"]
    assert ui.filter_ranking(r, categories=["Casa"])["familia"].tolist() == ["[SIMULADO] garrafa (sem família)"]
    assert ui.filter_ranking(r, classifications=["emergente"])["familia"].tolist() == ["[SIMULADO] fone (sem família)"]
    assert ui.filter_ranking(r, countries=["US"]).empty
    assert ui.filter_ranking(r, sources=["outra"]).empty
    assert ui.filter_ranking(r, min_score=99).empty


def test_categorias_em_destaque(engine, cfg):
    seed(engine, "[SIMULADO] fone", [10, 10, 11, 10, 12, 16, 22, 30], category="Eletrônicos")
    seed(engine, "[SIMULADO] garrafa", [30, 31, 29, 30, 30, 31, 30, 29], category="Casa")
    cats = ui.load_dashboard(engine, cfg, main_window=30, include_simulated=True).categories
    assert cats.iloc[0]["categoria"] == "Eletrônicos" and cats.iloc[0]["em_crescimento"] == 1


def test_tabelas_de_detalhe(engine, cfg):
    seed(engine, "[SIMULADO] fone", [10, 10, 11, 10, 12, 16, 22, 30])
    d = ui.load_dashboard(engine, cfg, main_window=30, include_simulated=True)
    key = ("[SIMULADO] fone (sem família)", "BR")
    [s] = d.latest[key]
    windows = ui.windows_table(s)
    assert windows["janela"].tolist() == ["7 dias", "14 dias", "30 dias", "90 dias"]
    assert windows.iloc[3]["classificacao"] == "dados insuficientes"
    contrib = ui.contributions_table(d.scores[key], cfg)
    assert contrib["pontos"].sum() == pytest.approx(d.scores[key].score, abs=0.1)
    assert len(ui.series_frame(s, start=date(2026, 2, 1))) == 4


def test_exportacoes_antigas_ficam_separadas(engine, cfg):
    seed(engine, "[SIMULADO] fone", [10, 20, 30, 40])
    seed(engine, "[SIMULADO] fone", [50, 60, 70, 80])
    d = ui.load_dashboard(engine, cfg, include_simulated=True)
    key = ("[SIMULADO] fone (sem família)", "BR")
    assert len(d.latest[key]) == 1 and len(d.all_series[key]) == 2


def test_tipo_de_tendencia_no_ranking(engine, cfg):
    seed(engine, "[SIMULADO] fone", [20] * 30 + [40, 38, 42, 41, 39, 44, 43, 40, 42, 45])
    seed(engine, "[SIMULADO] garrafa", [20] * 30 + [25, 60, 62])
    d = ui.load_dashboard(engine, cfg, main_window=30, include_simulated=True)
    tipos = dict(zip(d.ranking["familia"], d.ranking["tipo"]))
    assert tipos["[SIMULADO] fone (sem família)"] == "tendência sustentada (em alta)"
    assert tipos["[SIMULADO] garrafa (sem família)"] == "alta súbita (em alta)"
    so_subitas = ui.filter_ranking(d.ranking, types=["alta súbita"])
    assert so_subitas["familia"].tolist() == ["[SIMULADO] garrafa (sem família)"]
