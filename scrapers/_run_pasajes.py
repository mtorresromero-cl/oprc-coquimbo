"""Misma estrategia que _run_personal_apoyo.py (navegador nuevo por
diputado), aplicada a pasajes_aereos."""

import time

from gasto_parlamentario import DIPUTADOS_COQUIMBO, USER_AGENT, ScraperGastoParlamentario
from playwright.sync_api import sync_playwright

scraper = ScraperGastoParlamentario()

for autoridad_id, prm_id in DIPUTADOS_COQUIMBO.items():
    print(f"[{autoridad_id}] prmId={prm_id}", flush=True)
    intentos = 0
    while intentos < 2:
        intentos += 1
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                registros = scraper._pasajes_aereos(page, autoridad_id, prm_id)
                browser.close()
            scraper.guardar(registros)
            scraper.exportar_json()
            print(f"[{autoridad_id}] guardado ({len(registros)} filas)", flush=True)
            break
        except Exception as e:
            print(f"[{autoridad_id}] intento {intentos} fallo: {e}", flush=True)
            time.sleep(5)
    time.sleep(4)

print("listo", flush=True)
