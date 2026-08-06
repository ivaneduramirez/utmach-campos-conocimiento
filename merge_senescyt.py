#!/usr/bin/env python3
"""Integra los títulos oficiales SENESCYT en el consolidado de Campos del Conocimiento.

Los títulos de SENESCYT son la fuente más autoritativa y cubren casi el doble de
profesores que el registro de Talento Humano, así que sustituyen a éste cuando existen.
Para los profesores sin registro SENESCYT se conserva el título de Talento Humano.

Entrada:  json/profesores_campos_conocimiento_consolidado.json  (base)
          titulos.json                                          (SENESCYT)
          json/clasificacion_titulos_nuevos.json                (CINE/RANT de los títulos nuevos)
Salida:   json/profesores_campos_conocimiento_consolidado.json  (actualizado, con respaldo)
          campos-nuevo.js                                       (para recifrar-campos.html)
"""
import json
import os
import re
import shutil
import unicodedata
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CONS = os.path.join(HERE, "json", "profesores_campos_conocimiento_consolidado.json")
SEN = os.path.join(HERE, "titulos.json")
NUEVOS = os.path.join(HERE, "json", "clasificacion_titulos_nuevos.json")
OUT_JS = os.path.join(HERE, "campos-nuevo.js")

# Profesores extranjeros registrados en SENESCYT con pasaporte, presentes en el
# distributivo con cédula ecuatoriana. Mapea id SENESCYT -> cédula del distributivo.
ALIAS = {
    "B391691": "0706524386",     # MORENO HERRERA ALEXANDER
    "113419524": "0960188670",   # NIRCHIO TURSELLINO MAURO
}

RANK = {"Doctorado (PhD)": 5, "Maestría": 4, "Especialidad": 4,
        "Diplomado": 3, "Tercer nivel": 2, "Tecnológico": 1, "": 0}


def norm(s):
    s = unicodedata.normalize("NFD", (s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def main():
    cons = json.load(open(CONS, encoding="utf-8"))
    sen = json.load(open(SEN, encoding="utf-8"))
    P = cons["profesores"]

    # ---- mapa de clasificación: texto normalizado -> (cine, rant, conf, razon) ----
    clasif = {}
    for p in P:                                    # lo ya clasificado en el consolidado
        for t in (p.get("titulos") or []):
            if t.get("cine"):
                clasif[norm(t.get("titulo"))] = (t["cine"], t["rant"],
                                                 t.get("conf") or "alta", t.get("razon"))
    if os.path.exists(NUEVOS):                     # lo clasificado en esta ronda
        for it in json.load(open(NUEVOS, encoding="utf-8")):
            clasif[norm(it["titulo"])] = (it["cine"], it["rant"],
                                          it.get("confianza") or "media",
                                          it.get("razon") or None)
    print(f"mapa de clasificación: {len(clasif)} títulos distintos")

    # ---- índice SENESCYT por cédula (aplicando alias) ----
    sen_by = {}
    for k, v in sen.items():
        ced = (v.get("cedula") or k).strip()
        ced = ALIAS.get(ced, ced)
        sen_by[ced] = v

    sin_clasif = set()
    n_reemp = n_sin = 0

    for p in P:
        ced = p.get("cedula")
        v = sen_by.get(ced)
        if not v or not v.get("titulos"):
            n_sin += 1
            continue
        nuevos = []
        for t in v["titulos"]:
            if not isinstance(t, dict) or not t.get("Título"):
                continue
            key = norm(t["Título"])
            c = clasif.get(key)
            if not c:
                sin_clasif.add(t["Título"])
            cine, rant, conf, razon = c if c else (None, None, "baja", "sin clasificar")
            nuevos.append({
                "titulo": (t.get("Título") or "").strip(),
                "nivel": t.get("_nivel"),
                "institucion": (t.get("Institución de Educación Superior") or "").strip(),
                "tipo": (t.get("Tipo") or "").strip(),
                "fecha": (t.get("Fecha de Registro") or "").strip(),
                "registro": (t.get("Número de Registro") or "").strip(),
                "area_senescyt": (t.get("Área o Campo de Conocimiento") or "").strip(),
                "observacion": (t.get("Observación") or "").strip() or None,
                "oficial": True,                      # verificado contra SENESCYT
                "cine": cine, "rant": rant, "conf": conf, "razon": razon,
            })
        if nuevos:
            p["titulos"] = nuevos
            n_reemp += 1
            # recomputar el campo por titulación (fuente "th")
            p["res"]["th"] = {
                "cine": sorted({x["cine"] for x in nuevos if x["cine"]}),
                "rant": sorted({x["rant"] for x in nuevos if x["rant"]}),
            }
        # nivel máximo y PhD desde la fuente oficial
        from builder import nivel as niv
        niveles = [niv(t.get("Título"), t.get("Observación")) for t in v["titulos"]
                   if isinstance(t, dict) and t.get("Título")]
        if niveles:
            mx = max(niveles, key=lambda n: RANK.get(n, 0))
            p["max_titulo"] = mx
            p["phd"] = (mx == "Doctorado (PhD)")
        # nivel por título (para mostrarlo en la ficha)
        for t_new, t_raw in zip(p.get("titulos") or [], v["titulos"]):
            if isinstance(t_raw, dict):
                t_new["nivel"] = niv(t_raw.get("Título"), t_raw.get("Observación"))

    # ---- recomputar los campos de cada profesor (unión de las 3 fuentes) ----
    for p in P:
        campos = set()
        for f in ("th", "ap", "di"):
            campos.update(p["res"].get(f, {}).get("rant") or [])
        p["campos"] = sorted(campos)

    cons["tot"] = {
        "th": sum(1 for p in P if p["res"].get("th", {}).get("rant")),
        "ap": sum(1 for p in P if p["res"].get("ap", {}).get("rant")),
        "di": sum(1 for p in P if p["res"].get("di", {}).get("rant")),
    }
    cons["generado"] = date.today().isoformat()
    cons["fuente_titulos"] = "SENESCYT (registro oficial) + Talento Humano donde no hay registro"

    print(f"profesores con títulos SENESCYT integrados: {n_reemp}")
    print(f"profesores sin registro SENESCYT (se conserva TH): {n_sin}")
    print(f"cobertura por fuente: {cons['tot']}")
    print(f"profesores con PhD: {sum(1 for p in P if p.get('phd'))}")
    if sin_clasif:
        print(f"\n⚠️  {len(sin_clasif)} títulos SIN clasificar:")
        for t in sorted(sin_clasif)[:10]:
            print("   ", t[:80])

    shutil.copy(CONS, CONS + ".bak")
    json.dump(cons, open(CONS, "w", encoding="utf-8"), ensure_ascii=False)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.CAMPOS_NUEVO=" +
                json.dumps(cons, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"\n✓ {CONS} (respaldo .bak)")
    print(f"✓ {OUT_JS} ({os.path.getsize(OUT_JS)//1024} KB)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    main()
