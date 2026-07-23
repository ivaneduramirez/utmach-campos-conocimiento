#!/usr/bin/env python3
"""
Servidor local del proyecto UTMACH — Campos del Conocimiento.

Unifica en un solo sitio:
  /                                  Buscador de Títulos SENESCYT
  /utmach_campos_conocimiento.html   App "Campos Amplios del Conocimiento" (existente)
  /actualizar                        Actualizar títulos desde SENESCYT (captcha humano)
  /data.js                           Datos SENESCYT (dinámico: refleja updates al instante)

Solo para uso LOCAL (la actualización necesita backend). El despliegue a GitHub Pages
es estático y de solo lectura (ver README).

Ejecutar:  .venv/bin/python server.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from senescyt_titulos import Runner, _parse_cedulas_text, INDEX_HTML  # noqa: E402
from builder import data_js  # noqa: E402
from flask import Flask, request, jsonify, Response, send_from_directory  # noqa: E402

TITULOS = os.path.join(HERE, "titulos.json")
PORT = 8090

runner = Runner(output_path=TITULOS,
                save_html_dir=os.path.join(HERE, "debug_html"),
                page_size=6)

# Reutiliza la UI de captura (flujo continuo) con header unificado + "volver al buscador".
ADMIN_HTML = INDEX_HTML.replace(
    "<body>",
    '<body><a href="/buscador.html" style="position:fixed;top:10px;right:16px;z-index:100;'
    'background:#0A2A5E;color:#fff;padding:9px 15px;border-radius:9px;text-decoration:none;'
    'font-family:system-ui;font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.3)">← Volver al buscador</a>')
ADMIN_HTML = ADMIN_HTML.replace(
    "<h1>Consulta de títulos SENESCYT — captura continua</h1>",
    "<h1>Información Académica de Profesores UTMACH</h1>"
    '<div style="font-size:13px;color:#5A6472;margin-top:-4px;margin-bottom:6px">'
    "Actualizar títulos desde SENESCYT</div>")

app = Flask(__name__)


@app.get("/")
@app.get("/index.html")
def portada():
    return send_from_directory(HERE, "index.html")


@app.get("/buscador.html")
def buscador():
    return send_from_directory(HERE, "buscador.html")


@app.get("/utmach_campos_conocimiento.html")
def campos():
    return send_from_directory(HERE, "utmach_campos_conocimiento.html")


@app.get("/utmach-logo.png")
def logo():
    return send_from_directory(HERE, "utmach-logo.png")


@app.get("/cifrar.html")
def cifrar():
    return send_from_directory(HERE, "cifrar.html")


@app.get("/datos-senescyt.js")
def datos_cifrados():
    if os.path.exists(os.path.join(HERE, "datos-senescyt.js")):
        return send_from_directory(HERE, "datos-senescyt.js")
    return Response("", mimetype="application/javascript")  # aún no cifrado (modo local)


@app.get("/data.js")
def dyn_data():
    src = json.load(open(TITULOS, encoding="utf-8")) if os.path.exists(TITULOS) else {}
    return Response(data_js(src), mimetype="application/javascript",
                    headers={"Cache-Control": "no-store"})


@app.get("/actualizar")
def actualizar():
    return Response(ADMIN_HTML, mimetype="text/html")


@app.get("/api/ping")
def ping():
    return jsonify({"ok": True})


# ---- API de captura (reutiliza el Runner del scraper) ----
@app.get("/api/boot")
def boot():
    st = runner.state()
    st["cedulas"] = [e["label"] for e in runner.queue]
    st["outpath"] = TITULOS
    st["page_size"] = runner.page_size
    return jsonify(st)


@app.post("/api/load")
def load():
    ceds = _parse_cedulas_text(request.get_json(force=True).get("cedulas", ""))
    return jsonify(runner.load_cedulas(ceds, remember_initial=True))


@app.get("/api/cards")
def cards():
    try:
        n = int(request.args.get("n", runner.page_size))
    except (TypeError, ValueError):
        n = runner.page_size
    return jsonify(runner.take_cards(max(1, min(n, 20))))


@app.post("/api/submit_one")
def submit_one():
    d = request.get_json(force=True)
    return jsonify(runner.submit_one(d.get("token"), d.get("captcha", "")))


@app.post("/api/skip")
def skip():
    return jsonify(runner.skip(request.get_json(force=True).get("token")))


@app.post("/api/refetch")
def refetch():
    """Fuerza re-consultar UN profesor desde SENESCYT y devuelve su captcha."""
    ced = (request.get_json(force=True).get("cedula") or "").strip()
    if not ced:
        return jsonify({"error": "cédula vacía"}), 400
    with runner.lock:
        runner.results.pop(ced, None)          # quitar para que no se salte
    runner.load_cedulas([ced], remember_initial=False)
    d = runner.take_cards(1)
    card = (d.get("cards") or [None])[0]
    return jsonify({"card": card})


@app.get("/api/persona/<ced>")
def persona(ced):
    """Registro (slim) actualizado de un profesor, para refrescar el buscador tras actualizar."""
    src = json.load(open(TITULOS, encoding="utf-8")) if os.path.exists(TITULOS) else {}
    if ced not in src:
        return jsonify({"persona": None})
    from builder import payload
    lst, _ = payload({ced: src[ced]})
    return jsonify({"persona": lst[0] if lst else None})


@app.get("/api/download")
def download():
    return send_from_directory(HERE, "titulos.json", as_attachment=True)


if __name__ == "__main__":
    print(f"\n  Buscador SENESCYT:   http://127.0.0.1:{PORT}/")
    print(f"  Campos conocimiento: http://127.0.0.1:{PORT}/utmach_campos_conocimiento.html")
    print(f"  Actualizar SENESCYT: http://127.0.0.1:{PORT}/actualizar\n")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
