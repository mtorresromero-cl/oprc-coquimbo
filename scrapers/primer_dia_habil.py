"""¿Es hoy el primer día hábil (lunes a viernes, no feriado) del mes en
Chile? Se usa para el disparo mensual del informe (ver
.github/workflows/informe-mensual.yml): el cron corre todos los días 1 al 5
de cada mes, pero el informe solo debe generarse/enviarse una vez — el
primer día hábil real. Así, si el día 1 cae sábado, domingo o feriado, el
correo sale el primer día que la gente realmente lo va a revisar, en vez
de un fin de semana o un feriado donde nadie lo lee.

Uso: python scrapers/primer_dia_habil.py
Sale con código 0 (y "true") si hoy es el primer día hábil del mes, 1 (y
"false") si no.
"""

import sys
from datetime import date, timedelta

import holidays


def primer_dia_habil_del_mes(anno: int, mes: int) -> date:
    dia = date(anno, mes, 1)
    feriados_cl = holidays.Chile(years=anno)
    while dia.weekday() >= 5 or dia in feriados_cl:
        dia += timedelta(days=1)
    return dia


def main() -> None:
    hoy = date.today()
    es_hoy = hoy == primer_dia_habil_del_mes(hoy.year, hoy.month)
    print("true" if es_hoy else "false")
    sys.exit(0 if es_hoy else 1)


if __name__ == "__main__":
    main()
