"""Comparación de nombres de clase tolerante a tildes/mayúsculas/espacios,
compartida por CU12 (`reconocimiento_foto.py`, `deduccion_fk.py`)."""

import unicodedata


def normalizar_nombre(texto: str) -> str:
    """Clave de comparación de nombres de clase: sin tildes/diacríticos (vía
    NFKD), sin distinguir mayúsculas y con los espacios colapsados -- así
    "Préstamo", "prestamo" y " Prestamo " son la misma clase. No alcanza con
    `.strip().casefold()`: el modelo puede escribir un mismo nombre con y sin
    tilde en distintas partes de la misma respuesta (p. ej. en la lista de
    clases y en una relación), y eso descartaba la relación."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())
