# Ferromapas toolkit — Plan de implementación

Herramienta de línea de comandos para versionar en git el mapa ferroviario de Ferromapas.
Convierte el KMZ que se edita en Google Earth en un árbol de archivos de texto (`src/`) y vuelve a armar el KMZ a partir de ese árbol.

## 1. Decisiones ya tomadas

### Formato en el repo
- **Carpetas superiores** (desde la raíz hasta el nivel de ramal): cada una es un **directorio** con un `_folder.yaml`.
- **Ramal hacia abajo**: un único **archivo `.kml`** por ramal. Las subcarpetas internas se guardan como `<Folder>` anidados (por ejemplo "Desvío Ingenio Ledesma" dentro de C15).
- **Placemarks sueltos** en una carpeta que es directorio van en `_loose.kml`, dentro de ese mismo directorio.
- La raíz del `Document` tiene su propio `_document.yaml`.
- El orden de los hijos se guarda en `children` dentro del yaml. Los nombres de archivo no determinan el orden.
- **Nombres de archivo**: slug ASCII (`ramal-a1-cruz-del-eje-alta-cordoba.kml`). El nombre real queda en `<name>` o en el yaml. Si dos hermanos dan el mismo slug, se agrega `-2`, `-3`.
- **El KMZ no se versiona**: está en `.gitignore`, lo genera el build y se publica en GitHub Releases.

### Qué se conserva
Solo esto:
- `Folder`: `name`, `description`
- `Placemark`: `name`, `description` y **una** geometría `Point`, `LineString` o `Polygon` (anillo exterior más interiores)

### Qué se descarta en el split
- Estilos: `Style`, `StyleMap`, `styleUrl`
- Estado de carpetas: `open`, `visibility`
- Vistas guardadas: `LookAt` y `Camera`, con sus `gx:TimeStamp`, `gx:TimeSpan` y `gx:ViewerOptions`
- `Snippet`, `TimeStamp`, `Region`, todos los elementos `gx:*` y `atom:*`
- `ExtendedData`, `SchemaData` y `Schema`
- Dentro de las geometrías: `altitudeMode`, `gx:altitudeMode`, `tessellate`, `extrude`, `gx:drawOrder`
- La altitud de las coordenadas
- Los decimales de las coordenadas más allá del sexto (se **redondea**, no se trunca). Ver «Precisión de las coordenadas».

### Precisión de las coordenadas
Reducir las coordenadas a 6 decimales (el KMZ original llega a 14) es una pérdida de datos deliberada:
- **Resolución**: 1e-6° ≈ 11,1 cm en latitud y ≈ 9,2 cm en longitud a ~34° S. El error máximo por eje al redondear es la mitad: **±5,5 cm** en latitud y **±4,6 cm** en longitud; el error típico total es de 3 a 4 cm.
- **Por qué es aceptable**: los decimales descartados (de 1e-7 a 1e-14) representan escalas de centímetros a nanómetros, muy por debajo del ruido de un GPS o de un trazado manual en Google Earth.
- **Consecuencia para los tests**: el KMZ reconstruido **no** es idéntico al original en coordenadas. `compare` y el test semántico deben redondear a 6 decimales las coordenadas de ambos lados antes de comparar (ver Fase 4).
- **Idempotencia**: el redondeo se aplica una sola vez, al leer. Redondear de nuevo un valor ya redondeado no lo cambia, así que `build → split` no produce diferencias.
- Si en el futuro hiciera falta más precisión, subir a 7 decimales (≈ 1 cm) es un cambio de una constante, pero reescribe todos los archivos de `src/`.

### Idioma del código
- Todos los **identificadores** (módulos, clases, funciones, variables, parámetros) van en **inglés**.
- Siguen en español los mensajes de la CLI, los comentarios, los docstrings y los commits.
- También van en inglés los nombres que forman parte de un formato o de la interfaz: claves de `ferromapas.yaml` y `folders.yaml`, flags de la CLI (`--strict`) y nombres de archivo del repo (`_loose.kml`).

### Casos especiales del KMZ actual
- **22 estaciones FEPSA** escritas con la sintaxis vieja de KML 2.1: elemento `<S_Estaciones_FEPSA_desde_FEPSA_DDS>` tipado por un `<Schema parent="Placemark">`. Hay que convertirlas a `Placemark`, descartar `latitud` y `longitud`, y agregar `Est` al final de la descripción como `Nombre FEPSA: <Est>`.
  - Están en Roca: Zona Centro / "Olavarría - Bahía Blanca (Vía La Madrid)" (18), Zona Oeste / "Recalde - Pigüé" (2), "Empalme Altavista - Saavedra" (1) y "Olavarría - Bahía Blanca (Vía Pringles)" (1).
- **Placemark sin geometría** ("zoologico", en Belgrano / Línea A / Ramal A10 / Tracks): se elimina con un aviso.
- **12 `ExtendedData`** (basura de un foro en estaciones del ex-RPB) y **1 `SchemaData`** (datos de ejemplo de Google en "Río Blanco KM 33.900"): se eliminan.

### Normalización (para que los diffs sean limpios)
- Coordenadas con **6 decimales**, sin altitud. `Point` en una línea; `LineString` y anillos con **una coordenada por línea**.
- Indentación fija de 2 espacios, orden fijo de elementos (`name`, `description`, geometría), UTF-8 y `\n` como fin de línea.
- `description` vacía o solo con espacios → se omite. `\r\n` → `\n`.
- **El serializador lo escribe el programa a mano**, no un pretty-printer genérico, para que la salida sea siempre la misma.
- Cada `.kml` del repo es un KML válido por sí mismo: `<kml><Folder>…</Folder></kml>`. Así se puede abrir solo en Google Earth.

### Dónde cortar (profundidad de directorios)
En `ferromapas.yaml`, en la raíz del repo:
```yaml
output: dist/Ferromapas.kmz
split:
  max_dir_depth: 4          # Document=0, "Ferromapas"=1, "Ferrocarriles Argentinos"=2, "Ferrocarril X"=3, Línea/Zona/tramo=4
```
Si falta `max_dir_depth` (o el archivo), el valor por defecto es 3.

Regla: una carpeta es directorio si su profundidad es `<= max_dir_depth` **y además** tiene subcarpetas. En cualquier otro caso es un archivo `.kml`.

Una carpeta puntual se puede cortar distinto con `depth` en `folders.yaml` (ver abajo): indica cuántos niveles por debajo de esa carpeta se guardan como directorios, y gana sobre `max_dir_depth` para todo lo que cuelga de ella (gana el prefijo más largo).

### Estilos y profundidades (`folders.yaml`)
Las carpetas se anidan como en el mapa (por nombre o por slug). Cada nodo puede tener `styles` (estilo para todo lo que está debajo), `depth` (ver arriba) e `id` (nombre corto del `<Style>` generado; requiere `styles`). Los estilos solo se aplican en el build.
```yaml
default: { color: "#757575", line_width: 2.5, icon: "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png", icon_scale: 0.4, label_scale: 0.7, polygon_opacity: 0.35 }
folders:
  Ferromapas:
    Ferrocarriles Argentinos:
      Ferrocarril Belgrano: { styles: { color: "#6A1B9A" }, id: belgrano, depth: 2 }
      Ferrocarril Mitre:    { styles: { color: "#C62828" }, id: mitre }
      # ...
```
- El build genera un `<Style>` por entrada con `styles`, con LineStyle, IconStyle, LabelStyle y PolyStyle, en el `<Document>`. Sin `id`, el nombre se deriva de la ruta (`s-ferromapas--ferrocarriles-argentinos--ferrocarril-belgrano`).
- Las claves de `styles` que no se indican se toman de `default`. Una clave desconocida es un error.
- Cada Placemark recibe el `styleUrl` correspondiente y cada `LineString` lleva `tessellate=1`.
- Hay que convertir los colores de `#RRGGBB` a `aabbggrr`, el formato de KML.

## 2. Lenguaje: Python 3.12+

- **Sin dependencias pesadas**: con `xml.etree.ElementTree`, `zipfile` y `unicodedata` de la biblioteca estándar alcanza. La única dependencia externa es **PyYAML**.
- **Es el estándar en el mundo GIS**: si después hace falta algo más (reproyección, cortar líneas por estaciones con Shapely, exportar a GeoJSON), las librerías están ahí.
- Para la parte de reorganización (cortar líneas en empalmes, mover según el listado de ramales), Shapely resuelve "cortar esta LineString en el punto más cercano a esta estación" en pocas líneas.

La alternativa razonable es **TypeScript/Node**. Conviene si pensás hacer un visor web en React que reutilice el mismo parser. Para una CLI que procesa archivos, Python es más directo.

## 3. Estructura del repo

```
ferromapas-toolkit/
├── ferromapas/              # paquete Python
│   ├── __main__.py          # CLI (argparse): split | build | validate | compare | tree | kmz2kml | kml2kmz | fmt
│   ├── model.py             # Folder, Placemark, Geometry
│   ├── reader.py            # KML (de Google Earth o del repo) -> modelo, con política de descarte
│   ├── writer.py            # modelo -> KML normalizado (fragmento o documento con estilos)
│   ├── tree.py              # modelo <-> src/ (directorios, _folder.yaml, .kml, _loose.kml)
│   ├── config.py            # ferromapas.yaml (salida y profundidad máxima)
│   ├── styles.py            # folders.yaml -> <Style>, asignación por prefijo, depth e id
│   ├── build.py             # src/ -> KMZ/KML con estilos
│   ├── convert.py           # kmz2kml / kml2kmz sin pasar por el modelo
│   ├── validate.py
│   └── compare.py
├── tests/
│   ├── fixtures/mini.kml    # KML sintético con todos los casos raros
│   └── test_*.py
├── src/                     # datos del mapa (los genera split)
├── ferromapas.yaml
├── folders.yaml
├── pyproject.toml           # entry point: ferromapas = ferromapas.__main__:main
├── CLAUDE.md
└── .github/workflows/ci.yml  # pendiente (Fase 6)
```

## 4. Fases

Cada fase termina en un commit que funciona. Al final de cada una van los criterios para darla por terminada.

### Fase 0 — Esqueleto
- `pyproject.toml`, paquete vacío, CLI con subcomandos que imprimen "no implementado".
- `.gitignore` (`dist/`, `*.kmz`, `__pycache__/`), `CLAUDE.md` (ver sección 6), tests con `pytest`.
- **Listo cuando**: `pip install -e .` funciona, `ferromapas-toolkit --help` lista los comandos y `pytest` pasa (sin tests).

### Fase 1 — Modelo y lector
- `reader.py` lee un `.kml` o un `.kmz` (el `doc.kml` adentro del zip) y devuelve una `Folder` raíz.
- Política de elementos:
  - **Conservar**: lo de la sección 1.
  - **Descartar en silencio**: la lista de la sección 1. Se cuenta cuánto se descartó de cada tipo, para mostrar un resumen.
  - **Convertir**: los elementos tipados por un `Schema parent="Placemark"`, a Placemark, con `Est` agregado a la descripción.
  - **Error** (cortar la ejecución, indicando la ruta de carpetas): `GroundOverlay`, `ScreenOverlay`, `PhotoOverlay`, `NetworkLink`, `gx:Tour`, `MultiGeometry`, `Model`, `gx:Track`, un Placemark con más de una geometría, y **cualquier elemento desconocido**. Es mejor fallar que perder datos sin enterarse.
  - **Aviso y descarte**: Placemark sin geometría.
- Hay que reconocer los namespaces KML 2.2 y 2.1, `gx` y `atom`.
- Tests con `fixtures/mini.kml`, un archivo chico con: estilos, LookAt, ExtendedData, SchemaData, un elemento FEPSA tipado, un Polygon con hueco, un placemark sin geometría, carpetas anidadas y placemarks sueltos entre carpetas.
- **Listo cuando**, al leer el KMZ real, el resumen da:
  - 1.709 LineString, 5.112 Point (5.090 + 22 FEPSA) y 44 Polygon
  - 1 placemark descartado ("zoologico")
  - 665 carpetas
  - 0 errores

### Fase 2 — Escritor y árbol (split)
- `writer.py`: serialización normalizada (sección 1).
- `tree.py` / `split`: borra y regenera `src/` aplicando la regla de profundidad, con slugs, `_folder.yaml`, `_document.yaml`, `_loose.kml` y `children` en orden.
  - Si el `_folder.yaml` anterior en la misma ruta tenía claves extra (p. ej. `code`), las conserva.
  - Se niega a correr si `git status --porcelain -- src` no está vacío, salvo que se pase `--force`. Así no pisa ediciones manuales sin commitear.
  - En el YAML, las descripciones multilínea se escriben como bloque literal `|`.
- **Listo cuando**:
  - `ferromapas-toolkit split Ferromapas.kmz` genera el árbol.
  - Belgrano queda cortado en Línea / Ramal, Mitre en tramos y Roca en Zona / tramo.
  - Las 2 carpetas "Río Tercero - Córdoba" de Mitre quedan como `rio-tercero-cordoba` y `rio-tercero-cordoba-2`.

### Fase 3 — Build y estilos
- Cargar `src/` → modelo. Si hay archivos o directorios que no están en `children`, se agregan al final en orden alfabético y se muestra un aviso. Si algo listado no existe, es un error.
- Escribir el documento completo con estilos, empaquetar `doc.kml` en un `.kmz` (ZIP con fecha fija, para que el build sea reproducible).
- Opción `--kml` para generar un KML plano.
- **Listo cuando**: el KMZ abre en Google Earth con el mismo árbol de carpetas y cada ferrocarril en su color.

### Fase 4 — Ida y vuelta (lo más importante)
- **Test de idempotencia**: `split(mini) → src1 → build → split → src2`, y `src1 == src2` byte por byte.
- **Test semántico**: el multiconjunto `(camino de carpetas, nombre, tipo, coordenadas)` es el mismo en el original y en el reconstruido, comparando las coordenadas ya redondeadas a 6 decimales.
- `ferromapas-toolkit compare A B`: acepta `.kmz`, `.kml` o directorio `src`. Imprime los elementos que están solo en A o solo en B, y las carpetas agregadas o eliminadas. Sirve como diff semántico para los PR.
- `ferromapas-toolkit fmt`: normaliza `src/` en el lugar (cargar y volver a escribir).
- **Listo cuando**: con el KMZ real, `compare original.kmz dist/Ferromapas.kmz` no muestra diferencias, y el ciclo `build → split` no produce cambios en `git diff`.

### Fase 5 — Validación
`ferromapas-toolkit validate [--strict]`:
- **Errores**:
  - `children` que apunta a algo inexistente.
  - Un `.kml` que no está normalizado (al releerlo y reescribirlo da distinto).
  - Coordenadas fuera de la caja lon [-80, -50], lat [-60, -15].
- **Avisos**:
  - LineString con menos de 2 vértices (hoy hay 2: "Ruta sin título" en Circuito San Juan y "Tranvía a Vapor Formosa").
  - Anillos de polígono con menos de 4 vértices.
  - Carpetas vacías (hoy hay 6).
  - Placemarks sin nombre.
- Exit code ≠ 0 si hay errores, o si hay avisos y se usó `--strict`.

### Fase 6 — CI y releases
**Estado: pendiente.** Las fases 0 a 5 están implementadas; esta queda para después de probar el programa a mano.

- `ci.yml`, en cada push o PR:
  1. `pip install -e .[dev]` y `pytest`
  2. `ferromapas-toolkit validate`
  3. `ferromapas-toolkit build`, luego `ferromapas-toolkit split dist/Ferromapas.kmz --force`, y después `git diff --exit-code src`. Esto garantiza que `src` está normalizado.
- En cada tag `v*`: build y `gh release create $TAG dist/Ferromapas.kmz`.

### Fase 7 — Importación inicial
- Commit aparte: "Importación inicial desde Ferromapas (en Edición).kmz", que contiene solo `src/`.
- Así el historial separa el código de los datos, y la reorganización por ramales (siguiente proyecto) arranca desde ahí con commits limpios.

## 5. Flujo de trabajo diario

```
ferromapas-toolkit build # dist/Ferromapas.kmz
# abrir en Google Earth, editar, "Guardar lugar como…" sobre el mismo archivo
ferromapas-toolkit split dist/Ferromapas.kmz
git diff                              # o: ferromapas-toolkit compare HEAD-build dist/Ferromapas.kmz
git commit
```
Regla: **una sola fuente por vez**. Siempre `build` antes de abrir en Google Earth. Si editás un `.kml` a mano, hacé commit antes del próximo `split`.

## 6. CLAUDE.md sugerido

```markdown
# Ferromapas toolkit
CLI en Python que convierte el KMZ de Ferromapas (Google Earth) <-> árbol de archivos en src/.
Ver PLAN.md para decisiones de formato; no cambiarlas sin preguntar.

- Python 3.12+, dependencias: solo PyYAML (runtime) y pytest (dev).
- La salida del escritor debe ser determinística: mismo modelo => mismos bytes.
- El lector falla ante elementos KML desconocidos; nunca descartar datos en silencio
  salvo los listados en PLAN.md §1.
- Correr `pytest` antes de cada commit. Los tests de ida y vuelta no se pueden saltear.
- No commitear archivos .kmz ni dist/.
- Identificadores del código (módulos, clases, funciones, variables) en inglés.
- Mensajes de la CLI, comentarios, docstrings y commits en español.
```

## 7. Cómo encararlo en Claude Code

1. Poné `PLAN.md` y `CLAUDE.md` en la raíz del repo y hacé commit.
2. Pedile una fase por vez, por ejemplo: *"Implementá la Fase 1 de PLAN.md. Empezá por el fixture tests/fixtures/mini.kml y los tests, después el lector."* Revisá el diff y hacé commit antes de pasar a la siguiente.
3. Para las fases 1, 2 y 4, dejale el KMZ real fuera del repo (por ejemplo en `../datos/Ferromapas.kmz`), así puede verificar los números de los criterios de "listo cuando".
4. La fase 4 es la que da confianza: no pases a reorganizar ramales hasta que `compare` dé cero diferencias contra el original.
