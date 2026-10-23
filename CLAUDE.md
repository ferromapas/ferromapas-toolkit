# Ferromapas toolkit
CLI en Python que convierte el KMZ de Ferromapas (Google Earth) <-> árbol de archivos en src/.
Ver PLAN.md para decisiones de formato; no cambiarlas sin preguntar.

- Python 3.12+, dependencias: solo PyYAML (runtime) y pytest (dev).
- La salida del escritor debe ser determinística: mismo modelo => mismos bytes.
- El lector falla ante elementos KML desconocidos; nunca descartar datos en silencio
  salvo los listados en PLAN.md §1.
- Correr `pytest` antes de cada commit. Los tests de ida y vuelta no se pueden saltear.
- No commitear archivos .kmz ni dist/.
- Código, mensajes de la CLI y commits en español.
