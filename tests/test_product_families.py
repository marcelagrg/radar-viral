"""Testes das famílias de produtos. Termos inseridos aqui são SIMULADOS
(nomes realistas, mas nenhum dado real de popularidade)."""

from datetime import date

import numpy as np
import pytest

from radar_viral.models import ObservationIn
from radar_viral.processing import product_families as pf
from radar_viral.storage import repository as repo

TERMOS = [
    "mini aspirador portátil",
    "Mini Aspiradores Portáteis",
    "aspirador portátil para teclado",
    "aspirador de mesa USB",
    "garrafa térmica inteligente",
    "garrafa termica com display",
    "playstation 4",
    "playstation 5",
]


def seed(engine, terms, simulated=True):
    src = repo.get_or_create_source(engine, "teste", "Fonte de Teste")
    run = repo.start_run(engine, src, "BR")
    repo.add_observations(
        engine, run,
        [ObservationIn(term=t, reference_date=date(2026, 1, 1), is_simulated=simulated) for t in terms],
    )
    repo.finish_run(engine, run, "success")


def families_by_term(engine):
    return {t["term"]: f["name"] for f in repo.list_families(engine) for t in f["terms"]}


def test_matriz_de_similaridade():
    sim = pf.similarity_matrix(["mini aspirador portátil", "mini aspiradores portáteis", "playstation"])
    assert sim.shape == (3, 3)
    assert sim[0, 1] > 0.5 > sim[0, 2]
    assert np.allclose(np.diag(sim), 1.0)


def test_numeros_diferentes_nunca_se_juntam():
    sim = pf.similarity_matrix(["playstation 4", "playstation 5", "playstation"])
    assert np.isneginf(sim[0, 1])
    groups = pf.cluster(sim, threshold=0.45)
    assert not any({0, 1} <= set(g) for g in groups)


def test_agrupamento_basico(engine):
    seed(engine, TERMOS)
    s = pf.group_terms(engine, threshold=0.45, include_simulated=True)
    fam = families_by_term(engine)
    assert s.terms_total == len(TERMOS)
    assert fam["mini aspirador portátil"] == fam["Mini Aspiradores Portáteis"] == fam["aspirador portátil para teclado"]
    assert fam["garrafa térmica inteligente"] == fam["garrafa termica com display"]
    assert fam["playstation 4"] != fam["playstation 5"]
    # Limitação documentada: sem conhecer o SIGNIFICADO, "mesa USB" fica de fora
    assert fam["aspirador de mesa USB"] != fam["mini aspirador portátil"]


def test_simulados_ficam_fora_por_padrao(engine):
    seed(engine, TERMOS)
    assert pf.group_terms(engine, threshold=0.45).terms_total == 0


def test_incremental_mantem_ids(engine):
    seed(engine, TERMOS[:3])
    pf.group_terms(engine, threshold=0.45, include_simulated=True)
    id_antes = repo.get_term_assignments(engine)["mini aspirador portátil"]

    seed(engine, ["mini aspirador portatil sem fio"])
    s = pf.group_terms(engine, threshold=0.45, include_simulated=True)
    ids = repo.get_term_assignments(engine)
    assert s.already_assigned == 3 and s.joined_existing == 1 and s.new_families == 0
    assert ids["mini aspirador portátil"] == id_antes == ids["mini aspirador portatil sem fio"]


def test_correcao_manual_sobrevive_ao_refazer(engine):
    seed(engine, TERMOS)
    pf.group_terms(engine, threshold=0.45, include_simulated=True)
    destino = repo.get_term_assignments(engine)["mini aspirador portátil"]
    repo.assign_term(engine, "aspirador de mesa USB", destino, method="manual")

    pf.group_terms(engine, threshold=0.45, rebuild=True, include_simulated=True)
    fam = families_by_term(engine)
    assert fam["aspirador de mesa USB"] == fam["mini aspirador portátil"] == fam["Mini Aspiradores Portáteis"]
    assert not any(nome.endswith("(2)") for nome in fam.values())  # sem família duplicada


def test_limiar_alto_separa_mais(engine):
    seed(engine, TERMOS)
    baixo = pf.group_terms(engine, threshold=0.3, include_simulated=True).new_families
    alto = pf.group_terms(engine, threshold=0.9, rebuild=True, include_simulated=True).new_families
    assert alto > baixo


def test_nome_da_familia_e_o_termo_central():
    terms = ["mini aspirador portátil", "mini aspiradores portáteis", "aspirador portátil para teclado"]
    sim = pf.similarity_matrix(terms)
    assert terms[pf.representative([0, 1, 2], sim, terms)] == "mini aspirador portátil"


def test_renomear_e_nomes_repetidos(engine):
    a = repo.create_family(engine, "Aspirador", created_by="manual")
    b = repo.create_family(engine, "Aspirador", created_by="auto")
    assert a != b
    with pytest.raises(ValueError, match="já existe"):
        repo.rename_family(engine, "Aspirador (2)", "Aspirador")
    repo.rename_family(engine, "Aspirador (2)", "Aspirador portátil")
    assert repo.get_family_id(engine, "Aspirador portátil") == b


@pytest.mark.parametrize("threshold", [0, 1, 1.5, -0.1])
def test_limiar_invalido(engine, threshold):
    with pytest.raises(ValueError):
        pf.group_terms(engine, threshold=threshold)
