#!/usr/bin/env python3
"""Inserta en la app de Campos el payload cifrado generado por recifrar-campos.html.

Sustituye únicamente PAYLOAD_B64 e IV_B64 dentro de utmach_campos_conocimiento.html,
sin tocar el resto del archivo (para no pisar el trabajo hecho sobre la app).

Uso:  python3 insertar_payload.py ~/Downloads/payload-campos.txt
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "utmach_campos_conocimiento.html")


def main(src):
    txt = open(src, encoding="utf-8").read()
    m_p = re.search(r"^PAYLOAD_B64=(\S+)$", txt, re.M)
    m_i = re.search(r"^IV_B64=(\S+)$", txt, re.M)
    if not m_p or not m_i:
        sys.exit("✗ El archivo no contiene PAYLOAD_B64= e IV_B64=. ¿Es el que descargó recifrar-campos.html?")
    payload, iv = m_p.group(1), m_i.group(1)

    # validación mínima: base64 correcto y tamaños coherentes
    import base64
    try:
        raw = base64.b64decode(payload, validate=True)
        raw_iv = base64.b64decode(iv, validate=True)
    except Exception as e:
        sys.exit(f"✗ base64 inválido: {e}")
    if len(raw_iv) != 12:
        sys.exit(f"✗ IV de {len(raw_iv)} bytes; AES-GCM requiere 12.")
    if len(raw) < 50_000:
        sys.exit(f"✗ payload sospechosamente pequeño ({len(raw)} bytes).")

    app = open(APP, encoding="utf-8").read()
    ant_p = re.search(r'PAYLOAD_B64="([^"]*)"', app)
    ant_i = re.search(r'\bIV_B64="([^"]*)"', app)
    if not ant_p or not ant_i:
        sys.exit("✗ No se encontraron PAYLOAD_B64/IV_B64 en la app.")

    nuevo = app.replace(f'PAYLOAD_B64="{ant_p.group(1)}"', f'PAYLOAD_B64="{payload}"', 1)
    nuevo = nuevo.replace(f'IV_B64="{ant_i.group(1)}"', f'IV_B64="{iv}"', 1)

    if nuevo == app:
        sys.exit("✗ No se sustituyó nada.")
    # el resto del archivo debe quedar intacto
    resto_antes = app.replace(ant_p.group(1), "").replace(ant_i.group(1), "")
    resto_despues = nuevo.replace(payload, "").replace(iv, "")
    if resto_antes != resto_despues:
        sys.exit("✗ El reemplazo alteró algo más que el payload. Abortado.")

    shutil.copy(APP, APP + ".bak")
    open(APP, "w", encoding="utf-8").write(nuevo)
    print(f"✓ Payload insertado en utmach_campos_conocimiento.html (respaldo .bak)")
    print(f"  payload: {len(ant_p.group(1))//1024} KB → {len(payload)//1024} KB")
    print(f"  app:     {len(app)//1024} KB → {len(nuevo)//1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python3 insertar_payload.py <payload-campos.txt>")
    main(sys.argv[1])
