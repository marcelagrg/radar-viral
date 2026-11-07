"""Partes comuns a TODA importação de arquivo (CSV padrão, Google Trends...).

Cada formato só precisa saber transformar o texto do arquivo numa lista de
ObservationIn. Verificar o arquivo, evitar duplicação e gravar a coleta
ficam aqui, escritos uma única vez.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from radar_viral.models import ObservationIn
from radar_viral.storage import repository as repo

SOURCE_CODE_PATTERN = re.compile(r"^[a-z0-9_]{2,50}$")
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB: protege contra abrir um arquivo errado gigante
MAX_ERRORS_SHOWN = 20


class CsvImportError(Exception):
    """Erro geral de importação."""


class DuplicateImportError(CsvImportError):
    """O mesmo arquivo (mesmo conteúdo) já foi importado com sucesso."""


class CsvValidationError(CsvImportError):
    """Uma ou mais linhas são inválidas. Nada foi gravado."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        shown = errors[:MAX_ERRORS_SHOWN]
        extra = len(errors) - len(shown)
        msg = f"{len(errors)} erro(s) no arquivo; nada foi importado:\n  - " + "\n  - ".join(shown)
        if extra:
            msg += f"\n  ... e mais {extra} erro(s)."
        super().__init__(msg)


@dataclass
class ImportResult:
    run_id: int
    rows_imported: int
    source_code: str
    file_sha256: str
    rows_skipped: int = 0  # linhas válidas deixadas de fora de propósito (ex.: semana parcial)


def decode_bytes(data: bytes) -> str:
    """UTF-8 (com ou sem BOM) primeiro; senão cp1252, comum no Excel do Windows.

    O BOM é um marcador invisível que o Excel coloca no início de arquivos
    "CSV UTF-8". O codec 'utf-8-sig' o remove automaticamente.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def validate_source_code(source_code: str) -> None:
    if not SOURCE_CODE_PATTERN.match(source_code):
        raise CsvImportError(
            f"código de fonte inválido {source_code!r}: use 2–50 letras minúsculas, números ou _"
        )


def read_new_file(engine: Engine, path: Path) -> tuple[bytes, str]:
    """Lê o arquivo e devolve (bytes, sha256), recusando conteúdo já importado."""
    path = Path(path)
    if not path.is_file():
        raise CsvImportError(f"arquivo não encontrado: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise CsvImportError(f"arquivo maior que {MAX_FILE_BYTES // (1024 * 1024)} MB")
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    previous = repo.find_successful_import(engine, sha256)
    if previous:
        raise DuplicateImportError(
            f"este conteúdo já foi importado na coleta #{previous['id']} "
            f"(arquivo {previous['source_file']!r}); nada foi gravado"
        )
    return data, sha256


def save_import(
    engine: Engine,
    items: list[ObservationIn],
    *,
    file_name: str,
    file_sha256: str,
    source_code: str,
    source_name: str,
    country: str,
    rows_skipped: int = 0,
) -> ImportResult:
    """Grava itens JÁ VALIDADOS como uma nova coleta (collection_run)."""
    source_id = repo.get_or_create_source(engine, source_code, source_name)
    run_id = repo.start_run(engine, source_id, country, source_file=file_name, file_sha256=file_sha256)
    try:
        count = repo.add_observations(engine, run_id, items)
    except Exception as exc:
        # Registra a falha para auditoria e repassa o erro original.
        repo.finish_run(engine, run_id, "failed", error_message=str(exc)[:1000])
        raise
    repo.finish_run(engine, run_id, "success")
    return ImportResult(
        run_id=run_id,
        rows_imported=count,
        source_code=source_code,
        file_sha256=file_sha256,
        rows_skipped=rows_skipped,
    )
