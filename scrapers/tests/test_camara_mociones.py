import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camara_mociones import _fecha_a_iso  # noqa: E402


def test_fecha_a_iso_convierte_formato_camara():
    assert _fecha_a_iso("21 jul 2026") == "2026-07-21"


def test_fecha_a_iso_agrega_cero_a_dia_de_un_digito():
    assert _fecha_a_iso("02 jun 2026") == "2026-06-02"


def test_fecha_a_iso_texto_invalido_retorna_none():
    assert _fecha_a_iso("no es una fecha") is None
