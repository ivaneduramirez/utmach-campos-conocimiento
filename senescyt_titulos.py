#!/usr/bin/env python3
"""
Consulta de títulos registrados en SENESCYT (portal MINEDEC) por número de cédula.

El portal (JSF/PrimeFaces) valida un captcha en el servidor por cada consulta.
Esta herramienta automatiza TODO menos el captcha: manejo de sesión, ViewState,
envío del formulario, reintentos, parseo del resultado a JSON y el lote completo
con reanudación. El único paso manual es teclear los caracteres del captcha.

UI en modo cuadrícula (batch): muestra VARIAS cédulas con su captcha a la vez
—cada una en su propia sesión— y se envían todas juntas.

No resuelve el captcha automáticamente a propósito: es un control anti-bot y debe
resolverlo una persona.

Uso:
    # 1) Verificar conectividad/fontanería (no requiere resolver captcha):
    python senescyt_titulos.py --selftest

    # 2) Levantar la UI (abre http://127.0.0.1:5000):
    python senescyt_titulos.py --input cedulas.txt --output titulos.json
    python senescyt_titulos.py --page-size 8        # cuántas mostrar a la vez
    python senescyt_titulos.py                       # y pegas las cédulas en la UI

Requisitos: requests, beautifulsoup4, flask  (ya instalados en .venv)
"""
import argparse
import base64
import json
import os
import re
import threading
import time
import unicodedata
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

BASE = "https://titulos-edusuperior.minedec.gob.ec/consulta-titulos-web"
CONSULTA_URL = BASE + "/faces/vista/consulta/consulta.xhtml"
CAPTCHA_URL = BASE + "/Captcha.jpg"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

CAPTCHA_ERROR_MARK = "aracteres incorrectos"  # "Caracteres incorrectos"


# --------------------------------------------------------------------------- #
# Cliente HTTP contra el portal (una sesión = un captcha vivo)
# --------------------------------------------------------------------------- #
class SenescytClient:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.viewstate = None

    def load_form(self):
        r = self.session.get(CONSULTA_URL, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "javax.faces.ViewState"})
        if not vs or not vs.get("value"):
            raise RuntimeError("No se pudo obtener el ViewState (¿cambió el portal?).")
        self.viewstate = vs["value"]
        return self.viewstate

    def get_captcha(self):
        r = self.session.get(CAPTCHA_URL, timeout=self.timeout)
        r.raise_for_status()
        return r.content

    def new_challenge(self):
        """Prepara una consulta nueva: ViewState + imagen de captcha (bytes jpeg)."""
        self.load_form()
        return self.get_captcha()

    def submit(self, cedula, captcha, apellidos=""):
        data = {
            "formPrincipal": "formPrincipal",
            "formPrincipal:apellidos": apellidos,
            "formPrincipal:identificacion": cedula,
            "formPrincipal:captchaSellerInput": captcha,
            "formPrincipal:boton-buscar": "",
            "javax.faces.ViewState": self.viewstate or "",
        }
        r = self.session.post(CONSULTA_URL, data=data, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "javax.faces.ViewState"})
        if vs and vs.get("value"):
            self.viewstate = vs["value"]
        return r.text, soup

    def submit_ver_info(self, link_id, apellidos, captcha):
        """Paso 2 de la búsqueda por nombre: abre el detalle 'Ver Información' de una
        fila (commandLink JSF) reusando el ViewState de la búsqueda (sin captcha nuevo)."""
        data = {
            "formPrincipal": "formPrincipal",
            "formPrincipal:apellidos": apellidos,
            "formPrincipal:identificacion": "",
            "formPrincipal:captchaSellerInput": captcha,
            link_id: link_id,
            "javax.faces.ViewState": self.viewstate or "",
        }
        r = self.session.post(CONSULTA_URL, data=data, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "javax.faces.ViewState"})
        if vs and vs.get("value"):
            self.viewstate = vs["value"]
        return r.text, soup


# --------------------------------------------------------------------------- #
# Parseo del resultado
# --------------------------------------------------------------------------- #
def _clean(txt):
    return re.sub(r"\s+", " ", (txt or "")).strip()


def _extract_tables(soup):
    tablas = []
    for table in soup.find_all("table"):
        headers = [_clean(th.get_text()) for th in table.find_all("th")]
        body_rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td"])
            if not cells:
                continue
            row = [_clean(td.get_text()) for td in cells]
            if any(row):
                body_rows.append(row)
        if not body_rows and not headers:
            continue
        filas_dict = []
        if headers and body_rows:
            for row in body_rows:
                if len(row) == len(headers):
                    filas_dict.append(dict(zip(headers, row)))
        tablas.append({"encabezados": headers, "filas": body_rows, "filas_dict": filas_dict})
    return tablas


PERSONA_FIELDS = ("identificacion", "nombres", "genero", "nacionalidad")
TITULO_HEADER_KEYS = ("título", "titulo", "institución", "institucion",
                      "registro", "reconoc", "área", "area", "conocimiento", "tipo")


def _norm_key(s):
    """'Género:' -> 'genero' (sin acentos, sin dos puntos, minúsculas)."""
    s = _clean(s).rstrip(":").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _extract_persona_and_titulos(tablas):
    """Secciona las tablas en candidatos [{identificacion,nombres,genero,nacionalidad,titulos}]
    en orden de documento: cada bloque de persona abre un candidato y las tablas de títulos que
    le siguen se le asignan. Vale para 1 (por cédula) o N (por apellidos)."""
    candidatos = []
    actual = None
    for t in tablas:
        campos = {}
        for fila in t.get("filas", []):
            if len(fila) == 2 and fila[0].endswith(":"):
                k = _norm_key(fila[0])
                if k in PERSONA_FIELDS:
                    campos[k] = fila[1]
        if campos.get("nombres"):
            actual = {
                "identificacion": campos.get("identificacion", ""),
                "nombres": campos.get("nombres", ""),
                "genero": campos.get("genero", ""),
                "nacionalidad": campos.get("nacionalidad", ""),
                "titulos": [],
            }
            candidatos.append(actual)
            continue
        cab = " ".join(t.get("encabezados", [])).lower()
        if t.get("filas_dict") and any(k in cab for k in TITULO_HEADER_KEYS):
            if actual is None:      # títulos sin bloque de persona previo (raro)
                actual = {"identificacion": "", "nombres": "", "genero": "",
                          "nacionalidad": "", "titulos": []}
                candidatos.append(actual)
            vistos = {(x.get("Título", ""), x.get("Número de Registro", ""))
                      for x in actual["titulos"]}
            for d in t["filas_dict"]:
                clave = (d.get("Título", ""), d.get("Número de Registro", ""))
                if clave not in vistos:
                    vistos.add(clave)
                    actual["titulos"].append(d)
    return candidatos


def build_record(cedula, tablas):
    """Registro limpio para consulta por cédula (una sola persona)."""
    cands = _extract_persona_and_titulos(tablas)
    c = cands[0] if cands else {"nombres": "", "genero": "", "nacionalidad": "", "titulos": []}
    return {
        "cedula": cedula,
        "nombres": c["nombres"],
        "genero": c["genero"],
        "nacionalidad": c["nacionalidad"],
        "status": "ok" if c["titulos"] else "sin_resultados",
        "titulos": c["titulos"],
    }


def _norm_ced(s):
    return re.sub(r"\D", "", s or "")


def _extract_person_rows(soup):
    """Filas de la lista por apellidos -> [{cedula, nombre, link_id}], con el id del
    commandLink 'Ver Información' de cada fila (para el segundo paso)."""
    tabla = soup.find(id="formPrincipal:tablaTitulado")
    filas = tabla.find_all("tr", attrs={"data-ri": True}) if tabla else []
    out, seen = [], set()
    for tr in filas:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        ced = _norm_ced(tds[0].get_text())
        nombre = _clean(tds[1].get_text())
        link = tr.find("a", id=True)
        clave = (ced, nombre)
        if (ced or nombre) and clave not in seen:
            seen.add(clave)
            out.append({"cedula": ced, "nombre": nombre,
                        "link_id": link.get("id", "") if link else ""})
    return out


def _match_person(rows, apellidos, nombres):
    apell = _clean(apellidos).upper()
    toks = _clean(nombres).upper().split()
    return [r for r in rows
            if r["nombre"].upper().startswith(apell)
            and all(w in r["nombre"].upper() for w in toks)]


def _name_result(entry, rows, detalle=None):
    """Construye el resultado de una consulta por nombre (con detalle si se abrió)."""
    coincid = _match_person(rows, entry.get("apellidos", ""), entry.get("nombres", ""))
    res = {"consulta": entry["label"], "tipo": "nombre",
           "apellidos": entry.get("apellidos", ""),
           "nombres_filtro": entry.get("nombres", ""),
           "total_encontrados": len(rows),
           "coincidencias": [{"cedula": c["cedula"], "nombre": c["nombre"]} for c in coincid]}
    if detalle is not None:
        res["cedula"] = detalle.get("identificacion") or (coincid[0]["cedula"] if coincid else "")
        res["nombres"] = detalle.get("nombres", "")
        res["genero"] = detalle.get("genero", "")
        res["nacionalidad"] = detalle.get("nacionalidad", "")
        res["titulos"] = detalle.get("titulos", [])
        res["status"] = "ok" if detalle.get("titulos") else "sin_titulos"
    elif coincid:
        res["cedula"] = coincid[0]["cedula"]
        res["status"] = "match_sin_detalle"   # halló persona pero no pudo abrir su detalle
        res["titulos"] = []
    elif rows:
        res["status"] = "varios"              # apellidos con personas, ninguna coincide por nombre
        res["personas"] = [{"cedula": r["cedula"], "nombre": r["nombre"]} for r in rows]
    else:
        res["status"] = "sin_resultados"      # nadie con esos apellidos
    return res


def parse_response(entry, html, soup):
    """Parsea el paso 1. Para nombre NO abre el detalle 'Ver Información'
    (eso lo orquesta submit_one, que tiene la sesión viva)."""
    if CAPTCHA_ERROR_MARK in html:
        return {"status": "captcha_error"}
    if entry["kind"] == "nombre":
        return _name_result(entry, _extract_person_rows(soup))
    rec = build_record(entry["label"], _extract_tables(soup))
    if not rec["titulos"]:
        texto = _clean(soup.get_text(" "))
        no_data = re.search(r"no se encontr|no existe|sin resultado|no posee|no registra", texto, re.I)
        if not no_data and not rec["nombres"]:
            rec["status"] = "revisar"
    return rec


def _resumen(parsed):
    if parsed.get("tipo") == "nombre":
        st, ced = parsed.get("status"), parsed.get("cedula", "")
        if st == "ok":
            return "%s → %d título(s)" % (ced, len(parsed.get("titulos", [])))
        if st == "sin_titulos":
            return "%s → 0 títulos" % ced
        if st == "match_sin_detalle":
            return "%s (no abrió detalle)" % ced
        if st == "varios":
            return "%d personas, sin coincidencia por nombre" % parsed.get("total_encontrados", 0)
        return "sin resultados"
    if parsed.get("status") == "ok":
        return "%d título(s)" % len(parsed.get("titulos", []))
    return parsed.get("status", "")


# --------------------------------------------------------------------------- #
# Self-test (sin resolver captcha)
# --------------------------------------------------------------------------- #
def selftest():
    c = SenescytClient()
    print("→ GET página de consulta...")
    vs = c.load_form()
    print("  ViewState:", vs[:32], "...  cookies:", list(c.session.cookies.keys()))
    print("→ GET captcha...")
    img = c.get_captcha()
    print("  bytes:", len(img))
    print("→ POST con captcha incorrecto (esperado: 'Caracteres incorrectos')...")
    html, soup = c.submit("0000000000", "0000")  # cédula de ejemplo (captcha incorrecto a propósito)
    print("  captcha_error detectado:", CAPTCHA_ERROR_MARK in html)
    print("\nFontanería OK. Solo falta teclear el captcha real.")


# --------------------------------------------------------------------------- #
# Utilidades de cédulas
# --------------------------------------------------------------------------- #
def _parse_cedulas_text(text):
    """Divide por líneas/comas/;. Una línea con espacios se conserva entera (es un nombre),
    salvo que sean varias cédulas numéricas separadas por espacio."""
    entradas = []
    for linea in re.split(r"[\n,;]+", text or ""):
        linea = " ".join(linea.split())
        if not linea:
            continue
        toks = linea.split(" ")
        if len(toks) > 1 and all(re.fullmatch(r"\d{6,13}", t) for t in toks):
            entradas.extend(toks)          # varias cédulas puras en una línea
        else:
            entradas.append(linea)
    seen, out = set(), []
    for x in entradas:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _parse_entry(raw):
    """Convierte una entrada cruda en {kind, label, ident, apellidos, nombres}.
    - Con '|': izquierda=apellidos, derecha=nombres.
    - Con espacios (sin '|'): 2 primeros tokens=apellidos, resto=nombres.
    - Sin espacios: cédula/identificación."""
    raw = " ".join((raw or "").split())
    if not raw:
        return None
    if "|" in raw:
        izq, der = raw.split("|", 1)
        apellidos = " ".join(izq.split())
        nombres = " ".join(der.split())
        label = (apellidos + " " + nombres).strip()
        return {"kind": "nombre", "label": label, "ident": "",
                "apellidos": apellidos, "nombres": nombres}
    if " " in raw:
        toks = raw.split(" ")
        return {"kind": "nombre", "label": raw, "ident": "",
                "apellidos": " ".join(toks[:2]), "nombres": " ".join(toks[2:])}
    return {"kind": "cedula", "label": raw, "ident": raw, "apellidos": "", "nombres": ""}


def read_cedulas(path):
    with open(path, encoding="utf-8") as f:
        return _parse_cedulas_text(f.read())


# --------------------------------------------------------------------------- #
# Runner: flujo continuo (cada tarjeta = una sesión independiente)
# --------------------------------------------------------------------------- #
def _public_card(card):
    """Vista pública de una carta (sin el objeto Challenge interno)."""
    it = {"token": card["token"], "cedula": card["cedula"]}
    if card.get("captcha"):
        it["captcha"] = card["captcha"]
    else:
        it["error"] = card.get("error", "")
    return it


class Challenge:
    def __init__(self, entry):
        self.entry = entry
        self.label = entry["label"]          # clave/etiqueta (cédula o nombre completo)
        self.ident = entry.get("ident", "")
        self.apellidos = entry.get("apellidos", "")
        self.client = SenescytClient()

    def refresh_b64(self):
        img = self.client.new_challenge()
        return "data:image/jpeg;base64," + base64.b64encode(img).decode()


class Runner:
    def __init__(self, output_path, save_html_dir=None, page_size=8):
        self.output_path = output_path
        self.save_html_dir = save_html_dir
        self.page_size = page_size
        self.lock = threading.Lock()
        self.queue = []            # cédulas pendientes
        self.results = {}          # cedula -> dict
        self.active = {}           # token -> Challenge (página en curso)
        self.skipped = set()
        self.initial = []          # cédulas precargadas (para prefill de la UI)
        self._tok = 0
        self.buffer = []           # cartas listas (captcha ya descargado), para flujo continuo
        self.buffer_target = max(page_size + 4, 8)
        self._filling = False
        self._load_existing()

    def _load_existing(self):
        if os.path.exists(self.output_path):
            try:
                with open(self.output_path, encoding="utf-8") as f:
                    self.results = json.load(f)
            except Exception:
                self.results = {}

    def _persist(self):
        tmp = self.output_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.output_path)

    def _done(self, label):
        r = self.results.get(label)
        return bool(r) and r.get("status") in (
            "ok", "sin_resultados", "revisar", "sin_titulos",
            "match", "match_sin_detalle", "varios")

    @staticmethod
    def _tiene_titulos(r):
        return bool(r.get("titulos")) or any(c.get("titulos") for c in r.get("candidatos", []))

    def _state(self):
        hechas = [c for c in self.results if self._done(c)]
        con_titulos = sum(1 for c in hechas if self._tiene_titulos(self.results[c]))
        return {
            "pendientes": len(self.queue),
            "en_pantalla": len(self.active),
            "hechas": len(hechas),
            "con_titulos": con_titulos,
            "sin_titulos": len(hechas) - con_titulos,
            "saltadas": len(self.skipped),
        }

    def state(self):
        with self.lock:
            return self._state()

    def load_cedulas(self, cedulas, remember_initial=False):
        with self.lock:
            if remember_initial:
                self.initial = list(cedulas)
            entradas = [e for e in (_parse_entry(r) for r in cedulas) if e]
            self.queue = [e for e in entradas if not self._done(e["label"])]
            self.active = {}
            self.buffer = []
            self._filling = False
            return self._state()

    def _save_html(self, label, html):
        if not self.save_html_dir:
            return
        os.makedirs(self.save_html_dir, exist_ok=True)
        safe = re.sub(r"[^0-9A-Za-z]+", "_", label).strip("_") or "x"
        p = os.path.join(self.save_html_dir, f"{safe}_{int(time.time())}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)

    def _create_challenges(self, n):
        """Extrae hasta n entradas de la cola -> [(tok, Challenge)]. Requiere lock tomado."""
        pares = []
        while len(pares) < n and self.queue:
            entry = self.queue.pop(0)
            tok = str(self._tok); self._tok += 1
            pares.append((tok, Challenge(entry)))
        return pares

    @staticmethod
    def _one_card(tok, ch):
        try:
            return {"token": tok, "cedula": ch.label, "captcha": ch.refresh_b64(), "ch": ch}
        except Exception as e:
            return {"token": tok, "cedula": ch.label, "error": str(e), "ch": ch}

    def _fetch_cards(self, pares):
        """[(tok, ch)] -> [carta con 'ch'] en paralelo (todas a la vez)."""
        if not pares:
            return []
        with ThreadPoolExecutor(max_workers=min(len(pares), 5)) as ex:
            return list(ex.map(lambda p: self._one_card(*p), pares))

    def _fill_buffer(self):
        """Rellena el buffer en segundo plano; cada carta se agrega apenas está lista."""
        with self.lock:
            if self._filling or not self.queue:
                return
            faltan = self.buffer_target - len(self.buffer)
            if faltan <= 0:
                return
            self._filling = True
            pares = self._create_challenges(faltan)

        def _bg():
            try:
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = [ex.submit(self._one_card, tok, ch) for tok, ch in pares]
                    for fut in as_completed(futs):
                        card = fut.result()
                        with self.lock:
                            self.buffer.append(card)
            finally:
                with self.lock:
                    self._filling = False
            self._fill_buffer()   # continuar si aún falta

        threading.Thread(target=_bg, daemon=True).start()

    def take_cards(self, n):
        """Entrega hasta n cartas listas (instantáneo desde el buffer) y rellena el buffer."""
        out = []
        deadline = time.time() + 60
        while len(out) < n:
            with self.lock:
                while self.buffer and len(out) < n:
                    card = self.buffer.pop(0)
                    self.active[card["token"]] = card["ch"]
                    out.append(_public_card(card))
                hay_cola = bool(self.queue)
                llenando = self._filling
            if len(out) >= n:
                break
            if hay_cola and not llenando:
                # Buffer vacío: traer directo (en paralelo) para no dejar hueco.
                with self.lock:
                    pares = self._create_challenges(n - len(out))
                if not pares:
                    break
                for card in self._fetch_cards(pares):
                    with self.lock:
                        self.active[card["token"]] = card["ch"]
                    out.append(_public_card(card))
            elif llenando and time.time() < deadline:
                time.sleep(0.1)   # el buffer se está llenando: esperar un poco
            else:
                break
        self._fill_buffer()
        with self.lock:
            done = (not out) and (not self.buffer) and (not self.queue) and (not self._filling)
        return {"cards": out, "done": done, **self.state()}

    def submit_one(self, token, captcha):
        """Envía una sola carta. -> resultado o {'status':'retry', 'captcha':...}."""
        captcha = (captcha or "").strip()
        with self.lock:
            ch = self.active.get(token)
        if not ch:
            return {"token": token, "status": "expirado", **self.state()}
        if not captcha:
            return {"token": token, "cedula": ch.label, "status": "vacio", **self.state()}
        try:
            html, soup = ch.client.submit(ch.ident, captcha, apellidos=ch.apellidos)
        except Exception as e:
            return {"token": token, "cedula": ch.label, "status": "error",
                    "detalle": str(e), **self.state()}
        if CAPTCHA_ERROR_MARK in html:
            try:
                return {"token": token, "cedula": ch.label, "status": "retry",
                        "captcha": ch.refresh_b64(), **self.state()}
            except Exception as e:
                return {"token": token, "cedula": ch.label, "status": "error",
                        "detalle": str(e), **self.state()}

        saved = [html]
        if ch.entry["kind"] == "nombre":
            # Paso 2: abrir "Ver Información" de la persona que coincide (misma sesión).
            rows = _extract_person_rows(soup)
            coincid = _match_person(rows, ch.apellidos, ch.entry.get("nombres", ""))
            detalle = None
            if coincid and coincid[0].get("link_id"):
                try:
                    html2, soup2 = ch.client.submit_ver_info(
                        coincid[0]["link_id"], ch.apellidos, captcha)
                    saved.append(html2)
                    if CAPTCHA_ERROR_MARK not in html2:
                        cands = _extract_persona_and_titulos(_extract_tables(soup2))
                        detalle = cands[0] if cands else None
                except Exception:
                    detalle = None
            parsed = _name_result(ch.entry, rows, detalle)
        else:
            parsed = parse_response(ch.entry, html, soup)

        for h in saved:
            self._save_html(ch.label, h)
        with self.lock:
            self.results[ch.label] = parsed
            self.active.pop(token, None)
            self._persist()
        return {"token": token, "cedula": ch.label, "status": parsed["status"],
                "resumen": _resumen(parsed), **self.state()}

    def skip(self, tok):
        with self.lock:
            ch = self.active.pop(tok, None)
            if ch:
                self.skipped.add(ch.label)
            return self._state()


# --------------------------------------------------------------------------- #
# UI web (cuadrícula)
# --------------------------------------------------------------------------- #
INDEX_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consulta títulos SENESCYT</title>
<style>
 :root{color-scheme:light dark}
 *{box-sizing:border-box}
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;
      margin:20px auto;padding:0 16px;line-height:1.4}
 h1{font-size:1.2rem;margin:.2rem 0}
 .bar{display:flex;gap:18px;align-items:center;flex-wrap:wrap;
      position:sticky;top:0;background:Canvas;padding:10px 0;z-index:5;border-bottom:1px solid #8883}
 .stat b{font-size:1.1rem}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-top:16px}
 .card{border:1px solid #8884;border-radius:12px;padding:12px;text-align:center}
 .card.done{border-color:#2b9348aa;opacity:.55}
 .card.retry{border-color:#d17a00aa}
 .ced{font-weight:600;font-size:1.05rem;margin-bottom:6px}
 img.cap{width:100%;max-width:220px;image-rendering:pixelated;border:1px solid #8884;
         border-radius:8px;background:#000}
 .card input{font-size:1.3rem;letter-spacing:.15em;text-align:center;width:100%;
        padding:8px;border-radius:8px;border:1px solid #8886;margin:8px 0 4px}
 button{font-size:1rem;padding:9px 16px;border-radius:8px;border:0;cursor:pointer;
        background:#6c63b5;color:#fff}
 button.sec{background:#8883;color:inherit;font-size:.8rem;padding:4px 8px}
 a.dl{background:#8883;color:inherit;font-size:.85rem;padding:8px 12px;border-radius:8px;text-decoration:none}
 a.btn-dl{display:inline-block;margin-top:10px;background:#2b9348;color:#fff;padding:12px 20px;
          border-radius:10px;text-decoration:none;font-size:1.05rem}
 .muted{opacity:.7;font-size:.9rem}
 textarea{width:100%;height:120px;border-radius:8px;padding:8px}
 #log{margin-top:14px;font-size:.85rem;max-height:150px;overflow:auto}
 #log div{padding:2px 0;border-bottom:1px solid #8882}
 .ok{color:#2b9348}.warn{color:#d17a00}.err{color:#c1121f}
 .hidden{display:none}
 .res{font-size:.85rem;margin-top:4px;min-height:1.1em}
 .card.solving{opacity:.65}
 .card:focus-within{border-color:#6c63b5;box-shadow:0 0 0 2px #6c63b566}
 a.skip{font-size:.75rem;opacity:.6;cursor:pointer;text-decoration:underline}
 .hint{font-size:.85rem;opacity:.75;margin:8px 0 0}
 kbd{background:#8883;border-radius:5px;padding:1px 6px;font-size:.8rem}
</style></head>
<body>
<h1>Consulta de títulos SENESCYT — captura continua</h1>

<div id="loader" class="card" style="text-align:left">
  <p class="muted">Pega cédulas (una por línea) y/o nombres para buscar por apellidos
    — formato <code>APELLIDOS | NOMBRES</code> (o <code>APELLIDOS NOMBRES</code>, los 2 primeros = apellidos):</p>
  <textarea id="ceds" placeholder="0102030405&#10;APELLIDOS | NOMBRES&#10;..."></textarea>
  <div style="margin-top:8px"><button onclick="cargar()">Cargar y empezar</button></div>
</div>

<div id="work" class="hidden">
  <div class="bar">
    <span class="stat">Pendientes <b id="s_pend">0</b></span>
    <span class="stat">Hechas <b id="s_done">0</b></span>
    <span class="stat">Saltadas <b id="s_skip">0</b></span>
    <span style="flex:1"></span>
    <a class="dl" href="/api/download" title="Descargar avance actual">⬇ JSON</a>
  </div>
  <p class="hint">Escribe el captcha y pulsa <kbd>→</kbd> o <kbd>Enter</kbd>: se envía solo y saltas al siguiente (ya precargado). <kbd>←</kbd> vuelve · <kbd>Esc</kbd> salta. Sin ratón.</p>
  <div id="grid" class="grid"></div>
</div>

<div id="doneBox" class="card hidden">
  <h2>✅ Lote completado</h2>
  <p id="doneSummary" class="muted"></p>
  <p class="muted">Guardado en <code id="outpath"></code></p>
  <a class="btn-dl" href="/api/download">⬇ Descargar titulos.json</a>
</div>

<div id="log"></div>

<script>
const $=s=>document.querySelector(s);
let PAGE=5;
function setStat(s){ if(!s)return;
  if('pendientes' in s)$('#s_pend').textContent=s.pendientes;
  if('hechas' in s)$('#s_done').textContent=s.hechas;
  if('saltadas' in s)$('#s_skip').textContent=s.saltadas; }
function log(t,cls){ const d=document.createElement('div'); d.textContent=t;
  if(cls)d.className=cls; $('#log').prepend(d); }

async function boot(){
  const b=await (await fetch('/api/boot')).json();
  PAGE=b.page_size||5; $('#outpath').textContent=b.outpath||'titulos.json';
  if(b.pendientes>0){ $('#ceds').value=(b.cedulas||[]).join('\n'); start(b); }
}
async function cargar(){
  const s=await (await fetch('/api/load',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cedulas:$('#ceds').value})})).json();
  start(s);
}
function start(s){
  $('#loader').classList.add('hidden'); $('#work').classList.remove('hidden');
  setStat(s); $('#grid').innerHTML=''; fillGrid();
}

function inputs(){ return [...document.querySelectorAll('#grid input:not([disabled])')]; }
function focusAfter(el){ const xs=inputs(); if(!xs.length)return;
  const t=xs.find(i=>el.compareDocumentPosition(i)&Node.DOCUMENT_POSITION_FOLLOWING);
  (t||xs[0]).focus(); }
function focusBefore(el){ const xs=inputs(); if(!xs.length)return;
  const b=xs.filter(i=>el.compareDocumentPosition(i)&Node.DOCUMENT_POSITION_PRECEDING);
  (b.length?b[b.length-1]:xs[xs.length-1]).focus(); }

function cardHTML(it){
  return '<div class="ced">'+it.cedula+'</div>'+
    (it.error
      ? '<div class="res err">'+it.error+'</div>'
      : '<img class="cap" src="'+it.captcha+'">'+
        '<input data-token="'+it.token+'" autocomplete="off" autocapitalize="off" '+
          'spellcheck="false" placeholder="captcha">'+
        '<div class="res"></div>'+
        '<a class="skip" onclick="saltar(this)">saltar</a>');
}
function newCard(it){
  const c=document.createElement('div'); c.className='card';
  c.dataset.token=it.token||''; c.innerHTML=cardHTML(it); return c;
}
function finish(d){
  $('#work').classList.add('hidden');
  $('#doneSummary').textContent=(d.hechas||0)+' consultadas · '+(d.con_titulos||0)+
    ' con títulos · '+(d.sin_titulos||0)+' sin títulos · '+(d.saltadas||0)+' saltadas';
  $('#doneBox').classList.remove('hidden');
}
async function fillGrid(){
  const g=$('#grid');
  const faltan=PAGE-g.querySelectorAll('.card').length;
  if(faltan<=0){ const f=g.querySelector('input'); if(f)f.focus(); return; }
  if(!g.children.length) g.innerHTML='<p class="muted" style="padding:20px">Cargando captchas…</p>';
  const d=await (await fetch('/api/cards?n='+faltan)).json(); setStat(d);
  const p=g.querySelector('p'); if(p)p.remove();
  if(d.done && !g.querySelectorAll('.card').length){ finish(d); return; }
  for(const it of (d.cards||[])) g.appendChild(newCard(it));
  const first=g.querySelector('input'); if(first)first.focus();
}
async function replaceSlot(card){
  const d=await (await fetch('/api/cards?n=1')).json(); setStat(d);
  const it=(d.cards||[])[0];
  if(!it){ card.remove(); if(!$('#grid').querySelectorAll('.card').length) finish(d); return; }
  card.className='card'; card.dataset.token=it.token; card.innerHTML=cardHTML(it);
}
async function submitCard(card){
  const inp=card.querySelector('input'); if(!inp)return;
  const v=inp.value.trim(); if(!v)return;
  inp.disabled=true; card.classList.add('solving');
  card.querySelector('.res').innerHTML='<span class="muted">consultando…</span>';
  const d=await (await fetch('/api/submit_one',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:inp.dataset.token,captcha:v})})).json();
  setStat(d);
  if(d.status==='retry'){ card.classList.remove('solving'); card.classList.add('retry');
    const img=card.querySelector('img'); if(img)img.src=d.captcha;
    inp.disabled=false; inp.value='';
    card.querySelector('.res').innerHTML='<span class="warn">captcha incorrecto, reintenta</span>'; return; }
  if(d.status==='vacio'){ inp.disabled=false; card.classList.remove('solving'); return; }
  const cls=d.status==='ok'?'ok':(d.status==='error'||d.status==='expirado'?'err':'warn');
  log((d.cedula||'?')+' → '+(d.resumen||d.detalle||d.status), cls);
  card.classList.remove('solving'); card.classList.add('done');
  card.querySelector('.res').innerHTML='<span class="'+cls+'">'+(d.resumen||d.status)+'</span>';
  setTimeout(()=>replaceSlot(card), 450);
}
async function saltar(a){
  const card=a.closest('.card'); const inp=card.querySelector('input');
  const tok=inp?inp.dataset.token:card.dataset.token;
  const d=await (await fetch('/api/skip',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({token:tok})})).json();
  setStat(d);
  const ced=card.querySelector('.ced'); log((ced?ced.textContent:'?')+' → saltada','warn');
  replaceSlot(card);
}
// Flujo continuo: → o Enter envía el actual y salta al siguiente (ya precargado).
document.addEventListener('keydown',e=>{
  if(!e.target.matches || !e.target.matches('#grid input')) return;
  const inp=e.target, card=inp.closest('.card');
  if(e.key==='Enter' || e.key==='ArrowRight'){ e.preventDefault();
    if(inp.value.trim()) submitCard(card);
    focusAfter(inp);
  } else if(e.key==='ArrowLeft'){ e.preventDefault(); focusBefore(inp); }
  else if(e.key==='Escape'){ e.preventDefault();
    const a=card.querySelector('.skip'); if(a) saltar(a); }
});
boot();
</script>
</body></html>"""


def make_app(runner):
    from flask import Flask, request, jsonify, Response, send_file
    app = Flask(__name__)

    @app.get("/")
    def index():
        return Response(INDEX_HTML, mimetype="text/html")

    @app.get("/api/boot")
    def api_boot():
        st = runner.state()
        st["cedulas"] = [e["label"] for e in runner.queue]
        st["outpath"] = os.path.abspath(runner.output_path)
        st["page_size"] = runner.page_size
        return jsonify(st)

    @app.post("/api/load")
    def api_load():
        data = request.get_json(force=True)
        ceds = _parse_cedulas_text(data.get("cedulas", ""))
        return jsonify(runner.load_cedulas(ceds, remember_initial=True))

    @app.get("/api/cards")
    def api_cards():
        try:
            n = int(request.args.get("n", runner.page_size))
        except (TypeError, ValueError):
            n = runner.page_size
        n = max(1, min(n, 20))
        try:
            return jsonify(runner.take_cards(n))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/submit_one")
    def api_submit_one():
        data = request.get_json(force=True)
        try:
            return jsonify(runner.submit_one(data.get("token"), data.get("captcha", "")))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/skip")
    def api_skip():
        data = request.get_json(force=True)
        return jsonify(runner.skip(data.get("token")))

    @app.get("/api/download")
    def api_download():
        path = os.path.abspath(runner.output_path)
        if not os.path.exists(path):
            return jsonify({"error": "aún no hay resultados guardados"}), 404
        return send_file(path, as_attachment=True,
                         download_name=os.path.basename(path),
                         mimetype="application/json")

    return app


def main():
    ap = argparse.ArgumentParser(description="Consulta títulos SENESCYT (captcha humano, flujo continuo).")
    ap.add_argument("--selftest", action="store_true",
                    help="Verifica conectividad/fontanería sin resolver captcha.")
    ap.add_argument("--input", help="Archivo con cédulas (una por línea).")
    ap.add_argument("--output", default="titulos.json", help="JSON de salida (default: titulos.json).")
    ap.add_argument("--page-size", type=int, default=5, help="Cuántas cédulas mostrar a la vez (default: 5).")
    ap.add_argument("--port", type=int, default=8000,
                    help="Puerto de la UI (default: 8000; evita el 5000 que usa AirPlay en macOS).")
    ap.add_argument("--save-html-dir", default="debug_html",
                    help="Carpeta para guardar el HTML crudo de cada respuesta (para depurar el parseo).")
    ap.add_argument("--no-save-html", action="store_true", help="No guardar HTML crudo.")
    ap.add_argument("--no-open", action="store_true", help="No abrir el navegador automáticamente.")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    runner = Runner(
        output_path=args.output,
        save_html_dir=None if args.no_save_html else args.save_html_dir,
        page_size=args.page_size,
    )
    if args.input:
        ceds = read_cedulas(args.input)
        runner.load_cedulas(ceds, remember_initial=True)
        print(f"Cargadas {len(ceds)} cédulas ({runner.state()['pendientes']} pendientes).")

    app = make_app(runner)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  UI de captura (lote):  {url}")
    print(f"  Salida JSON:           {os.path.abspath(args.output)}")
    print(f"  Cédulas por pantalla:  {args.page_size}")
    print("  (Ctrl+C para detener; el progreso se guarda tras cada cédula.)\n")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
