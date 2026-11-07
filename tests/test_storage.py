"""Testes da camada de armazenamento.

ATENÇÃO: todos os dados aqui são SIMULADOS (is_simulated=True) e existem
apenas para verificar o funcionamento do código.
"""

import pytest
from sqlalchemy import inspect

from radar_viral.models import ObservationIn
from radar_viral.storage import repository as repo


def fake(term="mini aspirador portátil [SIMULADO]", **kwargs):
    return ObservationIn(term=term, is_simulated=True, **kwargs)


def test_tabelas_criadas(engine):
    assert set(inspect(engine).get_table_names()) == {"sources", "collection_runs", "observations"}


def test_fonte_nao_duplica(engine):
    a = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    b = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    assert a == b


def test_historico_e_preservado_entre_coletas(engine):
    """O ponto mais importante: uma nova coleta NÃO apaga a anterior."""
    src = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    for posicao in (10, 4):  # o produto "subiu" no ranking
        run = repo.start_run(engine, src, "BR")
        repo.add_observations(engine, run, [fake(rank_position=posicao, price=49.9, currency="BRL")])
        repo.finish_run(engine, run, "success")

    hist = repo.get_term_history(engine, "mini aspirador portátil [SIMULADO]", include_simulated=True)
    assert [h["rank_position"] for h in hist] == [10, 4]


def test_simulados_ficam_fora_por_padrao(engine):
    src = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    run = repo.start_run(engine, src, "BR")
    repo.add_observations(engine, run, [fake()])
    assert repo.get_term_history(engine, "mini aspirador portátil [SIMULADO]") == []


def test_finish_run_conta_itens(engine):
    src = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    run = repo.start_run(engine, src, "BR")
    repo.add_observations(engine, run, [fake("a"), fake("b"), fake("c")])
    repo.finish_run(engine, run, "success")
    with engine.connect() as conn:
        row = conn.execute(
            repo.select(repo.collection_runs).where(repo.collection_runs.c.id == run)
        ).one()
    assert row.items_collected == 3 and row.status == "success" and row.finished_at


def test_nao_grava_em_coleta_finalizada(engine):
    src = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    run = repo.start_run(engine, src, "BR")
    repo.finish_run(engine, run, "failed", "erro simulado")
    with pytest.raises(ValueError, match="finalizada"):
        repo.add_observations(engine, run, [fake()])


def test_coleta_inexistente(engine):
    with pytest.raises(ValueError, match="não existe"):
        repo.add_observations(engine, 999, [fake()])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"term": "   "},
        {"term": "x", "country": "BRA"},
        {"term": "x", "rank_position": 0},
        {"term": "x", "price": -1},
        {"term": "x", "popularity_value": 5},
        {"term": "x", "url": "javascript:alert(1)"},
    ],
)
def test_validacoes_da_observacao(kwargs):
    with pytest.raises(ValueError):
        ObservationIn(**kwargs)
