import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from poblar_catalogo import slugificar  # noqa: E402


def test_slugificar_normaliza_tildes_y_espacios():
    assert slugificar("María José Núñez") == "maria-jose-nunez"


def test_slugificar_colapsa_separadores_repetidos():
    assert slugificar("  Río   Hurtado  ") == "rio-hurtado"
