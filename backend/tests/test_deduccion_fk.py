"""Reglas puras de `app/services/deduccion_fk.py` (sin IA ni base de datos)."""

from app.schemas.reconocimiento_foto import AtributoDetectadoIO, ClaseDetectadaIO, RelacionDetectadaIO
from app.services.deduccion_fk import clases_referenciadas_no_detectadas, pistas_fk, revisar_con_fk


def _clase(nombre, *atributos):
    return ClaseDetectadaIO(nombre=nombre, atributos=[AtributoDetectadoIO(nombre=a) for a in atributos])


def _rel(a, b):
    return RelacionDetectadaIO(clase_origen=a, clase_destino=b, tipo="ASOCIACION")


# El diagrama del gimnasio usado para medir contra la API real.
GIMNASIO = [
    _clase("Gimnasio", "id", "nombre", "direccion", "telefono"),
    _clase("Entrenador", "id", "nombre", "especialidad", "telefono"),
    _clase("Clase", "id", "nombre", "horario", "cupo_maximo"),
    _clase("Socio", "id", "nombre", "email", "telefono", "fecha_registro"),
    _clase("Pago", "id", "id_socio", "id_membresia", "monto", "fecha_pago"),
    _clase("Inscripcion", "id", "id_socio", "id_clase", "fecha_inscripcion"),
    _clase("Membresia", "id", "tipo", "precio", "duracion_meses"),
]


def test_pistas_del_gimnasio():
    pares = {(p.clase, p.referenciada) for p in pistas_fk(GIMNASIO)}
    assert pares == {("Pago", "Socio"), ("Pago", "Membresia"), ("Inscripcion", "Socio"), ("Inscripcion", "Clase")}


def test_variantes_de_nombre_de_clave_foranea():
    clases = [
        _clase("LineaPedido", "id", "idPedido", "producto_id", "Id Cliente"),
        _clase("Pedido"),
        _clase("Producto"),
        _clase("Cliente"),
    ]
    referenciadas = {p.referenciada for p in pistas_fk(clases)}
    assert referenciadas == {"Pedido", "Producto", "Cliente"}


def test_clase_con_tilde_y_varias_palabras():
    clases = [_clase("Préstamo", "id_linea_pedido"), _clase("Línea Pedido")]
    assert [(p.clase, p.referenciada) for p in pistas_fk(clases)] == [("Préstamo", "Línea Pedido")]


def test_atributos_que_parecen_fk_pero_no_lo_son():
    # "id" es la clave primaria; "idioma"/"identificador" no nombran ninguna clase.
    clases = [_clase("Libro", "id", "idioma", "identificador"), _clase("Autor")]
    assert pistas_fk(clases) == []
    assert clases_referenciadas_no_detectadas(clases) == []


def test_autorreferencia_no_es_pista():
    assert pistas_fk([_clase("Persona", "id_persona")]) == []


def test_clase_referenciada_que_no_se_detecto():
    sin_membresia = [c for c in GIMNASIO if c.nombre != "Membresia"]
    faltantes = clases_referenciadas_no_detectadas(sin_membresia)
    assert [(p.clase, p.atributo, p.referenciada) for p in faltantes] == [("Pago", "id_membresia", "membresia")]


def test_revision_del_gimnasio_con_los_errores_reales_del_modelo():
    # Lo que devolvió gpt-4o en la medición real: la línea "Socio realiza
    # Pago" leída como Inscripcion–Pago (pasa justo por encima de Inscripcion).
    relaciones = [
        _rel("Gimnasio", "Entrenador"),
        _rel("Gimnasio", "Clase"),
        _rel("Entrenador", "Clase"),
        _rel("Clase", "Inscripcion"),
        _rel("Socio", "Inscripcion"),
        _rel("Inscripcion", "Pago"),
        _rel("Membresia", "Pago"),
    ]
    revision = revisar_con_fk(GIMNASIO, relaciones)
    assert revision.sospechosas == [5]
    assert [(p.clase, p.referenciada) for p in revision.faltantes] == [("Pago", "Socio")]


def test_relaciones_sin_claves_foraneas_en_ninguna_de_las_dos_clases_no_son_sospechosas():
    # Gimnasio–Entrenador no tiene "id_gimnasio" en ningún lado, pero ninguna
    # de las dos clases modela claves foráneas: no hay de dónde sospechar.
    revision = revisar_con_fk(GIMNASIO, [_rel("Gimnasio", "Entrenador")])
    assert revision.sospechosas == []


def test_solo_es_sospechosa_si_las_dos_clases_declaran_claves_foraneas():
    # Socio no declara ninguna clave foránea: una relación Socio–Clase no
    # tiene contra qué contrastarse (criterio estricto, porque se quita sin
    # preguntarle a la imagen).
    revision = revisar_con_fk(GIMNASIO, [_rel("Socio", "Inscripcion"), _rel("Clase", "Pago")])
    assert revision.sospechosas == []


def test_herencia_nunca_es_sospechosa():
    clases = [
        _clase("Persona", "id_direccion"),
        _clase("Estudiante", "id_carrera"),
        _clase("Direccion"),
        _clase("Carrera"),
    ]
    herencia = RelacionDetectadaIO(clase_origen="Estudiante", clase_destino="Persona", tipo="HERENCIA")
    assert revisar_con_fk(clases, [herencia]).sospechosas == []
    assert revisar_con_fk(clases, [_rel("Estudiante", "Persona")]).sospechosas == [0]


def test_diagrama_sin_claves_foraneas_no_genera_nada():
    clases = [_clase("Persona", "nombre"), _clase("Auto", "patente")]
    revision = revisar_con_fk(clases, [_rel("Persona", "Auto")])
    assert revision.sospechosas == []
    assert revision.faltantes == []


def test_faltante_no_se_repite_si_las_dos_clases_se_referencian():
    clases = [_clase("A", "id_b"), _clase("B", "id_a")]
    assert len(revisar_con_fk(clases, []).faltantes) == 1
