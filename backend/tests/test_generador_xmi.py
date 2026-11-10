import xml.etree.ElementTree as ET

import pytest

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion
from app.services.generador_xmi import UML_NS, XMI_NS, mapear_tipo_xmi

XMI = f"{{{XMI_NS}}}"
UML = f"{{{UML_NS}}}"


def _crear_diagrama_biblioteca(db_session, proyecto):
    """4 clases con las 4 relaciones soportadas, una de cada tipo:
    - HERENCIA: Empleado -> Persona (Empleado es la subclase/origen).
    - ASOCIACION: Persona -- Direccion (1 a 0..*).
    - AGREGACION: Departamento o-- Empleado (Departamento es el "todo"/origen).
    - COMPOSICION: Persona *-- Telefono (Persona es el "todo"/origen).
    """
    persona = ClaseUml(id="persona-id", id_proyecto=proyecto.id, nombre="Persona", estereotipo="entity", es_abstracta=False, pos_x=0, pos_y=0)
    persona.atributos = [
        Atributo(id="attr-nombre", nombre="nombre", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0),
        Atributo(id="attr-nacimiento", nombre="fechaNacimiento", tipo="date", visibilidad=VisibilidadMiembro.PROTEGIDO, orden=1),
    ]
    empleado = ClaseUml(id="empleado-id", id_proyecto=proyecto.id, nombre="Empleado", es_abstracta=False, pos_x=0, pos_y=0)
    empleado.atributos = [
        Atributo(id="attr-salario", nombre="salario", tipo="decimal", visibilidad=VisibilidadMiembro.PUBLICO, orden=0)
    ]
    direccion = ClaseUml(id="direccion-id", id_proyecto=proyecto.id, nombre="Direccion", es_abstracta=False, pos_x=0, pos_y=0)
    direccion.atributos = [
        Atributo(id="attr-ciudad", nombre="ciudad", tipo="un-tipo-raro", visibilidad=VisibilidadMiembro.PAQUETE, orden=0)
    ]
    departamento = ClaseUml(id="departamento-id", id_proyecto=proyecto.id, nombre="Departamento", es_abstracta=True, pos_x=0, pos_y=0)
    telefono = ClaseUml(id="telefono-id", id_proyecto=proyecto.id, nombre="Telefono", es_abstracta=False, pos_x=0, pos_y=0)

    for c in (persona, empleado, direccion, departamento, telefono):
        db_session.add(c)
    db_session.commit()

    relaciones = [
        Relacion(
            id="rel-herencia",
            id_proyecto=proyecto.id,
            id_clase_origen=empleado.id,
            id_clase_destino=persona.id,
            tipo=TipoRelacion.HERENCIA,
        ),
        Relacion(
            id="rel-asociacion",
            id_proyecto=proyecto.id,
            id_clase_origen=persona.id,
            id_clase_destino=direccion.id,
            tipo=TipoRelacion.ASOCIACION,
            etiqueta="vive en",
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        ),
        Relacion(
            id="rel-agregacion",
            id_proyecto=proyecto.id,
            id_clase_origen=departamento.id,
            id_clase_destino=empleado.id,
            tipo=TipoRelacion.AGREGACION,
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        ),
        Relacion(
            id="rel-composicion",
            id_proyecto=proyecto.id,
            id_clase_origen=persona.id,
            id_clase_destino=telefono.id,
            tipo=TipoRelacion.COMPOSICION,
            multiplicidad_origen="1",
            multiplicidad_destino="1..*",
        ),
    ]
    for r in relaciones:
        db_session.add(r)
    db_session.commit()


def test_reporte_xmi_es_xml_valido_y_parseable(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_biblioteca(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(admin))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/xml"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith('.xmi"')

    # Debe ser XML bien formado -- si esto no lanza, el archivo es parseable.
    root = ET.fromstring(resp.content)
    assert root.tag == f"{XMI}XMI"
    modelo = root.find(f"{UML}Model")
    assert modelo is not None
    assert modelo.get(f"{XMI}type") == "uml:Model"


def test_reporte_xmi_sin_clases_devuelve_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(admin))
    assert resp.status_code == 400
    assert "no tiene contenido disponible" in resp.json()["detail"]


def test_reporte_xmi_colaborador_no_dueno_recibe_403(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    admin = crear_usuario()
    colaborador = crear_usuario()
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)
    _crear_diagrama_biblioteca(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(colaborador))
    assert resp.status_code == 403


def _clases_por_nombre(modelo: ET.Element) -> dict[str, ET.Element]:
    return {c.get("name"): c for c in modelo.findall("packagedElement") if c.get(f"{XMI}type") == "uml:Class"}


def _asociaciones_por_nombre_extremos(modelo: ET.Element) -> list[ET.Element]:
    return [a for a in modelo.findall("packagedElement") if a.get(f"{XMI}type") == "uml:Association"]


def test_xmi_contiene_los_4_tipos_de_relacion_correctamente(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_biblioteca(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(admin))
    assert resp.status_code == 200
    root = ET.fromstring(resp.content)
    modelo = root.find(f"{UML}Model")

    clases = _clases_por_nombre(modelo)
    assert set(clases) == {"Persona", "Empleado", "Direccion", "Departamento", "Telefono"}
    assert clases["Departamento"].get("isAbstract") == "true"
    assert clases["Persona"].get("isAbstract") is None

    # --- HERENCIA: <generalization> anidada en la subclase (Empleado), no un
    # packagedElement suelto (Generalization no es un PackageableElement).
    generalizaciones_empleado = clases["Empleado"].findall("generalization")
    assert len(generalizaciones_empleado) == 1
    gen = generalizaciones_empleado[0]
    assert gen.get(f"{XMI}type") == "uml:Generalization"
    assert gen.get("general") == clases["Persona"].get(f"{XMI}id")
    # La superclase no debe tener ninguna generalization propia.
    assert clases["Persona"].findall("generalization") == []

    asociaciones = _asociaciones_por_nombre_extremos(modelo)
    assert len(asociaciones) == 3  # asociación + agregación + composición (herencia no cuenta)

    def _extremos(assoc: ET.Element) -> list[ET.Element]:
        return assoc.findall("ownedEnd")

    # --- ASOCIACION Persona 1 -- 0..* Direccion, etiqueta "vive en".
    asoc = next(a for a in asociaciones if a.get("name") == "vive en")
    extremos = _extremos(asoc)
    assert len(extremos) == 2
    extremo_persona = next(e for e in extremos if e.get("type") == clases["Persona"].get(f"{XMI}id"))
    extremo_direccion = next(e for e in extremos if e.get("type") == clases["Direccion"].get(f"{XMI}id"))
    assert extremo_persona.get("aggregation") is None
    assert extremo_direccion.get("aggregation") is None
    assert extremo_persona.find("lowerValue").get("value") == "1"
    assert extremo_persona.find("upperValue").get("value") == "1"
    assert extremo_direccion.find("lowerValue").get("value") == "0"
    assert extremo_direccion.find("upperValue").get("value") == "*"

    # --- AGREGACION Departamento (todo/origen) o-- Empleado (parte/destino):
    # el aggregation="shared" va en el extremo tipado con la clase PARTE.
    asoc_agregacion = next(
        a
        for a in asociaciones
        if {e.get("type") for e in _extremos(a)} == {clases["Departamento"].get(f"{XMI}id"), clases["Empleado"].get(f"{XMI}id")}
    )
    extremo_departamento = next(e for e in _extremos(asoc_agregacion) if e.get("type") == clases["Departamento"].get(f"{XMI}id"))
    extremo_empleado = next(e for e in _extremos(asoc_agregacion) if e.get("type") == clases["Empleado"].get(f"{XMI}id"))
    assert extremo_departamento.get("aggregation") is None
    assert extremo_empleado.get("aggregation") == "shared"

    # --- COMPOSICION Persona (todo/origen) *-- Telefono (parte/destino):
    # el aggregation="composite" va en el extremo tipado con la clase PARTE.
    asoc_composicion = next(
        a
        for a in asociaciones
        if {e.get("type") for e in _extremos(a)} == {clases["Persona"].get(f"{XMI}id"), clases["Telefono"].get(f"{XMI}id")}
    )
    extremo_persona_c = next(e for e in _extremos(asoc_composicion) if e.get("type") == clases["Persona"].get(f"{XMI}id"))
    extremo_telefono = next(e for e in _extremos(asoc_composicion) if e.get("type") == clases["Telefono"].get(f"{XMI}id"))
    assert extremo_persona_c.get("aggregation") is None
    assert extremo_telefono.get("aggregation") == "composite"
    assert extremo_telefono.find("lowerValue").get("value") == "1"
    assert extremo_telefono.find("upperValue").get("value") == "*"


def test_xmi_atributo_con_tipo_no_reconocido_deja_comentario_visible(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_biblioteca(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(admin))
    root = ET.fromstring(resp.content)
    modelo = root.find(f"{UML}Model")
    direccion = _clases_por_nombre(modelo)["Direccion"]

    atributo_ciudad = next(a for a in direccion.findall("ownedAttribute") if a.get("name") == "ciudad")
    tipo = atributo_ciudad.find("type")
    assert tipo.get("href").endswith("#String")  # default seguro, tipo no reconocido

    comentario = atributo_ciudad.find("ownedComment")
    assert comentario is not None
    assert "un-tipo-raro" in comentario.get("body")


def test_xmi_estereotipo_queda_como_comentario_no_como_stereotype_formal(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_biblioteca(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "xmi"}, headers=headers(admin))
    root = ET.fromstring(resp.content)
    modelo = root.find(f"{UML}Model")
    persona = _clases_por_nombre(modelo)["Persona"]

    comentario = persona.find("ownedComment")
    assert comentario is not None
    assert "entity" in comentario.get("body")


@pytest.mark.parametrize(
    ("tipo_uml", "tipo_xmi_esperado"),
    [
        ("string", "String"),
        ("str", "String"),
        ("texto", "String"),
        ("char", "String"),
        ("int", "Integer"),
        ("integer", "Integer"),
        ("entero", "Integer"),
        ("long", "Integer"),
        ("float", "Real"),
        ("double", "Real"),
        ("decimal", "Real"),
        ("bigdecimal", "Real"),
        ("real", "Real"),
        ("boolean", "Boolean"),
        ("bool", "Boolean"),
        # UML2 no tiene primitivo Date/UUID -- ver limitaciones documentadas
        # en el encabezado de generador_xmi.py.
        ("date", "String"),
        ("fecha", "String"),
        ("datetime", "String"),
        ("uuid", "String"),
        ("STRING", "String"),
        ("  Boolean  ", "Boolean"),
        (None, "String"),
        ("", "String"),
        ("un-tipo-inventado", "String"),
    ],
)
def test_mapeo_de_tipos_uml_a_primitivos_xmi(tipo_uml, tipo_xmi_esperado):
    assert mapear_tipo_xmi(tipo_uml) == tipo_xmi_esperado
