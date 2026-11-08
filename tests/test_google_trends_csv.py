"""Testes do conversor do Google Trends.

- time_series_BR_20251107-0805_20261107-0805.csv: trecho REAL (5 linhas).
- *_SIMULADO.csv e textos montados nos testes: dados SIMULADOS.
"""

from datetime import date, datetime, timedelta
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
    assert garrafa[0]["raw_payload"]["values"] == ["<1"]  # texto original preservado


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


# ------------------------------------------------- exports de 30 dias e 7 dias (Etapa 10)

REAL_30D = FIX / "trecho_real_30dias.csv"
REAL_7D = FIX / "trecho_real_7dias.csv"


def test_30_dias_real_diario(engine):
    # o arquivo foi renomeado (nome original não informado): país e fim da consulta à mão
    r = gt.import_google_trends(engine, REAL_30D, country="BR", period_end=date(2026, 11, 8))
    assert (r.rows_imported, r.rows_skipped) == (4, 0)
    hist = repo.get_term_history(engine, "galaxy tab s10")
    assert [h["reference_date"] for h in hist] == [date(2026, 10, d) for d in (10, 11, 12, 13)]
    assert [h["popularity_value"] for h in hist] == [76, 58, 41, 46]


def test_30_dias_ultimo_dia_parcial(engine):
    # consulta terminou em 13/10: o dia 13 ainda não estava completo
    r = gt.import_google_trends(engine, REAL_30D, country="BR", period_end=date(2026, 10, 13))
    assert (r.rows_imported, r.rows_skipped) == (3, 1)


def test_7_dias_real_dia_incompleto(engine):
    """Trecho real: 4 pontos que, no horário de Brasília, são 01/11 às 9h, 13h, 17h e 21h.
    Um dia completo tem 6 pontos (a cada 4 horas) -> o dia é descartado."""
    with pytest.raises(CsvValidationError, match="nenhum período completo"):
        gt.import_google_trends(engine, REAL_7D, country="BR", period_end=date(2026, 11, 8))


def test_7_dias_real_incluindo_parcial(engine):
    r = gt.import_google_trends(engine, REAL_7D, country="BR", period_end=date(2026, 11, 8),
                                include_partial=True)
    [h] = repo.get_term_history(engine, "s10 lite")
    # 00:00Z de 02/11 é 21h de 01/11 em Brasília: os 4 pontos são do mesmo dia
    assert r.rows_imported == 1 and h["reference_date"] == date(2026, 11, 1)
    assert h["popularity_value"] == pytest.approx((81 + 82 + 74 + 82) / 4)
    assert h["raw_payload"]["values"] == ["81", "82", "74", "82"]


def simulated_week(tmp_path, start="2026-11-01T12:00:00Z", points=42, values=None):
    """Export de 7 dias SIMULADO: um ponto a cada 4 horas."""
    t0 = datetime.fromisoformat(start)
    values = values or [10 + i for i in range(points)]
    lines = ['"Time","[SIMULADO] fone"'] + [
        f'"{(t0 + timedelta(hours=4 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")}",{v}' for i, v in enumerate(values)
    ]
    path = tmp_path / "semana_simulada.csv"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_7_dias_dias_completos(engine, tmp_path):
    # 42 pontos de 01/11 09h (Brasília) em diante: 01/11 incompleto (4 pontos),
    # 02 a 07/11 completos (6 cada = 36), 08/11 incompleto (2 pontos)
    r = gt.import_google_trends(engine, simulated_week(tmp_path), country="BR",
                                period_end=date(2026, 11, 8), simulated=True)
    assert (r.rows_imported, r.rows_skipped) == (6, 2)
    hist = repo.get_term_history(engine, "[SIMULADO] fone", include_simulated=True)
    assert [h["reference_date"].day for h in hist] == [2, 3, 4, 5, 6, 7]
    # 02/11 = pontos de índice 4 a 9 (valores 14..19) -> média 16,5
    assert hist[0]["popularity_value"] == pytest.approx(16.5)


def test_fuso_fora_do_brasil_usa_utc(engine, tmp_path):
    r = gt.import_google_trends(engine, simulated_week(tmp_path, start="2026-11-01T00:00:00Z"),
                                country="US", period_end=date(2026, 11, 8), simulated=True)
    assert r.rows_imported == 7 and r.rows_skipped == 0  # 42 pontos = 7 dias UTC completos


@pytest.mark.parametrize(
    "content, trecho",
    [
        ('"Time","x"\n"2026-11-01T12:00:00Z",5\n"2026-11-02",6\n', "data inválida"),       # formatos misturados
        ('"Time","x"\n"2026-11-01T12:00:00",5\n"2026-11-01T16:00:00",6\n', "data inválida"),  # sem fuso
        ('"Time","x"\n"2026-11-01T12:00:00Z",5\n"2026-11-01T12:08:00Z",6\n', "não é suportado"),  # 8 min
    ],
)
def test_erros_formato_com_horario(engine, tmp_path, content, trecho):
    path = tmp_path / "x.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CsvValidationError, match=trecho):
        gt.import_google_trends(engine, path, country="BR", period_end=date(2026, 11, 8), simulated=True)
