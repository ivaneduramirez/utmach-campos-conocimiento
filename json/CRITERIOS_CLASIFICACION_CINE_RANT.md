# Clasificación de títulos y asignaturas en Campo Amplio del Conocimiento (CINE 2013 y RANT)

Debes asignar a cada ítem (título académico o nombre de asignatura de la UTMACH, Ecuador) el **Campo Amplio del Conocimiento** que mejor se adecúe, en DOS taxonomías.

## Taxonomía 1: CINE-F 2013 (UNESCO, última versión)
- 00 Programas y certificaciones genéricos (solo para contenidos genéricos/transversales: habilidades personales, alfabetización básica)
- 01 Educación (ciencias de la educación, formación docente CON o SIN asignaturas de especialización, pedagogía, psicopedagogía, didáctica)
- 02 Artes y humanidades (artes, música, diseño, artesanías, audiovisuales, idiomas y lenguas, literatura, lingüística, religión, historia, arqueología, filosofía, ética)
- 03 Ciencias sociales, periodismo e información (psicología, sociología, economía, ciencias políticas, antropología, geografía social, periodismo, comunicación, bibliotecología)
- 04 Administración de empresas y derecho (administración, contabilidad y auditoría, finanzas, banca, seguros, marketing, ventas, secretariado, comercio, competencias empresariales, derecho)
- 05 Ciencias naturales, matemáticas y estadística (biología, bioquímica, medio ambiente/ecología, química, física, geología, ciencias de la tierra, matemáticas, estadística)
- 06 Tecnologías de la información y la comunicación — TIC (computación, informática, software, redes, bases de datos, sistemas)
- 07 Ingeniería, industria y construcción (ingenierías química/eléctrica/electrónica/mecánica/civil, procesamiento de alimentos, materiales, textiles, minería, industria, arquitectura, urbanismo, construcción)
- 08 Agricultura, silvicultura, pesca y veterinaria (agronomía, producción agrícola y pecuaria, horticultura, silvicultura, acuicultura, pesca, veterinaria)
- 09 Salud y bienestar (medicina, enfermería, obstetricia, odontología, farmacia, laboratorio/tecnología médica, terapias, nutrición, salud pública, trabajo social, asistencia social)
- 10 Servicios (servicios personales, gastronomía y hotelería, turismo, peluquería/estética, DEPORTES y actividad física recreativa, servicios de higiene y salud ocupacional, seguridad y salud en el trabajo, servicios de seguridad: policía/militar/defensa, transporte, servicios ambientales de saneamiento)

## Taxonomía 2: RANT (Reglamento de Armonización de la Nomenclatura de Títulos, CES Ecuador, Anexo II 2023)
Mismos campos amplios 01–10 (NO existe 00). Diferencias y precisiones frente a CINE observadas en el propio RANT:
- Psicología (general, organizacional, educativa) → 03. PERO Psicología Clínica → 09 (Salud). En CINE toda la psicología (incl. clínica) → 03.
- Ciencias de la Actividad Física y Deporte / Pedagogía de la Actividad Física → 01 (Educación) en RANT. En CINE el deporte NO docente → 10; el docente (pedagogía/educación física) → 01.
- Seguridad industrial / seguridad y salud ocupacional → 07 (campo específico "Industria y producción" incluye "Seguridad industrial") en RANT. En CINE → 10 (1022).
- Trabajo social → 09 en ambas.
- Economía → 03 en ambas. Administración, contabilidad, auditoría, marketing, comercio, derecho → 04 en ambas.
- Agroindustria / procesamiento de alimentos → 07 en ambas (NO 08).
- Gestión ambiental / manejo de recursos naturales → 05; Ingeniería ambiental → 07 (ambas taxonomías).
- Turismo, hotelería, gastronomía → 10 en ambas.

## Reglas de decisión
1. Clasifica por el DOMINIO DE CONTENIDO del título o asignatura, no por la facultad.
2. Títulos de formación docente ("PROFESOR DE...", "LICENCIADO EN CIENCIAS DE LA EDUCACIÓN...", "LICENCIADO EN EDUCACIÓN...", "PEDAGOGÍA DE X", "DOCENCIA", "MAGISTER EN EDUCACIÓN/ENSEÑANZA DE X") → 01 en ambas taxonomías, aunque X sea de otro dominio.
3. Asignaturas de enseñanza de una disciplina dentro de carreras de educación ("ENSEÑANZA-APRENDIZAJE DE X", "DIDÁCTICA DE X", "CÁTEDRA INTEGRADORA" pedagógica) → 01.
4. Asignaturas transversales sin dominio claro ("METODOLOGÍA DE LA INVESTIGACIÓN", "ESTADÍSTICA" aplicada genérica, "REALIDAD NACIONAL", "EMPRENDIMIENTO", "INGLÉS"): asigna el campo del contenido real: metodología de investigación → 00 en CINE y su mejor aproximación en RANT (usa 05 si es cuantitativa/estadística, si no el dominio más plausible); INGLÉS/idiomas → 02; EMPRENDIMIENTO → 04; ESTADÍSTICA → 05; REALIDAD NACIONAL/SOCIEDAD → 03. Para CINE puedes usar 00 solo si es genuinamente genérico (p. ej. "METODOLOGÍA DEL APRENDIZAJE", "TUTORÍA").
5. Si el ítem trae `match_rant` (titulación oficial RANT parecida con su campo), úsalo como evidencia fuerte para RANT salvo que sea claramente un falso amigo (revisa la similitud y el texto).
6. Si trae `area_senescyt` (área según registro SENESCYT, taxonomía CINE-1997 antigua), úsalo solo como pista débil.
7. Títulos médicos ("DOCTOR EN MEDICINA", "ESPECIALISTA EN <especialidad médica>", "MAGISTER EN <área clínica>") → 09. "DOCTOR EN..." NO médico es doctorado del dominio correspondiente (p. ej. "DOCTOR EN JURISPRUDENCIA" → 04, "DOCTOR EN CIENCIAS DE LA EDUCACIÓN" → 01).
8. En caso de duda razonable, elige el campo más probable y marca confianza "baja".

## Formato de salida
Para CADA línea del archivo de entrada, produce un objeto:
{"id": "<id>", "cine": "NN", "rant": "NN", "confianza": "alta|media|baja"}
- "cine": código 00–10. "rant": código 01–10 (nunca 00).
- Devuelve TODOS los ítems del lote, en el mismo orden, sin omitir ninguno.
