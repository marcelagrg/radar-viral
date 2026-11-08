"""Marketplaces onde os produtos podem ser comprados (Etapa 8).

Duas coisas, ambas SEM acessar os sites:
1. validar links que VOCÊ cola (produto ou link de afiliada);
2. montar links de BUSCA para abrir no navegador.

Para incluir outro marketplace, basta acrescentar uma entrada em MARKETPLACES.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus, urlparse

from sqlalchemy import Engine

from radar_viral.processing.text_normalizer import strip_accents
from radar_viral.storage import repository as repo


@dataclass(frozen=True)
class Marketplace:
    code: str
    name: str
    # Domínios aceitos (e seus subdomínios). Inclui os encurtadores oficiais
    # usados em links de afiliado.
    domains: tuple[str, ...]

    def search_url(self, term: str) -> str:
        return SEARCH_BUILDERS[self.code](term.strip())


def _mercadolivre_search(term: str) -> str:
    # O Mercado Livre usa o termo no caminho, com hífens: /mini-aspirador-portatil
    slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(term.lower())).strip("-")
    return f"https://lista.mercadolivre.com.br/{quote(slug)}"


SEARCH_BUILDERS = {
    "amazon": lambda t: f"https://www.amazon.com.br/s?k={quote_plus(t)}",
    "shopee": lambda t: f"https://shopee.com.br/search?keyword={quote_plus(t)}",
    "mercadolivre": _mercadolivre_search,
}

MARKETPLACES: dict[str, Marketplace] = {
    "amazon": Marketplace("amazon", "Amazon", ("amazon.com.br", "amzn.to")),
    "shopee": Marketplace("shopee", "Shopee", ("shopee.com.br",)),
    "mercadolivre": Marketplace("mercadolivre", "Mercado Livre", ("mercadolivre.com.br", "mercadolivre.com")),
}


def get_marketplace(code: str) -> Marketplace:
    try:
        return MARKETPLACES[code]
    except KeyError:
        raise ValueError(f"marketplace inválido {code!r}; opções: {', '.join(MARKETPLACES)}") from None


def validate_link(marketplace_code: str, url: str) -> str:
    """Confere se o link é https e pertence ao marketplace escolhido.

    Proteção contra erros de colagem e contra links falsos que imitam o nome
    do site: 'amazon.com.br.golpe.com' NÃO termina em '.amazon.com.br'.
    """
    mp = get_marketplace(marketplace_code)
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("o link deve começar com https://")
    host = (parsed.hostname or "").lower()
    if not any(host == d or host.endswith("." + d) for d in mp.domains):
        raise ValueError(
            f"o link não é do {mp.name} (domínio {host or 'vazio'!r}; aceitos: {', '.join(mp.domains)})"
        )
    if len(url) > 1000:
        raise ValueError("link longo demais (máx. 1000 caracteres)")
    return url


def search_links(term: str) -> dict[str, str]:
    """{'Amazon': 'https://...', ...} — buscas prontas para abrir no navegador."""
    return {mp.name: mp.search_url(term) for mp in MARKETPLACES.values()}


def save_link(engine: Engine, family_id: int, marketplace_code: str, url: str, label: str | None = None) -> int:
    """Valida e grava. Ponto único usado pelo terminal e pelo painel."""
    return repo.add_link(engine, family_id, marketplace_code, validate_link(marketplace_code, url), label)
