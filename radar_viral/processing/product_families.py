"""Agrupamento de termos em famílias de produtos.

Três camadas, da mais simples para a mais sofisticada:

1. REGRAS (text_normalizer.py): normalização e "números de modelo".
2. SIMILARIDADE DE TEXTO (este arquivo): TF-IDF de n-gramas de caracteres +
   similaridade de cosseno + agrupamento hierárquico.
3. CORREÇÃO MANUAL: você move termos entre famílias; o automático respeita.

Limitação conhecida: a camada 2 compara LETRAS, não SIGNIFICADO. Ela agrupa
"mini aspirador portátil" e "mini aspiradores portáteis", mas não sabe que
"aspirador de mesa USB" é o mesmo tipo de produto. Isso exigiria embeddings
ou IA (avaliados quando houver dados reais suficientes) ou correção manual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import Engine

from radar_viral.processing.text_normalizer import normalize_term, numbers_conflict
from radar_viral.storage import repository as repo

# Distância "infinita" para pares proibidos (números de modelo diferentes).
# Com average linkage a distância entre grupos é a MÉDIA dos pares; um valor
# enorme garante que a média estoure o limite mesmo em grupos grandes.
CANNOT_LINK_DISTANCE = 1_000.0


def similarity_matrix(terms: list[str]) -> np.ndarray:
    """Matriz N x N com a similaridade (0 a 1) entre cada par de termos.

    analyzer="char_wb", ngram_range=(3, 5): cada termo vira um vetor com os
    pedaços de 3 a 5 letras de cada palavra ("aspirador" -> "asp", "spi",
    "pir"...). Por isso "aspirador" e "aspiradores" ficam parecidos sem
    precisarmos de regras de plural.
    """
    normalized = [normalize_term(t) or t.lower() for t in terms]
    vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(normalized)
    sim = cosine_similarity(vectors)
    for i in range(len(terms)):
        for j in range(i + 1, len(terms)):
            if numbers_conflict(normalized[i], normalized[j]):
                sim[i, j] = sim[j, i] = -np.inf  # marcador de "proibido"
    return sim


def cluster(sim: np.ndarray, threshold: float) -> list[list[int]]:
    """Agrupa índices de modo que a similaridade MÉDIA dentro do grupo >= threshold.

    Agrupamento hierárquico aglomerativo: começa com cada termo sozinho e vai
    juntando os dois grupos mais parecidos até nenhum par passar do limite.
    "average" evita o efeito corrente (A~B, B~C, mas A muito diferente de C).
    """
    n = sim.shape[0]
    if n == 1:
        return [[0]]
    distance = np.where(np.isneginf(sim), CANNOT_LINK_DISTANCE, 1.0 - sim)
    np.fill_diagonal(distance, 0.0)
    labels = AgglomerativeClustering(
        n_clusters=None,
        metric="precomputed",
        linkage="average",
        distance_threshold=1.0 - threshold,
    ).fit_predict(distance)
    groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(idx)
    return sorted(groups.values(), key=lambda g: min(g))


def representative(indices: list[int], sim: np.ndarray, terms: list[str]) -> int:
    """Escolhe o termo mais "central" do grupo (o medoide) para nomear a família.

    É o termo com maior similaridade média com os demais. Empate -> o mais curto.
    """
    if len(indices) == 1:
        return indices[0]
    sub = np.where(np.isneginf(sim), 0.0, sim)[np.ix_(indices, indices)]
    scores = (sub.sum(axis=1) - 1.0) / (len(indices) - 1)
    return min(indices, key=lambda i: (-round(float(scores[indices.index(i)]), 6), len(terms[i]), terms[i]))


@dataclass
class GroupingSummary:
    terms_total: int
    already_assigned: int
    joined_existing: int
    new_families: int
    terms_in_new_families: int


def group_terms(
    engine: Engine,
    threshold: float,
    rebuild: bool = False,
    include_simulated: bool = False,
) -> GroupingSummary:
    """Atribui uma família a cada termo ainda sem família.

    Incremental por padrão: termos já agrupados ficam onde estão, para que os
    ids das famílias não mudem a cada execução. rebuild=True recalcula as
    atribuições automáticas; famílias com alguma correção manual ficam intactas.
    """
    if not 0 < threshold < 1:
        raise ValueError("threshold deve estar entre 0 e 1")
    if rebuild:
        repo.delete_auto_assignments(engine)

    terms = repo.list_distinct_terms(engine, include_simulated=include_simulated)
    if not terms:
        return GroupingSummary(0, 0, 0, 0, 0)
    assigned = repo.get_term_assignments(engine)  # termo -> family_id
    pool = terms  # só termos com observações (simulados ficam de fora por padrão)
    sim = similarity_matrix(pool)
    index = {t: i for i, t in enumerate(pool)}

    pending = [t for t in pool if t not in assigned]
    already = len(pool) - len(pending)

    # 1) Termos novos entram numa família existente se a similaridade média
    #    com os membros dela for >= threshold e não houver conflito de modelo.
    members: dict[int, list[int]] = {}
    for term, fam in assigned.items():
        if term in index:
            members.setdefault(fam, []).append(index[term])
    joined = 0
    leftovers: list[str] = []
    for term in pending:
        i = index[term]
        best_fam, best_score = None, -1.0
        for fam, idxs in members.items():
            row = sim[i, idxs]
            if np.isneginf(row).any():
                continue
            score = float(row.mean())
            if score > best_score:
                best_fam, best_score = fam, score
        if best_fam is not None and best_score >= threshold:
            repo.assign_term(engine, term, best_fam, method="auto", similarity=best_score)
            members[best_fam].append(i)
            joined += 1
        else:
            leftovers.append(term)

    # 2) O que sobrou é agrupado entre si e vira famílias novas.
    new_families = terms_in_new = 0
    if leftovers:
        sub_idx = [index[t] for t in leftovers]
        sub_sim = sim[np.ix_(sub_idx, sub_idx)]
        for group in cluster(sub_sim, threshold):
            rep = representative(group, sub_sim, leftovers)
            family_id = repo.create_family(engine, leftovers[rep], created_by="auto")
            for g in group:
                row = np.where(np.isneginf(sub_sim[g, group]), 0.0, sub_sim[g, group])
                avg = float((row.sum() - 1.0) / (len(group) - 1)) if len(group) > 1 else 1.0
                repo.assign_term(engine, leftovers[g], family_id, method="auto", similarity=avg)
            new_families += 1
            terms_in_new += len(group)

    repo.delete_empty_families(engine)
    return GroupingSummary(len(pool), already, joined, new_families, terms_in_new)
