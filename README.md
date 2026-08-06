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

Para generar los payloads cifrados: inicia sesión en la app de Campos (local) y abre
**`publicar.html`**, que cifra de una sola vez las dos herramientas y descarga
`datos-senescyt.js` (buscador) y `payload-campos.txt` (app de Campos). Tu contraseña y tu
código 2FA nunca salen del navegador: se usa la clave de sesión que dejó el login.

Después, `python3 insertar_payload.py <payload-campos.txt>` inserta el payload en la app
sustituyendo **solo** `PAYLOAD_B64`/`IV_B64` (aborta si alterara cualquier otra parte).
Los archivos cifrados **sí se versionan**; `titulos.json`, `data.js` y `campos-nuevo.js`
(datos en claro) no. Tras cambiar los datos o la clasificación hay que **regenerarlos**
para que el sitio público refleje los cambios.

## Campos del conocimiento a partir de los títulos oficiales

`merge_senescyt.py` integra los títulos verificados en SENESCYT como fuente de titulación
del consolidado —es más autoritativa y cubre casi el doble de profesores que el registro
de Talento Humano— y recomputa el campo por titulación, el nivel máximo y el claustro
doctoral. Los títulos se clasifican en **CINE 2013** y **RANT (CES)** siguiendo
`json/CRITERIOS_CLASIFICACION_CINE_RANT.md`; el mapa resultante se versiona en
`json/clasificacion_titulos_nuevos.json` con el nivel de confianza y la justificación de
cada decisión, de modo que la clasificación sea auditable ítem por ítem.

## Estructura

```
index.html                        Portada (menú: Campos + Buscador)
buscador.html                     Buscador SENESCYT (estático)
publicar.html                     Cifra las DOS herramientas de una vez
cifrar.html                       Cifra solo el buscador (data.js → datos-senescyt.js)
recifrar-campos.html              Cifra solo la app de campos (→ payload-campos.txt)
insertar_payload.py               Inserta el payload en la app de campos
merge_senescyt.py                 Títulos SENESCYT → fuente de titulación del consolidado
datos-senescyt.js                 Datos SENESCYT cifrados (sí se versiona)
utmach_campos_conocimiento.html   App de campos (existente, cifrada)
server.py                         Servidor local (buscador + campos + /actualizar)
senescyt_titulos.py               Scraper SENESCYT (captcha humano) — motor de /actualizar
build.py / builder.py             titulos.json → data.js
titulos.json                      Datos SENESCYT (local, en .gitignore)
json/ · sources/                  Fuentes (local, en .gitignore)
```

Fuente de datos: portal de títulos de la **SENESCYT**. Datos de carácter informativo.
