"""Executa o painel de verdade com o AppTest do Streamlit (sem navegador).
Dados: trecho REAL do Google Trends + dados SIMULADOS."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from radar_viral.collectors.google_trends_csv import import_google_trends
from radar_viral.collectors.csv_importer import import_csv
from radar_viral.processing.product_families import group_terms
from radar_viral.storage.database import get_engine, init_db

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "dashboard" / "app.py")
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'painel.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def by_label(widgets, label):
    """Busca um campo pelo rótulo (mais robusto que depender da ordem na tela)."""
    return next(w for w in widgets if w.label == label)


def run_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_painel_sem_dados(db_url):
    at = run_app()
    assert any("Ainda não há dados" in i.value for i in at.info)


def test_painel_com_dados_reais(db_url):
    engine = get_engine(db_url)
    init_db(engine)
    import_google_trends(engine, FIX / "google_trends" / "time_series_BR_20251107-0805_20261107-0805.csv")
    group_terms(engine, threshold=0.45)
    engine.dispose()

    at = run_app()
    assert at.title[0].value == "📡 Radar Viral"
    assert [t.label for t in at.tabs] == ["Ranking", "Emergentes", "Em crescimento", "Em desaceleração",
                                          "Categorias", "Detalhes"]
    assert by_label(at.selectbox, "Família").value == "playstation [BR]"  # página de detalhes
    assert [m.label for m in at.metric] == ["Pontuação", "Confiança", "Qualidade dos dados"]
    assert not at.warning                                   # sem aviso de simulados

    by_label(at.selectbox, "Janela de análise").select(14).run()       # muda a janela
    assert not at.exception


def test_painel_com_simulados_mostra_aviso(db_url):
    engine = get_engine(db_url)
    init_db(engine)
    import_csv(engine, FIX / "exemplo_simulado.csv", source_code="teste", simulated=True)
    engine.dispose()

    at = run_app()
    by_label(at.toggle, "Incluir dados SIMULADOS").set_value(True).run()
    assert not at.exception
    assert any("SIMULADOS" in w.value for w in at.warning)


def test_adicionar_link_pelo_painel(db_url):
    """Preenche o formulário 'Adicionar link de produto' e confere no banco."""
    from radar_viral.storage import repository as repo

    engine = get_engine(db_url)
    init_db(engine)
    import_google_trends(engine, FIX / "google_trends" / "time_series_BR_20251107-0805_20261107-0805.csv")
    group_terms(engine, threshold=0.45)

    at = run_app()
    assert any(s.value == "Onde comprar" for s in at.subheader)
    by_label(at.selectbox, "Marketplace").select("shopee")
    by_label(at.text_input, "Link do produto (https://...)").input("https://shopee.com.br/produto-teste")
    by_label(at.button, "Salvar link").click().run()
    assert not at.exception
    [link] = repo.list_links(engine)
    assert link["marketplace"] == "shopee" and link["family_name"] == "playstation"

    # link de outro site é recusado com mensagem, sem quebrar o painel
    by_label(at.selectbox, "Marketplace").select("amazon")
    by_label(at.text_input, "Link do produto (https://...)").input("https://shopee.com.br/outro")
    by_label(at.button, "Salvar link").click().run()
    assert any("não é do Amazon" in e.value for e in at.error)
    assert len(repo.list_links(engine)) == 1
    engine.dispose()
