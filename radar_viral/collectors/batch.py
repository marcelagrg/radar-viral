"""Importação em lote: todos os exports do Google Trends de uma pasta (Etapa 9).

Cada arquivo é importado de forma INDEPENDENTE: um arquivo com erro não
impede os outros. Arquivos já importados (mesmo conteúdo = mesmo hash SHA-256)
são pulados, então rodar duas vezes na mesma pasta é seguro (idempotente).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from radar_viral.collectors.file_import import CsvImportError, DuplicateImportError
from radar_viral.collectors.google_trends_csv import import_google_trends

PATTERN = "time_series_*.csv"   # nome que o Google Trends dá aos exports
DONE_FOLDER = "importados"

# Sufixo que o navegador acrescenta ao baixar de novo: "arquivo (1).csv"
_COPY_SUFFIX = re.compile(r" \((\d+)\)$")

IMPORTED, DUPLICATE, FAILED = "importado", "já importado", "erro"


@dataclass
class FileOutcome:
    file: str
    status: str            # importado | já importado | erro
    message: str
    rows: int = 0
    skipped: int = 0       # valores do período parcial ignorados
    moved_to: str | None = None


def find_exports(folder: Path) -> list[Path]:
    """Exports do Google Trends na pasta (sem entrar em subpastas), em ordem de nome.

    O nome contém as datas da consulta, então a ordem alfabética coincide com
    a ordem cronológica: as exportações mais antigas são importadas primeiro.

    Cópias "nome (1).csv" vêm DEPOIS do original: na ordem alfabética pura o
    espaço (código 32) vem antes do ponto (46), e a cópia seria importada
    primeiro — o original apareceria como "já importado", confundindo.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise CsvImportError(f"pasta não encontrada: {folder}")

    def order(p: Path) -> tuple[str, int]:
        m = _COPY_SUFFIX.search(p.stem)
        base = p.stem[: m.start()] if m else p.stem
        return base, int(m.group(1)) if m else 0

    return sorted((p for p in folder.glob(PATTERN) if p.is_file()), key=order)


def _move(path: Path, target_dir: Path) -> Path:
    """Move sem sobrescrever: se já existir um arquivo com o mesmo nome, acrescenta _2, _3..."""
    target_dir.mkdir(exist_ok=True)
    target = target_dir / path.name
    n = 2
    while target.exists():
        target = target_dir / f"{path.stem}_{n}{path.suffix}"
        n += 1
    return Path(shutil.move(str(path), str(target)))


def import_folder(
    engine: Engine,
    folder: Path,
    include_partial: bool = False,
    simulated: bool = False,
    move_done: bool = False,
) -> list[FileOutcome]:
    outcomes: list[FileOutcome] = []
    for path in find_exports(folder):
        try:
            result = import_google_trends(engine, path, include_partial=include_partial, simulated=simulated)
            outcome = FileOutcome(path.name, IMPORTED, f"coleta #{result.run_id}",
                                  rows=result.rows_imported, skipped=result.rows_skipped)
        except DuplicateImportError as exc:
            outcome = FileOutcome(path.name, DUPLICATE, str(exc))
        except (CsvImportError, ValueError, OSError) as exc:
            # Erro de UM arquivo: registra e segue para o próximo.
            outcome = FileOutcome(path.name, FAILED, str(exc))
        # Só move o que está resolvido; arquivos com erro ficam para você corrigir.
        if move_done and outcome.status in (IMPORTED, DUPLICATE):
            outcome.moved_to = str(_move(path, Path(folder) / DONE_FOLDER))
        outcomes.append(outcome)
    return outcomes
