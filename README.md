# Ferromapas toolkit

Herramienta de línea de comandos para trabajar con el mapa ferroviario de Ferromapas.
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

Esto instala el comando `ferromapas-toolkit`.

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

En todos los ejemplos de este README, `ferromapas-toolkit <comando>` equivale a `python3 -m ferromapas <comando>`. Hay que ejecutarlo desde la raíz del repo; desde otro directorio, el comando `ferromapas-toolkit` instalado con `pip install -e .` es más cómodo.

## Flujo de trabajo

```
ferromapas-toolkit build # genera dist/Ferromapas.kmz
# abrir en Google Earth, editar, "Guardar lugar como…" sobre el mismo archivo
ferromapas-toolkit split dist/Ferromapas.kmz
```

Regla: **una sola fuente por vez**. Siempre hay que hacer `build` antes de abrir en Google Earth. Si editás un `.kml` de `src/` a mano, hacé `build` antes del próximo `split`: `split` borra y regenera `src/` sin avisar, y las ediciones que no pasaron a un KMZ se pierden.

La primera vez, partí del KMZ original:

```bash
ferromapas-toolkit split Ferromapas.kmz
```

Ni el KMZ ni `src/` se versionan en este repo (`*.kmz`, `dist/` y `src/` están en `.gitignore`).

### Precisión de las coordenadas

Al hacer `split`, las coordenadas se **redondean a 6 decimales** (el KMZ original llega a 14) y se descarta la altitud. Es una pérdida de datos deliberada:

- 1e-6° ≈ 11,1 cm en latitud y ≈ 9,2 cm en longitud a ~34° S. El error máximo al redondear es de **±5,5 cm** en latitud y **±4,6 cm** en longitud; el error típico total es de 3 a 4 cm.
- Los decimales descartados representan escalas de centímetros a nanómetros, muy por debajo del ruido de un GPS o de un trazado manual en Google Earth.
- El KMZ reconstruido no tiene las coordenadas idénticas al original. `compare` y los tests redondean ambos lados a 6 decimales antes de comparar.
- El redondeo es idempotente: repetir `build → split` deja `src/` idéntico, byte por byte.

Más detalles en [PLAN.md](PLAN.md).

## Generar una versión nueva

1. Dejá `src/` al día (`split`) y actualizá la línea `Versión: X.Y.Z` de la `description` en `src/ferromapas/_folder.yaml`.
2. Armá el KMZ nuevo. Es el archivo que se publica; no va a este repo (`*.kmz` está en `.gitignore`):

   ```bash
   ferromapas-toolkit validate
   ferromapas-toolkit build -o ../datos/ferromapas_vX.Y.Z.kmz
   ```

3. Generá el registro de cambios comparando con el KMZ anterior publicado. Con `--out` queda directamente en el sitio:

   ```bash
   ferromapas-toolkit changelog ../ferromapas.github.io/public/descargas/ferromapas_vA.B.C.kmz \
     ../datos/ferromapas_vX.Y.Z.kmz --version X.Y.Z \
     --out ../ferromapas.github.io/src/data/changelog
   ```

4. Abrí el `X.Y.Z.yaml` generado y completá `notes` (acepta markdown).
5. Para publicar, seguí "Publicar una versión nueva del mapa" en el README de `ferromapas.github.io`.

## Comandos

### `ferromapas-toolkit split ENTRADA [--src DIR] [--config ARCHIVO] [--folders ARCHIVO]`

Convierte un `.kmz` o `.kml` en el árbol de `src/`. **Borra y regenera `src/`** por completo.

- No protege las ediciones a mano de `src/`: las pisa sin avisar.
- Sólo reemplaza un directorio que no exista, esté vacío o ya sea un `src/` del toolkit (con `_document.yaml`). Con otro `--src` falla y no borra nada.
- Conserva las claves extra que hayas agregado a los `_folder.yaml` y `_document.yaml` (por ejemplo `code`).
- Imprime un resumen: cantidad de carpetas y geometrías, lo que se descartó y los avisos.
- Falla, indicando la ruta de carpetas, si encuentra algo que no sabe leer (por ejemplo `NetworkLink`, `MultiGeometry` o un elemento desconocido). Es mejor fallar que perder datos sin enterarse.

### `ferromapas-toolkit build [--src DIR] [--folders ARCHIVO] [--config ARCHIVO] [-o SALIDA] [--version TEXTO] [--kml]`

Arma el KMZ a partir de `src/`, con los estilos de `folders.yaml`.

- La salida por defecto es la de `ferromapas.yaml` (`dist/Ferromapas.kmz`).
- `--version TEXTO` pone la versión en el nombre de la carpeta principal del mapa: `--version "en Edición"` da `Ferromapas (en Edición)`. Sin esta opción queda `Ferromapas`.
- `--kml` genera un KML plano en lugar de un KMZ.
- El resultado es reproducible: la misma entrada da el mismo archivo, byte por byte.
- Si hay archivos o directorios que no figuran en `children`, los agrega al final y muestra un aviso. Si algo que figura no existe, es un error.

### `ferromapas-toolkit validate [--src DIR] [--strict]`

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

### `ferromapas-toolkit compare A B [--ignore-top-level]`

Compara dos fuentes. Cada una puede ser un `.kmz`, un `.kml` o un directorio `src`.

Imprime dos tipos de diferencias:

- **Modificados** (`~`): el mismo elemento (misma ruta, nombre y tipo) en ambos lados, pero con otro contenido. La línea dice qué cambió, por ejemplo `coordenada: A → B`, `vértices: 2473 → 2521`, `1 de 39 vértices distintos` o `descripción: 'a' → 'b'`.
- **Solo en A / solo en B** (`-` / `+`): carpetas y placemarks que no tienen equivalente en el otro lado, incluidos los que cambiaron de nombre o de carpeta.

No importa el orden, y las coordenadas se comparan con 6 decimales. Sale con código 1 si hay diferencias. Con `--ignore-top-level` ignora el nombre de la carpeta de primer nivel, que forma parte de la ruta de todo: sirve para comparar versiones que la renombraron (por ejemplo "Ferromapas 1.0.0" y "Ferromapas (en Edición)"). Sirve como diff semántico:

```bash
ferromapas-toolkit compare Ferromapas.kmz dist/Ferromapas.kmz   # "Sin diferencias."
```

### `ferromapas-toolkit changelog ANTERIOR NUEVO --version X.Y.Z [--date AAAA-MM-DD] [--out DIR] [--force]`

Genera el registro de cambios de una versión nueva del mapa, para la sección "Cambios" de ferromapas.github.io. Usa el mismo diff semántico que `compare` (con `--ignore-top-level` implícito) y agrupa las diferencias por ferrocarril (`País / Ferrocarril`).

Escribe `DIR/X.Y.Z.yaml` con `version`, `date`, `notes` (vacío, para completar a mano), `summary` (totales de agregados, modificados y eliminados) y `railways` (la lista por ferrocarril). Un renombre o un movimiento aparece como eliminado + agregado, porque los placemarks no tienen identificador propio. Si el archivo ya existe falla; con `--force` lo regenera y conserva las `notes`. La salida es determinística.

```bash
ferromapas-toolkit changelog ferromapas_v1.0.0.kmz ferromapas_v1.1.0.kmz --version 1.1.0 \
  --out ../ferromapas.github.io/src/data/changelog
```

### `ferromapas-toolkit tree [--src DIR] [--depth N] [--names]`

Muestra cómo quedaron los archivos de `src/`, como el comando `tree`, en el orden de `children`. Cada `.kml` indica su cantidad de placemarks.

- `--depth N` limita cuántos niveles de directorios se despliegan (la raíz es 0).
- `--names` agrega el nombre real de cada carpeta (los nombres de archivo son slugs).

```
src/
└── ferromapas-1-0-0/
    ├── ferrocarriles-argentinos/
    │   ├── ferrocarril-mitre/
    │   │   ├── puerto-san-lorenzo.kml  (22 placemarks)
    │   │   ├── rosario-norte.kml  (8 placemarks)
    │   │   └── ...
    │   └── ...
    └── ferrocarriles-de-chile/
        └── ferrocarril-trasandino-central-chileno.kml  (15 placemarks)
```

### `ferromapas-toolkit kmz2kml ENTRADA [-o SALIDA] [--force]` y `ferromapas-toolkit kml2kmz ENTRADA [-o SALIDA] [--force]`

Convierten un archivo entre `.kmz` y `.kml`. Es una conversión directa del archivo: **no pasa por el modelo**, así que se conserva todo el contenido (estilos, vistas, etc.).

- `kmz2kml` extrae el `doc.kml` del KMZ. Si el KMZ trae otros archivos (por ejemplo íconos), avisa que no se copian.
- `kml2kmz` empaqueta el KML como `doc.kml`. El resultado es reproducible: la misma entrada da el mismo archivo.
- Sin `-o`, la salida tiene el nombre de la entrada con la otra extensión. Si ya existe, se niega a pisarla salvo con `--force`.

### `ferromapas-toolkit fmt [--src DIR] [--config ARCHIVO] [--folders ARCHIVO]`

Normaliza `src/` en el lugar: lo carga y lo vuelve a escribir. Útil después de editar `.kml` o `.yaml` a mano. A diferencia de `split`, conserva tus ediciones, así que no exige que `src/` esté limpio.

## Estructura de `src/`

```
src/
├── _document.yaml
└── ferromapas/
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
- Los placemarks sueltos de un directorio van en `_loose.kml`. Si hay sueltos antes y después de las subcarpetas, cada tanda contigua va a su propio archivo (`_loose.kml`, `_loose-2.kml`, ...), para conservar el orden.
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
  max_dir_depth: 4          # Document=0, "Ferromapas"=1, "Ferrocarriles Argentinos"=2, "Ferrocarril X"=3, Línea/Zona/tramo=4
```

Una carpeta es directorio si su profundidad es menor o igual al máximo **y además** tiene subcarpetas. En cualquier otro caso es un archivo `.kml`. Si `max_dir_depth` (o el archivo entero) falta, el valor por defecto es 3. La profundidad de una carpeta puntual se define con `depth` en `folders.yaml` (ver abajo). Si cambiás estos valores, volvé a correr `split` para reorganizar `src/`.

### `folders.yaml`

Los estilos se aplican solo en el `build`. Las carpetas se anidan como en el mapa (por nombre o por slug) y cada nodo puede tener:

- `styles`: estilo para todo lo que está debajo.
- `depth`: cuántos niveles por debajo de esa carpeta se guardan como directorios. `split` y `fmt` lo usan y gana sobre `max_dir_depth`.
- `id`: nombre corto del `<Style>` generado (requiere `styles`). Sin `id`, el nombre se deriva de la ruta, por ejemplo `s-ferromapas--ferrocarriles-argentinos--ferrocarril-belgrano`. Solo letras, números, `_`, `-` y `.`, sin espacios; no puede repetirse ni llamarse `default`.

```yaml
styles:
  default: { color: "#757575", line_width: 2.5, icon: "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png", icon_scale: 0.4, label_scale: 0.7, polygon_opacity: 0.35 }
folders:
  Ferromapas:
    Ferrocarriles Argentinos:
      Ferrocarril Belgrano: { styles: { color: "#6A1B9A" }, id: belgrano, depth: 2 }   # baja un nivel más que Chile
    Ferrocarriles de Chile:
      styles: { color: "#C62828" }
```

Los colores van como `#RRGGBB`. Las claves que no se indican se toman de `styles.default`. Una clave desconocida es un error.

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
