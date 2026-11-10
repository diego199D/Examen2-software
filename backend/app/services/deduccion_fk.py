"""CU12 — deducción de relaciones a partir de atributos clave foránea.

Lógica pura (sin IA ni base de datos) que usa `reconocimiento_foto.py` para
contrastar las relaciones que "vio" el modelo de visión con lo que dicen
los propios atributos del diagrama: si `Pago` tiene un atributo `id_socio`,
casi seguro hay una línea entre `Pago` y `Socio`; y una relación entre dos
clases que declaran sus claves foráneas pero ninguna la de la otra es
sospechosa (medido con una imagen real: el modelo leía la línea "Socio
realiza Pago", que pasa justo por encima de otra clase, como si saliera de
esa otra clase).

Cómo se usan (ver `reconocimiento_foto._revisar_relaciones_con_fk`):

- Una relación FALTANTE (hay un `id_x` pero el modelo no reportó la línea)
  solo se agrega si una pregunta enfocada sobre la imagen confirma que la
  línea existe -- de ahí salen también sus multiplicidades.
- Una relación SOSPECHOSA se quita sin preguntarle a la imagen. Primero se
  intentó confirmarlo con la imagen, pero medido contra la API real no
  sirvió: una línea que pasa POR DETRÁS de una caja (la de
  "Pago–Membresia" pasando detrás de "Inscripcion") toca visualmente el
  borde de esa caja, y el modelo respondía siempre que la relación
  "Inscripcion–Pago" existía -- incluso pidiéndole antes que describiera el
  recorrido de la línea, que describía de forma geométricamente imposible.
  Decisión de la usuaria: en este caso deciden las claves foráneas. Por eso
  el criterio de "sospechosa" es estricto (ver `RevisionFK`) y cada
  relación quitada queda avisada en la vista previa: en un diagrama donde
  esa relación exista de verdad sin su `id_`, se pierde y hay que agregarla
  a mano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.relacion import TipoRelacion
from app.schemas.reconocimiento_foto import ClaseDetectadaIO, RelacionDetectadaIO
from app.services.nombres import normalizar_nombre

# "id_socio", "idSocio", "socio_id", "socioId" (una vez normalizado a
# minúsculas y sin separadores quedan "idsocio" / "socioid"). El atributo
# que se llama solo "id" es la clave primaria, no una foránea. Sin
# separador solo cuenta si lo que queda es el nombre de una clase detectada
# (así "idioma" o "identificador" no se confunden con una FK).
_PATRON_ID_ADELANTE = re.compile(r"^id(.+)$")
_PATRON_ID_ATRAS = re.compile(r"^(.+)id$")
# Para avisar de una clase NO detectada hace falta un separador explícito
# ("id_membresia", "membresia_id"): sin clase contra la cual comparar, sin
# separador no hay forma de distinguir "idioma" de una FK.
_PATRON_FK_EXPLICITA = re.compile(r"^(?:id[\s_\-]+(?P<adelante>.+)|(?P<atras>.+?)[\s_\-]+id)$")


def _compacto(texto: str) -> str:
    """Clave para comparar un atributo con un nombre de clase: sin tildes,
    sin mayúsculas, sin espacios ni guiones bajos ("Línea Pedido" y
    "linea_pedido" quedan iguales)."""
    return re.sub(r"[\s_\-]", "", normalizar_nombre(texto))


@dataclass(frozen=True)
class PistaFK:
    """`clase` tiene un atributo (`atributo`) que referencia a `referenciada`."""

    clase: str
    atributo: str
    referenciada: str


def pistas_fk(clases: list[ClaseDetectadaIO]) -> list[PistaFK]:
    """Todos los atributos de tipo clave foránea que apuntan a OTRA clase
    del mismo diagrama. Un `id_x` cuyo `x` no es ninguna clase detectada no
    genera pista acá (ver `clases_referenciadas_no_detectadas`)."""
    por_compacto = {_compacto(c.nombre): c.nombre for c in clases}
    pistas: list[PistaFK] = []
    for c in clases:
        for a in c.atributos:
            referenciada = _clase_referenciada(a.nombre, por_compacto)
            if referenciada and _compacto(referenciada) != _compacto(c.nombre):
                pistas.append(PistaFK(clase=c.nombre, atributo=a.nombre, referenciada=referenciada))
    return pistas


def clases_referenciadas_no_detectadas(clases: list[ClaseDetectadaIO]) -> list[PistaFK]:
    """Atributos `id_x` cuyo `x` no coincide con ninguna clase detectada --
    posible clase que el modelo no vio (visto en pruebas reales: `Pago`
    tenía `id_membresia` y la clase `Membresia` no aparecía). Solo sirve
    para avisar: nunca se inventa la clase."""
    por_compacto = {_compacto(c.nombre): c.nombre for c in clases}
    faltantes: list[PistaFK] = []
    vistas: set[str] = set()
    for c in clases:
        for a in c.atributos:
            if _clase_referenciada(a.nombre, por_compacto) is not None:
                continue
            coincidencia = _PATRON_FK_EXPLICITA.match(normalizar_nombre(a.nombre))
            if not coincidencia:
                continue
            nombre = (coincidencia.group("adelante") or coincidencia.group("atras")).strip()
            if nombre and _compacto(nombre) not in vistas:
                vistas.add(_compacto(nombre))
                faltantes.append(PistaFK(clase=c.nombre, atributo=a.nombre, referenciada=nombre))
    return faltantes


def _clase_referenciada(nombre_atributo: str, por_compacto: dict[str, str]) -> str | None:
    compacto = _compacto(nombre_atributo)
    if compacto == "id":
        return None
    for patron in (_PATRON_ID_ADELANTE, _PATRON_ID_ATRAS):
        coincidencia = patron.match(compacto)
        if coincidencia and coincidencia.group(1) in por_compacto:
            return por_compacto[coincidencia.group(1)]
    return None


def _par(a: str, b: str) -> frozenset[str]:
    return frozenset((_compacto(a), _compacto(b)))


@dataclass(frozen=True)
class RevisionFK:
    """Qué hay que preguntarle a la imagen, según las pistas de claves
    foráneas:

    - `sospechosas`: índices (en la lista de relaciones) de relaciones que
      el modelo reportó pero que las claves foráneas contradicen -- ninguna
      de las dos clases referencia a la otra, y LAS DOS declaran claves
      foráneas (o sea, ambas modelan sus referencias: si esta relación
      existiera, lo esperable es que alguna tuviera su `id_`). Nunca una
      HERENCIA (no lleva clave foránea). Criterio estricto a propósito: estas
      se quitan sin preguntarle a la imagen -- ver
      `reconocimiento_foto._revisar_relaciones_con_fk`.
    - `faltantes`: pistas (una por par de clases) de relaciones que las
      claves foráneas indican pero que el modelo no reportó.
    """

    sospechosas: list[int]
    faltantes: list[PistaFK]


def revisar_con_fk(clases: list[ClaseDetectadaIO], relaciones: list[RelacionDetectadaIO]) -> RevisionFK:
    pistas = pistas_fk(clases)
    pares_respaldados = {_par(p.clase, p.referenciada) for p in pistas}
    clases_con_fk = {_compacto(p.clase) for p in pistas}

    sospechosas = []
    for i, r in enumerate(relaciones):
        par = _par(r.clase_origen, r.clase_destino)
        # Una herencia nunca tiene clave foránea: sin esta excepción, una
        # generalización entre dos clases que declaran otras FKs se marcaría
        # (y se quitaría) siempre.
        if r.tipo == TipoRelacion.HERENCIA or par in pares_respaldados or len(par) < 2:
            continue
        if par <= clases_con_fk:
            sospechosas.append(i)

    pares_reportados = {_par(r.clase_origen, r.clase_destino) for r in relaciones}
    faltantes: list[PistaFK] = []
    vistos: set[frozenset[str]] = set()
    for p in pistas:
        par = _par(p.clase, p.referenciada)
        if par in pares_reportados or par in vistos:
            continue
        vistos.add(par)
        faltantes.append(p)
    return RevisionFK(sospechosas=sospechosas, faltantes=faltantes)
