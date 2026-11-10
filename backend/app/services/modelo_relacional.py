"""
Modelo relacional intermedio (segundo parcial): traduce el diagrama de
clases a tablas, columnas, claves foráneas, tablas intermedias N:M y
herencia — UNA sola vez, en un solo lugar. Lo consumen:

- `generador_spring.py` (entidades JPA, servicios, controladores),
- `generador_ddl.py` (script SQL / migración Flyway, export DDL),
- `generador_postman.py` (colección Postman con todas las rutas),
- `generador_flutter.py` (CU15, vía `relaciones_efectivas`/`lado_con_fk`/
  `resolver_nombres_relaciones`),

así el JSON, las columnas y las rutas de los cuatro nunca se desincronizan.

Reglas de mapeo (documentadas también en docs/decisiones.md):

- Multiplicidad "plural" = `*`, `0..*`, `1..*`; cualquier otra (o ninguna)
  es "singular".
- **1:1** — la FK (con `UNIQUE`) va en el origen; salvo composición/
  agregación, donde va en la *parte* (destino) apuntando al *todo* (origen),
  para que el `ON DELETE` tenga sentido.
- **1:N** — la FK va en el lado "muchos".
- **N:M** — tabla intermedia `tablaA_tablaB` (tablas en orden alfabético,
  o el nombre que eligió el usuario en la relación) con PK compuesta,
  FKs `ON DELETE CASCADE` e índice sobre la segunda columna (la primera ya
  la cubre la PK). Dueño JPA: el origen.
- **Clase de asociación** (`Relacion.id_clase_asociacion`, ej. `Matricula`
  entre Estudiante *--* Curso): su propia tabla ES la intermedia — PK
  propia + `UNIQUE (a_id, b_id)` + dos FKs `NOT NULL ON DELETE CASCADE`.
  Internamente se reemplaza la relación por dos 1:N sintéticas
  (Estudiante 1 -- * Matricula, Curso 1 -- * Matricula).
- **Herencia** — tabla por subclase (JPA `JOINED`): la tabla hija tiene
  `id` como PK y a la vez FK a la tabla padre (`ON DELETE CASCADE`). Si
  una clase tiene más de un padre se usa el primero (por id de relación);
  los ciclos se descartan.
- **ON DELETE** de las FKs: composición → `CASCADE`, agregación →
  `SET NULL` (la columna siempre admite NULL), asociación → `RESTRICT`.
- **NOT NULL**: la FK es obligatoria cuando la multiplicidad del extremo
  referenciado es exactamente `1` (y no es agregación).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion
from app.services.diagrama import MULTIPLICIDADES_PLURALES
from app.services.identificadores import (
    a_snake_case,
    nombre_campo_java,
    nombre_clase_java,
    pluralizar,
    ruta_api_clase,
)
from app.services.tipos import mapear_tipo_java, tipo_no_reconocido, tipo_sql

LIMITE_IDENTIFICADOR_SQL = 63


def es_plural(multiplicidad: str | None) -> bool:
    return multiplicidad in MULTIPLICIDADES_PLURALES


def identificador_sql(texto: str) -> str:
    """Recorta a 63 caracteres (límite de PostgreSQL) sin perder unicidad."""
    if len(texto) <= LIMITE_IDENTIFICADOR_SQL:
        return texto
    sufijo = hashlib.sha1(texto.encode()).hexdigest()[:8]
    return texto[: LIMITE_IDENTIFICADOR_SQL - 9] + "_" + sufijo


def campo_plural(nombre_uml: str) -> str:
    """'DetalleFactura' -> 'detalleFacturas' (nombre de una colección)."""
    return nombre_campo_java(pluralizar(nombre_clase_java(nombre_uml)))


def _nombre_unico(usados: set[str], propuesto: str) -> str:
    if propuesto not in usados:
        usados.add(propuesto)
        return propuesto
    i = 2
    while f"{propuesto}{i}" in usados:
        i += 1
    usados.add(f"{propuesto}{i}")
    return f"{propuesto}{i}"


# ---------------------------------------------------------------------------
# Relaciones "efectivas": sin herencia y con las clases de asociación ya
# expandidas a dos 1:N. Es lo que tienen que mirar los generadores para
# decidir columnas FK.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelacionEfectiva:
    id: str
    id_clase_origen: str
    id_clase_destino: str
    tipo: TipoRelacion
    multiplicidad_origen: str | None
    multiplicidad_destino: str | None
    etiqueta: str | None = None
    # Si salió de expandir una clase de asociación: id de la relación N:M original.
    de_asociacion: str | None = None


def _clase_asociacion_valida(r: Relacion, ids: set[str]) -> str | None:
    ca = getattr(r, "id_clase_asociacion", None)
    if r.tipo == TipoRelacion.HERENCIA or not ca or ca not in ids:
        return None
    if ca in (r.id_clase_origen, r.id_clase_destino):
        return None
    return ca


def relaciones_efectivas(clases: list[ClaseUml], relaciones: list[Relacion]) -> list[RelacionEfectiva]:
    ids = {c.id for c in clases}
    resultado: list[RelacionEfectiva] = []
    for r in sorted(relaciones, key=lambda r: r.id):
        if r.id_clase_origen not in ids or r.id_clase_destino not in ids:
            continue
        if r.tipo == TipoRelacion.HERENCIA:
            continue
        ca = _clase_asociacion_valida(r, ids)
        if ca is None:
            resultado.append(
                RelacionEfectiva(
                    id=r.id,
                    id_clase_origen=r.id_clase_origen,
                    id_clase_destino=r.id_clase_destino,
                    tipo=r.tipo,
                    multiplicidad_origen=r.multiplicidad_origen,
                    multiplicidad_destino=r.multiplicidad_destino,
                    etiqueta=r.etiqueta,
                )
            )
            continue
        for sufijo, extremo in (("a", r.id_clase_origen), ("b", r.id_clase_destino)):
            resultado.append(
                RelacionEfectiva(
                    id=f"{r.id}#{sufijo}",
                    id_clase_origen=extremo,
                    id_clase_destino=ca,
                    tipo=TipoRelacion.COMPOSICION,
                    multiplicidad_origen="1",
                    multiplicidad_destino="0..*",
                    de_asociacion=r.id,
                )
            )
    return resultado


def lado_con_fk(r: RelacionEfectiva | Relacion) -> tuple[str, str] | None:
    """(id de la clase que guarda la FK, id de la clase referenciada), o None
    si es N:M (no hay FK escalar)."""
    po, pd = es_plural(r.multiplicidad_origen), es_plural(r.multiplicidad_destino)
    if po and pd:
        return None
    if not po and not pd:
        if r.tipo in (TipoRelacion.COMPOSICION, TipoRelacion.AGREGACION):
            return r.id_clase_destino, r.id_clase_origen
        return r.id_clase_origen, r.id_clase_destino
    if not po and pd:
        return r.id_clase_destino, r.id_clase_origen
    return r.id_clase_origen, r.id_clase_destino


def _multiplicidad_del_extremo(r: RelacionEfectiva, id_clase: str) -> str | None:
    return r.multiplicidad_origen if id_clase == r.id_clase_origen else r.multiplicidad_destino


@dataclass
class NombresRelacion:
    """Nombre de campo ya desambiguado de cada lado de una relación efectiva:
    `dueño` en la clase con la FK (o el dueño JPA de un N:M), `inverso` en
    la otra. Compartido con el generador Flutter: la clave JSON tiene que
    numerarse igual en backend y app."""

    dueño: str
    inverso: str


def resolver_nombres_relaciones(
    clases: list[ClaseUml], relaciones: list[Relacion] | list[RelacionEfectiva]
) -> dict[str, NombresRelacion]:
    """Acepta relaciones crudas (se expanden) o ya efectivas. Orden estable
    por id: CU08 y CU15 numeran siempre igual."""
    efectivas = (
        relaciones
        if relaciones and isinstance(relaciones[0], RelacionEfectiva)
        else relaciones_efectivas(clases, relaciones)  # type: ignore[arg-type]
    )
    clases_por_id = {c.id: c for c in clases}
    usados: dict[str, set[str]] = {
        c.id: {nombre_campo_java(a.nombre) for a in c.atributos} | {"id"} for c in clases
    }
    resultado: dict[str, NombresRelacion] = {}
    for r in sorted(efectivas, key=lambda r: r.id):
        origen, destino = clases_por_id[r.id_clase_origen], clases_por_id[r.id_clase_destino]
        lados = lado_con_fk(r)
        if lados is None:  # N:M: dueño = origen
            dueño = _nombre_unico(usados[origen.id], campo_plural(destino.nombre))
            inverso = _nombre_unico(usados[destino.id], campo_plural(origen.nombre))
        else:
            con_fk, ref = clases_por_id[lados[0]], clases_por_id[lados[1]]
            dueño = _nombre_unico(usados[con_fk.id], nombre_campo_java(ref.nombre))
            inverso_lista = es_plural(_multiplicidad_del_extremo(r, con_fk.id))
            base_inverso = campo_plural(con_fk.nombre) if inverso_lista else nombre_campo_java(con_fk.nombre)
            inverso = _nombre_unico(usados[ref.id], base_inverso)
        resultado[r.id] = NombresRelacion(dueño=dueño, inverso=inverso)
    return resultado


def resolver_herencia(clases: list[ClaseUml], relaciones: list[Relacion]) -> tuple[dict[str, str], list[str]]:
    """{id_hijo: id_padre} (origen = subclase, destino = superclase) y avisos."""
    ids = {c.id for c in clases}
    nombres = {c.id: c.nombre for c in clases}
    padres: dict[str, str] = {}
    avisos: list[str] = []

    def ancestros(i: str) -> set[str]:
        vistos: set[str] = set()
        while i in padres and padres[i] not in vistos:
            i = padres[i]
            vistos.add(i)
        return vistos

    for r in sorted(relaciones, key=lambda r: r.id):
        if r.tipo != TipoRelacion.HERENCIA:
            continue
        hijo, padre = r.id_clase_origen, r.id_clase_destino
        if hijo not in ids or padre not in ids or hijo == padre:
            continue
        if hijo in padres:
            avisos.append(
                f"{nombres[hijo]} hereda de más de una clase; se usó {nombres[padres[hijo]]} "
                f"(JPA no admite herencia múltiple), se ignoró {nombres[padre]}"
            )
            continue
        if hijo in ancestros(padre) or padre == hijo:
            avisos.append(f"Ciclo de herencia entre {nombres[hijo]} y {nombres[padre]}: se ignoró")
            continue
        padres[hijo] = padre
    return padres, avisos


# ---------------------------------------------------------------------------
# Modelo completo
# ---------------------------------------------------------------------------


@dataclass
class Columna:
    nombre_campo: str
    columna: str
    tipo_uml: str | None
    tipo_java: str
    tipo_sql: str
    aviso: str | None = None


@dataclass
class ClaveForanea:
    relacion_id: str
    id_entidad: str  # clase que guarda la FK
    id_referida: str
    campo: str
    columna: str
    unica: bool
    obligatoria: bool
    on_delete: str  # CASCADE | SET NULL | RESTRICT
    campo_inverso: str
    inverso_lista: bool
    composicion: bool
    de_asociacion: str | None = None


@dataclass
class MuchosAMuchos:
    relacion_id: str
    id_dueño: str
    id_inverso: str
    campo_dueño: str  # Set<Inverso> en el dueño (solo sin clase de asociación)
    campo_inverso: str
    segmento_dueño: str  # /api/{dueño}/{id}/{segmento_dueño}/{inversoId}
    segmento_inverso: str  # /api/{inverso}/{id}/{segmento_inverso}/{dueñoId}
    tabla: str | None = None  # tabla intermedia (sin clase de asociación)
    columna_dueño: str | None = None
    columna_inverso: str | None = None
    id_asociacion: str | None = None  # clase de asociación, si la hay
    fk_asociacion_dueño: ClaveForanea | None = None
    fk_asociacion_inverso: ClaveForanea | None = None


@dataclass
class Entidad:
    clase: ClaseUml
    nombre_java: str
    tabla: str
    ruta: str
    abstracta: bool
    atributos: list[Columna] = field(default_factory=list)
    id_padre: str | None = None
    ids_hijos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


@dataclass
class ModeloRelacional:
    entidades: dict[str, Entidad]
    claves: list[ClaveForanea]
    muchos_a_muchos: list[MuchosAMuchos]
    avisos: list[str]

    # -- consultas de conveniencia ------------------------------------------------

    def ordenadas(self) -> list[Entidad]:
        return sorted(self.entidades.values(), key=lambda e: e.nombre_java.lower())

    def ancestros(self, id_clase: str) -> list[Entidad]:
        """Del padre inmediato hacia la raíz."""
        res = []
        e = self.entidades[id_clase]
        while e.id_padre:
            e = self.entidades[e.id_padre]
            res.append(e)
        return res

    def raiz(self, id_clase: str) -> Entidad:
        cadena = self.ancestros(id_clase)
        return cadena[-1] if cadena else self.entidades[id_clase]

    def atributos_totales(self, id_clase: str) -> list[Columna]:
        """Atributos heredados (de la raíz hacia abajo) + propios."""
        cadena = [*reversed(self.ancestros(id_clase)), self.entidades[id_clase]]
        return [a for e in cadena for a in e.atributos]

    def claves_de(self, id_clase: str, heredadas: bool = False) -> list[ClaveForanea]:
        ids = {id_clase} | ({a.clase.id for a in self.ancestros(id_clase)} if heredadas else set())
        return [k for k in self.claves if k.id_entidad in ids]

    def claves_hacia(self, id_clase: str) -> list[ClaveForanea]:
        return [k for k in self.claves if k.id_referida == id_clase]

    def mn_de(self, id_clase: str) -> list[MuchosAMuchos]:
        return [m for m in self.muchos_a_muchos if id_clase in (m.id_dueño, m.id_inverso)]

    def descendientes_concretos(self, id_clase: str) -> list[Entidad]:
        res = []
        for e in self.entidades.values():
            if e.abstracta:
                continue
            if e.clase.id == id_clase or id_clase in {a.clase.id for a in self.ancestros(e.clase.id)}:
                res.append(e)
        return sorted(res, key=lambda e: (e.clase.id != id_clase, e.nombre_java))

    def orden_creacion(self) -> list[Entidad]:
        """Orden topológico: primero las referenciadas por FK obligatoria (y
        los padres de herencia). Los ciclos caen al orden alfabético."""
        dependencias: dict[str, set[str]] = {i: set() for i in self.entidades}
        for k in self.claves:
            if k.id_entidad != k.id_referida:
                for hijo in self._con_descendientes(k.id_entidad):
                    dependencias[hijo].add(k.id_referida)
        resueltos: list[Entidad] = []
        hechos: set[str] = set()
        restantes = self.ordenadas()
        while restantes:
            listos = [
                e
                for e in restantes
                if all(d in hechos or self._satisfecha_por_descendiente(d, hechos) for d in dependencias[e.clase.id])
            ]
            if not listos:
                listos = [restantes[0]]
            resueltos.extend(listos)
            hechos.update(e.clase.id for e in listos)
            restantes = [e for e in restantes if e not in listos]
        return resueltos

    def _con_descendientes(self, id_clase: str) -> list[str]:
        return [e.clase.id for e in self.entidades.values() if e.clase.id == id_clase or id_clase in {a.clase.id for a in self.ancestros(e.clase.id)}]

    def _satisfecha_por_descendiente(self, id_clase: str, hechos: set[str]) -> bool:
        return any(i in hechos for i in self._con_descendientes(id_clase))


def construir_modelo(clases: list[ClaseUml], relaciones: list[Relacion]) -> ModeloRelacional:
    avisos: list[str] = []
    padres, avisos_herencia = resolver_herencia(clases, relaciones)
    avisos.extend(avisos_herencia)

    entidades: dict[str, Entidad] = {}
    for c in clases:
        nombre_java = nombre_clase_java(c.nombre)
        entidades[c.id] = Entidad(
            clase=c,
            nombre_java=nombre_java,
            tabla=identificador_sql(a_snake_case(pluralizar(nombre_java))),
            ruta=ruta_api_clase(nombre_java),
            abstracta=bool(c.es_abstracta),
            id_padre=padres.get(c.id),
        )
    for hijo, padre in padres.items():
        entidades[padre].ids_hijos.append(hijo)

    # -- atributos (el "id" del diagrama lo cubre el @Id autogenerado; un
    #    atributo que repite uno heredado se omite: Java no admite dos campos
    #    con el mismo nombre en la jerarquía con getters/setters distintos).
    def nombres_heredados(id_clase: str) -> set[str]:
        res: set[str] = set()
        i = padres.get(id_clase)
        visitados: set[str] = set()
        while i and i not in visitados:
            visitados.add(i)
            res |= {nombre_campo_java(a.nombre) for a in entidades[i].clase.atributos}
            i = padres.get(i)
        return res

    for e in entidades.values():
        heredados = nombres_heredados(e.clase.id)
        vistos: set[str] = set()
        for a in sorted(e.clase.atributos, key=lambda a: a.orden):
            campo = nombre_campo_java(a.nombre)
            if campo.lower() == "id" or campo in vistos:
                continue
            if campo in heredados:
                e.avisos.append(f'atributo "{a.nombre}" ya existe en una superclase, se omitió')
                continue
            vistos.add(campo)
            tipo_java = mapear_tipo_java(a.tipo)
            e.atributos.append(
                Columna(
                    nombre_campo=campo,
                    columna=identificador_sql(a_snake_case(campo)),
                    tipo_uml=a.tipo,
                    tipo_java=tipo_java,
                    tipo_sql=tipo_sql(tipo_java),
                    aviso=(
                        f'tipo UML "{a.tipo}" no reconocido, se usó String por defecto'
                        if tipo_no_reconocido(a.tipo)
                        else None
                    ),
                )
            )

    # -- relaciones
    efectivas = relaciones_efectivas(clases, relaciones)
    nombres = resolver_nombres_relaciones(clases, efectivas)
    claves: list[ClaveForanea] = []
    claves_por_relacion: dict[str, ClaveForanea] = {}
    mn: list[MuchosAMuchos] = []
    segmentos_usados: dict[str, set[str]] = {i: set() for i in entidades}
    tablas_usadas = {e.tabla for e in entidades.values()}

    for r in efectivas:
        n = nombres[r.id]
        lados = lado_con_fk(r)
        if lados is None:
            dueño, inverso = entidades[r.id_clase_origen], entidades[r.id_clase_destino]
            base = sorted([dueño.tabla, inverso.tabla])
            original = next((x for x in relaciones if x.id == r.id), None)
            tabla = getattr(original, "tabla_intermedia", None) or identificador_sql(f"{base[0]}_{base[1]}")
            tabla = _nombre_unico(tablas_usadas, tabla)
            col_d = a_snake_case(dueño.nombre_java) + "_id"
            col_i = a_snake_case(inverso.nombre_java) + "_id"
            if col_i == col_d:
                col_i = col_i[:-3] + "_2_id"
            mn.append(
                MuchosAMuchos(
                    relacion_id=r.id,
                    id_dueño=dueño.clase.id,
                    id_inverso=inverso.clase.id,
                    campo_dueño=n.dueño,
                    campo_inverso=n.inverso,
                    segmento_dueño=_nombre_unico(segmentos_usados[dueño.clase.id], inverso.ruta),
                    segmento_inverso=_nombre_unico(segmentos_usados[inverso.clase.id], dueño.ruta),
                    tabla=tabla,
                    columna_dueño=col_d,
                    columna_inverso=col_i,
                )
            )
            continue

        id_fk, id_ref = lados
        mult_ref = _multiplicidad_del_extremo(r, id_ref)
        es_agregacion = r.tipo == TipoRelacion.AGREGACION
        es_composicion = r.tipo == TipoRelacion.COMPOSICION
        obligatoria = (mult_ref == "1" and not es_agregacion) or r.de_asociacion is not None
        clave = ClaveForanea(
            relacion_id=r.id,
            id_entidad=id_fk,
            id_referida=id_ref,
            campo=n.dueño,
            columna=identificador_sql(a_snake_case(n.dueño) + "_id"),
            unica=not es_plural(_multiplicidad_del_extremo(r, id_fk)),
            obligatoria=obligatoria,
            on_delete="CASCADE" if es_composicion else ("SET NULL" if es_agregacion else "RESTRICT"),
            campo_inverso=n.inverso,
            inverso_lista=es_plural(_multiplicidad_del_extremo(r, id_fk)),
            composicion=es_composicion,
            de_asociacion=r.de_asociacion,
        )
        claves.append(clave)
        claves_por_relacion[r.id] = clave

    # -- N:M con clase de asociación: rutas de vínculo sobre las dos FKs
    for r in sorted(relaciones, key=lambda r: r.id):
        ca = _clase_asociacion_valida(r, set(entidades))
        if ca is None or r.id_clase_origen not in entidades or r.id_clase_destino not in entidades:
            continue
        dueño, inverso = entidades[r.id_clase_origen], entidades[r.id_clase_destino]
        fk_a, fk_b = claves_por_relacion[f"{r.id}#a"], claves_por_relacion[f"{r.id}#b"]
        mn.append(
            MuchosAMuchos(
                relacion_id=r.id,
                id_dueño=dueño.clase.id,
                id_inverso=inverso.clase.id,
                campo_dueño=fk_a.campo_inverso,
                campo_inverso=fk_b.campo_inverso,
                segmento_dueño=_nombre_unico(segmentos_usados[dueño.clase.id], inverso.ruta),
                segmento_inverso=_nombre_unico(segmentos_usados[inverso.clase.id], dueño.ruta),
                id_asociacion=ca,
                fk_asociacion_dueño=fk_a,
                fk_asociacion_inverso=fk_b,
            )
        )

    # -- un atributo que choca con una columna FK de la misma tabla se omite
    for k in claves:
        e = entidades[k.id_entidad]
        antes = len(e.atributos)
        e.atributos = [a for a in e.atributos if a.columna != k.columna]
        if len(e.atributos) != antes:
            e.avisos.append(f'columna "{k.columna}" la define la relación; se omitió el atributo homónimo')

    return ModeloRelacional(entidades=entidades, claves=claves, muchos_a_muchos=mn, avisos=avisos)
