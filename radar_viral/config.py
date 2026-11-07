"""Configurações centrais do Radar Viral.

Todas as configurações vêm de variáveis de ambiente (ou do arquivo .env).
Assim, nenhum segredo fica escrito no código, e o mesmo código roda em
máquinas diferentes apenas trocando o .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto: a pasta acima de "radar_viral/".
PROJECT_ROOT = Path(__file__).resolve().parent.parent

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Settings:
    """Configurações já validadas. frozen=True impede alteração acidental."""

    database_url: str
    default_country: str
    log_level: str
    family_similarity_threshold: float = 0.45


def _resolve_sqlite_path(url: str) -> str:
    """Transforma caminhos SQLite relativos em absolutos a partir da raiz.

    Sem isso, 'sqlite:///data/radar_viral.db' criaria o banco em lugares
    diferentes dependendo da pasta em que o terminal estivesse aberto.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url == "sqlite:///:memory:":
        return url
    path = Path(url[len(prefix):])
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    # as_posix() usa "/" mesmo no Windows, formato aceito pelo SQLAlchemy.
    return prefix + path.as_posix()


def load_settings(env_file: Path | None = None) -> Settings:
    """Lê o .env (se existir) e as variáveis de ambiente, validando valores."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

    database_url = os.getenv("DATABASE_URL", "sqlite:///data/radar_viral.db").strip()
    country = os.getenv("DEFAULT_COUNTRY", "BR").strip().upper()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    if len(country) != 2 or not country.isalpha():
        raise ValueError(
            f"DEFAULT_COUNTRY inválido: {country!r}. Use um código de 2 letras, ex.: BR."
        )
    raw_threshold = os.getenv("FAMILY_SIMILARITY_THRESHOLD", "0.45").strip()
    try:
        threshold = float(raw_threshold)
    except ValueError:
        raise ValueError(f"FAMILY_SIMILARITY_THRESHOLD inválido: {raw_threshold!r}") from None
    if not 0 < threshold < 1:
        raise ValueError("FAMILY_SIMILARITY_THRESHOLD deve estar entre 0 e 1 (exclusive)")

    if log_level not in VALID_LOG_LEVELS:
        raise ValueError(f"LOG_LEVEL inválido: {log_level!r}. Opções: {sorted(VALID_LOG_LEVELS)}")

    return Settings(
        database_url=_resolve_sqlite_path(database_url),
        default_country=country,
        log_level=log_level,
        family_similarity_threshold=threshold,
    )
