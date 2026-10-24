# Ferromapas toolkit

Herramienta de línea de comandos para versionar en git el mapa ferroviario de Ferromapas.
Convierte el KMZ que se edita en Google Earth en un árbol de archivos de texto (`src/`) y vuelve a armar el KMZ a partir de ese árbol.

Las decisiones de formato están en [PLAN.md](PLAN.md).

## Instalación

Requiere Python 3.12 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest                      # opcional: corre los tests
```

Esto instala el comando `ferromapas`.

### Sin instalar el paquete

No hace falta instalarlo: alcanza con tener PyYAML y correr el módulo desde la raíz del repo.

```bash
# Opción A: usar el entorno virtual del repo, que ya tiene PyYAML
source .venv/bin/activate
python -m ferromapas --help

# Opción B: instalar PyYAML en tu Python
pip install PyYAML
python3 -m ferromapas split ../datos/Ferromapas.kmz
```

Si ves `ModuleNotFoundError: No module named 'yaml'`, es que falta PyYAML en el Python que estás usando: aplicá una de las dos opciones. Si `pip` falla con `externally-managed-environment`, usá la A.

En todos los ejemplos de este README, `ferromapas <comando>` equivale a `python3 -m ferromapas <comando>`. Hay que ejecutarlo desde la raíz del repo; desde otro directorio, el comando `ferromapas` instalado con `pip install -e .` es más cómodo.

## Flujo de trabajo

```
ferromapas build                     # genera dist/Ferromapas.kmz
# abrir en Google Earth, editar, "Guardar lugar como…" sobre el mismo archivo
ferromapas split dist/Ferromapas.kmz
git diff
git commit
```

Regla: **una sola fuente por vez**. Siempre hay que hacer `build` antes de abrir en Google Earth. Si editás un `.kml` a mano, hacé commit antes del próximo `split`.

La primera vez, partí del KMZ original:

```bash
ferromapas split Ferromapas.kmz
```

El KMZ no se versiona (`*.kmz` y `dist/` están en `.gitignore`).

## Comandos

### `ferromapas split ENTRADA [--src DIR] [--config ARCHIVO] [--force]`

Convierte un `.kmz` o `.kml` en el árbol de `src/`. **Borra y regenera `src/`** por completo.

- Se niega a correr si hay cambios sin commitear en `src/`. Con `--force` los pisa.
- Conserva las claves extra que hayas agregado a los `_folder.yaml` y `_document.yaml` (por ejemplo `code`).
- Imprime un resumen: cantidad de carpetas y geometrías, lo que se descartó y los avisos.
- Falla, indicando la ruta de carpetas, si encuentra algo que no sabe leer (por ejemplo `NetworkLink`, `MultiGeometry` o un elemento desconocido). Es mejor fallar que perder datos sin enterarse.

### `ferromapas build [--src DIR] [--styles ARCHIVO] [--config ARCHIVO] [-o SALIDA] [--kml]`

Arma el KMZ a partir de `src/`, con los estilos de `styles.yaml`.

- La salida por defecto es la de `ferromapas.yaml` (`dist/Ferromapas.kmz`).
- `--kml` genera un KML plano en lugar de un KMZ.
- El resultado es reproducible: la misma entrada da el mismo archivo, byte por byte.
- Si hay archivos o directorios que no figuran en `children`, los agrega al final y muestra un aviso. Si algo que figura no existe, es un error.

### `ferromapas validate [--src DIR] [--strict]`

Revisa `src/`.

| Tipo | Qué detecta |
|---|---|
| Error | `children` que apunta a algo inexistente |
| Error | un `.kml` no normalizado (se arregla con `fmt`) |
| Error | coordenadas fuera de lon [-80, -50] y lat [-60, -15] |
| Aviso | LineString con menos de 2 vértices |
| Aviso | anillos de polígono con menos de 4 vértices |
| Aviso | carpetas vacías |
| Aviso | placemarks sin nombre |

Sale con código 1 si hay errores, o si hay avisos y se usó `--strict`.

### `ferromapas compare A B`

Compara dos fuentes. Cada una puede ser un `.kmz`, un `.kml` o un directorio `src`.

Imprime las carpetas y los placemarks que están solo en A o solo en B. No importa el orden, y las coordenadas se comparan con 6 decimales. Sale con código 1 si hay diferencias. Sirve como diff semántico:

```bash
ferromapas compare Ferromapas.kmz dist/Ferromapas.kmz   # "Sin diferencias."
```

### `ferromapas fmt [--src DIR] [--config ARCHIVO]`

Normaliza `src/` en el lugar: lo carga y lo vuelve a escribir. Útil después de editar `.kml` o `.yaml` a mano. A diferencia de `split`, conserva tus ediciones, así que no exige que `src/` esté limpio.

## Estructura de `src/`

```
src/
├── _document.yaml
└── ferromapas-en-edicion/
    ├── _folder.yaml
    └── ferrocarriles-argentinos/
        ├── _folder.yaml
        └── ferrocarril-mitre/
            ├── _folder.yaml
            ├── _loose.kml
            └── ramal-x.kml
```

- Las carpetas superiores son directorios con un `_folder.yaml`. La raíz del `Document` tiene `_document.yaml`.
- Desde el ramal hacia abajo, cada carpeta es un único `.kml`. Las subcarpetas internas quedan como `<Folder>` anidados.
- Los placemarks sueltos de un directorio van juntos en `_loose.kml`.
- El orden de los hijos se guarda en `children` dentro del yaml, no en los nombres de archivo.
- Los nombres de archivo son slugs ASCII (`rio-tercero-cordoba.kml`). Si dos hermanos dan el mismo slug, se agrega `-2`, `-3`. El nombre real queda en el `<name>` o en el yaml.
- Cada `.kml` es un KML válido por sí mismo: se puede abrir solo en Google Earth.

Ejemplo de `_folder.yaml`:

```yaml
name: Ferrocarril Mitre
description: |-
  Texto de varias líneas
children:
- _loose.kml
- ramal-x.kml
- tramo-y/
```

Una entrada que termina en `/` es un directorio y una que termina en `.kml` es un archivo.

## Configuración

### `ferromapas.yaml`

```yaml
output: dist/Ferromapas.kmz
split:
  max_dir_depth: 3          # Document=0, "Ferromapas (en Edición)"=1, "Ferrocarriles Argentinos"=2, "Ferrocarril X"=3
  overrides:                # por prefijo de ruta (slugs); gana el prefijo más largo
    ferromapas-en-edicion/ferrocarriles-argentinos/ferrocarril-belgrano: 4
```

Una carpeta es directorio si su profundidad es menor o igual al máximo **y además** tiene subcarpetas. En cualquier otro caso es un archivo `.kml`. Si cambiás estos valores, volvé a correr `split` para reorganizar `src/`.

### `styles.yaml`

Los estilos se aplican solo en el `build`, por prefijo de ruta de slugs, a todo lo que está debajo:

```yaml
default: { color: "#757575", line_width: 2.5, icon: "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png", icon_scale: 0.4, label_scale: 0.7, polygon_opacity: 0.35 }
styles:
  ferromapas-en-edicion/ferrocarriles-argentinos/ferrocarril-mitre: { color: "#C62828" }
```

Los colores van como `#RRGGBB`. Las claves que no se indican se toman de `default`. Una clave desconocida es un error.

## Qué se conserva y qué se descarta

Solo se conserva:

- `Folder`: `name` y `description`.
- `Placemark`: `name`, `description` y **una** geometría (`Point`, `LineString` o `Polygon`, con anillos interiores).

Al hacer `split` se descartan los estilos, el estado de carpetas, las vistas guardadas, los `ExtendedData`, la altitud de las coordenadas y otros elementos. La lista completa está en [PLAN.md](PLAN.md#qué-se-descarta-en-el-split). Las coordenadas se guardan con 6 decimales.

Casos especiales del KMZ actual:

- Las estaciones FEPSA escritas con la sintaxis vieja de KML 2.1 se convierten en `Placemark`, con `Nombre FEPSA: <Est>` al final de la descripción.
- Un placemark sin geometría se elimina con un aviso.
- Un `<Document>` anidado dentro de una carpeta se trata como una carpeta más.

## Desarrollo

```bash
pytest
```

Los tests de ida y vuelta (`split` → `build` → `split` sin cambios) no se pueden saltear.
