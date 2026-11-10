import io
import zipfile

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion


def _crear_diagrama_persona_direccion(db_session, proyecto):
    """Persona 1 --- 0..* Direccion -- Direccion es "el lado muchos" (dueña
    de la FK), mismo escenario que test_generador_flutter.py."""
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


def _generar(client, proyecto, headers, admin):
    return client.post(
        f"/proyectos/{proyecto.id}/generar-frontend",
        json={"url_base": "http://localhost:8000"},
        headers=headers(admin),
    )


def test_pubspec_declara_dependencias_offline(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    pubspec = zf.read(next(n for n in zf.namelist() if n.endswith("pubspec.yaml"))).decode("utf-8")

    assert "sqflite:" in pubspec
    assert "connectivity_plus:" in pubspec
    assert "path:" in pubspec
    assert "uuid:" in pubspec


def test_db_dart_tiene_create_table_por_clase(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    db_dart = zf.read(next(n for n in zf.namelist() if n.endswith("lib/offline/db.dart"))).decode("utf-8")

    assert "CREATE TABLE persona" in db_dart
    assert "CREATE TABLE direccion" in db_dart
    assert "localId TEXT PRIMARY KEY" in db_dart
    assert "personaLocalId TEXT" in db_dart
    assert "estadoSync TEXT NOT NULL DEFAULT 'sincronizado'" in db_dart


def test_modelo_tiene_campos_offline(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    modelo = zf.read(next(n for n in zf.namelist() if n.endswith("lib/models/direccion.dart"))).decode("utf-8")

    assert "String localId;" in modelo
    assert "String estadoSync;" in modelo
    assert "String? errorSync;" in modelo
    assert "String? personaLocalId;" in modelo
    assert "factory Direccion.fromRow(Map<String, dynamic> fila)" in modelo
    assert "Map<String, dynamic> toRow()" in modelo
    # fromJson/toJson (red) siguen intactos -- CU14 no les tocó una línea.
    assert "int? personaId;" in modelo
    assert "'persona': {'id': personaId}" in modelo


def test_repositorio_existe_con_metodos_esperados(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    repo = zf.read(
        next(n for n in zf.namelist() if n.endswith("lib/offline/direccion_repositorio.dart"))
    ).decode("utf-8")

    assert "class DireccionRepositorio" in repo
    assert "Future<List<Direccion>> listar()" in repo
    assert "Future<void> refrescarDesdeRed()" in repo
    assert "Future<Direccion> crear(Direccion direccion)" in repo
    assert "Future<Direccion> actualizar(Direccion direccion)" in repo
    assert "Future<void> eliminar(String localId)" in repo
    assert "Future<bool> sincronizar()" in repo
    assert "Future<void> reintentar(String localId)" in repo
    assert "Future<void> descartar(String localId)" in repo
    # Resuelve la FK por localId del padre, nunca por su id de backend.
    assert "objeto.personaLocalId != null" in repo
    assert "objeto.personaId = filasPadre.first['id'] as int;" in repo


def test_orden_topologico_en_sync_manager(client, crear_usuario, crear_proyecto, headers, db_session):
    """Direccion depende de Persona (dueña de la FK) -- el sync de Persona
    tiene que llamarse antes que el de Direccion en sync_manager.dart."""
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    sync_manager = zf.read(
        next(n for n in zf.namelist() if n.endswith("lib/offline/sync_manager.dart"))
    ).decode("utf-8")

    assert "personaRepositorio.sincronizar()" in sync_manager
    assert "direccionRepositorio.sincronizar()" in sync_manager
    assert sync_manager.index("personaRepositorio.sincronizar()") < sync_manager.index(
        "direccionRepositorio.sincronizar()"
    )


def test_list_screen_muestra_indicador_de_estado(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    list_screen = zf.read(
        next(n for n in zf.namelist() if n.endswith("lib/screens/direccion_list_screen.dart"))
    ).decode("utf-8")

    assert "DireccionRepositorio _repositorio = DireccionRepositorio();" in list_screen
    assert "_repositorio.refrescarDesdeRed()" in list_screen
    assert "SyncManager.sincronizarTodo()" in list_screen
    assert "item.estadoSync" in list_screen


def test_sincronizacion_screen_existe_con_reintentar_y_descartar(
    client, crear_usuario, crear_proyecto, headers, db_session
):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    pantalla = zf.read(
        next(n for n in zf.namelist() if n.endswith("lib/screens/sincronizacion_screen.dart"))
    ).decode("utf-8")

    assert "class SincronizacionScreen" in pantalla
    assert "Reintentar" in pantalla
    assert "Descartar" in pantalla
    assert "_personaRepositorio" in pantalla
    assert "_direccionRepositorio" in pantalla


def test_main_inicializa_db_y_conectividad(client, crear_usuario, crear_proyecto, headers, db_session):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    _crear_diagrama_persona_direccion(db_session, proyecto)

    resp = _generar(client, proyecto, headers, admin)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    main_dart = zf.read(next(n for n in zf.namelist() if n.endswith("lib/main.dart"))).decode("utf-8")

    assert "WidgetsFlutterBinding.ensureInitialized();" in main_dart
    assert "await OfflineDb.instancia();" in main_dart
    assert "Conectividad.escucharReconexion(" in main_dart
    assert "SincronizacionScreen" in main_dart
