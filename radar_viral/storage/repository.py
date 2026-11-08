"""Repositório: funções de leitura e escrita no banco.

O resto do sistema chama estas funções em vez de escrever SQL espalhado
pelo código. Se um dia trocarmos o banco, só esta camada muda.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, delete, func, insert, select, update

from radar_viral.models import ObservationIn
from radar_viral.storage.schema import (
    collection_runs,
    observations,
    product_families,
    product_links,
    sources,
    term_families,
)

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


def start_run(
    engine: Engine,
    source_id: int,
    country: str,
    source_file: str | None = None,
    file_sha256: str | None = None,
) -> int:
    """Registra o início de uma coleta e devolve o id da execução.

    source_file e file_sha256 só são usados em importações de arquivo.
    """
    with engine.begin() as conn:
        result = conn.execute(
            insert(collection_runs).values(
                source_id=source_id,
                country=country.upper(),
                started_at=utc_now(),
                status="running",
                items_collected=0,
                source_file=source_file,
                file_sha256=file_sha256,
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


def find_successful_import(engine: Engine, file_sha256: str) -> dict[str, Any] | None:
    """Procura uma importação bem-sucedida de um arquivo com este hash."""
    query = select(collection_runs).where(
        collection_runs.c.file_sha256 == file_sha256,
        collection_runs.c.status == "success",
    )
    with engine.connect() as conn:
        row = conn.execute(query).first()
    return dict(row._mapping) if row else None


def last_successful_run_at(engine: Engine) -> datetime | None:
    """Quando terminou a coleta/importação bem-sucedida mais recente."""
    query = select(collection_runs.c.finished_at).where(collection_runs.c.status == "success")
    with engine.connect() as conn:
        return conn.execute(query.order_by(collection_runs.c.finished_at.desc())).scalar()


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
    # Ordena pela data de referência; dados sem ela (coletas "ao vivo")
    # usam a data da coleta como desempate.
    query = query.order_by(
        observations.c.reference_date, observations.c.collected_at, observations.c.id
    )
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]


# ----------------------------------------------------------- famílias (Etapa 4)

def list_distinct_terms(engine: Engine, include_simulated: bool = False) -> list[str]:
    query = select(observations.c.term).distinct()
    if not include_simulated:
        query = query.where(observations.c.is_simulated.is_(False))
    with engine.connect() as conn:
        return sorted(conn.execute(query).scalars())


def get_term_assignments(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(select(term_families.c.term, term_families.c.family_id))
        return {r.term: r.family_id for r in rows}


def _unique_family_name(conn, name: str) -> str:
    candidate, n = name, 2
    while conn.execute(select(product_families.c.id).where(product_families.c.name == candidate)).first():
        candidate, n = f"{name} ({n})", n + 1
    return candidate


def create_family(engine: Engine, name: str, created_by: str) -> int:
    """Cria uma família. Se o nome já existir, acrescenta ' (2)', ' (3)'..."""
    name = (name or "").strip()
    if not name:
        raise ValueError("nome da família não pode ser vazio")
    with engine.begin() as conn:
        result = conn.execute(
            insert(product_families).values(
                name=_unique_family_name(conn, name), created_by=created_by, created_at=utc_now()
            )
        )
        return result.inserted_primary_key[0]


def get_family_id(engine: Engine, name: str) -> int | None:
    with engine.connect() as conn:
        return conn.execute(
            select(product_families.c.id).where(product_families.c.name == name.strip())
        ).scalar()


def assign_term(engine: Engine, term: str, family_id: int, method: str, similarity: float | None = None) -> None:
    """Coloca o termo na família (substitui a atribuição anterior, se houver)."""
    if method not in {"auto", "manual"}:
        raise ValueError("method deve ser 'auto' ou 'manual'")
    with engine.begin() as conn:
        conn.execute(delete(term_families).where(term_families.c.term == term))
        conn.execute(
            insert(term_families).values(
                term=term, family_id=family_id, method=method, similarity=similarity, assigned_at=utc_now()
            )
        )


def delete_auto_assignments(engine: Engine) -> int:
    """Apaga atribuições automáticas, EXCETO nas famílias que você corrigiu.

    Famílias com links de compra (Etapa 8) também ficam intactas.

    Uma correção manual ("este termo pertence a esta família") só faz sentido
    junto com os outros membros da família; por isso a família inteira fica
    congelada. Sem isso, um --refazer esvaziaria a família e criaria uma cópia.
    """
    corrected = select(term_families.c.family_id).where(term_families.c.method == "manual").union(
        select(product_links.c.family_id)  # famílias com links de compra também ficam congeladas
    )
    with engine.begin() as conn:
        result = conn.execute(
            delete(term_families).where(
                term_families.c.method == "auto", term_families.c.family_id.not_in(corrected)
            )
        )
    delete_empty_families(engine)
    return result.rowcount


def delete_empty_families(engine: Engine) -> int:
    """Apaga famílias sem termos — exceto as que têm links de compra."""
    used = select(term_families.c.family_id).union(select(product_links.c.family_id))
    with engine.begin() as conn:
        result = conn.execute(delete(product_families).where(product_families.c.id.not_in(used)))
    return result.rowcount


def rename_family(engine: Engine, old_name: str, new_name: str) -> None:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("novo nome não pode ser vazio")
    family_id = get_family_id(engine, old_name)
    if family_id is None:
        raise ValueError(f"família não encontrada: {old_name!r}")
    if get_family_id(engine, new_name) is not None:
        raise ValueError(f"já existe uma família chamada {new_name!r}")
    with engine.begin() as conn:
        conn.execute(update(product_families).where(product_families.c.id == family_id).values(name=new_name))


def list_families(engine: Engine) -> list[dict[str, Any]]:
    """Famílias com seus termos, maiores primeiro."""
    query = (
        select(
            product_families.c.id,
            product_families.c.name,
            term_families.c.term,
            term_families.c.method,
            term_families.c.similarity,
        )
        .join(term_families, term_families.c.family_id == product_families.c.id)
        .order_by(product_families.c.name, term_families.c.term)
    )
    families: dict[int, dict[str, Any]] = {}
    with engine.connect() as conn:
        for r in conn.execute(query):
            fam = families.setdefault(r.id, {"id": r.id, "name": r.name, "terms": []})
            fam["terms"].append({"term": r.term, "method": r.method, "similarity": r.similarity})
    return sorted(families.values(), key=lambda f: (-len(f["terms"]), f["name"]))


# ----------------------------------------------------------- links (Etapa 8)

def add_link(engine: Engine, family_id: int, marketplace: str, url: str, label: str | None = None) -> int:
    """Grava um link de compra JÁ VALIDADO (ver marketplaces.validate_link)."""
    with engine.begin() as conn:
        if conn.execute(select(product_families.c.id).where(product_families.c.id == family_id)).first() is None:
            raise ValueError(f"família {family_id} não existe")
        exists = conn.execute(
            select(product_links.c.id).where(product_links.c.family_id == family_id, product_links.c.url == url)
        ).first()
        if exists:
            raise ValueError(f"este link já está cadastrado nesta família (link #{exists.id})")
        result = conn.execute(
            insert(product_links).values(
                family_id=family_id, marketplace=marketplace, url=url,
                label=(label or "").strip() or None, created_at=utc_now(),
            )
        )
        return result.inserted_primary_key[0]


def list_links(engine: Engine, family_id: int | None = None) -> list[dict[str, Any]]:
    query = (
        select(product_links, product_families.c.name.label("family_name"))
        .join(product_families, product_families.c.id == product_links.c.family_id)
        .order_by(product_families.c.name, product_links.c.marketplace, product_links.c.id)
    )
    if family_id is not None:
        query = query.where(product_links.c.family_id == family_id)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(query)]


def delete_link(engine: Engine, link_id: int) -> None:
    with engine.begin() as conn:
        result = conn.execute(delete(product_links).where(product_links.c.id == link_id))
    if result.rowcount == 0:
        raise ValueError(f"link #{link_id} não encontrado")


def count_links_by_family(engine: Engine) -> dict[int, int]:
    query = select(product_links.c.family_id, func.count()).group_by(product_links.c.family_id)
    with engine.connect() as conn:
        return {fid: n for fid, n in conn.execute(query)}
