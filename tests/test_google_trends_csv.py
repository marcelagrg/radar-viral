"""Testes do conversor do Google Trends.

- time_series_BR_20251107-0805_20261107-0805.csv: trecho REAL (5 linhas).
- *_SIMULADO.csv e textos montados nos testes: dados SIMULADOS.
"""

from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from radar_viral.collectors import google_trends_csv as gt
from radar_viral.collectors.file_import import CsvImportError, CsvValidationError, DuplicateImportError
from radar_viral.storage import repository as repo

FIX = Path(__file__).parent / "fixtures" / "google_trends"
REAL = FIX / "time_series_BR_20251107-0805_20261107-0805.csv"
SIMULADO = FIX / "time_series_BR_20260901-1200_20261008-1200_SIMULADO.csv"


def test_nome_do_arquivo():
    assert gt.parse_filename(REAL.name) == ("BR", date(2025, 11, 7), date(2026, 11, 7))
    # sufixo que o navegador adiciona ao baixar de novo
    assert gt.parse_filename("time_series_BR_20251107-0805_20261107-0805 (1).csv")[0] == "BR"
    assert gt.parse_filename("meu_arquivo.csv") is None


@pytest.mark.parametrize("text, expected", [("0", 0.0), ("59", 59.0), ("100", 100.0), ("<1", 0.5)])
def test_valores(text, expected):
    assert gt.parse_value(text) == expected


@pytest.mark.parametrize("text", ["101", "-1", "abc", ""])
def test_valores_invalidos(text):
    with pytest.raises(ValueError):
        gt.parse_value(text)


def test_link_da_consulta():
    url = gt.explore_url("mini aspirador", "BR", date(2025, 11, 7), date(2026, 11, 7))
    q = parse_qs(urlparse(url).query)
    assert q == {"q": ["mini aspirador"], "geo": ["BR"], "date": ["2025-11-07 2026-11-07"]}


def test_importa_trecho_real(engine):
    result = gt.import_google_trends(engine, REAL)
    assert (result.rows_imported, result.rows_skipped) == (5, 0)
    hist = repo.get_term_history(engine, "playstation")
    assert [h["popularity_value"] for h in hist] == [59, 68, 99, 100, 83]
    assert hist[0]["reference_date"] == date(2025, 11, 2)
    assert hist[0]["country"] == "BR" and hist[0]["popularity_metric"] == "google_trends_0_100"
    assert hist[0]["search_volume"] is None  # escala relativa NÃO é volume de buscas
    assert not hist[0]["is_simulated"]


def test_varios_termos_menor_que_um_e_semana_parcial(engine):
    result = gt.import_google_trends(engine, SIMULADO, simulated=True)
    # 5 semanas x 2 termos = 10; a semana de 04/10 termina depois de 08/10 -> ignorada
    assert (result.rows_imported, result.rows_skipped) == (8, 2)
    garrafa = repo.get_term_history(engine, "[SIMULADO] garrafa termica", include_simulated=True)
    assert [h["popularity_value"] for h in garrafa] == [0.5, 3, 4, 2]
    assert garrafa[0]["raw_payload"]["value"] == "<1"  # texto original preservado


def test_incluir_parcial(engine):
    result = gt.import_google_trends(engine, SIMULADO, include_partial=True, simulated=True)
    assert (result.rows_imported, result.rows_skipped) == (10, 0)


def test_mesmo_export_nao_duplica(engine):
    gt.import_google_trends(engine, REAL)
    with pytest.raises(DuplicateImportError):
        gt.import_google_trends(engine, REAL)


def test_arquivo_renomeado_exige_pais_e_fim(engine, tmp_path):
    renomeado = tmp_path / "playstation.csv"
    renomeado.write_bytes(REAL.read_bytes())
    with pytest.raises(CsvImportError, match="--pais"):
        gt.import_google_trends(engine, renomeado)
    result = gt.import_google_trends(engine, renomeado, country="BR", period_end=date(2026, 11, 7))
    assert result.rows_imported == 5


def test_pais_conflitante(engine):
    with pytest.raises(CsvImportError, match="indica país BR"):
        gt.import_google_trends(engine, REAL, country="US")


@pytest.mark.parametrize(
    "content, trecho",
    [
        ('"Time"\n"2025-11-02"\n', "cabeçalho"),
        ('"Time","x"\n', "nenhuma linha"),
        ('"Time","x"\n"02/11/2025",5\n', "data inválida"),
        ('"Time","x"\n"2025-11-02",5,7\n', "esperado 2 valores"),
        ('"Time","x"\n"2025-11-09",5\n"2025-11-02",6\n', "ordem crescente"),
        ('"Time","x"\n"2025-11-02",150\n', "fora da escala"),
    ],
)
def test_erros(engine, tmp_path, content, trecho):
    path = tmp_path / "time_series_BR_20251101-0000_20251201-0000_SIMULADO.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CsvValidationError, match=trecho):
        gt.import_google_trends(engine, path, simulated=True)
