from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.metodo import Metodo
from app.models.relacion import Relacion, TipoRelacion


def _crear_diagrama_simple(db_session, proyecto):
    persona = ClaseUml(id="persona-id", id_proyecto=proyecto.id, nombre="Persona", es_abstracta=False, pos_x=0, pos_y=0)
    persona.atributos = [
        Atributo(id="attr-nombre", nombre="nombre", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    persona.metodos = [
        Metodo(id="met-saludar", nombre="saludar", tipo_retorno="void", visibilidad=VisibilidadMiembro.PUBLICO, orden=0)
    ]
    direccion = ClaseUml(id="direccion-id", id_proyecto=proyecto.id, nombre="Direccion", es_abstracta=False, pos_x=0, pos_y=0)
    direccion.atributos = [
        Atributo(id="attr-ciudad", nombre="ciudad", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    db_session.add(persona)
    db_session.add(direccion)
    db_session.commit()

    relacion = Relacion(
        id="rel-1",
        id_proyecto=proyecto.id,
        id_clase_origen=persona.id,
        id_clase_destino=direccion.id,
        tipo=TipoRelacion.ASOCIACION,
        multiplicidad_origen="1",
        multiplicidad_destino="0..*",
    )
    db_session.add(relacion)
    db_session.commit()


def test_reporte_proyecto_vacio_da_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "pdf"}, headers=headers(admin))
    assert resp.status_code == 400
    assert "no tiene contenido disponible" in resp.json()["detail"]


def test_reporte_con_clases_genera_pdf(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_simple(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", params={"formato": "pdf"}, headers=headers(admin))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert len(resp.content) > 0
    assert resp.content.startswith(b"%PDF")


def test_reporte_default_formato_pdf(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_simple(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", headers=headers(admin))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_reporte_colaborador_no_dueno_recibe_403(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    admin = crear_usuario()
    colaborador = crear_usuario()
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)
    _crear_diagrama_simple(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", headers=headers(colaborador))
    assert resp.status_code == 403


def test_reporte_usuario_sin_acceso_recibe_403(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    ajeno = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_simple(db_session, proyecto)

    resp = client.get(f"/proyectos/{proyecto.id}/reporte", headers=headers(ajeno))
    assert resp.status_code == 403
