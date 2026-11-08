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
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

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


# Fuso usado para decidir a que DIA pertence um horário (exports de 7 dias
# vêm em UTC). Países fora da lista usam UTC.
COUNTRY_TIMEZONES = {"BR": "America/Sao_Paulo"}


def _parse_rows(data_rows, header) -> tuple[list[tuple[int, datetime | date, list[str]]], bool, list[str]]:
    """Lê a 1ª coluna como data ('2026-10-10') ou data-hora ('2026-11-01T12:00:00Z').

    Devolve (linhas, tem_horario, erros). Todas as linhas precisam do mesmo formato.
    """
    errors, parsed = [], []
    has_time = "T" in data_rows[0][0] if data_rows and data_rows[0] else False
    for line_no, row in enumerate(data_rows, start=2):
        if len(row) != len(header):
            errors.append(f"linha {line_no}: esperado {len(header)} valores, encontrado {len(row)}")
            continue
        text = row[0].strip()
        try:
            if has_time != ("T" in text):
                raise ValueError
            # fromisoformat entende o 'Z' (UTC) a partir do Python 3.11
            when = datetime.fromisoformat(text) if has_time else datetime.strptime(text, "%Y-%m-%d").date()
            if has_time and when.tzinfo is None:
                raise ValueError
            parsed.append((line_no, when, row[1:]))
        except ValueError:
            errors.append(f"linha {line_no}: data inválida {row[0]!r}")
    stamps = [w for _, w, _ in parsed]
    if stamps != sorted(set(stamps)):
        errors.append("as datas precisam estar em ordem crescente e sem repetição")
    return parsed, has_time, errors


def _daily_from_subdaily(parsed, terms, country, include_partial, errors):
    """Agrupa pontos de algumas horas (export de 7 dias) em UM valor por dia.

    - O dia é o do fuso do país (BR: horário de Brasília), não o de UTC.
    - Valor do dia = MÉDIA dos pontos (mantém a escala 0–100 do Trends).
    - Dia incompleto (menos pontos que o esperado, típico do 1º e do último
      dia do export) é descartado, salvo include_partial=True.
    Devolve [(linhas, dia, {termo: (valor, textos_originais)})] e o nº de dias descartados.
    """
    if len(parsed) < 2:
        errors.append("export com horário precisa de pelo menos 2 pontos")
        return [], 0
    step = min(b[1] - a[1] for a, b in zip(parsed, parsed[1:]))
    if step < timedelta(hours=1) or timedelta(days=1) % step:
        errors.append(
            f"intervalo de {step} entre pontos não é suportado; use exports de 7 dias, 30 dias ou 12 meses"
        )
        return [], 0
    expected = timedelta(days=1) // step
    tz = ZoneInfo(COUNTRY_TIMEZONES.get(country, "UTC"))

    by_day: dict[date, list] = {}
    for line_no, when, values in parsed:
        by_day.setdefault(when.astimezone(tz).date(), []).append((line_no, values))

    out, dropped = [], 0
    for day, points in sorted(by_day.items()):
        if len(points) < expected and not include_partial:
            dropped += 1
            continue
        per_term = {}
        for i, term in enumerate(terms):
            raws = [values[i].strip() for _, values in points]
            try:
                per_term[term] = (sum(parse_value(r) for r in raws) / len(raws), raws)
            except ValueError as exc:
                errors.append(f"dia {day:%d/%m/%Y} ({term}): {exc}")
        out.append(([ln for ln, _ in points], day, per_term))
    return out, dropped


def read_trends(
    text: str,
    country: str,
    period_end: date | None,
    url_info: tuple[str, date, date] | None = None,
    include_partial: bool = False,
    simulated: bool = False,
) -> tuple[list[ObservationIn], int]:
    """Converte o texto do arquivo em ObservationIn. Devolve (itens, valores ignorados).

    Aceita os três formatos de export confirmados com arquivos reais:
    12 meses (semanal, '2025-11-02'), 30 dias (diário, '2026-10-10') e
    7 dias (a cada 4 horas, '2026-11-01T12:00:00Z' -> agregado por dia).
    """
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

    parsed, has_time, errors = _parse_rows(data_rows, header)
    if errors:
        raise CsvValidationError(errors)

    # periods: [(linhas_do_csv, dia, {termo: (valor, textos_originais)})]
    if has_time:
        periods, dropped_days = _daily_from_subdaily(parsed, terms, country, include_partial, errors)
        skipped = dropped_days * len(terms)
    else:
        periods = []
        for line_no, day, values in parsed:
            per_term = {}
            for term, raw in zip(terms, values):
                try:
                    per_term[term] = (parse_value(raw), [raw.strip()])
                except ValueError as exc:
                    errors.append(f"linha {line_no} ({term}): {exc}")
            periods.append(([line_no], day, per_term))
        # Período parcial: o último ponto só está completo se o período inteiro
        # (ex.: 7 dias, ou 1 dia) terminou ANTES do fim da consulta. Um ponto
        # parcial parece uma queda de interesse que não aconteceu.
        skipped = 0
        days = [d for _, d, _ in periods]
        if len(days) >= 2 and period_end is not None and not include_partial:
            if days[-1] + (days[-1] - days[-2]) > period_end:
                periods, skipped = periods[:-1], len(terms)
    if errors:
        raise CsvValidationError(errors)

    items: list[ObservationIn] = []
    for line_nos, day, per_term in periods:
        for term, (value, raws) in per_term.items():
            try:
                items.append(
                    ObservationIn(
                        term=term,
                        country=country,
                        reference_date=day,
                        popularity_value=value,
                        popularity_metric=METRIC,
                        url=explore_url(term, *url_info) if url_info else None,
                        is_simulated=simulated,
                        raw_payload={"csv_lines": line_nos, "date": day.isoformat(), "term": term,
                                     "values": raws, "terms_in_query": terms,
                                     "aggregated": "média diária" if has_time else None},
                    )
                )
            except ValueError as exc:
                errors.append(f"{day:%d/%m/%Y} ({term}): {exc}")
    if errors:
        raise CsvValidationError(errors)
    return items, skipped


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
