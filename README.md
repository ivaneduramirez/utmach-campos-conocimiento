# UTMACH · Campos del Conocimiento

Proyecto único con dos herramientas que comparten estilo y (en despliegue) login:

| Página | Qué es |
|---|---|
| `buscador.html` | **Buscador de Títulos SENESCYT** — búsqueda ágil por nombre/cédula/universidad/título, con copiar/imprimir. Fuente: registros SENESCYT (la información más exacta). |
| `utmach_campos_conocimiento.html` | App **Campos Amplios del Conocimiento** (existente) — datos cifrados + login 2FA. |

## Uso local (con actualización desde SENESCYT)

Requiere el entorno Python (`.venv`) con `flask requests beautifulsoup4`.

```bash
.venv/bin/python server.py     # http://127.0.0.1:8090
```

- `/`            → Portada (menú: Campos + Buscador)
- `/buscador.html` → Buscador SENESCYT
- `/utmach_campos_conocimiento.html` → App de Campos (login 2FA)
- `/actualizar`  → **Actualizar títulos desde SENESCYT**: pegas cédulas, resuelves los
  captchas (flujo humano-en-el-bucle) y trae los títulos. Escribe en `titulos.json`;
  el buscador refleja los cambios al instante (`/data.js` es dinámico).

Para un snapshot estático de datos: `.venv/bin/python build.py` → genera `data.js`.

## Despliegue a GitHub Pages (público, con gate)

El sitio público es **estático y de solo lectura** (la actualización solo corre local).
Los datos personales (cédulas/nombres) **no se suben en claro**: se publican **cifrados**
con el mismo esquema del app de campos (PBKDF2 → AES-GCM → gzip) y se descifran tras el
login. Ver `.gitignore` — `titulos.json`, `data.js`, `json/`, `sources/` y el secreto 2FA
**no se versionan**.

Para generar el payload cifrado: inicia sesión en la app de Campos (local), abre
`cifrar.html` y descarga `datos-senescyt.js` (tu contraseña nunca sale del navegador; se
usa la clave de sesión que dejó el login). Ese archivo **cifrado sí se versiona**;
`titulos.json` / `data.js` no. Tras cambiar los datos o la clasificación, hay que
**regenerarlo** para que el sitio público refleje los cambios.

## Estructura

```
index.html                        Portada (menú: Campos + Buscador)
buscador.html                     Buscador SENESCYT (estático)
cifrar.html                       Cifra data.js → datos-senescyt.js (para el deploy)
datos-senescyt.js                 Datos SENESCYT cifrados (sí se versiona)
utmach_campos_conocimiento.html   App de campos (existente, cifrada)
server.py                         Servidor local (buscador + campos + /actualizar)
senescyt_titulos.py               Scraper SENESCYT (captcha humano) — motor de /actualizar
build.py / builder.py             titulos.json → data.js
titulos.json                      Datos SENESCYT (local, en .gitignore)
json/ · sources/                  Fuentes (local, en .gitignore)
```

Fuente de datos: portal de títulos de la **SENESCYT**. Datos de carácter informativo.
