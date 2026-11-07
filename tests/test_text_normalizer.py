import pytest

from radar_viral.processing.text_normalizer import model_numbers, normalize_term, numbers_conflict


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Mini Aspirador Portátil", "mini aspirador portatil"),
        ("aspirador de mesa USB", "aspirador mesa usb"),
        ("KIT Garrafa Térmica - PROMOÇÃO!!", "garrafa termica"),
        ("PlayStation 5", "playstation 5"),
        ("   ", ""),
    ],
)
def test_normalize(raw, expected):
    assert normalize_term(raw) == expected


def test_numeros_de_modelo():
    assert model_numbers("iphone 15 pro 256") == {"15", "256"}
    assert numbers_conflict("playstation 4", "playstation 5")
    assert not numbers_conflict("playstation", "playstation 5")
    assert not numbers_conflict("fone x 2", "fone x 2")


def test_marcador_simulado_e_ignorado():
    assert normalize_term("mini aspirador [SIMULADO]") == "mini aspirador"
