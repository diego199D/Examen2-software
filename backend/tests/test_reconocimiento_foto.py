import io
import json
import uuid

import pytest
from PIL import Image

from app.models.usuario import RolUsuario
from app.models.clase_uml import ClaseUml
from app.schemas.reconocimiento_foto import (
    AtributoDetectadoIO,
    ClaseDetectadaIO,
    ReconocimientoFotoResultado,
    RelacionDetectadaIO,
)
from app.services import reconocimiento_foto


@pytest.fixture(autouse=True)
def _sin_llamadas_reales_a_openai(monkeypatch):
    """Ningún test de este módulo puede pegarle a la API real (cuesta plata,
    no es determinístico, y con la clave del `.env` cargada lo haría de
    verdad -- pasó una vez con un test que no mockeaba `_verificar_lineas`).
    Los tests que necesitan una respuesta la simulan con `_ClienteOpenAIFalso`
    o mockeando la función, lo que reemplaza este bloqueo.

    El intento se REGISTRA y se hace fallar el test al final, en vez de solo
    lanzar una excepción: las verificaciones opcionales del módulo atrapan
    cualquier excepción a propósito (para no romper la vista previa), así
    que una excepción sola pasaría inadvertida."""
    intentos = []

    class _OpenAIBloqueado:
        def __init__(self, *_, **__):
            intentos.append(1)
            raise RuntimeError("llamada real a OpenAI bloqueada en tests")

    monkeypatch.setattr(reconocimiento_foto, "OpenAI", _OpenAIBloqueado)
    yield
    assert not intentos, (
        "el test intentó llamar a la API real de OpenAI -- mockeá la función que la usa "
        "(_llamar_openai_reconocimiento, _verificar_extremos_marcados, _verificar_lineas)"
    )


def _png_bytes(ancho=20, alto=20) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), "white").save(buf, format="PNG")
    return buf.getvalue()


def _mock_llamada(monkeypatch, resultado: ReconocimientoFotoResultado):
    monkeypatch.setattr(reconocimiento_foto, "_llamar_openai_reconocimiento", lambda *_: resultado)


def _mock_verificacion(monkeypatch, respuesta):
    """`respuesta` puede ser una lista (una entrada por relación dirigida, en
    orden) de nombres de clase -- atajo para "hay marcador, está en esa
    clase" sin opinión sobre si es visible -- o de `ExtremoVerificado`; o
    una excepción a lanzar, para simular que la verificación falla entera."""
    if isinstance(respuesta, Exception):
        def _falla(*_):
            raise respuesta
        monkeypatch.setattr(reconocimiento_foto, "_verificar_extremos_marcados", _falla)
    else:
        valores = [
            v if isinstance(v, reconocimiento_foto.ExtremoVerificado) else reconocimiento_foto.ExtremoVerificado(clase=v)
            for v in respuesta
        ]
        monkeypatch.setattr(reconocimiento_foto, "_verificar_extremos_marcados", lambda *_: valores)


def _mock_verificacion_no_debe_llamarse(monkeypatch):
    def _falla(*_):
        raise AssertionError("no debería haberse llamado a la verificación -- no hay relaciones dirigidas")

    monkeypatch.setattr(reconocimiento_foto, "_verificar_extremos_marcados", _falla)


def test_prompt_establece_convencion_de_direccion_para_relaciones_dirigidas():
    """Tripwire: _llamar_openai_reconocimiento se mockea en el resto de esta
    suite (no se llama a la API real en tests), así que la única forma de
    cubrir por test que el prompt siga pidiendo la convención origen=subclase
    /destino=superclase (HERENCIA) y origen=todo/destino=parte (AGREGACION/
    COMPOSICION) es una aserción de texto -- no reemplaza la verificación
    manual real (repetir el reconocimiento contra una foto conocida)."""
    prompt = reconocimiento_foto._PROMPT_SISTEMA
    assert "SUBCLASE" in prompt
    assert "SUPERCLASE" in prompt
    assert '"todo"' in prompt
    assert '"parte"' in prompt


class TestCorregirDireccionPorExtremoMarcado:
    """`_corregir_direccion_por_extremo_marcado` es lógica Python pura (no
    depende de mockear OpenAI) -- a diferencia del texto del prompt, esto sí
    se puede testear de verdad."""

    def test_herencia_extremo_marcado_en_destino_no_cambia(self):
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "HERENCIA", "subclase-id", "superclase-id", "superclase-id"
        )
        assert (origen, destino, invertido) == ("subclase-id", "superclase-id", False)

    def test_herencia_extremo_marcado_en_origen_invierte(self):
        # El modelo puso el orden al revés (origen=superclase); el
        # triángulo (clase_extremo_marcado) dice que la superclase real es
        # la que vino como "origen" -- hay que swapear.
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "HERENCIA", "superclase-id", "subclase-id", "superclase-id"
        )
        assert (origen, destino, invertido) == ("subclase-id", "superclase-id", True)

    def test_agregacion_extremo_marcado_en_destino_invierte(self):
        # origen debería ser el "todo" -- si el rombo está en destino, mal.
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "AGREGACION", "parte-id", "todo-id", "todo-id"
        )
        assert (origen, destino, invertido) == ("todo-id", "parte-id", True)

    def test_composicion_extremo_marcado_en_origen_no_cambia(self):
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "COMPOSICION", "todo-id", "parte-id", "todo-id"
        )
        assert (origen, destino, invertido) == ("todo-id", "parte-id", False)

    def test_extremo_marcado_none_no_toca_nada(self):
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "HERENCIA", "a", "b", None
        )
        assert (origen, destino, invertido) == ("a", "b", False)

    def test_extremo_marcado_que_no_coincide_con_ninguna_clase_no_toca_nada(self):
        # El modelo alucinó un tercer nombre -- no se inventa nada, se deja
        # el orden tal cual vino.
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "HERENCIA", "a", "b", "c-no-es-ninguna-de-las-dos"
        )
        assert (origen, destino, invertido) == ("a", "b", False)

    def test_asociacion_ignora_extremo_marcado(self):
        origen, destino, invertido = reconocimiento_foto._corregir_direccion_por_extremo_marcado(
            "ASOCIACION", "a", "b", "a"
        )
        assert (origen, destino, invertido) == ("a", "b", False)


def _mock_llamada_no_debe_llamarse(monkeypatch):
    def _falla(*_):
        raise AssertionError("no debería haberse llamado a OpenAI -- la validación de archivo tendría que cortar antes")

    monkeypatch.setattr(reconocimiento_foto, "_llamar_openai_reconocimiento", _falla)


def _crear_clase(db_session, proyecto, nombre="ClaseExistente"):
    clase = ClaseUml(id=str(uuid.uuid4()), id_proyecto=proyecto.id, nombre=nombre)
    db_session.add(clase)
    db_session.commit()
    db_session.refresh(clase)
    return clase


_RESULTADO_DOS_CLASES = ReconocimientoFotoResultado(
    reconocido=True,
    mensaje="Se detectaron 2 clases y 1 relación.",
    clases=[
        ClaseDetectadaIO(nombre="Cliente", atributos=[AtributoDetectadoIO(nombre="nombre", tipo="String")]),
        ClaseDetectadaIO(nombre="Pedido", atributos=[AtributoDetectadoIO(nombre="total", tipo="float")]),
    ],
    relaciones=[
        RelacionDetectadaIO(
            clase_origen="Cliente", clase_destino="Pedido", tipo="ASOCIACION",
            multiplicidad_origen="1", multiplicidad_destino="0..*",
        )
    ],
)


class TestReconocer:
    def test_imagen_valida_con_clases(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, _RESULTADO_DOS_CLASES)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["reconocido"] is True
        assert len(datos["clases"]) == 2
        assert len(datos["relaciones"]) == 1

    def test_imagen_sin_contenido_reconocible(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(reconocido=False, mensaje="La imagen no parece contener un diagrama UML.", clases=[], relaciones=[]),
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("foto.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 400
        assert "no parece" in resp.json()["detail"]

    def test_tipo_de_archivo_invalido_no_llama_a_openai(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada_no_debe_llamarse(monkeypatch)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("documento.pdf", b"%PDF-1.4 no es una imagen", "application/pdf")},
            headers=headers(admin),
        )
        assert resp.status_code == 400
        assert "Formato de imagen no soportado" in resp.json()["detail"]

    def test_archivo_demasiado_grande_no_llama_a_openai(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada_no_debe_llamarse(monkeypatch)

        contenido_grande = b"\x00" * (10 * 1024 * 1024 + 1)
        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("grande.png", contenido_grande, "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 400
        assert "grande" in resp.json()["detail"]

    def test_sin_acceso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        otro = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, _RESULTADO_DOS_CLASES)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(otro),
        )
        assert resp.status_code == 403

    def test_clase_duplicada_exacta_se_colapsa(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        # El modelo de visión ocasionalmente repite una clase idéntica dos
        # veces en el mismo resultado (verificado contra la API real) --
        # `_sin_clases_duplicadas` la colapsa antes de mostrar la vista previa.
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado_con_duplicado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="Se detectaron 2 clases y 1 relación.",
            clases=[
                ClaseDetectadaIO(nombre="Cliente", atributos=[AtributoDetectadoIO(nombre="nombre", tipo="String")]),
                ClaseDetectadaIO(nombre="Pedido", atributos=[AtributoDetectadoIO(nombre="total", tipo="float")]),
                ClaseDetectadaIO(nombre="Cliente", atributos=[AtributoDetectadoIO(nombre="nombre", tipo="String")]),
            ],
            relaciones=[],
        )
        _mock_llamada(monkeypatch, resultado_con_duplicado)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        nombres = [c["nombre"] for c in resp.json()["clases"]]
        assert nombres == ["Cliente", "Pedido"]

    def test_colaborador_activo_puede_usarlo(
        self, client, db_session, crear_usuario, crear_proyecto, agregar_colaborador, headers, monkeypatch
    ):
        admin = crear_usuario()
        colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
        proyecto = crear_proyecto(admin)
        agregar_colaborador(proyecto, colaborador)
        _mock_llamada(monkeypatch, _RESULTADO_DOS_CLASES)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(colaborador),
        )
        assert resp.status_code == 200


_RESULTADO_HERENCIA_SIN_CONFIRMAR = ReconocimientoFotoResultado(
    reconocido=True,
    mensaje="2 clases y 1 relación.",
    clases=[ClaseDetectadaIO(nombre="Persona"), ClaseDetectadaIO(nombre="Estudiante")],
    relaciones=[
        RelacionDetectadaIO(
            clase_origen="Persona",
            clase_destino="Estudiante",
            tipo="HERENCIA",
            # La primera pasada no pudo determinar dónde está el triángulo.
            clase_extremo_marcado=None,
        )
    ],
)


class TestVerificacionExtremosMarcados:
    """`reconocer_diagrama` llama a `_verificar_extremos_marcados` (segunda
    pasada de OpenAI, enfocada solo en el marcador) para las relaciones
    dirigidas antes de devolver la vista previa -- ver el docstring del
    módulo. Estos tests mockean esa segunda pasada por separado de
    `_llamar_openai_reconocimiento`, nunca pegan a la API real."""

    def test_verificacion_completa_un_extremo_marcado_que_vino_vacio(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, _RESULTADO_HERENCIA_SIN_CONFIRMAR)
        _mock_verificacion(monkeypatch, ["Persona"])

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["relaciones"][0]["clase_extremo_marcado"] == "Persona"

    def test_no_se_llama_a_verificacion_si_no_hay_relaciones_dirigidas(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, _RESULTADO_DOS_CLASES)  # solo tiene una ASOCIACION
        _mock_verificacion_no_debe_llamarse(monkeypatch)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200

    def test_valor_verificado_que_no_coincide_con_ninguna_clase_se_ignora(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases",
            clases=[ClaseDetectadaIO(nombre="Persona"), ClaseDetectadaIO(nombre="Estudiante")],
            relaciones=[
                RelacionDetectadaIO(
                    clase_origen="Persona",
                    clase_destino="Estudiante",
                    tipo="HERENCIA",
                    clase_extremo_marcado="Persona",
                )
            ],
        )
        _mock_llamada(monkeypatch, resultado)
        # La verificación alucinó un nombre que no es ninguna de las dos
        # clases de esta relación -- se ignora, se mantiene "Persona".
        _mock_verificacion(monkeypatch, ["Fantasma"])

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["relaciones"][0]["clase_extremo_marcado"] == "Persona"

    def test_si_la_verificacion_falla_entera_se_mantiene_el_valor_original(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases",
            clases=[ClaseDetectadaIO(nombre="Persona"), ClaseDetectadaIO(nombre="Estudiante")],
            relaciones=[
                RelacionDetectadaIO(
                    clase_origen="Persona",
                    clase_destino="Estudiante",
                    tipo="HERENCIA",
                    clase_extremo_marcado="Persona",
                )
            ],
        )
        _mock_llamada(monkeypatch, resultado)
        _mock_verificacion(monkeypatch, RuntimeError("fallo inesperado"))

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["relaciones"][0]["clase_extremo_marcado"] == "Persona"


def _post_reconocer(client, proyecto, usuario, headers):
    return client.post(
        f"/proyectos/{proyecto.id}/reconocimiento-foto",
        files={"archivo": ("diagrama.png", _png_bytes(), "image/png")},
        headers=headers(usuario),
    )


class TestComposicionInventada:
    """Caso real: la pasada principal devuelve una composición/agregación
    entre clases que "suenan" a todo-parte, pero en la imagen hay una línea
    simple. La verificación enfocada responde si de verdad hay un marcador
    dibujado, y si no lo hay la relación se baja a ASOCIACION en código."""

    @staticmethod
    def _resultado(tipo):
        return ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases y 1 relación.",
            clases=[ClaseDetectadaIO(nombre="Pedido"), ClaseDetectadaIO(nombre="LineaPedido")],
            relaciones=[
                RelacionDetectadaIO(
                    clase_origen="Pedido",
                    clase_destino="LineaPedido",
                    tipo=tipo,
                    multiplicidad_origen="1",
                    multiplicidad_destino="1..*",
                    clase_extremo_marcado="Pedido",
                )
            ],
        )

    @pytest.mark.parametrize("tipo", ["COMPOSICION", "AGREGACION"])
    def test_sin_marcador_visible_se_baja_a_asociacion_con_advertencia(
        self, tipo, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, self._resultado(tipo))
        _mock_verificacion(monkeypatch, [reconocimiento_foto.ExtremoVerificado(clase=None, marcador_visible=False)])

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        relacion = datos["relaciones"][0]
        assert relacion["tipo"] == "ASOCIACION"
        assert relacion["clase_extremo_marcado"] is None
        # Las multiplicidades son de la línea, no del rombo: se conservan.
        assert relacion["multiplicidad_origen"] == "1"
        assert relacion["multiplicidad_destino"] == "1..*"
        assert len(datos["advertencias"]) == 1
        assert "Pedido – LineaPedido" in datos["advertencias"][0]
        assert "asociación" in datos["advertencias"][0]

    def test_marcador_visible_mantiene_la_composicion(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, self._resultado("COMPOSICION"))
        _mock_verificacion(monkeypatch, [reconocimiento_foto.ExtremoVerificado(clase="Pedido", marcador_visible=True)])

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        assert datos["relaciones"][0]["tipo"] == "COMPOSICION"
        assert datos["advertencias"] == []

    def test_verificacion_que_no_sabe_no_cambia_el_tipo(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, self._resultado("COMPOSICION"))
        _mock_verificacion(monkeypatch, [reconocimiento_foto.ExtremoVerificado(clase=None, marcador_visible=None)])

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        assert datos["relaciones"][0]["tipo"] == "COMPOSICION"
        assert datos["advertencias"] == []


def test_herencia_nunca_lleva_multiplicidad(client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    resultado = ReconocimientoFotoResultado(
        reconocido=True,
        mensaje="2 clases",
        clases=[ClaseDetectadaIO(nombre="Persona"), ClaseDetectadaIO(nombre="Estudiante")],
        relaciones=[
            RelacionDetectadaIO(
                clase_origen="Estudiante",
                clase_destino="Persona",
                tipo="HERENCIA",
                multiplicidad_origen="0..*",
                multiplicidad_destino="1",
                clase_extremo_marcado="Persona",
            )
        ],
    )
    _mock_llamada(monkeypatch, resultado)
    _mock_verificacion(monkeypatch, ["Persona"])

    relacion = _post_reconocer(client, proyecto, admin, headers).json()["relaciones"][0]
    assert relacion["multiplicidad_origen"] is None
    assert relacion["multiplicidad_destino"] is None


class _ClienteOpenAIFalso:
    """Reemplaza a `openai.OpenAI` dentro del módulo: devuelve `respuesta`
    (un dict, serializado a JSON) como contenido del mensaje del modelo y
    guarda los kwargs de la llamada, para verificar el esquema enviado."""

    def __init__(self, respuesta: dict):
        self.respuesta = respuesta
        self.kwargs = None
        cliente = self

        class _Completions:
            def create(self, **kwargs):
                cliente.kwargs = kwargs
                mensaje = type("M", (), {"content": json.dumps(cliente.respuesta)})
                return type("R", (), {"choices": [type("C", (), {"message": mensaje})]})

        self.chat = type("Chat", (), {"completions": _Completions()})

    def __call__(self, **_):
        return self


class TestRespuestaDelModelo:
    """Parseo real de lo que devuelve la API (solo el cliente HTTP es falso)."""

    def test_multiplicidades_quedan_junto_a_su_clase(self, monkeypatch):
        falso = _ClienteOpenAIFalso(
            {
                "reconocido": True,
                "mensaje": "ok",
                "clases": [
                    {"nombre": "Gimnasio", "atributos": [], "metodos": []},
                    {"nombre": "Entrenador", "atributos": [], "metodos": []},
                ],
                "relaciones": [
                    {
                        "clase_origen": "Gimnasio",
                        "clase_destino": "Entrenador",
                        "tipo": "ASOCIACION",
                        "multiplicidad_junto_a_clase_origen": "1",
                        "multiplicidad_junto_a_clase_destino": "0..*",
                        "clase_extremo_marcado": None,
                    }
                ],
            }
        )
        monkeypatch.setattr(reconocimiento_foto, "OpenAI", falso)
        monkeypatch.setattr(reconocimiento_foto.settings, "OPENAI_API_KEY", "clave-de-test")

        resultado = reconocimiento_foto._llamar_openai_reconocimiento(_png_bytes(), "image/png")

        relacion = resultado.relaciones[0]
        assert (relacion.clase_origen, relacion.multiplicidad_origen) == ("Gimnasio", "1")
        assert (relacion.clase_destino, relacion.multiplicidad_destino) == ("Entrenador", "0..*")
        # El esquema enviado usa los nombres explícitos, no los ambiguos.
        esquema_rel = falso.kwargs["response_format"]["json_schema"]["schema"]["properties"]["relaciones"]["items"]
        assert "multiplicidad_junto_a_clase_origen" in esquema_rel["required"]
        assert "multiplicidad_origen" not in esquema_rel["properties"]
        # Cada multiplicidad inmediatamente después de SU clase: con las dos
        # al final, el modelo las invertía (medido contra la API real).
        orden = list(esquema_rel["properties"])
        assert orden.index("multiplicidad_junto_a_clase_origen") == orden.index("clase_origen") + 1
        assert orden.index("multiplicidad_junto_a_clase_destino") == orden.index("clase_destino") + 1

    def test_verificacion_interpreta_marcador_visible(self, monkeypatch):
        relaciones = [
            RelacionDetectadaIO(clase_origen="Pedido", clase_destino="Linea", tipo="COMPOSICION"),
            RelacionDetectadaIO(clase_origen="Persona", clase_destino="Alumno", tipo="HERENCIA"),
            RelacionDetectadaIO(clase_origen="A", clase_destino="B", tipo="AGREGACION"),
        ]
        falso = _ClienteOpenAIFalso(
            {
                "extremos": [
                    {"indice": 0, "marcador_visible": "NO", "clase_extremo_marcado": None},
                    {"indice": 1, "marcador_visible": "SI", "clase_extremo_marcado": "Persona"},
                    {"indice": 2, "marcador_visible": "NO_SE", "clase_extremo_marcado": "Fantasma"},
                ]
            }
        )
        monkeypatch.setattr(reconocimiento_foto, "OpenAI", falso)

        verificados = reconocimiento_foto._verificar_extremos_marcados(_png_bytes(), "image/png", relaciones)

        assert verificados[0] == reconocimiento_foto.ExtremoVerificado(clase=None, marcador_visible=False)
        assert verificados[1] == reconocimiento_foto.ExtremoVerificado(clase="Persona", marcador_visible=True)
        # Nombre alucinado descartado; "no sé" queda como None.
        assert verificados[2] == reconocimiento_foto.ExtremoVerificado(clase=None, marcador_visible=None)


def test_prompt_prohibe_inferir_composicion_por_significado():
    """Tripwire de texto, mismo criterio que el test de convención de
    dirección de arriba: cubre que el prompt siga describiendo el símbolo
    exacto y la regla anti-alucinación, y el ejemplo de multiplicidades."""
    prompt = reconocimiento_foto._PROMPT_SISTEMA
    assert "ÚNICAMENTE" in prompt
    assert "rombo RELLENO" in prompt
    assert "rombo HUECO" in prompt
    assert "multiplicidad_junto_a_clase_origen" in prompt
    assert "Gimnasio 1" in prompt


class TestConfirmar:
    def test_agrega_sobre_proyecto_con_clases_existentes(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Existente")

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=_RESULTADO_DOS_CLASES.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        nombres = {c["nombre"] for c in datos["diagrama"]["clases"]}
        assert nombres == {"Existente", "Cliente", "Pedido"}
        assert datos["advertencias"] == []

    def test_colision_de_nombre_renombra_con_sufijo(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Cliente")

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=_RESULTADO_DOS_CLASES.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        nombres = {c["nombre"] for c in datos["diagrama"]["clases"]}
        assert "Cliente 2" in nombres
        assert "Cliente" in nombres
        assert any("renombró" in a for a in datos["advertencias"])
        # La relación detectada seguía apuntando a "Cliente" (nombre original
        # detectado) -> tiene que resolver contra la clase recién creada
        # ("Cliente 2"), no contra la preexistente.
        relacion = datos["diagrama"]["relaciones"][0]
        clase_cliente_2 = next(c for c in datos["diagrama"]["clases"] if c["nombre"] == "Cliente 2")
        assert relacion["id_clase_origen"] == clase_cliente_2["id"]

    def test_relacion_a_clase_no_detectada_se_descarta(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="1 clase",
            clases=[ClaseDetectadaIO(nombre="Solitaria", atributos=[])],
            relaciones=[
                RelacionDetectadaIO(clase_origen="Solitaria", clase_destino="Fantasma", tipo="ASOCIACION")
            ],
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["diagrama"]["relaciones"] == []
        assert any("descartó una relación" in a for a in datos["advertencias"])

    def test_herencia_con_orden_al_reves_se_corrige_con_extremo_marcado(
        self, client, db_session, crear_usuario, crear_proyecto, headers
    ):
        """El modelo puso clase_origen/clase_destino al revés (un caso real
        que se siguió viendo incluso con la regla de convención en el
        prompt) -- clase_extremo_marcado sí viene bien (dice dónde está el
        triángulo) y el backend tiene que corregir el orden con eso, sin
        depender de que el modelo haya acertado la convención."""
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases",
            clases=[ClaseDetectadaIO(nombre="Persona"), ClaseDetectadaIO(nombre="Estudiante")],
            relaciones=[
                RelacionDetectadaIO(
                    # "al revés": el modelo puso la superclase como origen.
                    clase_origen="Persona",
                    clase_destino="Estudiante",
                    tipo="HERENCIA",
                    clase_extremo_marcado="Persona",  # el triángulo está en Persona -> es la superclase real
                )
            ],
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        clases_por_nombre = {c["nombre"]: c["id"] for c in datos["diagrama"]["clases"]}
        relacion = datos["diagrama"]["relaciones"][0]
        assert relacion["id_clase_origen"] == clases_por_nombre["Estudiante"]
        assert relacion["id_clase_destino"] == clases_por_nombre["Persona"]

    def test_sin_clases_es_400(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(reconocido=False, mensaje="nada", clases=[], relaciones=[])

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 400

    def test_sin_acceso(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        otro = crear_usuario()
        proyecto = crear_proyecto(admin)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=_RESULTADO_DOS_CLASES.model_dump(),
            headers=headers(otro),
        )
        assert resp.status_code == 403

    def test_proyecto_inexistente(self, client, db_session, crear_usuario, headers):
        admin = crear_usuario()

        resp = client.post(
            "/proyectos/999999/reconocimiento-foto/confirmar",
            json=_RESULTADO_DOS_CLASES.model_dump(),
            headers=headers(admin),
        )
        assert resp.status_code == 404


class TestNombresSinTildes:
    """El modelo a veces escribe un mismo nombre con y sin tilde (o con otra
    mayúscula) en distintas partes de la misma respuesta -- la relación igual
    tiene que conectarse, no descartarse."""

    def test_normalizar_nombre(self):
        n = reconocimiento_foto.normalizar_nombre
        assert n("Préstamo") == n("prestamo") == n("  PRESTAMO ")
        assert n("Línea   Pedido") == "linea pedido"
        assert n("Pedido") != n("Pedidos")

    def test_relacion_con_otra_tilde_se_conecta(self, client, db_session, crear_usuario, crear_proyecto, headers):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases",
            clases=[ClaseDetectadaIO(nombre="Préstamo"), ClaseDetectadaIO(nombre="Socio")],
            relaciones=[
                RelacionDetectadaIO(
                    clase_origen="socio", clase_destino="Prestamo", tipo="ASOCIACION",
                    multiplicidad_origen="1", multiplicidad_destino="0..*",
                )
            ],
        )

        datos = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        ).json()

        ids = {c["nombre"]: c["id"] for c in datos["diagrama"]["clases"]}
        assert len(datos["diagrama"]["relaciones"]) == 1
        relacion = datos["diagrama"]["relaciones"][0]
        assert relacion["id_clase_origen"] == ids["Socio"]
        assert relacion["id_clase_destino"] == ids["Préstamo"]
        assert relacion["multiplicidad_origen"] == "1"
        assert not any("descartó" in a for a in datos["advertencias"])

    def test_extremo_marcado_con_otra_tilde_corrige_la_direccion(
        self, client, db_session, crear_usuario, crear_proyecto, headers
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        resultado = ReconocimientoFotoResultado(
            reconocido=True,
            mensaje="2 clases",
            clases=[ClaseDetectadaIO(nombre="Vehículo"), ClaseDetectadaIO(nombre="Auto")],
            relaciones=[
                # Orden al revés (origen = superclase) y el triángulo nombrado sin tilde.
                RelacionDetectadaIO(
                    clase_origen="Vehículo", clase_destino="Auto", tipo="HERENCIA", clase_extremo_marcado="vehiculo"
                )
            ],
        )

        datos = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        ).json()

        ids = {c["nombre"]: c["id"] for c in datos["diagrama"]["clases"]}
        relacion = datos["diagrama"]["relaciones"][0]
        assert relacion["id_clase_origen"] == ids["Auto"]
        assert relacion["id_clase_destino"] == ids["Vehículo"]

    def test_colision_con_clase_existente_sin_tilde_renombra(
        self, client, db_session, crear_usuario, crear_proyecto, headers
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, nombre="Prestamo")
        resultado = ReconocimientoFotoResultado(
            reconocido=True, mensaje="1 clase", clases=[ClaseDetectadaIO(nombre="Préstamo")]
        )

        datos = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar",
            json=resultado.model_dump(),
            headers=headers(admin),
        ).json()

        nombres = sorted(c["nombre"] for c in datos["diagrama"]["clases"])
        assert nombres == ["Prestamo", "Préstamo 2"]

    def test_verificacion_acepta_el_nombre_con_otra_tilde(self, monkeypatch):
        relaciones = [RelacionDetectadaIO(clase_origen="Auto", clase_destino="Vehículo", tipo="HERENCIA")]
        falso = _ClienteOpenAIFalso(
            {"extremos": [{"indice": 0, "marcador_visible": "SI", "clase_extremo_marcado": "VEHICULO"}]}
        )
        monkeypatch.setattr(reconocimiento_foto, "OpenAI", falso)

        verificados = reconocimiento_foto._verificar_extremos_marcados(_png_bytes(), "image/png", relaciones)

        # Devuelto con la grafía de la propia relación.
        assert verificados[0].clase == "Vehículo"


class TestPrepararImagen:
    @staticmethod
    def _tamanio(contenido: bytes) -> tuple[int, int]:
        return Image.open(io.BytesIO(contenido)).size

    def test_imagen_chica_se_agranda_hasta_lado_corto_768(self):
        contenido, tipo = reconocimiento_foto._preparar_imagen(_png_bytes(660, 440), "image/png")
        assert tipo == "image/png"
        assert self._tamanio(contenido) == (1152, 768)

    def test_imagen_grande_no_se_toca(self):
        original = _png_bytes(1600, 1000)
        contenido, tipo = reconocimiento_foto._preparar_imagen(original, "image/png")
        assert contenido is original
        assert tipo == "image/png"

    def test_imagen_muy_alargada_respeta_el_lado_largo_maximo(self):
        contenido, _ = reconocimiento_foto._preparar_imagen(_png_bytes(1500, 300), "image/png")
        ancho, alto = self._tamanio(contenido)
        assert ancho == 2048
        assert alto < 768

    def test_archivo_que_no_es_imagen_es_400_sin_llamar_a_openai(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada_no_debe_llamarse(monkeypatch)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("roto.png", b"esto no es un png", "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 400
        assert "No se pudo leer la imagen" in resp.json()["detail"]

    def test_al_modelo_le_llega_la_imagen_agrandada(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        recibido = {}

        def _captura(contenido, content_type):
            recibido["tamanio"] = self._tamanio(contenido)
            recibido["tipo"] = content_type
            return _RESULTADO_DOS_CLASES

        monkeypatch.setattr(reconocimiento_foto, "_llamar_openai_reconocimiento", _captura)

        resp = client.post(
            f"/proyectos/{proyecto.id}/reconocimiento-foto",
            files={"archivo": ("chica.png", _png_bytes(400, 300), "image/png")},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert min(recibido["tamanio"]) == 768
        assert recibido["tipo"] == "image/png"


def test_reconocimiento_usa_su_propio_modelo_de_vision(monkeypatch):
    """Las dos llamadas de CU12 (principal y verificación de marcadores)
    usan OPENAI_VISION_MODEL, no el OPENAI_MODEL que comparten los comandos
    de voz y el agente."""
    monkeypatch.setattr(reconocimiento_foto.settings, "OPENAI_API_KEY", "clave-de-test")
    monkeypatch.setattr(reconocimiento_foto.settings, "OPENAI_MODEL", "modelo-de-texto")
    monkeypatch.setattr(reconocimiento_foto.settings, "OPENAI_VISION_MODEL", "modelo-de-vision")

    principal = _ClienteOpenAIFalso({"reconocido": True, "mensaje": "ok", "clases": [], "relaciones": []})
    monkeypatch.setattr(reconocimiento_foto, "OpenAI", principal)
    reconocimiento_foto._llamar_openai_reconocimiento(_png_bytes(), "image/png")
    assert principal.kwargs["model"] == "modelo-de-vision"

    verificacion = _ClienteOpenAIFalso({"extremos": []})
    monkeypatch.setattr(reconocimiento_foto, "OpenAI", verificacion)
    reconocimiento_foto._verificar_extremos_marcados(
        _png_bytes(), "image/png", [RelacionDetectadaIO(clase_origen="A", clase_destino="B", tipo="HERENCIA")]
    )
    assert verificacion.kwargs["model"] == "modelo-de-vision"


def test_modelo_de_vision_por_defecto_es_gpt_4o():
    from app.core.config import Settings

    assert Settings.model_fields["OPENAI_VISION_MODEL"].default == "gpt-4o"


# --- Paso 4: duplicados, etiquetas y deducción por claves foráneas -------------

def _clase_con(nombre, *atributos):
    return ClaseDetectadaIO(nombre=nombre, atributos=[AtributoDetectadoIO(nombre=a) for a in atributos])


def _asoc(a, b, mult_a=None, mult_b=None, etiqueta=None):
    return RelacionDetectadaIO(
        clase_origen=a, clase_destino=b, tipo="ASOCIACION",
        multiplicidad_origen=mult_a, multiplicidad_destino=mult_b, etiqueta=etiqueta,
    )


def _mock_lineas(monkeypatch, respuesta_por_par):
    """`respuesta_por_par`: {frozenset({a, b}): LineaVerificada}. Registra
    qué pares se preguntaron, para verificar que no se pregunte de más."""
    preguntados = []

    def _falso(contenido, content_type, pares):
        preguntados.extend(frozenset(p) for p in pares)
        return [respuesta_por_par.get(frozenset(p), reconocimiento_foto._LINEA_SIN_VERIFICAR) for p in pares]

    monkeypatch.setattr(reconocimiento_foto, "_verificar_lineas", _falso)
    return preguntados


def _linea(existe, **mult):
    return reconocimiento_foto.LineaVerificada(
        existe=existe,
        multiplicidades=tuple((reconocimiento_foto.normalizar_nombre(k), v) for k, v in mult.items()),
    )


_CLASES_GIMNASIO = [
    _clase_con("Gimnasio", "id", "nombre", "direccion", "telefono"),
    _clase_con("Entrenador", "id", "nombre", "especialidad", "telefono"),
    _clase_con("Clase", "id", "nombre", "horario", "cupo_maximo"),
    _clase_con("Socio", "id", "nombre", "email", "telefono", "fecha_registro"),
    _clase_con("Pago", "id", "id_socio", "id_membresia", "monto", "fecha_pago"),
    _clase_con("Inscripcion", "id", "id_socio", "id_clase", "fecha_inscripcion"),
    _clase_con("Membresia", "id", "tipo", "precio", "duracion_meses"),
]


class TestDeduccionPorClavesForaneas:
    def test_gimnasio_con_los_errores_reales_queda_con_las_7_relaciones_correctas(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        """Reproduce la respuesta real de gpt-4o con la imagen del gimnasio
        (7 clases, líneas que se cruzan): la línea "Socio realiza Pago" leída
        como Inscripcion–Pago, y además la relación Clase–Inscripcion
        repetida en orden inverso. La imagen (simulada acá con la verdad del
        diagrama) confirma que Inscripcion–Pago no existe y que Socio–Pago sí."""
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True,
                mensaje="Se detectaron 7 clases y 8 relaciones.",
                clases=_CLASES_GIMNASIO,
                relaciones=[
                    _asoc("Gimnasio", "Entrenador", "1", "0..*", "emplea"),
                    _asoc("Gimnasio", "Clase", "1", "0..*", "ofrece"),
                    _asoc("Entrenador", "Clase", "1", "0..*", "imparte"),
                    _asoc("Clase", "Inscripcion", "1", "0..*", "tiene"),
                    _asoc("Inscripcion", "Clase", "0..*", "1", "tiene"),
                    _asoc("Socio", "Inscripcion", "1", "0..*", "se inscribe"),
                    _asoc("Inscripcion", "Pago", "0..*", "0..*"),
                    _asoc("Membresia", "Pago", "1", "0..*", "corresponde a"),
                ],
            ),
        )
        preguntados = _mock_lineas(
            monkeypatch,
            {
                frozenset({"Inscripcion", "Pago"}): _linea(False),
                frozenset({"Socio", "Pago"}): _linea(True, Socio="1", Pago="0..*"),
            },
        )

        datos = _post_reconocer(client, proyecto, admin, headers).json()

        # A la imagen solo se le preguntó por la relación faltante; la
        # sospechosa se quitó directamente (deciden las claves foráneas).
        assert sorted(sorted(p) for p in preguntados) == [["Pago", "Socio"]]
        obtenido = {}
        for r in datos["relaciones"]:
            obtenido[frozenset({r["clase_origen"], r["clase_destino"]})] = {
                r["clase_origen"]: r["multiplicidad_origen"],
                r["clase_destino"]: r["multiplicidad_destino"],
            }
        assert len(datos["relaciones"]) == 7
        assert obtenido == {
            frozenset({"Gimnasio", "Entrenador"}): {"Gimnasio": "1", "Entrenador": "0..*"},
            frozenset({"Gimnasio", "Clase"}): {"Gimnasio": "1", "Clase": "0..*"},
            frozenset({"Entrenador", "Clase"}): {"Entrenador": "1", "Clase": "0..*"},
            frozenset({"Clase", "Inscripcion"}): {"Clase": "1", "Inscripcion": "0..*"},
            frozenset({"Socio", "Inscripcion"}): {"Socio": "1", "Inscripcion": "0..*"},
            frozenset({"Socio", "Pago"}): {"Socio": "1", "Pago": "0..*"},
            frozenset({"Membresia", "Pago"}): {"Membresia": "1", "Pago": "0..*"},
        }
        assert len(datos["clases"]) == 7
        assert datos["mensaje"] == "Se detectaron 7 clases y 7 relaciones."
        assert any("Se quitó la relación Inscripcion – Pago" in a for a in datos["advertencias"])
        assert any("Se agregó la relación Socio – Pago" in a and "id_socio" in a for a in datos["advertencias"])

    def test_sospechosa_se_quita_aunque_la_imagen_diga_que_existe_y_sin_preguntarle(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        """Decisión tomada con la medición real: la pregunta enfocada también
        se equivoca con una línea que pasa por detrás de una caja, así que en
        este caso deciden las claves foráneas."""
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True, mensaje="", clases=_CLASES_GIMNASIO,
                relaciones=[_asoc("Inscripcion", "Pago"), _asoc("Socio", "Pago"), _asoc("Membresia", "Pago"),
                            _asoc("Socio", "Inscripcion"), _asoc("Clase", "Inscripcion")],
            ),
        )
        preguntados = _mock_lineas(monkeypatch, {frozenset({"Inscripcion", "Pago"}): _linea(True)})

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        pares = {frozenset({r["clase_origen"], r["clase_destino"]}) for r in datos["relaciones"]}
        assert frozenset({"Inscripcion", "Pago"}) not in pares
        assert len(pares) == 4
        assert any("Se quitó la relación Inscripcion – Pago" in a for a in datos["advertencias"])
        # No faltaba ninguna relación indicada por las claves foráneas: no se gastó la llamada extra.
        assert preguntados == []

    def test_faltante_que_la_imagen_no_confirma_no_se_agrega(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True, mensaje="", clases=_CLASES_GIMNASIO, relaciones=[_asoc("Socio", "Pago")]
            ),
        )
        _mock_lineas(monkeypatch, {})  # todo "no sé"

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        assert [(r["clase_origen"], r["clase_destino"]) for r in datos["relaciones"]] == [("Socio", "Pago")]

    def test_si_la_verificacion_falla_entera_no_se_agrega_nada(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True, mensaje="", clases=_CLASES_GIMNASIO, relaciones=[_asoc("Socio", "Pago")]
            ),
        )

        def _falla(*_):
            raise RuntimeError("fallo inesperado")

        monkeypatch.setattr(reconocimiento_foto, "_verificar_lineas", _falla)

        resp = _post_reconocer(client, proyecto, admin, headers)
        assert resp.status_code == 200
        assert len(resp.json()["relaciones"]) == 1

    def test_herencia_entre_clases_con_claves_foraneas_nunca_se_quita(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True, mensaje="",
                clases=[
                    _clase_con("Persona", "id", "id_direccion"),
                    _clase_con("Estudiante", "id", "id_carrera"),
                    _clase_con("Direccion", "id"),
                    _clase_con("Carrera", "id"),
                ],
                relaciones=[
                    RelacionDetectadaIO(
                        clase_origen="Estudiante", clase_destino="Persona", tipo="HERENCIA",
                        clase_extremo_marcado="Persona",
                    )
                ],
            ),
        )
        _mock_verificacion(monkeypatch, ["Persona"])
        # Persona–Direccion y Estudiante–Carrera faltan: la imagen dice que no hay línea.
        _mock_lineas(
            monkeypatch,
            {frozenset({"Persona", "Direccion"}): _linea(False), frozenset({"Estudiante", "Carrera"}): _linea(False)},
        )

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        assert [r["tipo"] for r in datos["relaciones"]] == ["HERENCIA"]
        assert not any("Se quitó" in a for a in datos["advertencias"])

    def test_sin_claves_foraneas_no_se_hace_la_llamada_extra(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, _RESULTADO_DOS_CLASES)

        def _no_debe_llamarse(*_):
            raise AssertionError("sin contradicciones con las claves foráneas no hay nada que preguntar")

        monkeypatch.setattr(reconocimiento_foto, "_verificar_lineas", _no_debe_llamarse)
        assert _post_reconocer(client, proyecto, admin, headers).status_code == 200

    def test_avisa_si_una_clave_foranea_apunta_a_una_clase_no_detectada(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        sin_membresia = [c for c in _CLASES_GIMNASIO if c.nombre != "Membresia"]
        _mock_llamada(
            monkeypatch,
            ReconocimientoFotoResultado(
                reconocido=True, mensaje="", clases=sin_membresia,
                relaciones=[_asoc("Socio", "Pago"), _asoc("Socio", "Inscripcion"), _asoc("Clase", "Inscripcion")],
            ),
        )
        _mock_lineas(monkeypatch, {})

        datos = _post_reconocer(client, proyecto, admin, headers).json()
        assert any('"id_membresia"' in a and "no se detectó ninguna clase" in a for a in datos["advertencias"])
        # Nunca se inventa la clase.
        assert len(datos["clases"]) == 6


class TestRelacionesDuplicadas:
    def test_misma_linea_en_orden_inverso_se_colapsa_y_completa_multiplicidades(self):
        resultado = reconocimiento_foto._sin_relaciones_duplicadas(
            [_asoc("Clase", "Inscripcion", "1", None, "tiene"), _asoc("Inscripcion", "Clase", "0..*", "1", "tiene")]
        )
        assert len(resultado) == 1
        r = resultado[0]
        assert (r.clase_origen, r.multiplicidad_origen) == ("Clase", "1")
        # La que faltaba se tomó del duplicado, anclada por nombre (no por posición).
        assert (r.clase_destino, r.multiplicidad_destino) == ("Inscripcion", "0..*")

    def test_dos_relaciones_reales_entre_el_mismo_par_con_distinta_etiqueta_se_conservan(self):
        resultado = reconocimiento_foto._sin_relaciones_duplicadas(
            [_asoc("Miembro", "Libro", etiqueta="presta"), _asoc("Miembro", "Libro", etiqueta="reserva")]
        )
        assert [r.etiqueta for r in resultado] == ["presta", "reserva"]

    def test_distinto_tipo_no_es_duplicado(self):
        resultado = reconocimiento_foto._sin_relaciones_duplicadas(
            [_asoc("A", "B"), RelacionDetectadaIO(clase_origen="A", clase_destino="B", tipo="COMPOSICION")]
        )
        assert len(resultado) == 2

    def test_duplicado_con_otra_tilde_se_colapsa(self):
        resultado = reconocimiento_foto._sin_relaciones_duplicadas(
            [_asoc("Préstamo", "Socio"), _asoc("socio", "Prestamo")]
        )
        assert len(resultado) == 1


def test_etiqueta_se_guarda_al_confirmar(client, db_session, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)
    resultado = ReconocimientoFotoResultado(
        reconocido=True, mensaje="",
        clases=[ClaseDetectadaIO(nombre="Gimnasio"), ClaseDetectadaIO(nombre="Entrenador")],
        relaciones=[_asoc("Gimnasio", "Entrenador", "1", "0..*", "emplea" + " x" * 80)],
    )
    datos = client.post(
        f"/proyectos/{proyecto.id}/reconocimiento-foto/confirmar", json=resultado.model_dump(), headers=headers(admin)
    ).json()
    etiqueta = datos["diagrama"]["relaciones"][0]["etiqueta"]
    assert etiqueta.startswith("emplea")
    assert len(etiqueta) == 100


def test_verificar_lineas_ancla_multiplicidades_por_nombre(monkeypatch):
    falso = _ClienteOpenAIFalso(
        {
            "lineas": [
                # El modelo repitió el par invertido: igual quedan junto a su clase.
                {"indice": 0, "existe": "SI", "clase_a": "Pago", "multiplicidad_junto_a_clase_a": "0..*",
                 "clase_b": "Socio", "multiplicidad_junto_a_clase_b": "1", "tipo": "ASOCIACION", "etiqueta": "realiza"},
                {"indice": 1, "existe": "NO_SE", "clase_a": "A", "multiplicidad_junto_a_clase_a": None,
                 "clase_b": "B", "multiplicidad_junto_a_clase_b": None, "tipo": "ASOCIACION", "etiqueta": None},
                {"indice": 7, "existe": "NO", "clase_a": "X", "multiplicidad_junto_a_clase_a": None,
                 "clase_b": "Y", "multiplicidad_junto_a_clase_b": None, "tipo": "ASOCIACION", "etiqueta": None},
            ]
        }
    )
    monkeypatch.setattr(reconocimiento_foto, "OpenAI", falso)

    lineas = reconocimiento_foto._verificar_lineas(
        _png_bytes(), "image/png", [("Socio", "Pago"), ("A", "B"), ("C", "D")]
    )

    assert lineas[0].existe is True
    assert lineas[0].multiplicidad_junto_a("Socio") == "1"
    assert lineas[0].multiplicidad_junto_a("Pago") == "0..*"
    assert lineas[0].etiqueta == "realiza"
    assert lineas[1].existe is None
    # Índice fuera de rango ignorado: el tercer par queda "sin verificar".
    assert lineas[2] == reconocimiento_foto._LINEA_SIN_VERIFICAR
    assert falso.kwargs["model"] == reconocimiento_foto.settings.OPENAI_VISION_MODEL
