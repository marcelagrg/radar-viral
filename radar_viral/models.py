"""Modelos de dados usados entre os módulos.

Um coletor (Etapa 2 em diante) não fala diretamente com o banco: ele produz
objetos ObservationIn, e o repositório decide como gravá-los. Essa separação
permite trocar ou adicionar fontes sem mexer no armazenamento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ObservationIn:
    """Uma observação: o que uma fonte disse sobre um produto/termo num momento.

    Campos opcionais ficam None quando a fonte não fornece a informação.
    Nunca preenchemos com valores inventados.
    """

    term: str                         # nome do produto ou termo pesquisado
    country: str = "BR"               # código ISO de 2 letras
    reference_date: date | None = None  # data a que o valor se refere
    external_id: str | None = None    # id do item na fonte (ex.: MLB123...)
    category_id: str | None = None
    category_name: str | None = None
    rank_position: int | None = None  # posição no ranking da fonte (1 = topo)
    search_volume: float | None = None
    popularity_value: float | None = None  # indicador de popularidade da fonte
    popularity_metric: str | None = None   # o que popularity_value significa
    price: float | None = None
    currency: str | None = None
    url: str | None = None            # link para conferir a informação original
    is_simulated: bool = False        # True = dado de teste, NÃO real
    raw_payload: dict[str, Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.term = (self.term or "").strip()
        if not self.term:
            raise ValueError("term não pode ser vazio")
        self.country = (self.country or "").strip().upper()
        if len(self.country) != 2 or not self.country.isalpha():
            raise ValueError(f"country inválido: {self.country!r}")
        if self.reference_date is not None and self.reference_date > date.today():
            raise ValueError(f"reference_date no futuro: {self.reference_date}")
        if self.rank_position is not None and self.rank_position < 1:
            raise ValueError("rank_position deve ser >= 1")
        for name in ("price", "search_volume"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} não pode ser negativo")
        if self.popularity_value is not None and not self.popularity_metric:
            raise ValueError("informe popularity_metric junto com popularity_value")
        if self.url is not None and not self.url.startswith(("http://", "https://")):
            raise ValueError(f"url inválida: {self.url!r}")
