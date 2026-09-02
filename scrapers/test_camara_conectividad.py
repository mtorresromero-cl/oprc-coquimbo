"""Diagnóstico manual: ¿camara.cl responde bien desde esta máquina?

Causa raíz encontrada el 2026-09-02 (ver docs/06-bitacora.md): el
dominio "pelado" `camara.cl` (sin `www`) tiene una configuración TLS
rota en Cloudflare — el handshake falla siempre, desde cualquier red y
con cualquier cliente (hasta un Chromium real vía Playwright). El sitio
real funciona perfecto en `www.camara.cl`. Todos los scrapers de
camara.cl ya se corrigieron para usar `www.camara.cl`. Este script sigue
sirviendo como chequeo rápido de salud y como comparación permanente
entre ambos dominios, por si la configuración de Cloudflare vuelve a
cambiar.

Uso:
    pip install curl_cffi httpx playwright
    playwright install chromium
    python3 test_camara_conectividad.py

No requiere el resto del proyecto (sin imports de scrapers/, sin BD).
Playwright es opcional (~300MB, descarga un Chromium real).
"""

URLS = [
    ("Portada — SIN www (dominio roto)", "https://camara.cl/"),
    ("Portada — CON www (dominio correcto)", "https://www.camara.cl/"),
    (
        "Ficha diputado (votaciones) — CON www",
        "https://www.camara.cl/diputados/detalle/votaciones_sala.aspx?prmId=1142",
    ),
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def probar_con_httpx():
    print("\n=== 1) httpx (Python puro, sin imitar navegador) ===")
    try:
        import httpx
    except ImportError:
        print("  httpx no está instalado (pip install httpx) — se salta")
        return

    for nombre, url in URLS:
        try:
            resp = httpx.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
            )
            print(f"  [{nombre}] OK — status {resp.status_code}, {len(resp.text)} bytes")
        except Exception as e:
            print(f"  [{nombre}] ERROR — {type(e).__name__}: {e}")


def probar_con_curl_cffi():
    print("\n=== 2) curl_cffi con impersonate=chrome (misma técnica del scraper) ===")
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        print("  curl_cffi no está instalado (pip install curl_cffi) — se salta")
        return

    session = cffi_requests.Session(impersonate="chrome")
    session.headers.update({"User-Agent": USER_AGENT})
    for nombre, url in URLS:
        try:
            resp = session.get(url, timeout=20)
            print(f"  [{nombre}] OK — status {resp.status_code}, {len(resp.text)} bytes")
        except Exception as e:
            print(f"  [{nombre}] ERROR — {type(e).__name__}: {e}")


def probar_con_curl_binario():
    print("\n=== 3) curl del sistema (para comparar con lo anterior) ===")
    import subprocess

    for nombre, url in URLS:
        try:
            resultado = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", url],
                capture_output=True, text=True, timeout=25,
            )
            print(f"  [{nombre}] código HTTP: {resultado.stdout.strip() or '(sin respuesta)'}"
                  f"{' — stderr: ' + resultado.stderr.strip() if resultado.stderr else ''}")
        except Exception as e:
            print(f"  [{nombre}] ERROR — {type(e).__name__}: {e}")


def probar_con_playwright():
    print("\n=== 4) Playwright (Chromium real, headless) ===")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "  playwright no está instalado "
            "(pip install playwright && playwright install chromium) — se salta"
        )
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        for nombre, url in URLS:
            try:
                resp = page.goto(url, timeout=20000, wait_until="domcontentloaded")
                largo = len(page.content())
                print(f"  [{nombre}] OK — status {resp.status if resp else '?'}, {largo} bytes")
            except Exception as e:
                print(f"  [{nombre}] ERROR — {type(e).__name__}: {e}")
        browser.close()


if __name__ == "__main__":
    print("Probando conectividad a camara.cl desde esta máquina...")
    probar_con_httpx()
    probar_con_curl_cffi()
    probar_con_curl_binario()
    probar_con_playwright()
    print(
        "\nLo esperado: todo lo que dice 'SIN www' falla (dominio roto en "
        "Cloudflare) y todo lo que dice 'CON www' funciona (status 200). "
        "Si CON www también falla en todos los métodos, es un problema "
        "nuevo — revisar docs/06-bitacora.md."
    )
