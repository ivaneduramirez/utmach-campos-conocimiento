#!/usr/bin/env python3
"""Genera un snapshot estático data.js desde titulos.json (para desplegar a GitHub Pages).
Para uso local con actualización en vivo, usa server.py (sirve /data.js dinámico)."""
import json
import os
from builder import data_js

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "titulos.json")   # fuente SENESCYT (local, en .gitignore)
OUT = os.path.join(HERE, "data.js")


def main():
    src = json.load(open(SRC, encoding="utf-8"))
    text = data_js(src)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    import builder
    _, meta = builder.payload(src)
    print(f"OK -> data.js ({os.path.getsize(OUT)/1024:.0f} KB) · {meta['n']} personas · {meta['titulos']} títulos")


if __name__ == "__main__":
    main()
