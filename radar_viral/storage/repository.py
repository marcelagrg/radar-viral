"""Repositório: funções de leitura e escrita no banco.

O resto do sistema chama estas funções em vez de escrever SQL espalhado
pelo código. Se um dia trocarmos o banco, só esta camada muda.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, insert, select, update

from radar_viral.models import ObservationIn
from radar_viral.storage.schema import collection_runs, observations, sources

VALID_FINAL_STATUS = {"success", "partial", "failed"}


def utc_now() -> datetime:
    """Sempre gravamos horários em UTC para evitar confusão de fuso/horário de verão."""
    return datetime.now(timezone.utc)


def get_or_create_source(engine: Engine, code: str, name: str, base_url: str | None = None) -> int:
    """Devolve o id da fonte; cria o registro se ainda não existir."""
    with engine.begin() as conn:  # begin() = transação com commit automático
        found = conn.execute(select(sources.c.id).where(sources.c.code == code)).scalar()
        if found is not None:
            return found
        result = conn.execute(
            insert(sources).values(code=code, name=name, base_url=base_url, created_at=utc_now())
        )
        return result.inserted_primary_key[0]


def start_run(engine: Engine, source_id: int, country: str) -> int:
    """Registra o início de uma coleta e devolve o id da execução."""
    with engine.begin() as conn:
        result = conn.execute(
            insert(collection_runs).values(
                source_id=source_id,
                country=country.upper(),
                started_at=utc_now(),
                status="running",
                items_collected=0,
            )
        )
        return result.inserted_primary_key[0]


def finish_run(engine: Engine, run_id: int, status: str, error_message: str | None = None) -> None:
    """Fecha uma coleta, gravando status final e total de itens."""
    if status not in VALID_FINAL_STATUS:
        raise ValueError(f"status inválido: {status!r}. Opções: {sorted(VALID_FINAL_STATUS)}")
    with engine.begin() as conn:
        total = conn.execute(
            select(observations.c.id).where(observations.c.run_id == run_id)
        ).all()
        conn.execute(
            update(collection_runs)
            .where(collection_runs.c.id == run_id)
            .values(
                finished_at=utc_now(),
                status=status,
                items_collected=len(total),
                error_message=error_message,
            )
        )


def add_observations(engine: Engine, run_id: int, items: Iterable[ObservationIn]) -> int:
    """Grava observações de uma coleta. Tudo ou nada: se uma falhar, nenhuma é gravada."""
    items = list(items)
    if not items:
        return 0
    with engine.begin() as conn:
        run = conn.execute(
            select(collection_runs.c.source_id, collection_runs.c.status).where(
                collection_runs.c.id == run_id
            )
        ).first()
        if run is None:
            raise ValueError(f"coleta {run_id} não existe")
        if run.status != "running":
            raise ValueError(f"coleta {run_id} já foi finalizada ({run.status})")
        collected_at = utc_now()
        rows = [
            {**asdict(item), "run_id": run_id, "source_id": run.source_id, "collected_at": collected_at}
            for item in items
        ]
        conn.execute(insert(observations), rows)
    return len(rows)


def get_term_history(engine: Engine, term: str, include_simulated: bool = False) -> list[dict[str, Any]]:
    """Histórico completo de um termo, do mais antigo ao mais recente."""
    query = select(observations).where(observations.c.term == term)
    if not include_simulated:
        query = query.where(observations.c.is_simulated.is_(False))
    query = query.order_by(observations.c.collected_at, observations.c.id)
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]
