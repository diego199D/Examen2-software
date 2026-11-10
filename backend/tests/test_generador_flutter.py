import io
import zipfile

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion


def _crear_diagrama_persona_direccion(db_session, proyecto):
    """2 clases con una relación singular-plural (Persona 1 --- 0..* Direccion)
    — mismo escenario que usa test_generador_spring.py, Direccion es "el lado
    muchos" (cada Direccion pertenece a una sola Persona)."""
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


def test_generar_frontend_con_relacion_singular_plural(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(admin),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nombres = zf.namelist()

    # Estructura mínima de un proyecto Flutter esperada.
    assert any(n.endswith("pubspec.yaml") for n in nombres)
    assert any(n.endswith("lib/config.dart") for n in nombres)
    assert any(n.endswith("lib/main.dart") for n in nombres)
    for archivo in ("persona", "direccion"):
        assert any(n.endswith(f"lib/models/{archivo}.dart") for n in nombres)
        assert any(n.endswith(f"lib/services/{archivo}_service.dart") for n in nombres)
        assert any(n.endswith(f"lib/screens/{archivo}_list_screen.dart") for n in nombres)
        assert any(n.endswith(f"lib/screens/{archivo}_form_screen.dart") for n in nombres)

    # pubspec.yaml declara el paquete http como dependencia.
    pubspec = zf.read(next(n for n in nombres if n.endswith("pubspec.yaml"))).decode("utf-8")
    assert "http:" in pubspec

    # config.dart guarda la URL base en un solo lugar (no hardcodeada en cada servicio).
    config = zf.read(next(n for n in nombres if n.endswith("lib/config.dart"))).decode("utf-8")
    assert "http://localhost:8000" in config

    # Direccion es "el lado muchos" -> tiene el campo de referencia a Persona por id.
    modelo_direccion = zf.read(next(n for n in nombres if n.endswith("lib/models/direccion.dart"))).decode("utf-8")
    assert "int? personaId;" in modelo_direccion
    # El JSON que espera/produce el backend de CU08 anida el objeto (Jackson), no un id plano.
    assert "'persona': {'id': personaId}" in modelo_direccion
    assert "(json['persona'] as Map<String, dynamic>)['id'] as int?" in modelo_direccion

    # Persona (el lado "uno") NO recibe un campo de lista con las direcciones
    # — la ficha de CU15 solo pide el campo de referencia del lado "muchos".
    modelo_persona = zf.read(next(n for n in nombres if n.endswith("lib/models/persona.dart"))).decode("utf-8")
    assert "direccion" not in modelo_persona.lower()

    # El servicio de Direccion apunta a la URL base configurada + la misma
    # convención de ruta que usa el backend Spring Boot generado (CU08).
    servicio_direccion = zf.read(
        next(n for n in nombres if n.endswith("lib/services/direccion_service.dart"))
    ).decode("utf-8")
    assert "${Config.urlBase}/api/direcciones" in servicio_direccion

    # El formulario de Direccion tiene un Dropdown para elegir la Persona,
    # que carga la lista llamando al repositorio de Persona antes de
    # mostrarse (CU14: local-first, funciona offline -- ya no el service
    # de red directo). El Dropdown es <String> keyeado por localId (no
    # <int> por id de backend), porque el padre elegido puede no haber
    # sincronizado todavía.
    form_direccion = zf.read(
        next(n for n in nombres if n.endswith("lib/screens/direccion_form_screen.dart"))
    ).decode("utf-8")
    assert "DropdownButtonFormField<String>" in form_direccion
    assert "_personaRepositorio.listar()" in form_direccion
    assert "PersonaRepositorio _personaRepositorio = PersonaRepositorio();" in form_direccion

    # El formulario de Persona, en cambio, no tiene ningún Dropdown (no
    # referencia a ninguna otra clase).
    form_persona = zf.read(
        next(n for n in nombres if n.endswith("lib/screens/persona_form_screen.dart"))
    ).decode("utf-8")
    assert "DropdownButtonFormField" not in form_persona


def test_generar_frontend_sin_clases_devuelve_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)  # sin clases en el diagrama

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(admin),
    )
    assert resp.status_code == 400
    assert "no tiene contenido disponible para exportar" in resp.json()["detail"]


def test_generar_frontend_colaborador_no_dueno_recibe_403(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    """A diferencia de CU08 (obtener_proyecto_con_acceso: dueño o
    colaborador activo), la ficha de CU15 marca como único actor al
    Administrador -- un colaborador activo, que SÍ puede generar el
    backend, NO puede generar el frontend Flutter."""
    admin = crear_usuario()
    colaborador = crear_usuario()
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(colaborador),
    )
    assert resp.status_code == 403


def test_generar_frontend_usuario_sin_relacion_al_proyecto_recibe_403(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    ajeno = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(ajeno),
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Regresión: más de una relación entre el mismo par de clases (ej. un
# sistema de biblioteca con "Miembro presta Libro" y "Miembro reserva
# Libro") — el nombre de campo/clave JSON de la segunda relación tiene que
# desambiguarse EXACTAMENTE igual en el generador Flutter (CU15) que en el
# de Spring Boot (CU08), porque ambos apuntan a la misma clave JSON.
# --------------------------------------------------------------------------


def _crear_diagrama_miembro_libro_dos_relaciones(db_session, proyecto):
    """Miembro 1 --- 0..* Libro, dos veces ("presta" y "reserva") — Libro es
    "el lado muchos" en ambas, cada una debería generar su propio campo de
    referencia a Miembro (ninguna se puede pisar con la otra)."""
    miembro = ClaseUml(id="miembro-id", id_proyecto=proyecto.id, nombre="Miembro", es_abstracta=False, pos_x=0, pos_y=0)
    miembro.atributos = [
        Atributo(id="attr-nombre-m", nombre="nombre", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    libro = ClaseUml(id="libro-id", id_proyecto=proyecto.id, nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    libro.atributos = [
        Atributo(id="attr-titulo", nombre="titulo", tipo="string", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    db_session.add(miembro)
    db_session.add(libro)
    db_session.commit()

    db_session.add(
        Relacion(
            id="rel-presta",
            id_proyecto=proyecto.id,
            id_clase_origen=miembro.id,
            id_clase_destino=libro.id,
            tipo=TipoRelacion.ASOCIACION,
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        )
    )
    db_session.add(
        Relacion(
            id="rel-reserva",
            id_proyecto=proyecto.id,
            id_clase_origen=miembro.id,
            id_clase_destino=libro.id,
            tipo=TipoRelacion.ASOCIACION,
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        )
    )
    db_session.commit()


def test_dos_relaciones_al_mismo_par_de_clases_no_se_pisan_en_el_modelo_dart(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_miembro_libro_dos_relaciones(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(admin),
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    modelo_libro = zf.read(next(n for n in zf.namelist() if n.endswith("lib/models/libro.dart"))).decode("utf-8")

    # Dos campos de referencia distintos (uno por cada relación), no uno
    # pisando al otro. El sufijo de desambiguación va en el nombre base
    # ("miembro2"), antes de agregarle "Id" -- no "miembroId2".
    assert "int? miembroId;" in modelo_libro
    assert "int? miembro2Id;" in modelo_libro
    assert "'miembro': {'id': miembroId}" in modelo_libro
    assert "'miembro2': {'id': miembro2Id}" in modelo_libro


def test_dos_relaciones_al_mismo_par_de_clases_flutter_coincide_con_spring(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    """El nombre de campo (== clave JSON) que le asigna CU15 a cada relación
    tiene que ser exactamente el mismo que el campo Java que le asigna CU08
    a esa misma relación -- si no, el modelo Dart generado no interopera de
    verdad con el backend Spring Boot generado para este diagrama."""
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_miembro_libro_dos_relaciones(db_session, proyecto)

    resp_backend = client.post(f"/proyectos/{proyecto.id}/generar-backend", headers=headers(admin))
    assert resp_backend.status_code == 200
    resp_frontend = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(admin),
    )
    assert resp_frontend.status_code == 200

    zf_backend = zipfile.ZipFile(io.BytesIO(resp_backend.content))
    libro_java = zf_backend.read(
        next(n for n in zf_backend.namelist() if n.endswith("model/Libro.java"))
    ).decode("utf-8")

    zf_frontend = zipfile.ZipFile(io.BytesIO(resp_frontend.content))
    libro_dart = zf_frontend.read(
        next(n for n in zf_frontend.namelist() if n.endswith("lib/models/libro.dart"))
    ).decode("utf-8")

    # Cada @JoinColumn de Spring nombra la columna a partir del campo YA
    # desambiguado (ver fix en generador_spring.py) -- las dos columnas
    # deben ser distintas (si no, Hibernate no arranca).
    assert "private Miembro miembro;" in libro_java
    assert "private Miembro miembro2;" in libro_java
    assert '@JoinColumn(name = "miembro_id")' in libro_java
    assert '@JoinColumn(name = "miembro2_id")' in libro_java

    # Las mismas dos claves JSON ("miembro" / "miembro2") tienen que
    # aparecer en el modelo Dart, empaquetando/desempaquetando el id.
    assert "'miembro': {'id': miembroId}" in libro_dart
    assert "'miembro2': {'id': miembro2Id}" in libro_dart


# --------------------------------------------------------------------------
# Frontend generado listo para probar sin `flutter create .`: carpeta
# android/ completa, README con instrucciones, solo Android (sin iOS).
# --------------------------------------------------------------------------


def test_generar_frontend_incluye_carpeta_android_lista_para_correr(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8080"},
        headers=headers(admin),
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nombres = zf.namelist()

    esperados = [
        "android/app/build.gradle.kts",
        "android/settings.gradle.kts",
        "android/build.gradle.kts",
        "android/gradle.properties",
        "android/gradle/wrapper/gradle-wrapper.properties",
        "android/gradlew",
        "android/gradlew.bat",
        "android/app/src/main/AndroidManifest.xml",
        "android/app/src/debug/AndroidManifest.xml",
        "android/app/src/profile/AndroidManifest.xml",
        "android/app/src/main/res/values/styles.xml",
        "android/app/src/main/res/values-night/styles.xml",
        "android/app/src/main/res/drawable/launch_background.xml",
        "android/app/src/main/res/drawable-v21/launch_background.xml",
    ]
    for sufijo in esperados:
        assert any(n.endswith(sufijo) for n in nombres), f"falta {sufijo}"

    for densidad in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        assert any(n.endswith(f"mipmap-{densidad}/ic_launcher.png") for n in nombres)

    jar_path = next(n for n in nombres if n.endswith("gradle-wrapper.jar"))
    assert len(zf.read(jar_path)) > 0

    # Alcance explícito: solo Android, nada de iOS/web/desktop.
    assert not any("/ios/" in n or n.startswith("ios/") for n in nombres)
    assert not any("/web/" in n or n.startswith("web/") for n in nombres)


def test_generar_frontend_android_usa_paquete_y_nombre_consistentes(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)
    slug = "".join(ch for ch in proyecto.nombre.lower() if ch.isalnum())
    paquete = f"com.generado.{slug}"

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8080"},
        headers=headers(admin),
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nombres = zf.namelist()

    build_gradle = zf.read(next(n for n in nombres if n.endswith("android/app/build.gradle.kts"))).decode(
        "utf-8"
    )
    assert f'namespace = "{paquete}"' in build_gradle
    assert f'applicationId = "{paquete}"' in build_gradle

    ruta_esperada = f"android/app/src/main/kotlin/{paquete.replace('.', '/')}/MainActivity.kt"
    main_activity_path = next(n for n in nombres if n.endswith(ruta_esperada))
    main_activity = zf.read(main_activity_path).decode("utf-8")
    assert f"package {paquete}" in main_activity

    manifest = zf.read(next(n for n in nombres if n.endswith("android/app/src/main/AndroidManifest.xml"))).decode(
        "utf-8"
    )
    assert f'android:label="{proyecto.nombre}"' in manifest


def test_generar_frontend_incluye_readme(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8080"},
        headers=headers(admin),
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    readme_path = next(n for n in zf.namelist() if n.endswith("README.md"))
    contenido = zf.read(readme_path).decode("utf-8")

    assert "flutter pub get" in contenido
    assert "flutter run" in contenido
    # Menciona explícitamente que es solo Android -- no promete iOS/web.
    assert "Android" in contenido
    assert "no se genera `ios/`" in contenido
