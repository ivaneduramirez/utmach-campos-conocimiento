"""Lógica compartida: convierte titulos.json (SENESCYT) al payload del buscador.
Usado por build.py (snapshot data.js) y server.py (data.js dinámico)."""
import json
import re
import unicodedata

NIVEL_RANK = {
    "Doctorado (PhD)": 5, "Maestría": 4, "Especialidad": 4,
    "Diplomado": 3, "Tercer nivel": 2, "Tecnológico": 1, "": 0,
}


def sa(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def nivel(titulo, obs=""):
    t = sa(titulo).upper()
    o = sa(obs).upper()
    # Los antiguos títulos de "Doctor" (Medicina, Jurisprudencia, Odontología...) NO son PhD:
    # SENESCYT los marca "No equivalente al título de doctorado 'PhD'" (Resolución 0023-2008-TC).
    # No deben clasificarse como Doctorado (PhD); caen a su nivel real (normalmente tercer nivel).
    no_phd = "NO EQUIVALENTE" in o or "0023-2008" in o
    if not no_phd and (any(k in t for k in ("PHD", "PH.D", "DOCTORADO", "DOCTOR OF PHILOSOPHY"))
                       or "PHD" in o or "DOCTOR O PHD" in o):
        return "Doctorado (PhD)"
    # Maestría, incluyendo formas no españolas: "Maestro en …" (México), "Mestre em/Mestrado" (Brasil).
    if any(k in t for k in ("MAGISTER", "MASTER", "MAESTRIA", "MAESTRO EN", "MESTRE EM", "MESTRADO")):
        return "Maestría"
    if "ESPECIALISTA" in t or "ESPECIALIDAD" in t:
        return "Especialidad"
    if "DIPLOMA SUPERIOR" in t or "DIPLOMADO" in t:
        return "Diplomado"
    # Nivel técnico-tecnológico superior (incluye "Técnico Superior en …", distinto del tercer nivel de grado).
    if ("TECNOLOG" in t and "INGENIER" not in t) or "TECNICO SUPERIOR" in t:
        return "Tecnológico"
    return "Tercer nivel"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def payload(src):
    """src = dict {clave: registro SENESCYT}. Devuelve (lista, meta)."""
    people = {}
    for key, v in (src or {}).items():
        ced = norm(v.get("cedula")) or key
        raw = v.get("titulos")
        if not isinstance(raw, list) or not raw:
            continue                      # ignora registros sin títulos limpios (búsquedas por nombre sin detalle)
        if not any(isinstance(t, dict) and t.get("Título") for t in raw):
            continue
        tits = []
        for t in raw:
            if not isinstance(t, dict):
                continue
            nv = nivel(t.get("Título"), t.get("Observación"))
            tits.append({
                "ti": norm(t.get("Título")),
                "in": norm(t.get("Institución de Educación Superior")),
                "tp": norm(t.get("Tipo")),
                "ar": norm(t.get("Área o Campo de Conocimiento")),
                "fr": norm(t.get("Fecha de Registro")),
                "nr": norm(t.get("Número de Registro")),
                "rp": norm(t.get("Reconocido Por")),
                "ob": norm(t.get("Observación")),
                "nv": nv,
            })
        if not tits:
            continue
        tits.sort(key=lambda x: (NIVEL_RANK.get(x["nv"], 0), x["fr"]), reverse=True)
        blob = " ".join([v.get("nombres", ""), ced] +
                        [x["in"] for x in tits] + [x["ti"] for x in tits] +
                        [x["ar"] for x in tits])
        people[ced] = {
            "c": ced,
            "n": norm(v.get("nombres")),
            "g": norm(v.get("genero")),
            "na": norm(v.get("nacionalidad")),
            "mx": tits[0]["nv"],
            "t": tits,
            "s": sa(blob).lower(),
        }
    out = sorted(people.values(), key=lambda p: p["n"])
    meta = {"n": len(out), "titulos": sum(len(p["t"]) for p in out)}
    return out, meta


def data_js(src):
    out, meta = payload(src)
    return ("window.DATA=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "window.META=" + json.dumps(meta) + ";\n")
