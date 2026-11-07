"""Testes do importador de CSV. Todos os dados são SIMULADOS."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, select

from radar_viral.collectors import csv_importer as ci
from radar_viral.storage import repository as repo
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db
from radar_viral.storage.schema import collection_runs, observations

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_simulado.csv"


def write(tmp_path, content, name="dados.csv", encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(content.encode(encoding))
    return path


# --------------------------------------------------------- conversões

@pytest.mark.parametrize(
    "text, sep, expected",
    [
        ("49,90", ",", 49.9),
        ("1.234,56", ",", 1234.56),
        ("1,234.56", ".", 1234.56),
        ("1200", ",", 1200.0),
        ("", ",", None),
    ],
)
def test_parse_number(text, sep, expected):
    assert ci.parse_number(text, sep) == expected


def test_parse_number_invalido():
    with pytest.raises(ValueError):
        ci.parse_number("abc", ",")


def test_parse_date_dois_formatos():
    assert ci.parse_date("2025-09-15") == ci.parse_date("15/09/2025") == date(2025, 9, 15)
    with pytest.raises(ValueError):
        ci.parse_date("09/15/2025")  # formato americano é rejeitado: mês 15 não existe


def test_decode_cp1252_do_excel():
    assert ci.decode_bytes("garrafa térmica".encode("cp1252")) == "garrafa térmica"


# --------------------------------------------------------- importação

def test_importa_exemplo_simulado(engine):
    result = ci.import_csv(engine, FIXTURE, source_code="teste", simulated=True)
    assert result.rows_imported == 5

    hist = repo.get_term_history(engine, "mini aspirador portátil [SIMULADO]", include_simulated=True)
    assert [h["reference_date"] for h in hist] == [date(2025, 9, 1), date(2025, 9, 8), date(2025, 9, 15)]
    assert [h["rank_position"] for h in hist] == [12, 7, 3]
    assert hist[0]["price"] == 49.9 and hist[0]["search_volume"] == 1200.0
    assert all(h["is_simulated"] for h in hist)


def test_mesmo_arquivo_nao_importa_duas_vezes(engine):
    ci.import_csv(engine, FIXTURE, source_code="teste", simulated=True)
    with pytest.raises(ci.DuplicateImportError):
        ci.import_csv(engine, FIXTURE, source_code="teste", simulated=True)


def test_virgula_e_utf8_bom(engine, tmp_path):
    path = write(tmp_path, "data_referencia,termo,preco\n2025-09-01,produto x [SIMULADO],19.9\n",
                 encoding="utf-8-sig")
    ci.import_csv(engine, path, source_code="teste", decimal_sep=".", simulated=True)
    assert repo.get_term_history(engine, "produto x [SIMULADO]", include_simulated=True)[0]["price"] == 19.9


def test_linha_invalida_nao_grava_nada(engine, tmp_path):
    path = write(
        tmp_path,
        "data_referencia;termo;preco\n"
        "01/09/2025;ok [SIMULADO];10\n"
        "31/02/2025;data ruim;10\n"
        "01/09/2025;;10\n"
        "01/09/2025;preço ruim;-5\n",
    )
    with pytest.raises(ci.CsvValidationError) as info:
        ci.import_csv(engine, path, source_code="teste", simulated=True)
    erros = info.value.errors
    assert len(erros) == 3
    assert erros[0].startswith("linha 3") and erros[1].startswith("linha 4") and erros[2].startswith("linha 5")
    with engine.connect() as conn:
        assert conn.execute(select(observations)).first() is None
        assert conn.execute(select(collection_runs)).first() is None  # nem a coleta foi aberta


@pytest.mark.parametrize(
    "content, trecho",
    [
        ("termo;preco\nx;1\n", "obrigatória"),
        ("data_referencia;termo;cor\n01/09/2025;x;azul\n", "desconhecida"),
        ("data_referencia;termo\n", "nenhuma linha"),
        ("", "vazio"),
        ("data_referencia;termo\n01/09/2025;x;extra\n", "mais valores"),
    ],
)
def test_erros_de_estrutura(engine, tmp_path, content, trecho):
    with pytest.raises(ci.CsvValidationError, match=trecho):
        ci.import_csv(engine, write(tmp_path, content), source_code="teste", simulated=True)


def test_codigo_de_fonte_invalido(engine):
    with pytest.raises(ci.CsvImportError, match="código de fonte"):
        ci.import_csv(engine, FIXTURE, source_code="Google Trends!")


def test_arquivo_inexistente(engine, tmp_path):
    with pytest.raises(ci.CsvImportError, match="não encontrado"):
        ci.import_csv(engine, tmp_path / "nao_existe.csv", source_code="teste")


def test_falha_no_banco_marca_coleta_como_failed(engine, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("falha simulada no banco")

    monkeypatch.setattr(repo, "add_observations", explode)
    with pytest.raises(RuntimeError):
        ci.import_csv(engine, FIXTURE, source_code="teste", simulated=True)
    with engine.connect() as conn:
        run = conn.execute(select(collection_runs)).one()
    assert run.status == "failed" and "falha simulada" in run.error_message
    # Depois de uma falha, o mesmo arquivo PODE ser importado de novo.
    monkeypatch.undo()
    assert ci.import_csv(engine, FIXTURE, source_code="teste", simulated=True).rows_imported == 5


# --------------------------------------------------------- esquema antigo

def test_banco_antigo_e_detectado(tmp_path):
    eng = get_engine(f"sqlite:///{(tmp_path / 'antigo.db').as_posix()}")
    old = MetaData()
    Table("observations", old, Column("id", Integer, primary_key=True))
    old.create_all(eng)
    try:
        with pytest.raises(SchemaOutdatedError, match="observations.term"):
            init_db(eng)
    finally:
        eng.dispose()  # fecha as conexões; sem isso o Python avisa (ResourceWarning)
