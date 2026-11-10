from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion
from app.services.generador_xmi import generar_xmi_reporte


def _crear_diagrama_biblioteca(db_session, proyecto):
    """Mismo diagrama con las 4 relaciones que test_generador_xmi.py."""
    persona = ClaseUml(id="persona-id", id_proyecto=proyecto.id, nombre="Persona", es_abstracta=True, pos_x=0, pos_y=0)
    persona.atributos = [
        Atributo(id="attr-nombre", nombre="nombre", tipo="String", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    miembro = ClaseUml(id="miembro-id", id_proyecto=proyecto.id, nombre="Miembro", es_abstracta=False, pos_x=0, pos_y=0)
    libro = ClaseUml(id="libro-id", id_proyecto=proyecto.id, nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    ejemplar = ClaseUml(id="ejemplar-id", id_proyecto=proyecto.id, nombre="Ejemplar", es_abstracta=False, pos_x=0, pos_y=0)

    for c in (persona, miembro, libro, ejemplar):
        db_session.add(c)
    db_session.commit()

    relaciones = [
        Relacion(id="rel-h", id_proyecto=proyecto.id, id_clase_origen=miembro.id, id_clase_destino=persona.id, tipo=TipoRelacion.HERENCIA),
        Relacion(
            id="rel-a",
            id_proyecto=proyecto.id,
            id_clase_origen=miembro.id,
            id_clase_destino=libro.id,
            tipo=TipoRelacion.ASOCIACION,
            etiqueta="presta",
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        ),
        Relacion(
            id="rel-c",
            id_proyecto=proyecto.id,
            id_clase_origen=libro.id,
            id_clase_destino=ejemplar.id,
            tipo=TipoRelacion.COMPOSICION,
            multiplicidad_origen="1",
            multiplicidad_destino="1..*",
        ),
    ]
    for r in relaciones:
        db_session.add(r)
    db_session.commit()

    proyecto_obj = type("_", (), {})()  # el generador solo lee .nombre
    proyecto_obj.nombre = proyecto.nombre
    return generar_xmi_reporte(proyecto_obj, [persona, miembro, libro, ejemplar], relaciones)


def _subir(client, proyecto_id, contenido, headers, nombre_archivo="diagrama.xmi"):
    return client.post(
        f"/proyectos/{proyecto_id}/diagrama/importar-xmi",
        files={"archivo": (nombre_archivo, contenido, "application/xml")},
        headers=headers,
    )


def test_importar_xmi_round_trip_sobre_proyecto_vacio(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto_origen = crear_proyecto(admin, nombre="Origen")
    xmi_bytes = _crear_diagrama_biblioteca(db_session, proyecto_origen)

    proyecto_destino = crear_proyecto(admin, nombre="Destino vacío")
    resp = _subir(client, proyecto_destino.id, xmi_bytes, headers(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["advertencias"] == []

    diagrama = body["diagrama"]
    assert {c["nombre"] for c in diagrama["clases"]} == {"Persona", "Miembro", "Libro", "Ejemplar"}
    tipos_relacion = sorted(r["tipo"] for r in diagrama["relaciones"])
    assert tipos_relacion == ["ASOCIACION", "COMPOSICION", "HERENCIA"]

    # Confirma que también quedó persistido de verdad (no solo en la respuesta).
    resp_get = client.get(f"/proyectos/{proyecto_destino.id}/diagrama", headers=headers(admin))
    assert resp_get.status_code == 200
    assert len(resp_get.json()["clases"]) == 4


def test_importar_xmi_sobre_proyecto_con_clases_da_409(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto_origen = crear_proyecto(admin, nombre="Origen")
    xmi_bytes = _crear_diagrama_biblioteca(db_session, proyecto_origen)

    # proyecto_origen ya tiene clases -- justamente el que no debería aceptar import.
    resp = _subir(client, proyecto_origen.id, xmi_bytes, headers(admin))
    assert resp.status_code == 409
    assert "ya tiene clases" in resp.json()["detail"]


def test_importar_xml_invalido_da_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    resp = _subir(client, proyecto.id, b"esto no es xml <<<", headers(admin))
    assert resp.status_code == 400
    assert "no es XML válido" in resp.json()["detail"]


def test_importar_xmi_sin_clases_da_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    xml_sin_clases = b'<?xml version="1.0"?><xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"><algo/></xmi:XMI>'
    resp = _subir(client, proyecto.id, xml_sin_clases, headers(admin))
    assert resp.status_code == 400
    assert "ninguna clase" in resp.json()["detail"]


def test_importar_xmi_usuario_sin_acceso_da_403(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    ajeno = crear_usuario()
    proyecto = crear_proyecto(admin)
    resp = _subir(client, proyecto.id, b"<xmi/>", headers(ajeno))
    assert resp.status_code == 403


def test_importar_xmi_colaborador_activo_puede_importar(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    """Mismo criterio que el resto de CU09 (GET/PUT diagrama): dueño o
    colaborador activo, no solo el dueño."""
    admin = crear_usuario()
    colaborador = crear_usuario()
    proyecto_origen = crear_proyecto(admin, nombre="Origen")
    xmi_bytes = _crear_diagrama_biblioteca(db_session, proyecto_origen)

    proyecto_destino = crear_proyecto(admin, nombre="Destino vacío")
    agregar_colaborador(proyecto_destino, colaborador, activo=True)

    resp = _subir(client, proyecto_destino.id, xmi_bytes, headers(colaborador))
    assert resp.status_code == 200


def test_importar_xmi_real_de_enterprise_architect(client, crear_usuario, crear_proyecto, headers):
    """Archivo real exportado por Enterprise Architect: antes daba 409 por
    "nombres de clase duplicados" (EA repite cada clase en su xmi:Extension)."""
    from pathlib import Path

    admin = crear_usuario()
    proyecto = crear_proyecto(admin, nombre="Desde EA")
    contenido = (Path(__file__).parent / "fixtures" / "ea_pedidos.xmi").read_bytes()

    resp = _subir(client, proyecto.id, contenido, headers(admin), nombre_archivo="prueba.xml")
    assert resp.status_code == 200
    body = resp.json()
    assert body["advertencias"] == []
    assert sorted(c["nombre"] for c in body["diagrama"]["clases"]) == ["Cliente", "ItemPedido", "Pedido", "Producto"]
    assert sorted(r["tipo"] for r in body["diagrama"]["relaciones"]) == ["ASOCIACION", "ASOCIACION", "COMPOSICION"]
