"""Corrida aislada de solo _personal_apoyo, con un navegador NUEVO por
diputado (no una sola sesión larga) — el patrón que sí funcionó de forma
confiable en las pruebas manuales, a diferencia de encadenar las 4
categorías en una sola sesión de Playwright (que gatilla algún tipo de
throttling de camara.cl/Cloudflare después de ~5-6 peticiones seguidas)."""

import time

from gasto_parlamentario import DIPUTADOS_COQUIMBO, USER_AGENT, ScraperGastoParlamentario
from playwright.sync_api import sync_playwright

scraper = ScraperGastoParlamentario()
scraper.log_inicio()

for autoridad_id, prm_id in DIPUTADOS_COQUIMBO.items():
    print(f"[{autoridad_id}] prmId={prm_id}", flush=True)
    intentos = 0
    while intentos < 2:
        intentos += 1
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                registros = scraper._personal_apoyo(page, autoridad_id, prm_id)
                browser.close()
            scraper.guardar(registros)
            scraper.exportar_json()
            print(f"[{autoridad_id}] guardado ({len(registros)} filas)", flush=True)
            break
        except Exception as e:
            print(f"[{autoridad_id}] intento {intentos} fallo: {e}", flush=True)
            time.sleep(5)
    time.sleep(4)

scraper.log_fin("ok")
print("listo", flush=True)
