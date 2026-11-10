"""Segundo parcial — `apply_diagram_mutations`: lotes atómicos con tempId."""

import pytest

from app.schemas.diagrama import AtributoIO, ClaseIO, DiagramaIO, RelacionIO
from app.services.ai.gemini_client import esquema_gemini
from app.services.mutaciones import (
    ESQUEMA_HERRAMIENTA,
    MutacionInvalidaError,
    _alto,
    aplicar_mutaciones,
    posicion_libre,
)


def _diagrama():
    return DiagramaIO(
        clases=[
            ClaseIO(id="f", nombre="Factura", pos_x=0, pos_y=0, atributos=[AtributoIO(id="a1", nombre="numero", tipo="int")]),
            ClaseIO(id="c", nombre="Cliente", pos_x=260, pos_y=0),
        ],
        relaciones=[
            RelacionIO(id="r1", id_clase_origen="c", id_clase_destino="f", tipo="ASOCIACION",
                       multiplicidad_origen="1", multiplicidad_destino="0..*")
        ],
    )


def test_temp_id_permite_relacionar_lo_creado_en_el_mismo_lote():
    r = aplicar_mutaciones(
        _diagrama(),
        [
            {"action": "ADD_ENTITY", "tempId": "t1", "entityData": {"name": "detalle factura",
             "attributes": [{"name": "cantidad", "type": "integer"}, {"name": "precio", "type": "numeric"}]}},
            {"action": "ADD_RELATIONSHIP", "tempId": "tr", "relationshipData": {
                "sourceId": "Factura", "targetId": "t1", "type": "composition",
                "sourceCardinality": "1", "targetCardinality": "1..*"}},
        ],
    )
    detalle = next(c for c in r.diagrama.clases if c.nombre == "DetalleFactura")
    assert [(a.nombre, a.tipo) for a in detalle.atributos] == [("cantidad", "int"), ("precio", "decimal")]
    rel = r.diagrama.relaciones[-1]
    assert (rel.id_clase_origen, rel.id_clase_destino) == ("f", detalle.id)
    assert detalle.id != "t1"  # el tempId nunca se usa como id real
    assert len(r.resumen) == 2


def test_lote_atomico_si_una_accion_falla_no_cambia_nada():
    original = _diagrama()
    with pytest.raises(MutacionInvalidaError, match="Acción 2"):
        aplicar_mutaciones(
            original,
            [
                {"action": "ADD_ENTITY", "entityData": {"name": "Pedido"}},
                {"action": "ADD_ATTRIBUTE", "entityId": "NoExiste", "attributeData": {"name": "x", "type": "int"}},
            ],
        )
    assert [c.nombre for c in original.clases] == ["Factura", "Cliente"]


@pytest.mark.parametrize(
    "accion,mensaje",
    [
        ({"action": "ADD_ATTRIBUTE", "entityId": "Factura", "attributeData": {"name": "x", "type": "blob"}}, "tipo"),
        ({"action": "ADD_RELATIONSHIP", "relationshipData": {"sourceId": "Factura", "targetId": "Cliente",
          "type": "association", "sourceCardinality": "muchos"}}, "cardinalidad"),
        ({"action": "ADD_ENTITY", "entityData": {"name": "factura"}}, "ya existe"),
        ({"action": "ADD_ATTRIBUTE", "entityId": "Factura", "attributeData": {"name": "Numero", "type": "int"}}, "ya tiene"),
        ({"action": "BORRAR_TODO"}, "desconocida"),
    ],
)
def test_validaciones(accion, mensaje):
    with pytest.raises(MutacionInvalidaError, match=mensaje):
        aplicar_mutaciones(_diagrama(), [accion])


def test_seguimiento_por_nombre_e_id():
    r = aplicar_mutaciones(
        _diagrama(),
        [
            {"action": "ADD_ATTRIBUTE", "entityId": "c", "attributeData": {"name": "telefono", "type": "String"}},
            {"action": "UPDATE_ATTRIBUTE", "entityId": "factura", "attributeId": "numero",
             "attributeData": {"type": "long"}},
        ],
    )
    cliente = next(c for c in r.diagrama.clases if c.id == "c")
    assert cliente.atributos[0].nombre == "telefono"
    assert r.diagrama.clases[0].atributos[0].tipo == "long"


def test_borrar_clase_quita_sus_relaciones():
    r = aplicar_mutaciones(_diagrama(), [{"action": "DELETE_ENTITY", "entityId": "Cliente"}])
    assert [c.nombre for c in r.diagrama.clases] == ["Factura"]
    assert r.diagrama.relaciones == []


def test_nm_con_clase_de_asociacion_y_herencia_sin_cardinalidad():
    r = aplicar_mutaciones(
        DiagramaIO(clases=[ClaseIO(id="e", nombre="Estudiante"), ClaseIO(id="cu", nombre="Curso")]),
        [
            {"action": "ADD_ENTITY", "tempId": "m", "entityData": {"name": "Matricula",
             "attributes": [{"name": "nota", "type": "double"}, {"name": "fecha", "type": "date"}]}},
            {"action": "ADD_RELATIONSHIP", "relationshipData": {"sourceId": "Estudiante", "targetId": "Curso",
             "type": "association", "sourceCardinality": "*", "targetCardinality": "*", "associationClassId": "m"}},
            {"action": "ADD_ENTITY", "tempId": "p", "entityData": {"name": "Persona", "isAbstract": True}},
            {"action": "ADD_RELATIONSHIP", "relationshipData": {"sourceId": "e", "targetId": "p",
             "type": "inheritance", "sourceCardinality": "1", "targetCardinality": "1"}},
        ],
    )
    nm, herencia = r.diagrama.relaciones
    matricula = next(c for c in r.diagrama.clases if c.nombre == "Matricula")
    assert nm.id_clase_asociacion == matricula.id
    assert (nm.multiplicidad_origen, nm.multiplicidad_destino) == ("*", "*")
    assert herencia.tipo.value == "HERENCIA" and herencia.multiplicidad_origen is None


def test_clases_nuevas_no_se_enciman():
    base = _diagrama()
    acciones = [{"action": "ADD_ENTITY", "entityData": {"name": f"Clase{i}",
                 "attributes": [{"name": f"a{j}", "type": "int"} for j in range(i)]}} for i in range(8)]
    clases = aplicar_mutaciones(base, acciones).diagrama.clases
    for i, a in enumerate(clases):
        for b in clases[i + 1:]:
            separadas = (
                a.pos_x + 200 <= b.pos_x or b.pos_x + 200 <= a.pos_x
                or a.pos_y + _alto(a) <= b.pos_y or b.pos_y + _alto(b) <= a.pos_y
            )
            assert separadas, (a.nombre, b.nombre)


def test_posicion_libre_en_lienzo_vacio():
    assert posicion_libre([], 100) == (0.0, 0.0)


def test_esquema_de_la_herramienta_es_valido_para_gemini():
    from google.genai import types

    types.Schema.model_validate(esquema_gemini(ESQUEMA_HERRAMIENTA["function"]["parameters"]))


def test_composicion_al_reves_se_orienta_todo_parte():
    r = aplicar_mutaciones(
        _diagrama(),
        [{"action": "ADD_ENTITY", "tempId": "d", "entityData": {"name": "DetalleFactura"}},
         {"action": "ADD_RELATIONSHIP", "relationshipData": {"sourceId": "d", "targetId": "Factura",
          "type": "composition", "sourceCardinality": "1..*", "targetCardinality": "1"}}],
    )
    rel = r.diagrama.relaciones[-1]
    assert rel.id_clase_origen == "f"  # Factura (el todo) queda como origen
    assert (rel.multiplicidad_origen, rel.multiplicidad_destino) == ("1", "1..*")
