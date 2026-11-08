"""Links de compra. Links e famílias aqui são de TESTE (não verificados nos sites)."""

from datetime import date

import pytest

from radar_viral.marketplaces import save_link, search_links, validate_link
from radar_viral.models import ObservationIn
from radar_viral.processing.product_families import group_terms
from radar_viral.storage import repository as repo


@pytest.mark.parametrize(
    "mp, url",
    [
        ("amazon", "https://www.amazon.com.br/dp/B0EXEMPLO"),
        ("amazon", "https://amzn.to/abc123"),
        ("shopee", "https://shopee.com.br/produto-i.1.2"),
        ("shopee", "https://s.shopee.com.br/abc"),
        ("mercadolivre", "https://produto.mercadolivre.com.br/MLB-123"),
        ("mercadolivre", "https://mercadolivre.com/sec/abc"),
    ],
)
def test_links_validos(mp, url):
    assert validate_link(mp, url) == url


@pytest.mark.parametrize(
    "mp, url, trecho",
    [
        ("amazon", "http://www.amazon.com.br/dp/X", "https"),
        ("amazon", "https://www.amazon.com.br.golpe.com/dp/X", "não é do Amazon"),  # imitação
        ("amazon", "https://shopee.com.br/x", "não é do Amazon"),                    # site trocado
        ("shopee", "javascript:alert(1)", "https"),
        ("shopee", "", "https"),
        ("ebay", "https://ebay.com/x", "marketplace inválido"),
    ],
)
def test_links_invalidos(mp, url, trecho):
    with pytest.raises(ValueError, match=trecho):
        validate_link(mp, url)


def test_links_de_busca():
    links = search_links("Mini Aspirador Portátil")
    assert links["Amazon"] == "https://www.amazon.com.br/s?k=Mini+Aspirador+Port%C3%A1til"
    assert links["Shopee"] == "https://shopee.com.br/search?keyword=Mini+Aspirador+Port%C3%A1til"
    assert links["Mercado Livre"] == "https://lista.mercadolivre.com.br/mini-aspirador-portatil"


def make_family(engine, term="[SIMULADO] fone bluetooth"):
    src = repo.get_or_create_source(engine, "teste", "Teste")
    run = repo.start_run(engine, src, "BR")
    repo.add_observations(engine, run, [ObservationIn(term=term, reference_date=date(2026, 1, 4), is_simulated=True)])
    repo.finish_run(engine, run, "success")
    group_terms(engine, threshold=0.45, include_simulated=True)
    return repo.get_term_assignments(engine)[term]


def test_salvar_listar_remover(engine):
    fid = make_family(engine)
    lid = save_link(engine, fid, "shopee", "https://shopee.com.br/x", "  kit com 2  ")
    [link] = repo.list_links(engine, fid)
    assert link["label"] == "kit com 2" and link["family_name"] == "[SIMULADO] fone bluetooth"
    assert repo.count_links_by_family(engine) == {fid: 1}
    with pytest.raises(ValueError, match="já está cadastrado"):
        save_link(engine, fid, "shopee", "https://shopee.com.br/x")
    repo.delete_link(engine, lid)
    assert repo.list_links(engine) == []
    with pytest.raises(ValueError, match="não encontrado"):
        repo.delete_link(engine, lid)


def test_familia_inexistente(engine):
    with pytest.raises(ValueError, match="não existe"):
        save_link(engine, 999, "amazon", "https://www.amazon.com.br/dp/X")


def test_refazer_preserva_familia_com_links(engine):
    """Sem esta proteção, --refazer apagaria a família e os seus links."""
    fid = make_family(engine)
    save_link(engine, fid, "amazon", "https://www.amazon.com.br/dp/X")
    group_terms(engine, threshold=0.45, rebuild=True, include_simulated=True)
    assert repo.get_term_assignments(engine)["[SIMULADO] fone bluetooth"] == fid
    assert len(repo.list_links(engine, fid)) == 1
