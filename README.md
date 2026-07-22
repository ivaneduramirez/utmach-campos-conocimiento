# Campos Amplios del Conocimiento — UTMACH

Consulta por profesor de los Campos Amplios del Conocimiento según tres fuentes
(títulos obtenidos, acciones de personal y distributivos académicos), clasificados
en las taxonomías **CINE-F 2013 (UNESCO)** y **RANT (CES, Anexo II 2023)**.

## Acceso

El sitio es una única página estática. **Los datos van cifrados dentro del propio
archivo** y solo se descifran en el navegador de quien tenga las credenciales.

Requiere dos factores:

1. Usuario y contraseña.
2. Código de seguridad de 6 dígitos de la aplicación de autenticación
   (Google Authenticator o equivalente).

Cifrado AES-256-GCM con clave derivada por PBKDF2-SHA256 (600 000 iteraciones).
El código de seguridad se verifica antes de descifrar, y no se guarda ningún
dato en claro dentro de la página.

Funciona igual en cualquier equipo, sin pasos de alta previos. La sesión
permanece abierta hasta pulsar **Cerrar sesión**.

## Contenido

Una sola página (`index.html`) sin dependencias externas ni llamadas de red.
