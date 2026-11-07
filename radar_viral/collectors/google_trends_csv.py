"""Importa o CSV exportado do gráfico "Interesse ao longo do tempo" do Google Trends.

Formato confirmado com um arquivo real exportado em 07/11/2026:

    nome:  time_series_BR_20251107-0805_20261107-0805.csv
    "Time","playstation"
    "2025-11-02",59
    "2025-11-09",68

- 1ª coluna: data de início de cada período (aqui, semanas).
- Demais colunas: um termo pesquisado por coluna, valores de 0 a 100.
- O nome traz o país (BR) e o período consultado (início_fim).

COMO LER OS VALORES (importante para não tirar conclusões erradas):
os números são RELATIVOS. 100 = o ponto de maior interesse DENTRO desta
consulta (termos, país e período). Não são quantidades de buscas, e valores
de exportações diferentes não são diretamente comparáveis.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import Engine

from radar_viral.collectors.file_import import (
    CsvImportError,
    CsvValidationError,
    ImportResult,
    decode_bytes,
    read_new_file,
    save_import,
)
from radar_viral.models import ObservationIn

SOURCE_CODE = "google_trends"
SOURCE_NAME = "Google Trends (exportação manual)"
METRIC = "google_trends_0_100"
LESS_THAN_ONE_VALUE = 0.5  # "<1" = entre 0 e 1; usamos o ponto médio (texto original fica no raw_payload)

# time_series_<PAÍS>[-<REGIÃO>]_<AAAAMMDD>-<HHMM>_<AAAAMMDD>-<HHMM>
# re.match só exige que o INÍCIO combine: aceita sufixos como " (1)" que o
# navegador acrescenta quando o arquivo é baixado de novo.
FILENAME_PATTERN = re.compile(
    r"^time_series_(?P<geo>[A-Z]{2})(?:-[A-Z0-9]+)?_(?P<start>\d{8})-\d{4}_(?P<end>\d{8})-\d{4}"
)


def parse_filename(name: str) -> tuple[str, date, date] | None:
    """Extrai (país, início, fim) do nome padrão. None se o nome foi alterado."""
    m = FILENAME_PATTERN.match(name)
    if not m:
        return None
    to_date = lambda s: datetime.strptime(s, "%Y%m%d").date()  # noqa: E731
    try:
        return m["geo"], to_date(m["start"]), to_date(m["end"])
    except ValueError:
        return None


def parse_value(text: str) -> float:
    text = text.strip()
    if text == "<1":
        return LESS_THAN_ONE_VALUE
    if not text.isdigit() or int(text) > 100:
        raise ValueError(f"valor fora da escala 0–100: {text!r}")
    return float(text)


def explore_url(term: str, geo: str, start: date, end: date) -> str:
    """Link para refazer a consulta no site. Confira-o no navegador."""
    query = urlencode({"q": term, "geo": geo, "date": f"{start:%Y-%m-%d} {end:%Y-%m-%d}"})
    return f"https://trends.google.com.br/trends/explore?{query}"


def read_trends(
    text: str,
    country: str,
    period_end: date | None,
    url_info: tuple[str, date, date] | None = None,
    include_partial: bool = False,
    simulated: bool = False,
) -> tuple[list[ObservationIn], int]:
    """Converte o texto do arquivo em ObservationIn. Devolve (itens, ignorados)."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise CsvValidationError(["arquivo vazio"])

    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    header, data_rows = rows[0], rows[1:]
    terms = [t.strip() for t in header[1:]]
    if not terms or any(not t for t in terms):
        raise CsvValidationError(
            [f"cabeçalho inesperado {header!r}: esperado data seguida de um ou mais termos"]
        )
    if not data_rows:
        raise CsvValidationError(["nenhuma linha de dados encontrada"])

    errors: list[str] = []
    parsed: list[tuple[int, date, list[str]]] = []
    for line_no, row in enumerate(data_rows, start=2):
        if len(row) != len(header):
            errors.append(f"linha {line_no}: esperado {len(header)} valores, encontrado {len(row)}")
            continue
        try:
            parsed.append((line_no, datetime.strptime(row[0].strip(), "%Y-%m-%d").date(), row[1:]))
        except ValueError:
            errors.append(f"linha {line_no}: data inválida {row[0]!r}")
    dates = [d for _, d, _ in parsed]
    if dates != sorted(set(dates)):
        errors.append("as datas precisam estar em ordem crescente e sem repetição")
    if errors:
        raise CsvValidationError(errors)

    # Período parcial: o último ponto só está completo se o período inteiro
    # (ex.: 7 dias) terminou ANTES do fim da consulta. Um ponto parcial
    # parece uma queda de interesse que não aconteceu.
    skip_last = False
    if len(dates) >= 2 and period_end is not None and not include_partial:
        step = dates[-1] - dates[-2]
        skip_last = dates[-1] + step > period_end

    items: list[ObservationIn] = []
    for idx, (line_no, ref_date, values) in enumerate(parsed):
        if skip_last and idx == len(parsed) - 1:
            break
        for term, raw in zip(terms, values):
            try:
                items.append(
                    ObservationIn(
                        term=term,
                        country=country,
                        reference_date=ref_date,
                        popularity_value=parse_value(raw),
                        popularity_metric=METRIC,
                        url=explore_url(term, *url_info) if url_info else None,
                        is_simulated=simulated,
                        raw_payload={"csv_line": line_no, "date": ref_date.isoformat(), "term": term,
                                     "value": raw.strip(), "terms_in_query": terms},
                    )
                )
            except ValueError as exc:
                errors.append(f"linha {line_no} ({term}): {exc}")
    if errors:
        raise CsvValidationError(errors)
    return items, (len(terms) if skip_last else 0)


def import_google_trends(
    engine: Engine,
    path: Path,
    country: str | None = None,
    period_end: date | None = None,
    include_partial: bool = False,
    simulated: bool = False,
) -> ImportResult:
    """Importa um export do Google Trends como uma nova coleta.

    País e fim do período vêm do nome do arquivo; os parâmetros country e
    period_end servem para arquivos renomeados (ou para sobrescrever).
    """
    path = Path(path)
    info = parse_filename(path.name)
    if info:
        geo, start, end = info
        if country and country.upper() != geo:
            raise CsvImportError(f"o nome do arquivo indica país {geo}, mas foi informado {country.upper()}")
        country, period_end = geo, period_end or end
        url_info = (geo, start, end)
    else:
        if not country or period_end is None:
            raise CsvImportError(
                "o nome do arquivo não está no padrão time_series_BR_AAAAMMDD-HHMM_AAAAMMDD-HHMM; "
                "informe o país e a data final da consulta (--pais e --fim)"
            )
        url_info = None

    data, sha256 = read_new_file(engine, path)
    items, skipped = read_trends(
        decode_bytes(data), country.upper(), period_end, url_info, include_partial, simulated
    )
    if not items:
        raise CsvValidationError(["nenhum período completo para importar"])
    return save_import(
        engine,
        items,
        file_name=path.name,
        file_sha256=sha256,
        source_code=SOURCE_CODE,
        source_name=SOURCE_NAME,
        country=country.upper(),
        rows_skipped=skipped,
    )
