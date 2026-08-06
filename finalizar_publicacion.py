#!/usr/bin/env python3
"""Cierra la publicación una vez que existen los dos archivos cifrados.

Toma los archivos que genera publicar.html, los coloca en el proyecto, verifica que
todo esté coherente y deja el commit hecho. No hace push por sí solo: lo muestra para
que se revise antes.

Uso:
    python3 finalizar_publicacion.py                      # los busca en ~/Downloads
    python3 finalizar_publicacion.py ruta/datos-senescyt.js ruta/payload-campos.txt
    python3 finalizar_publicacion.py --push               # además publica
"""
import base64
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.expanduser("~/Downloads")
APP = os.path.join(HERE, "utmach_campos_conocimiento.html")
SEN_JS = os.path.join(HERE, "datos-senescyt.js")


def err(m):
    sys.exit(f"✗ {m}")


def buscar(nombre, explicito=None):
    if explicito:
        if not os.path.exists(explicito):
            err(f"no existe {explicito}")
        return explicito
    p = os.path.join(DOWNLOADS, nombre)
    if not os.path.exists(p):
        err(f"no encuentro {nombre} en {DOWNLOADS}. Genéralo en publicar.html "
            f"o pásame la ruta como argumento.")
    return p


def verificar_sen(path):
    """El payload del buscador debe ser window.SEN={p,iv} con base64 válido."""
    t = open(path, encoding="utf-8").read()
    m = re.search(r'window\.SEN\s*=\s*\{p:"([^"]+)",iv:"([^"]+)"\}', t)
    if not m:
        err(f"{os.path.basename(path)} no tiene la forma window.SEN={{p,iv}}")
    ct, iv = base64.b64decode(m.group(1), validate=True), base64.b64decode(m.group(2), validate=True)
    if len(iv) != 12:
        err(f"IV de {len(iv)} bytes; AES-GCM requiere 12")
    if len(ct) < 50_000:
        err(f"payload del buscador sospechosamente pequeño ({len(ct)} bytes)")
    return len(ct)


def main():
    argv = [a for a in sys.argv[1:] if a != "--push"]
    push = "--push" in sys.argv
    sen = buscar("datos-senescyt.js", argv[0] if len(argv) > 0 else None)
    camp = buscar("payload-campos.txt", argv[1] if len(argv) > 1 else None)

    # --- 1. buscador ---
    n = verificar_sen(sen)
    import shutil
    shutil.copy(sen, SEN_JS)
    print(f"✓ datos-senescyt.js colocado ({n // 1024} KB cifrados)")

    # --- 2. campos: se delega en el script que ya valida y aborta si toca otra cosa ---
    r = subprocess.run([sys.executable, os.path.join(HERE, "insertar_payload.py"), camp],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        err("falló la inserción del payload de campos")

    # --- 3. comprobaciones antes de commitear ---
    app = open(APP, encoding="utf-8").read()
    if 'PAYLOAD_B64="' not in app or "</script>" not in app:
        err("la app quedó en un estado inesperado")
    ig = subprocess.run(["git", "check-ignore", "campos-nuevo.js", "data.js", "titulos.json"],
                        cwd=HERE, capture_output=True, text=True)
    if len(ig.stdout.split()) != 3:
        err("los datos en claro NO están todos ignorados; abortado por seguridad")
    print("✓ datos en claro protegidos por .gitignore")

    # --- 4. commit ---
    subprocess.run(["git", "add", "datos-senescyt.js", "utmach_campos_conocimiento.html"], cwd=HERE, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=HERE,
                          capture_output=True, text=True).stdout.split()
    if not diff:
        print("· no hay cambios que publicar (¿ya estaba actualizado?)")
        return
    print("  se publican:", ", ".join(diff))
    subprocess.run(["git", "commit", "-q", "-m",
                    "data: publica titulos SENESCYT y campos del conocimiento actualizados\n\n"
                    "Buscador y app de campos regenerados con los titulos oficiales\n"
                    "verificados en SENESCYT y su clasificacion CINE 2013 / RANT."],
                   cwd=HERE, check=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    print(f"✓ commit {head}")

    if push:
        subprocess.run(["git", "push", "origin", "main"], cwd=HERE, check=True)
        print("✓ publicado en GitHub")
    else:
        print("\nRevisa y publica con:  git push origin main")


if __name__ == "__main__":
    main()
