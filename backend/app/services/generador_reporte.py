"""
Generador de reporte PDF del diagrama de clases de un proyecto (CU07).

Reporte técnico simple y legible (no es una pieza de diseño): encabezado con
nombre del proyecto y fecha de generación, una sección por clase (atributos y
métodos si tiene) y una tabla de relaciones. Usa reportlab (Platypus) porque
es puro Python — no depende de binarios/librerías del sistema como WeasyPrint
(GTK/Pango), lo que lo hace más simple de instalar en Windows sin pasos extra.
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion

_ETIQUETAS_TIPO_RELACION = {
    "ASOCIACION": "Asociación",
    "HERENCIA": "Herencia",
    "AGREGACION": "Agregación",
    "COMPOSICION": "Composición",
}


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="ClaseNombre", parent=base["Heading2"], spaceBefore=14, spaceAfter=4))
    base.add(ParagraphStyle(name="Subtitulo", parent=base["Normal"], textColor=colors.grey, spaceAfter=12))
    base.add(ParagraphStyle(name="Miembro", parent=base["Normal"], leftIndent=12, spaceAfter=2))
    base.add(ParagraphStyle(name="SinContenido", parent=base["Normal"], leftIndent=12, textColor=colors.grey))
    return base


def _visibilidad_simbolo(visibilidad) -> str:
    return {
        "PUBLICO": "+",
        "PRIVADO": "-",
        "PROTEGIDO": "#",
        "PAQUETE": "~",
    }.get(getattr(visibilidad, "value", visibilidad), "")


def _seccion_clase(clase: ClaseUml, estilos: dict[str, ParagraphStyle]) -> list:
    elementos = []
    titulo = clase.nombre + (f" «{clase.estereotipo}»" if clase.estereotipo else "")
    if clase.es_abstracta:
        titulo += " (abstracta)"
    elementos.append(Paragraph(titulo, estilos["ClaseNombre"]))

    elementos.append(Paragraph("Atributos", estilos["Heading4"]))
    atributos = sorted(clase.atributos, key=lambda a: a.orden)
    if atributos:
        for a in atributos:
            tipo = f": {a.tipo}" if a.tipo else ""
            elementos.append(
                Paragraph(f"{_visibilidad_simbolo(a.visibilidad)} {a.nombre}{tipo}", estilos["Miembro"])
            )
    else:
        elementos.append(Paragraph("(sin atributos)", estilos["SinContenido"]))

    metodos = sorted(clase.metodos, key=lambda m: m.orden)
    if metodos:
        elementos.append(Paragraph("Métodos", estilos["Heading4"]))
        for m in metodos:
            parametros = m.parametros or ""
            retorno = f": {m.tipo_retorno}" if m.tipo_retorno else ""
            elementos.append(
                Paragraph(
                    f"{_visibilidad_simbolo(m.visibilidad)} {m.nombre}({parametros}){retorno}",
                    estilos["Miembro"],
                )
            )

    return elementos


def _tabla_relaciones(
    relaciones: list[Relacion], clases_por_id: dict[str, ClaseUml], estilos: dict[str, ParagraphStyle]
) -> list:
    if not relaciones:
        return [
            Paragraph("Relaciones", estilos["Heading3"]),
            Paragraph("(sin relaciones)", estilos["SinContenido"]),
        ]

    encabezado = ["Origen", "Destino", "Tipo", "Mult. origen", "Mult. destino", "Etiqueta"]
    filas = [encabezado]
    for r in relaciones:
        origen = clases_por_id.get(r.id_clase_origen)
        destino = clases_por_id.get(r.id_clase_destino)
        filas.append(
            [
                origen.nombre if origen else "?",
                destino.nombre if destino else "?",
                _ETIQUETAS_TIPO_RELACION.get(getattr(r.tipo, "value", r.tipo), str(r.tipo)),
                r.multiplicidad_origen or "",
                r.multiplicidad_destino or "",
                r.etiqueta or "",
            ]
        )

    tabla = Table(filas, repeatRows=1, hAlign="LEFT")
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eaf0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7cdd6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [Paragraph("Relaciones", estilos["Heading3"]), Spacer(1, 4), tabla]


def generar_pdf_reporte(proyecto: Proyecto, clases: list[ClaseUml], relaciones: list[Relacion]) -> bytes:
    """Arma el PDF del reporte técnico (CU07) del diagrama de clases del
    proyecto. Asume que `clases` no está vacío (el llamador ya valida el caso
    "sin contenido para exportar" antes de invocar esta función)."""
    estilos = _estilos()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Reporte UML — {proyecto.nombre}",
    )

    elementos: list = [
        Paragraph(f"Reporte de diagrama de clases — {proyecto.nombre}", estilos["Title"]),
        Paragraph(
            f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            estilos["Subtitulo"],
        ),
    ]

    for clase in sorted(clases, key=lambda c: c.nombre.lower()):
        elementos.extend(_seccion_clase(clase, estilos))

    clases_por_id = {c.id: c for c in clases}
    elementos.append(Spacer(1, 10))
    elementos.extend(_tabla_relaciones(relaciones, clases_por_id, estilos))

    doc.build(elementos)
    return buffer.getvalue()
