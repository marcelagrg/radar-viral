"""Importação em lote. Usa o trecho REAL do Google Trends e arquivos SIMULADOS."""

import shutil
from pathlib import Path

import pytest

from radar_viral.collectors import batch
from radar_viral.collectors.file_import import CsvImportError
from radar_viral.config import load_settings
from radar_viral.storage import repository as repo

FIX = Path(__file__).parent / "fixtures" / "google_trends"
REAL = FIX / "time_series_BR_20251107-0805_20261107-0805.csv"
SIMULADO = FIX / "time_series_BR_20260901-1200_20261008-1200_SIMULADO.csv"


@pytest.fixture
def pasta(tmp_path):
    """Uma pasta 'Downloads' de teste com vários tipos de arquivo."""
    d = tmp_path / "Downloads"
    d.mkdir()
    shutil.copy(REAL, d)
    shutil.copy(SIMULADO, d)
    shutil.copy(REAL, d / "time_series_BR_20251107-0805_20261107-0805 (1).csv")  # baixado 2x
    (d / "time_series_BR_20251101-0000_20251201-0000_quebrado.csv").write_text("lixo", encoding="utf-8")
    (d / "foto.jpg").write_bytes(b"x")                    # ignorado: não é export
    (d / "planilha.csv").write_text("a;b\n", encoding="utf-8")  # ignorado: outro nome
    (d / "sub").mkdir()
    shutil.copy(REAL, d / "sub" / REAL.name)              # ignorado: subpasta
    return d


def test_encontra_so_exports(pasta):
    nomes = [p.name for p in batch.find_exports(pasta)]
    assert len(nomes) == 4 and all(n.startswith("time_series_") for n in nomes)
    # a cópia "(1)" vem logo depois do original, não antes
    assert nomes.index(REAL.name) + 1 == nomes.index("time_series_BR_20251107-0805_20261107-0805 (1).csv")


def test_lote_com_erro_e_duplicado(engine, pasta):
    out = {o.file: o for o in batch.import_folder(engine, pasta, simulated=True)}
    assert out[REAL.name].status == batch.IMPORTED and out[REAL.name].rows == 5
    assert out[SIMULADO.name].status == batch.IMPORTED and out[SIMULADO.name].skipped == 2
    assert out["time_series_BR_20251107-0805_20261107-0805 (1).csv"].status == batch.DUPLICATE
    assert out["time_series_BR_20251101-0000_20251201-0000_quebrado.csv"].status == batch.FAILED
    # o erro de um arquivo não impediu os outros
    assert len(repo.get_term_history(engine, "playstation", include_simulated=True)) == 5


def test_rodar_duas_vezes_e_seguro(engine, pasta):
    batch.import_folder(engine, pasta, simulated=True)
    segunda = batch.import_folder(engine, pasta, simulated=True)
    assert not any(o.status == batch.IMPORTED for o in segunda)
    assert len(repo.get_term_history(engine, "playstation", include_simulated=True)) == 5


def test_mover_arquivos_resolvidos(engine, pasta):
    batch.import_folder(engine, pasta, simulated=True, move_done=True)
    feitos = sorted(p.name for p in (pasta / batch.DONE_FOLDER).iterdir())
    assert len(feitos) == 3                     # 2 importados + 1 repetido
    restantes = [p.name for p in batch.find_exports(pasta)]
    assert restantes == ["time_series_BR_20251101-0000_20251201-0000_quebrado.csv"]  # erro fica


def test_mover_nao_sobrescreve(engine, tmp_path):
    d = tmp_path / "d"
    (d / batch.DONE_FOLDER).mkdir(parents=True)
    shutil.copy(REAL, d / batch.DONE_FOLDER / REAL.name)  # já existe um com o mesmo nome
    shutil.copy(REAL, d)
    [o] = batch.import_folder(engine, d, move_done=True)
    assert Path(o.moved_to).name == REAL.stem + "_2.csv"
    assert (d / batch.DONE_FOLDER / REAL.name).exists()


def test_pasta_inexistente(engine, tmp_path):
    with pytest.raises(CsvImportError, match="pasta não encontrada"):
        batch.import_folder(engine, tmp_path / "nao_existe")


def test_exports_dir_no_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    assert load_settings(env_file=tmp_path / "x.env").exports_dir == tmp_path
    monkeypatch.setenv("EXPORTS_DIR", "  ")
    assert load_settings(env_file=tmp_path / "x.env").exports_dir is None


def test_script_completo(engine, pasta, monkeypatch, tmp_path, capsys):
    """Roda o comando como você rodaria, num banco temporário."""
    import importlib.util

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    spec = importlib.util.spec_from_file_location(
        "import_pasta", Path(__file__).parent.parent / "scripts" / "import_pasta.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main([str(pasta), "--simulado"])
    out = capsys.readouterr().out
    assert code == 1  # houve 1 arquivo com erro -> código de saída 1
    assert "Resumo: 2 importado(s), 1 já importado(s), 1 com erro." in out
    assert "Famílias:" in out
