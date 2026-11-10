import io
import re
import zipfile

import pytest

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion
from app.services.generador_spring import mapear_tipo_java


def _crear_diagrama_persona_direccion(db_session, proyecto):
    """2 clases con una relación singular-plural (Persona 1 --- 0..* Direccion)."""
    persona = ClaseUml(id="persona-id", id_proyecto=proyecto.id, nombre="Persona", es_abstracta=False, pos_x=0, pos_y=0)
    persona.atributos = [
        Atributo(id="attr-nombre", nombre="nombre", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
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


def test_generar_backend_con_relacion_singular_plural(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nombres = zf.namelist()

    # Estructura Maven esperada.
    assert any(n.endswith("pom.xml") for n in nombres)
    assert any(n.endswith("src/main/resources/application.properties") for n in nombres)
    assert any(n.endswith("BackendApplication.java") for n in nombres)
    assert any(n.endswith("model/Persona.java") for n in nombres)
    assert any(n.endswith("model/Direccion.java") for n in nombres)
    assert any(n.endswith("repository/PersonaRepository.java") for n in nombres)
    assert any(n.endswith("repository/DireccionRepository.java") for n in nombres)
    assert any(n.endswith("service/PersonaService.java") for n in nombres)
    assert any(n.endswith("service/DireccionService.java") for n in nombres)
    assert any(n.endswith("controller/PersonaController.java") for n in nombres)
    assert any(n.endswith("controller/DireccionController.java") for n in nombres)

    # Direccion es el lado "muchos" -> dueño de la FK -> @ManyToOne hacia Persona.
    direccion_java = next(n for n in nombres if n.endswith("model/Direccion.java"))
    contenido_direccion = zf.read(direccion_java).decode("utf-8")
    assert "@ManyToOne" in contenido_direccion
    assert '@JoinColumn(name = "persona_id")' in contenido_direccion
    assert "private Persona persona;" in contenido_direccion

    # Persona es el lado "uno" -> inverso, @OneToMany(mappedBy = "persona").
    persona_java = next(n for n in nombres if n.endswith("model/Persona.java"))
    contenido_persona = zf.read(persona_java).decode("utf-8")
    assert '@OneToMany(mappedBy = "persona")' in contenido_persona
    assert "private List<Direccion> direccionList;" in contenido_persona

    # El endpoint del controller REST sigue /api/{plural minúscula}.
    controller_direccion = next(n for n in nombres if n.endswith("controller/DireccionController.java"))
    contenido_controller = zf.read(controller_direccion).decode("utf-8")
    assert '@RequestMapping("/api/direcciones")' in contenido_controller


def test_etiqueta_de_relacion_no_se_usa_como_nombre_de_campo(client, crear_usuario, crear_proyecto, headers, db_session):
    """Regresión: con `etiqueta` seteada, el campo/columna de la relación
    debía seguir nombrándose según la clase destino real (ej. "persona" /
    "persona_id" en Direccion), no según la etiqueta (ej. "direcciones")."""
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    persona = ClaseUml(id="persona-id", id_proyecto=proyecto.id, nombre="Persona", es_abstracta=False, pos_x=0, pos_y=0)
    direccion = ClaseUml(id="direccion-id", id_proyecto=proyecto.id, nombre="Direccion", es_abstracta=False, pos_x=0, pos_y=0)
    db_session.add(persona)
    db_session.add(direccion)
    db_session.commit()

    relacion = Relacion(
        id="rel-1",
        id_proyecto=proyecto.id,
        id_clase_origen=persona.id,
        id_clase_destino=direccion.id,
        tipo=TipoRelacion.ASOCIACION,
        etiqueta="direcciones",  # etiqueta distinta al nombre de cualquiera de las dos clases
        multiplicidad_origen="1",
        multiplicidad_destino="0..*",
    )
    db_session.add(relacion)
    db_session.commit()

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    direccion_java = next(n for n in zf.namelist() if n.endswith("model/Direccion.java"))
    contenido = zf.read(direccion_java).decode("utf-8")

    # El campo y la FK deben nombrarse según la clase destino (Persona), no
    # según la etiqueta ("direcciones") — @Table(name = "direcciones") sí es
    # correcto (nombre de tabla pluralizado de la propia clase Direccion).
    assert "private Persona persona;" in contenido
    assert '@JoinColumn(name = "persona_id")' in contenido
    assert '@JoinColumn(name = "direcciones_id")' not in contenido
    assert "private Persona direcciones;" not in contenido


def test_dos_relaciones_al_mismo_par_de_clases_no_duplican_columna(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    """Regresión: antes, dos relaciones entre el mismo par de clases (ej.
    un sistema de biblioteca con "Miembro presta Libro" y "Miembro reserva
    Libro") generaban el mismo nombre de columna/campo dos veces en la
    misma entidad -- @JoinColumn(name="miembro_id") repetido -- que
    Hibernate rechaza al arrancar. El nombre de columna ahora sale del
    campo ya desambiguado (resolver_nombres_relaciones), no del nombre base
    sin desambiguar."""
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    miembro = ClaseUml(id="miembro-id", id_proyecto=proyecto.id, nombre="Miembro", es_abstracta=False, pos_x=0, pos_y=0)
    libro = ClaseUml(id="libro-id", id_proyecto=proyecto.id, nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    db_session.add(miembro)
    db_session.add(libro)
    db_session.commit()

    for id_rel in ("rel-presta", "rel-reserva"):
        db_session.add(
            Relacion(
                id=id_rel,
                id_proyecto=proyecto.id,
                id_clase_origen=miembro.id,
                id_clase_destino=libro.id,
                tipo=TipoRelacion.ASOCIACION,
                multiplicidad_origen="1",
                multiplicidad_destino="0..*",
            )
        )
    db_session.commit()

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    libro_java = zf.read(next(n for n in zf.namelist() if n.endswith("model/Libro.java"))).decode("utf-8")

    assert libro_java.count('@JoinColumn(name = "miembro_id")') == 1
    assert '@JoinColumn(name = "miembro2_id")' in libro_java
    assert "private Miembro miembro;" in libro_java
    assert "private Miembro miembro2;" in libro_java


# --------------------------------------------------------------------------
# Backend generado listo para probar sin configuración manual: H2 por
# defecto, README con instrucciones, CORS abierto para desarrollo.
# --------------------------------------------------------------------------


def test_generar_backend_usa_h2_sin_placeholders_activos(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    props_path = next(n for n in zf.namelist() if n.endswith("application.properties"))
    contenido = zf.read(props_path).decode("utf-8")

    assert "jdbc:h2:mem:" in contenido
    assert "spring.datasource.username=sa" in contenido

    # Ninguna línea ACTIVA (no comentada) debe seguir pidiendo completar
    # placeholders de Postgres -- solo puede aparecer dentro del bloque
    # comentado de ejemplo para quien quiera cambiar a Postgres.
    lineas_activas = [l for l in contenido.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert not any("CAMBIAR_" in l for l in lineas_activas)

    pom_path = next(n for n in zf.namelist() if n.endswith("pom.xml"))
    contenido_pom = zf.read(pom_path).decode("utf-8")
    assert "<artifactId>h2</artifactId>" in contenido_pom
    assert "<artifactId>postgresql</artifactId>" in contenido_pom  # se mantiene disponible


def test_generar_backend_incluye_readme_con_endpoints(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    readme_path = next(n for n in zf.namelist() if n.endswith("README.md"))
    contenido = zf.read(readme_path).decode("utf-8")

    assert "mvn spring-boot:run" in contenido
    assert "Java 17" in contenido
    assert "8080" in contenido
    assert "/api/personas" in contenido
    assert "/api/direcciones" in contenido
    assert "JWT" in contenido
    assert "CORS" in contenido


def test_generar_backend_incluye_cors_config_valido(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    cors_path = next(n for n in zf.namelist() if n.endswith("config/CorsConfig.java"))
    contenido = zf.read(cors_path).decode("utf-8")

    assert "@Configuration" in contenido
    assert "implements WebMvcConfigurer" in contenido
    assert 'addMapping("/api/**")' in contenido
    assert contenido.count("{") == contenido.count("}")


def test_generar_backend_sin_clases_devuelve_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)  # sin clases en el diagrama

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 400
    assert "no tiene clases" in resp.json()["detail"]


def test_generar_backend_requiere_acceso(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    otro = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(otro))
    assert resp.status_code == 403


def test_generar_backend_composicion_agrega_cascade_y_orphan_removal_en_el_padre(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    pedido = ClaseUml(id="pedido-id", id_proyecto=proyecto.id, nombre="Pedido", es_abstracta=False, pos_x=0, pos_y=0)
    item = ClaseUml(id="item-id", id_proyecto=proyecto.id, nombre="Item", es_abstracta=False, pos_x=0, pos_y=0)
    db_session.add(pedido)
    db_session.add(item)
    db_session.commit()

    relacion = Relacion(
        id="rel-comp",
        id_proyecto=proyecto.id,
        id_clase_origen=pedido.id,
        id_clase_destino=item.id,
        tipo=TipoRelacion.COMPOSICION,
        multiplicidad_origen="1",
        multiplicidad_destino="0..*",
    )
    db_session.add(relacion)
    db_session.commit()

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    pedido_java = next(n for n in zf.namelist() if n.endswith("model/Pedido.java"))
    contenido_pedido = zf.read(pedido_java).decode("utf-8")
    # cascade + orphanRemoval van en el lado @OneToMany (el "padre" real),
    # no en el @ManyToOne — ver limitación documentada en generador_spring.py.
    assert "cascade = CascadeType.ALL, orphanRemoval = true" in contenido_pedido

    item_java = next(n for n in zf.namelist() if n.endswith("model/Item.java"))
    contenido_item = zf.read(item_java).decode("utf-8")
    assert "orphanRemoval" not in contenido_item


# --------------------------------------------------------------------------
# BUG 1 (crítico): un atributo del diagrama llamado "id" no debe duplicar
# el campo Java del @Id autogenerado.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("nombre_atributo", ["id", "ID", "Id", "iD", " id "])
def test_atributo_llamado_id_no_duplica_el_campo_autogenerado(
    client, crear_usuario, crear_proyecto, headers, db_session, nombre_atributo
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    libro = ClaseUml(id="libro-id", id_proyecto=proyecto.id, nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    libro.atributos = [
        Atributo(id="attr-id", nombre=nombre_atributo, tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0),
        Atributo(id="attr-titulo", nombre="titulo", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=1),
    ]
    db_session.add(libro)
    db_session.commit()

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    libro_java = next(n for n in zf.namelist() if n.endswith("model/Libro.java"))
    contenido = zf.read(libro_java).decode("utf-8")

    # Exactamente un campo "id" (el autogenerado) — ninguno más, sea cual
    # sea el tipo Java que hubiera tenido el atributo "id" del diagrama.
    ocurrencias_campo_id = re.findall(r"private \w+(?:<\w+>)? id;", contenido)
    assert len(ocurrencias_campo_id) == 1
    assert "private String id;" not in contenido
    assert contenido.count("@Column") == 1  # solo "titulo"; "id" no generó @Column


# --------------------------------------------------------------------------
# BUG 2: auditoría del mapeo de tipos UML -> Java, uno por uno.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo_uml", "tipo_java_esperado"),
    [
        ("string", "String"),
        ("str", "String"),
        ("texto", "String"),
        ("char", "String"),
        ("int", "Integer"),
        ("integer", "Integer"),
        ("entero", "Integer"),
        ("long", "Long"),
        ("float", "Double"),
        ("double", "Double"),
        ("decimal", "BigDecimal"),
        ("bigdecimal", "BigDecimal"),
        ("boolean", "Boolean"),
        ("bool", "Boolean"),
        ("date", "LocalDate"),
        ("fecha", "LocalDate"),
        ("datetime", "LocalDateTime"),
        ("fechahora", "LocalDateTime"),
        ("timestamp", "LocalDateTime"),
        ("uuid", "UUID"),
        # Mayúsculas / espacios no deberían importar.
        ("STRING", "String"),
        ("  Boolean  ", "Boolean"),
        # Sin tipo especificado -> default String (comportamiento esperado, no un bug).
        (None, "String"),
        ("", "String"),
        # Tipo no reconocido -> también cae a String (ver test de aviso abajo).
        ("un-tipo-inventado", "String"),
    ],
)
def test_mapeo_de_tipos_uml_a_java(tipo_uml, tipo_java_esperado):
    assert mapear_tipo_java(tipo_uml) == tipo_java_esperado


def test_tipo_no_reconocido_deja_comentario_visible_en_vez_de_fallar_en_silencio(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    libro = ClaseUml(id="libro-id", id_proyecto=proyecto.id, nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    libro.atributos = [
        Atributo(
            id="attr-raro",
            nombre="paginas",
            tipo="numerico-raro",
            visibilidad=VisibilidadMiembro.PRIVADO,
            orden=0,
        )
    ]
    db_session.add(libro)
    db_session.commit()

    resp = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    libro_java = next(n for n in zf.namelist() if n.endswith("model/Libro.java"))
    contenido = zf.read(libro_java).decode("utf-8")

    assert 'tipo UML "numerico-raro" no reconocido' in contenido
    assert "private String paginas;" in contenido
