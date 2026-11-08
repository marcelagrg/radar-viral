"""Testes da pontuação. Séries e dados são SIMULADOS."""

import tomllib
from datetime import date, timedelta

import pandas as pd
import pytest

from radar_viral.analysis.growth import window_indicators
from radar_viral.analysis.series import Series
from radar_viral.models import ObservationIn
from radar_viral.scoring import scorer as sc
from radar_viral.scoring.config import (
    DEFAULT_PATH,
    ScoringConfigError,
    load_scoring_config,
    parse_scoring_config,
)
from radar_viral.storage import repository as repo


@pytest.fixture
def cfg():
    return load_scoring_config()


@pytest.fixture
def raw():
    return tomllib.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


def make_series(values, source="google_trends", family="[SIMULADO] x"):
    data = pd.Series([float(v) for v in values], index=pd.date_range("2026-01-04", periods=len(values), freq="7D"))
    return Series(None, family, source, "BR", "google_trends_0_100", 1, [family], data, 7, 0)


CRESCENTE = [10, 10, 11, 10, 12, 16, 22, 30]
ESTAVEL = [30, 31, 29, 30, 30, 31, 30, 29]
PICO = [20, 20, 20, 20, 25, 100, 40, 30]


# ---------------------------------------------------------------- configuração

def test_config_padrao_e_valida(cfg):
    assert cfg.main_window == 90 and cfg.missing_strategy == "neutro"
    assert sum(cfg.weights.values()) == 100


@pytest.mark.parametrize(
    "mudanca, trecho",
    [
        (lambda r: r["geral"].update(janela_principal=45), "janela_principal"),
        (lambda r: r["geral"].update(criterios_ausentes="ignorar"), "criterios_ausentes"),
        (lambda r: r["geral"].update(valor_neutro=2), "valor_neutro"),
        (lambda r: r["pesos"].update(viralidade=10), "desconhecido"),
        (lambda r: r["pesos"].update(velocidade=-1), ">= 0"),
        (lambda r: r.update(pesos={c: 0 for c in r["pesos"]}), "maior que zero"),
        (lambda r: r["normalizacao"]["aceleracao_pp"].update(min=10), "menor que max"),
        (lambda r: r["tetos"].update(pico_passageiro=200), "entre 0 e 100"),
        (lambda r: r["tetos"].update(saturacao=5), "desconhecido"),
    ],
)
def test_config_invalida(raw, mudanca, trecho):
    mudanca(raw)
    with pytest.raises(ScoringConfigError, match=trecho):
        parse_scoring_config(raw)


def test_sintaxe_toml_invalida(tmp_path):
    bad = tmp_path / "ruim.toml"
    bad.write_text("[pesos\nvelocidade = 1", encoding="utf-8")
    with pytest.raises(ScoringConfigError, match="sintaxe"):
        load_scoring_config(bad)


# ---------------------------------------------------------------- matemática

@pytest.mark.parametrize("v, expected", [(-50, 0.0), (25, 0.5), (100, 1.0), (500, 1.0), (-90, 0.0), (None, None)])
def test_normalizacao(v, expected):
    assert sc.normalize(v, -50, 100) == expected


def test_combinar_neutro_e_renormalizar(raw):
    raw["pesos"] = {"velocidade": 50, "concorrencia": 50}
    criteria = {"velocidade": 1.0, "concorrencia": None}
    neutro = parse_scoring_config(raw)
    score, contrib, missing, coverage = sc.combine(criteria, neutro)
    assert score == pytest.approx(75.0)  # 50×1 + 50×0,5
    assert missing == ["concorrencia"] and coverage == 0.5

    raw["geral"]["criterios_ausentes"] = "renormalizar"
    score, *_ = sc.combine(criteria, parse_scoring_config(raw))
    assert score == pytest.approx(100.0)  # só o que se sabe: velocidade = 1


def test_contribuicoes_somam_a_pontuacao(cfg):
    r = sc.score_group("x", "BR", [make_series(CRESCENTE)], cfg_30(cfg))
    assert sum(r.contributions.values()) == pytest.approx(r.score, abs=0.1)


def cfg_30(cfg):
    from dataclasses import replace
    return replace(cfg, main_window=30)


# ---------------------------------------------------------------- comportamento

def test_crescente_supera_estavel_que_supera_pico(cfg):
    c = cfg_30(cfg)
    cres = sc.score_group("a", "BR", [make_series(CRESCENTE)], c)
    est = sc.score_group("b", "BR", [make_series(ESTAVEL)], c)
    pico = sc.score_group("c", "BR", [make_series(PICO)], c)
    assert cres.score > est.score > pico.score
    assert pico.score <= 40
    assert cres.criteria["persistencia"] > pico.criteria["persistencia"]
    assert cres.classification == "emergente" and pico.classification == "pico passageiro"


def test_com_uma_fonte_a_nota_fica_contida(cfg):
    """Modo neutro: só 55% do peso tem dados -> nota máxima possível = 77,5."""
    perfeito = sc.score_group("x", "BR", [make_series([1, 1, 1, 1, 10, 30, 60, 100])], cfg_30(cfg))
    assert perfeito.score <= 77.5
    assert set(perfeito.missing) == {
        "multiplataforma", "engajamento", "intencao_compra", "concorrencia", "sazonalidade", "potencial_comercial"
    }


def test_confianca_reflete_cobertura_e_qualidade(cfg):
    c = cfg_30(cfg)
    r = sc.score_group("x", "BR", [make_series(CRESCENTE)], c)
    # cobertura 55% (velocidade+aceleração+persistência); 8 pontos / (4×4) = 0,5
    assert r.quality == pytest.approx(0.5)
    assert r.confidence == pytest.approx(100 * 0.55 * 0.5, abs=0.1)


def test_base_baixa_reduz_qualidade(cfg):
    c = cfg_30(cfg)
    s = make_series([0.5, 0.5, 0.5, 0.5, 1, 2, 3, 4])
    ind = window_indicators(s.data, 30, 7, s.metric)
    assert ind.low_base and sc.data_quality(s, ind) == pytest.approx(0.25)


def test_dados_insuficientes(cfg):
    r = sc.score_group("x", "BR", [make_series([10, 20, 30])], cfg)  # 90d exige 26 pontos
    assert r.confidence == 0 and r.classification == "dados insuficientes"
    assert r.score == pytest.approx(50.0)  # tudo neutro


def test_multiplataforma_com_duas_fontes(cfg):
    c = cfg_30(cfg)
    r = sc.score_group("x", "BR", [make_series(CRESCENTE), make_series(ESTAVEL, source="outra")], c)
    assert r.criteria["multiplataforma"] == 0.5 and "multiplataforma" not in r.missing


# ---------------------------------------------------------------- de ponta a ponta

def test_score_all_do_banco(engine, cfg):
    src = repo.get_or_create_source(engine, "google_trends", "Google Trends")
    for term, values in (("[SIMULADO] a", CRESCENTE), ("[SIMULADO] b", ESTAVEL)):
        run = repo.start_run(engine, src, "BR")
        repo.add_observations(engine, run, [
            ObservationIn(term=term, reference_date=date(2026, 1, 4) + timedelta(weeks=i), popularity_value=v,
                          popularity_metric="google_trends_0_100", is_simulated=True)
            for i, v in enumerate(values)
        ])
        repo.finish_run(engine, run, "success")
    results = sc.score_all(engine, cfg_30(cfg), include_simulated=True)
    assert [r.family.split()[1] for r in results] == ["a", "b"]  # ordenado por pontuação
    assert sc.results_to_frame(results).shape[0] == 2


def test_teto_corrige_janela_curta(cfg):
    """Documenta POR QUE o teto existe: em janelas curtas (14d = 2 semanas)
    não há pontos para velocidade/aceleração, só o crescimento da média conta,
    e um pico que já passou parecia melhor que um produto estável."""
    from dataclasses import replace
    pico_curto, estavel_curto = [10, 20, 100, 40], [30, 31, 30, 29]
    sem = replace(cfg, main_window=14, caps={"pico_passageiro": 100.0})
    com = replace(cfg, main_window=14)
    assert (sc.score_group("p", "BR", [make_series(pico_curto)], sem).score
            > sc.score_group("e", "BR", [make_series(estavel_curto)], sem).score)
    assert (sc.score_group("p", "BR", [make_series(pico_curto)], com).score
            < sc.score_group("e", "BR", [make_series(estavel_curto)], com).score)


def test_teto_aparece_no_detalhamento(cfg):
    from dataclasses import replace
    r = sc.score_group("p", "BR", [make_series([10, 20, 100, 40])], replace(cfg, main_window=14))
    assert r.score == 40 and r.contributions["teto_pico_passageiro"] < 0
    assert sum(r.contributions.values()) == pytest.approx(r.score, abs=0.1)


def test_export_curto_nao_rebaixa_qualidade(cfg):
    """Família com série semanal longa + série diária curta: a confiança vem da melhor."""
    import pandas as pd
    from radar_viral.analysis.series import Series

    semanal = make_series([10 + i for i in range(52)])
    diaria = Series(None, "[SIMULADO] x", "google_trends", "BR", "google_trends_0_100", 2, ["x"],
                    pd.Series([50.0] * 30, index=pd.date_range("2026-10-01", periods=30, freq="D")), 1, 0)
    so_semanal = sc.score_group("x", "BR", [semanal], cfg)
    as_duas = sc.score_group("x", "BR", [semanal, diaria], cfg)
    assert as_duas.quality == so_semanal.quality == 1.0
    assert as_duas.confidence == so_semanal.confidence
