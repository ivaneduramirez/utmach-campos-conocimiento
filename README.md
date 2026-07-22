# Campos Amplios del Conocimiento — UTMACH

Consulta por profesor de los Campos Amplios del Conocimiento según tres fuentes
(títulos obtenidos, acciones de personal y distributivos académicos), clasificados
en las taxonomías **CINE-F 2013 (UNESCO)** y **RANT (CES, Anexo II 2023)**.

## Acceso

El sitio es una única página estática. **Los datos van cifrados dentro del propio
archivo** y solo se descifran en el navegador de quien tenga las credenciales.

Requiere dos factores:

1. Usuario y contraseña.
2. Código de 6 dígitos de **Google Authenticator**.

La clave de descifrado se deriva de la contraseña **y** del secreto del
autenticador (PBKDF2-SHA256, 600 000 iteraciones → AES-256-GCM). Sin ambos
factores el contenido es indescifrable: el secreto del autenticador **no está
en este repositorio**.

La primera vez que se entra desde un equipo se pide, además, la clave de
configuración del autenticador para autorizar ese dispositivo; queda guardada
cifrada en el navegador y no vuelve a pedirse.

La sesión permanece abierta hasta pulsar **Cerrar sesión**.

## Contenido

Una sola página (`index.html`) sin dependencias externas ni llamadas de red.
