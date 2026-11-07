"""Normalização de texto: a camada de REGRAS da identificação de produtos.

Antes de comparar termos, removemos diferenças que não mudam o produto:
maiúsculas, acentos, pontuação e palavras "de enchimento".

    normalize_term("Mini Aspirador Portátil - KIT")  ->  "mini aspirador portatil"
"""

from __future__ import annotations

import re
import unicodedata

# Palavras que não ajudam a distinguir produtos. A lista é propositalmente
# curta: remover palavras demais apaga diferenças reais. Números NÃO são
# removidos ("playstation 4" ≠ "playstation 5").
# "simulado" é o marcador dos nossos dados de teste: um texto igual em vários
# termos infla a similaridade entre eles.
STOPWORDS = frozenset(
    """
    a o as os de da do das dos e em no na nos nas para pra por com sem um uma
    kit promocao oferta original novo nova barato barata
    simulado
    """.split()
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_NUMBER = re.compile(r"\d+")


def strip_accents(text: str) -> str:
    """'portátil' -> 'portatil'.

    NFKD separa a letra do acento ('á' vira 'a' + acento combinante);
    depois descartamos os caracteres combinantes.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_term(text: str) -> str:
    text = strip_accents((text or "").lower())
    words = _NON_ALNUM.sub(" ", text).split()
    return " ".join(w for w in words if w not in STOPWORDS)


def model_numbers(normalized: str) -> frozenset[str]:
    """Números que costumam indicar modelo/versão: 'iphone 15 pro' -> {'15'}."""
    return frozenset(_NUMBER.findall(normalized))


def numbers_conflict(a: str, b: str) -> bool:
    """True quando os dois termos têm números E eles são diferentes.

    'playstation 4' x 'playstation 5' -> True  (modelos diferentes)
    'playstation'   x 'playstation 5' -> False (um deles não especifica)
    """
    na, nb = model_numbers(a), model_numbers(b)
    return bool(na) and bool(nb) and na != nb
