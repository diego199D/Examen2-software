"""Segundo parcial — N:M de punta a punta en los generadores: modelo
relacional, DDL, entidades/rutas Spring, Postman y Flutter. El diagrama de
prueba (`diagrama_completo.py`) cubre herencia, N:M simple, N:M con clase de
asociación, 1:N, composición, agregación y 1:1. La misma salida se verificó
compilando con Maven y corriendo la colección Postman con newman (H2 y
PostgreSQL 17): 92/92 aserciones."""

import io
import json
import re
import zipfile

import pytest

from app.models.relacion import Relacion, TipoRelacion
from app.services.generador_ddl import generar_ddl
from app.services.generador_flutter import generar_zip_frontend
from app.services.generador_postman import generar_coleccion_postman
from app.services.generador_spring import generar_zip_backend
from app.services.modelo_relacional import construir_modelo
from tests.diagrama_completo import _clase, _rel, diagrama_completo


@pytest.fixture
def completo():
    return diagrama_completo()


def _zip(contenido: bytes) -> dict[str, str]:
    zf = zipfile.ZipFile(io.BytesIO(contenido))
    return {n.split("/", 1)[1]: zf.read(n).decode("utf-8", errors="replace") for n in zf.namelist()}


def _java(archivos, ruta_final):
    return next(v for k, v in archivos.items() if k.endswith(ruta_final))


class TestDdl:
    def test_tabla_intermedia_nm(self, completo):
        p, c, r = completo
        ddl = generar_ddl(p.nombre, construir_modelo(c, r))
        # Orden alfabético de tablas, PK compuesta, ambas FKs CASCADE, índice.
        assert 'CREATE TABLE "cursos_estudiantes"' in ddl
        assert 'PRIMARY KEY ("estudiante_id", "curso_id")' in ddl
        assert re.search(r'"cursos_estudiantes".*"estudiante_id"\) REFERENCES "estudiantes".*ON DELETE CASCADE', ddl)
        assert re.search(r'"cursos_estudiantes".*"curso_id"\) REFERENCES "cursos".*ON DELETE CASCADE', ddl)
        assert 'CREATE INDEX "ix_cursos_estudiantes_curso_id"' in ddl

    def test_clase_de_asociacion_es_la_tabla_intermedia(self, completo):
        p, c, r = completo
        ddl = generar_ddl(p.nombre, construir_modelo(c, r))
        assert 'CONSTRAINT "uq_inscripciones_estudiante_id_taller_id" UNIQUE ("estudiante_id", "taller_id")' in ddl
        assert '"estudiante_id" BIGINT NOT NULL' in ddl and '"taller_id" BIGINT NOT NULL' in ddl
        assert "talleres_estudiantes" not in ddl and "estudiantes_talleres" not in ddl

    def test_on_delete_segun_tipo_y_unique_1a1(self, completo):
        p, c, r = completo
        ddl = generar_ddl(p.nombre, construir_modelo(c, r))
        assert '"factura_id") REFERENCES "facturas" ("id") ON DELETE CASCADE' in ddl  # composición
        assert '"equipo_id") REFERENCES "equipos" ("id") ON DELETE SET NULL' in ddl  # agregación
        assert '"equipo_id" BIGINT,' in ddl or '"equipo_id" BIGINT\n' in ddl  # agregación: nullable
        assert '"cliente_id") REFERENCES "clientes" ("id") ON DELETE RESTRICT' in ddl  # asociación
        assert 'UNIQUE ("perfil_id")' in ddl  # 1:1

    def test_herencia_tabla_por_subclase(self, completo):
        p, c, r = completo
        ddl = generar_ddl(p.nombre, construir_modelo(c, r))
        tabla_estudiantes = ddl.split('CREATE TABLE "estudiantes" (')[1].split(");")[0]
        assert '"id" BIGINT PRIMARY KEY' in tabla_estudiantes
        assert "IDENTITY" not in tabla_estudiantes
        assert '"ci"' not in tabla_estudiantes  # el atributo heredado vive en personas
        assert 'FOREIGN KEY ("id") REFERENCES "personas" ("id") ON DELETE CASCADE' in ddl

    def test_nombre_de_tabla_intermedia_elegido_por_el_usuario(self):
        clases = [_clase("a", "Autor"), _clase("l", "Libro")]
        rel = _rel("r", "a", "l", TipoRelacion.ASOCIACION, "*", "*", tabla_intermedia="autoria")
        ddl = generar_ddl("x", construir_modelo(clases, [rel]))
        assert 'CREATE TABLE "autoria"' in ddl

    def test_dos_nm_entre_el_mismo_par_no_chocan(self):
        clases = [_clase("m", "Miembro"), _clase("l", "Libro")]
        rels = [
            _rel("r1", "m", "l", TipoRelacion.ASOCIACION, "0..*", "0..*"),
            _rel("r2", "m", "l", TipoRelacion.ASOCIACION, "0..*", "0..*"),
        ]
        modelo = construir_modelo(clases, rels)
        tablas = [m.tabla for m in modelo.muchos_a_muchos]
        assert len(set(tablas)) == 2
        segmentos = [m.segmento_dueño for m in modelo.muchos_a_muchos]
        assert len(set(segmentos)) == 2


class TestSpring:
    def test_herencia_joined_y_abstracta(self, completo):
        archivos = _zip(generar_zip_backend(*completo))
        persona = _java(archivos, "model/Persona.java")
        estudiante = _java(archivos, "model/Estudiante.java")
        assert "@Inheritance(strategy = InheritanceType.JOINED)" in persona
        assert "public abstract class Persona" in persona
        assert "public class Estudiante extends Persona" in estudiante
        assert '@PrimaryKeyJoinColumn(name = "id")' in estudiante
        assert "private Long id;" not in estudiante
        # Una clase abstracta no expone POST/PUT.
        assert "@PostMapping\n" not in _java(archivos, "controller/PersonaController.java")

    def test_many_to_many_con_set_y_join_table(self, completo):
        archivos = _zip(generar_zip_backend(*completo))
        estudiante = _java(archivos, "model/Estudiante.java")
        curso = _java(archivos, "model/Curso.java")
        assert '@JoinTable(\n        name = "cursos_estudiantes",' in estudiante
        assert "private Set<Curso> cursos = new HashSet<>();" in estudiante
        assert '@ManyToMany(mappedBy = "cursos")' in curso
        # Las colecciones no se serializan (no hay recursión infinita).
        assert estudiante.count("@JsonIgnore\n") >= 1

    def test_rutas_vincular_desvincular_en_ambos_sentidos(self, completo):
        archivos = _zip(generar_zip_backend(*completo))
        ctrl_e = _java(archivos, "controller/EstudianteController.java")
        ctrl_c = _java(archivos, "controller/CursoController.java")
        assert '@GetMapping("/{id}/cursos")' in ctrl_e
        assert '@PostMapping("/{id}/cursos/{cursoId}")' in ctrl_e
        assert '@DeleteMapping("/{id}/cursos/{cursoId}")' in ctrl_e
        assert '@PostMapping("/{id}/estudiantes/{estudianteId}")' in ctrl_c
        # Clase de asociación: la ruta de vínculo crea/borra la Inscripcion.
        assert '@PostMapping("/{id}/talleres/{tallerId}")' in ctrl_e
        servicio = _java(archivos, "service/EstudianteService.java")
        assert "inscripcionRepository.save(vinculo)" in servicio
        repo = _java(archivos, "repository/InscripcionRepository.java")
        assert "findByEstudiante_IdAndTaller_Id" in repo

    def test_actualizar_no_borra_vinculos(self, completo):
        """Regresión: el PUT hacía save(datos) y borraba la tabla intermedia."""
        archivos = _zip(generar_zip_backend(*completo))
        servicio = _java(archivos, "service/EstudianteService.java")
        bloque = servicio.split("public Estudiante actualizar")[1].split("\n    }\n")[0]
        assert "existente.setCarnet(datos.getCarnet());" in bloque
        assert "existente.setCi(datos.getCi());" in bloque  # heredado
        assert "Cursos" not in bloque

    def test_zip_trae_postman_docker_y_migracion(self, completo):
        archivos = _zip(generar_zip_backend(*completo))
        for nombre in ("postman_collection.json", "docker-compose.yml", "Dockerfile", "README.md"):
            assert nombre in archivos
        assert "springdoc-openapi-starter-webmvc-ui" in archivos["pom.xml"]
        assert "flyway-core" in archivos["pom.xml"]


class TestPostman:
    def test_coleccion_valida_y_con_rutas_nm(self, completo):
        p, c, r = completo
        col = json.loads(generar_coleccion_postman(p.nombre, construir_modelo(c, r)))
        assert col["info"]["schema"].endswith("v2.1.0/collection.json")
        carpetas = {f["name"]: f["item"] for f in col["item"]}
        assert set(carpetas) == {"1. CRUD", "2. Relaciones N:M", "3. Integridad referencial", "4. Eliminar"}
        rutas = [
            "/".join(i["request"]["url"]["path"]) for g in carpetas["2. Relaciones N:M"] for i in g["item"]
        ]
        assert "api/estudiantes/{{estudianteId}}/cursos/{{cursoId}}" in rutas
        assert "api/cursos/{{cursoId}}/estudiantes" in rutas

    def test_referidas_se_crean_antes(self, completo):
        p, c, r = completo
        modelo = construir_modelo(c, r)
        orden = [e.nombre_java for e in modelo.orden_creacion()]
        assert orden.index("Cliente") < orden.index("Factura") < orden.index("DetalleFactura")
        assert orden.index("Perfil") < orden.index("Usuario")
        assert orden.index("Estudiante") < orden.index("Inscripcion")


class TestFlutter:
    def test_clase_de_asociacion_recibe_sus_dos_referencias_y_herencia_sus_atributos(self, completo):
        p, c, r = completo
        archivos = _zip(generar_zip_frontend(p, c, r, "http://localhost:8080"))
        inscripcion = archivos["lib/models/inscripcion.dart"]
        assert "int? estudianteId;" in inscripcion and "int? tallerId;" in inscripcion
        estudiante = archivos["lib/models/estudiante.dart"]
        assert "ci;" in estudiante  # heredado de Persona
        assert "personaId" not in estudiante  # la herencia ya no es una FK


class TestValidacion:
    def test_multiplicidad_asterisco_y_clase_de_asociacion(self, client, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clases = [
            {"id": i, "nombre": n, "atributos": [], "metodos": []} for i, n in (("e", "Estudiante"), ("c", "Curso"), ("m", "Matricula"))
        ]
        rel = {
            "id": "r",
            "id_clase_origen": "e",
            "id_clase_destino": "c",
            "tipo": "ASOCIACION",
            "multiplicidad_origen": "*",
            "multiplicidad_destino": "*",
            "id_clase_asociacion": "m",
        }
        resp = client.put(
            f"/proyectos/{proyecto.id}/diagrama", json={"clases": clases, "relaciones": [rel]}, headers=headers(admin)
        )
        assert resp.status_code == 200, resp.text
        guardado = client.get(f"/proyectos/{proyecto.id}/diagrama", headers=headers(admin)).json()
        assert guardado["relaciones"][0]["multiplicidad_origen"] == "*"
        assert guardado["relaciones"][0]["id_clase_asociacion"] == "m"

    def test_clase_de_asociacion_inexistente_se_descarta(self, client, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clases = [{"id": i, "nombre": i.upper(), "atributos": [], "metodos": []} for i in ("a", "b")]
        rel = {"id": "r", "id_clase_origen": "a", "id_clase_destino": "b", "tipo": "ASOCIACION", "id_clase_asociacion": "fantasma"}
        resp = client.put(
            f"/proyectos/{proyecto.id}/diagrama", json={"clases": clases, "relaciones": [rel]}, headers=headers(admin)
        )
        assert resp.status_code == 200
        guardado = client.get(f"/proyectos/{proyecto.id}/diagrama", headers=headers(admin)).json()
        assert guardado["relaciones"][0]["id_clase_asociacion"] is None

    def test_nombre_de_tabla_intermedia_invalido(self, client, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clases = [{"id": i, "nombre": i.upper(), "atributos": [], "metodos": []} for i in ("a", "b")]
        rel = {"id": "r", "id_clase_origen": "a", "id_clase_destino": "b", "tipo": "ASOCIACION", "tabla_intermedia": "drop table;"}
        resp = client.put(
            f"/proyectos/{proyecto.id}/diagrama", json={"clases": clases, "relaciones": [rel]}, headers=headers(admin)
        )
        assert resp.status_code == 400


def test_relacion_orm_acepta_campos_nuevos():
    r = Relacion(id="x", id_proyecto=1, id_clase_origen="a", id_clase_destino="b", tipo=TipoRelacion.ASOCIACION,
                 id_clase_asociacion="c", tabla_intermedia="t")
    assert r.id_clase_asociacion == "c"


class TestReporteDdlJson:
    def _proyecto_con_nm(self, client, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clases = [{"id": i, "nombre": n, "atributos": [], "metodos": []} for i, n in (("e", "Estudiante"), ("c", "Curso"))]
        rel = {"id": "r", "id_clase_origen": "e", "id_clase_destino": "c", "tipo": "ASOCIACION",
               "multiplicidad_origen": "*", "multiplicidad_destino": "*"}
        client.put(f"/proyectos/{proyecto.id}/diagrama", json={"clases": clases, "relaciones": [rel]}, headers=headers(admin))
        return admin, proyecto

    def test_ddl_incluye_tabla_intermedia(self, client, crear_usuario, crear_proyecto, headers):
        admin, proyecto = self._proyecto_con_nm(client, crear_usuario, crear_proyecto, headers)
        resp = client.get(f"/proyectos/{proyecto.id}/reporte?formato=ddl", headers=headers(admin))
        assert resp.status_code == 200
        assert resp.headers["content-disposition"].endswith('.sql"')
        assert 'CREATE TABLE "cursos_estudiantes"' in resp.text

    def test_json_del_diagrama(self, client, crear_usuario, crear_proyecto, headers):
        admin, proyecto = self._proyecto_con_nm(client, crear_usuario, crear_proyecto, headers)
        resp = client.get(f"/proyectos/{proyecto.id}/reporte?formato=json", headers=headers(admin))
        assert resp.status_code == 200
        datos = resp.json()
        assert {c["nombre"] for c in datos["clases"]} == {"Estudiante", "Curso"}
        assert datos["relaciones"][0]["multiplicidad_destino"] == "*"
