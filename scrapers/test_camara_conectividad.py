"""Diagnóstico manual: ¿camara.cl responde desde esta red o no?

Corre esto desde una máquina/servidor DISTINTO a este sandbox y a GitHub
Actions (ej. el VPS propio, o tu computador) para saber si el bloqueo es
específico de esas IPs o del sitio en general. Ver docs/06-bitacora.md
(entradas del 2026-09-02) para todo el contexto: desde el 25 de agosto
camara.cl falla con error TLS (ERR_SSL_VERSION_OR_CIPHER_MISMATCH) tanto
con Playwright como con curl_cffi, desde este sandbox y desde GitHub
Actions — nunca desde un navegador normal.

Uso:
    pip install curl_cffi httpx
    python3 test_camara_conectividad.py

No requiere el resto del proyecto (sin imports de scrapers/, sin BD).
"""

URLS = [
    ("Portada", "https://camara.cl/"),
    (
        "Ficha diputado (mociones, GET simple)",
        "https://camara.cl/diputados/detalle/mociones.aspx?prmID=1142",
    ),
    (
        "Ficha diputado (votaciones, la que falla siempre)",
        "https://camara.cl/diputados/detalle/votaciones_sala.aspx?prmId=1142",
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


if __name__ == "__main__":
    print("Probando conectividad a camara.cl desde esta máquina...")
    probar_con_httpx()
    probar_con_curl_cffi()
    probar_con_curl_binario()
    print(
        "\nSi todo lo anterior falló con errores tipo SSL/TLS (handshake, "
        "cipher mismatch), esta red también está bloqueada — probar desde "
        "otra (otro VPS, otra nube, casa) para seguir acotando el problema.\n"
        "Si algo funcionó (status 200 y bytes > 0), esta red SÍ puede "
        "usarse para correr los scrapers de camara.cl."
    )
