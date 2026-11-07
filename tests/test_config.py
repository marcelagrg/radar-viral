import pytest

from radar_viral.config import load_settings


def test_valores_padrao(monkeypatch, tmp_path):
    for var in ("DATABASE_URL", "DEFAULT_COUNTRY", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    settings = load_settings(env_file=tmp_path / "nao_existe.env")
    assert settings.default_country == "BR"
    assert settings.log_level == "INFO"
    assert settings.database_url.endswith("data/radar_viral.db")


def test_pais_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_COUNTRY", "Brasil")
    with pytest.raises(ValueError, match="DEFAULT_COUNTRY"):
        load_settings(env_file=tmp_path / "nao_existe.env")


def test_pais_normalizado_para_maiusculas(monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_COUNTRY", "us")
    assert load_settings(env_file=tmp_path / "nao_existe.env").default_country == "US"
