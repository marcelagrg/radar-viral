"""Importação de arquivos CSV no formato padrão do Radar Viral.

Fluxo:  arquivo -> bytes -> hash -> texto -> linhas -> validação -> banco

Regra "tudo ou nada": se QUALQUER linha tiver erro, nada é gravado e todos
os erros são listados com o número da linha, para você corrigir de uma vez.
O formato está documentado em docs/formato_csv.md.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Engine

from radar_viral.models import ObservationIn
from radar_viral.storage import repository as repo

REQUIRED_COLUMNS = {"data_referencia", "termo"}

# Coluna do CSV -> campo de ObservationIn
OPTIONAL_COLUMNS = {
    "id_externo": "external_id",
    "categoria_id": "category_id",
    "categoria": "category_name",
    "posicao": "rank_position",
    "volume_busca": "search_volume",
    "valor_popularidade": "popularity_value",
    "metrica_popularidade": "popularity_metric",
    "preco": "price",
    "moeda": "currency",
    "url": "url",
}
INT_FIELDS = {"rank_position"}
FLOAT_FIELDS = {"search_volume", "popularity_value", "price"}

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


# ---------------------------------------------------------------- conversões

def parse_date(text: str) -> date:
    """Aceita 2025-03-15 (ISO) ou 15/03/2025 (padrão brasileiro do Excel)."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"data inválida {text!r} (use AAAA-MM-DD ou DD/MM/AAAA)")


def parse_number(text: str, decimal_sep: str) -> float | None:
    """Converte texto em número respeitando o separador decimal escolhido.

    decimal_sep=","  ->  "1.234,56" = 1234.56   (padrão brasileiro)
    decimal_sep="."  ->  "1,234.56" = 1234.56   (padrão americano)
    """
    text = text.strip().replace(" ", "")
    if not text:
        return None
    thousands_sep = "." if decimal_sep == "," else ","
    normalized = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    try:
        return float(normalized)
    except ValueError:
        raise ValueError(f"número inválido {text!r}") from None


def parse_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if not text.isdigit():
        raise ValueError(f"inteiro inválido {text!r}")
    return int(text)


def decode_bytes(data: bytes) -> str:
    """UTF-8 (com ou sem BOM) primeiro; senão cp1252, comum no Excel do Windows.

    O BOM é um marcador invisível que o Excel coloca no início de arquivos
    "CSV UTF-8". O codec 'utf-8-sig' o remove automaticamente.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def detect_delimiter(text: str) -> str:
    """O Excel em português salva CSV com ';' (porque ',' é o decimal)."""
    first_line = text.splitlines()[0] if text else ""
    return ";" if first_line.count(";") > first_line.count(",") else ","


def normalize_header(name: str) -> str:
    return (name or "").strip().lower()


# ---------------------------------------------------------------- leitura

def read_observations(
    text: str, country: str, decimal_sep: str = ",", simulated: bool = False
) -> list[ObservationIn]:
    """Transforma o texto do CSV em ObservationIn, acumulando todos os erros."""
    if not text.strip():
        raise CsvValidationError(["arquivo vazio"])

    reader = csv.DictReader(io.StringIO(text), delimiter=detect_delimiter(text))
    headers = [normalize_header(h) for h in (reader.fieldnames or [])]
    reader.fieldnames = headers

    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise CsvValidationError([f"coluna(s) obrigatória(s) ausente(s): {', '.join(sorted(missing))}"])
    known = REQUIRED_COLUMNS | set(OPTIONAL_COLUMNS)
    unknown = [h for h in headers if h and h not in known]
    if unknown:
        raise CsvValidationError(
            [f"coluna(s) desconhecida(s): {', '.join(unknown)} (veja docs/formato_csv.md)"]
        )

    items: list[ObservationIn] = []
    errors: list[str] = []
    # start=2: a linha 1 do arquivo é o cabeçalho
    for line_no, row in enumerate(reader, start=2):
        if None in row:  # mais valores do que colunas no cabeçalho
            errors.append(f"linha {line_no}: há mais valores do que colunas")
            continue
        values = {k: (v or "").strip() for k, v in row.items()}
        if not any(values.values()):
            continue  # ignora linhas totalmente vazias
        try:
            kwargs: dict = {
                "term": values["termo"],
                "reference_date": parse_date(values["data_referencia"]),
                "country": country,
                "is_simulated": simulated,
                "raw_payload": {"csv_line": line_no, **values},
            }
            for column, field_name in OPTIONAL_COLUMNS.items():
                raw = values.get(column, "")
                if field_name in INT_FIELDS:
                    kwargs[field_name] = parse_int(raw)
                elif field_name in FLOAT_FIELDS:
                    kwargs[field_name] = parse_number(raw, decimal_sep)
                else:
                    kwargs[field_name] = raw or None
            if kwargs["currency"]:
                kwargs["currency"] = kwargs["currency"].upper()
            items.append(ObservationIn(**kwargs))
        except ValueError as exc:
            errors.append(f"linha {line_no}: {exc}")

    if errors:
        raise CsvValidationError(errors)
    if not items:
        raise CsvValidationError(["nenhuma linha de dados encontrada"])
    return items


# ---------------------------------------------------------------- importação

def import_csv(
    engine: Engine,
    path: Path,
    source_code: str,
    source_name: str | None = None,
    country: str = "BR",
    decimal_sep: str = ",",
    simulated: bool = False,
) -> ImportResult:
    """Valida e grava um CSV como uma nova coleta (collection_run)."""
    path = Path(path)
    if not SOURCE_CODE_PATTERN.match(source_code):
        raise CsvImportError(
            f"código de fonte inválido {source_code!r}: use 2–50 letras minúsculas, números ou _"
        )
    if decimal_sep not in {",", "."}:
        raise CsvImportError("decimal_sep deve ser ',' ou '.'")
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

    # Valida TUDO antes de abrir a coleta no banco.
    items = read_observations(decode_bytes(data), country, decimal_sep, simulated)

    source_id = repo.get_or_create_source(engine, source_code, source_name or source_code)
    run_id = repo.start_run(engine, source_id, country, source_file=path.name, file_sha256=sha256)
    try:
        count = repo.add_observations(engine, run_id, items)
    except Exception as exc:
        # Registra a falha para auditoria e repassa o erro original.
        repo.finish_run(engine, run_id, "failed", error_message=str(exc)[:1000])
        raise
    repo.finish_run(engine, run_id, "success")
    return ImportResult(run_id=run_id, rows_imported=count, source_code=source_code, file_sha256=sha256)
