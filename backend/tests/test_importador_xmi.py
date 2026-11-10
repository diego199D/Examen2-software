import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion
from app.models.proyecto import Proyecto
from app.services.generador_xmi import generar_xmi_reporte
from app.services.importador_xmi import XmiInvalidoError, importar_xmi


def _xmi_biblioteca() -> bytes:
    """El mismo diagrama de 5 clases / 4 tipos de relación que usa
    test_generador_xmi.py, exportado de verdad con generar_xmi_reporte (no
    un XMI escrito a mano) -- así el test de round-trip ejercita el
    exportador y el importador juntos, tal como se van a usar en la práctica."""
    proyecto = Proyecto(id=1, nombre="Biblioteca RoundTrip", id_administrador=1)

    persona = ClaseUml(id="p1", nombre="Persona", es_abstracta=True, pos_x=0, pos_y=0)
    persona.atributos = [
        Atributo(id="a1", nombre="nombre", tipo="String", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    miembro = ClaseUml(id="p2", nombre="Miembro", es_abstracta=False, pos_x=0, pos_y=0)
    miembro.atributos = [
        Atributo(id="a2", nombre="numeroSocio", tipo="Integer", visibilidad=VisibilidadMiembro.PUBLICO, orden=0)
    ]
    libro = ClaseUml(id="l1", nombre="Libro", es_abstracta=False, pos_x=0, pos_y=0)
    libro.atributos = [
        Atributo(id="a3", nombre="precio", tipo="Real", visibilidad=VisibilidadMiembro.PRIVADO, orden=0)
    ]
    ejemplar = ClaseUml(id="e1", nombre="Ejemplar", es_abstracta=False, pos_x=0, pos_y=0)
    ejemplar.atributos = []
    biblioteca = ClaseUml(id="b1", nombre="Biblioteca", es_abstracta=False, pos_x=0, pos_y=0)
    biblioteca.atributos = []

    clases = [persona, miembro, libro, ejemplar, biblioteca]
    relaciones = [
        Relacion(id="r1", id_clase_origen="p2", id_clase_destino="p1", tipo=TipoRelacion.HERENCIA),
        Relacion(
            id="r2",
            id_clase_origen="p2",
            id_clase_destino="l1",
            tipo=TipoRelacion.ASOCIACION,
            etiqueta="presta",
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        ),
        Relacion(
            id="r3",
            id_clase_origen="b1",
            id_clase_destino="l1",
            tipo=TipoRelacion.AGREGACION,
            multiplicidad_origen="1",
            multiplicidad_destino="0..*",
        ),
        Relacion(
            id="r4",
            id_clase_origen="l1",
            id_clase_destino="e1",
            tipo=TipoRelacion.COMPOSICION,
            multiplicidad_origen="1",
            multiplicidad_destino="1..*",
        ),
    ]
    return generar_xmi_reporte(proyecto, clases, relaciones)


# --------------------------------------------------------------------------
# Round-trip a nivel del módulo (sin pasar por HTTP) -- confirma que lo que
# arma generador_xmi.py se interpreta exactamente igual al volver a leerlo.
# --------------------------------------------------------------------------


def test_round_trip_sin_advertencias_y_datos_identicos():
    resultado = importar_xmi(_xmi_biblioteca())
    assert resultado.advertencias == []

    diagrama = resultado.diagrama
    assert {c.nombre for c in diagrama.clases} == {"Persona", "Miembro", "Libro", "Ejemplar", "Biblioteca"}

    por_nombre = {c.nombre: c for c in diagrama.clases}
    assert por_nombre["Persona"].es_abstracta is True
    assert por_nombre["Miembro"].es_abstracta is False
    assert [(a.nombre, a.tipo, a.visibilidad) for a in por_nombre["Persona"].atributos] == [
        ("nombre", "String", VisibilidadMiembro.PRIVADO)
    ]
    assert [(a.nombre, a.tipo, a.visibilidad) for a in por_nombre["Miembro"].atributos] == [
        ("numeroSocio", "Integer", VisibilidadMiembro.PUBLICO)
    ]
    assert [(a.nombre, a.tipo, a.visibilidad) for a in por_nombre["Libro"].atributos] == [
        ("precio", "Real", VisibilidadMiembro.PRIVADO)
    ]

    nombre_por_id = {c.id: c.nombre for c in diagrama.clases}
    relaciones = {
        (nombre_por_id[r.id_clase_origen], nombre_por_id[r.id_clase_destino]): r for r in diagrama.relaciones
    }
    assert relaciones[("Miembro", "Persona")].tipo == TipoRelacion.HERENCIA
    asociacion = relaciones[("Miembro", "Libro")]
    assert asociacion.tipo == TipoRelacion.ASOCIACION
    assert asociacion.etiqueta == "presta"
    assert (asociacion.multiplicidad_origen, asociacion.multiplicidad_destino) == ("1", "0..*")
    agregacion = relaciones[("Biblioteca", "Libro")]
    assert agregacion.tipo == TipoRelacion.AGREGACION
    assert (agregacion.multiplicidad_origen, agregacion.multiplicidad_destino) == ("1", "0..*")
    composicion = relaciones[("Libro", "Ejemplar")]
    assert composicion.tipo == TipoRelacion.COMPOSICION
    assert (composicion.multiplicidad_origen, composicion.multiplicidad_destino) == ("1", "1..*")


def test_ids_internos_nuevos_no_se_reusan_del_archivo():
    """Los xmi:id del archivo ('cls_p1', etc.) no deben terminar como
    ClaseUml.id -- son una clave primaria GLOBAL en la base de datos, no
    scoped por proyecto, así que reusarlos podría chocar con una clase de
    cualquier otro proyecto (bug real encontrado manualmente durante la
    implementación de CU07)."""
    resultado = importar_xmi(_xmi_biblioteca())
    ids_generados = {c.id for c in resultado.diagrama.clases}
    ids_del_archivo = {"cls_p1", "cls_p2", "cls_l1", "cls_e1", "cls_b1", "p1", "p2", "l1", "e1", "b1"}
    assert ids_generados.isdisjoint(ids_del_archivo)


# --------------------------------------------------------------------------
# Tolerancia a XMI que no viene de nuestro propio exportador.
# --------------------------------------------------------------------------

_XMI_ESTILO_EA = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://www.omg.org/spec/UML/20131001" xmlns:xmi="http://www.omg.org/spec/XMI/20131001">
  <uml:Model xmi:type="uml:Model" xmi:id="EAPK_model" name="EA Model">
    <packagedElement xmi:type="uml:Package" xmi:id="EAPK_pkg" name="Paquete">
      <packagedElement xmi:type="uml:PrimitiveType" xmi:id="EAJava_int" name="int"/>
      <packagedElement xmi:type="uml:Class" xmi:id="EAID_cliente" name="Cliente">
        <ownedAttribute xmi:type="uml:Property" xmi:id="EAID_attr_edad" name="edad" visibility="public" type="EAJava_int"/>
      </packagedElement>
      <packagedElement xmi:type="uml:Class" xmi:id="EAID_pedido" name="Pedido"/>
      <packagedElement xmi:type="uml:Association" xmi:id="EAID_assoc1">
        <ownedEnd xmi:type="uml:Property" xmi:id="EAID_end_cliente" type="EAID_cliente" association="EAID_assoc1">
          <lowerValue xmi:type="uml:LiteralInteger" value="1"/>
          <upperValue xmi:type="uml:LiteralUnlimitedNatural" value="1"/>
        </ownedEnd>
        <ownedEnd xmi:type="uml:Property" xmi:id="EAID_end_pedido" type="EAID_pedido" association="EAID_assoc1" aggregation="composite">
          <lowerValue xmi:type="uml:LiteralInteger" value="0"/>
          <upperValue xmi:type="uml:LiteralUnlimitedNatural" value="*"/>
        </ownedEnd>
      </packagedElement>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""


def test_tolera_namespace_2013_clase_anidada_en_package_y_tipo_por_idref_local():
    resultado = importar_xmi(_XMI_ESTILO_EA.encode("utf-8"))
    assert resultado.advertencias == []
    diagrama = resultado.diagrama
    assert {c.nombre for c in diagrama.clases} == {"Cliente", "Pedido"}

    cliente = next(c for c in diagrama.clases if c.nombre == "Cliente")
    assert [(a.nombre, a.tipo) for a in cliente.atributos] == [("edad", "int")]

    nombre_por_id = {c.id: c.nombre for c in diagrama.clases}
    assert len(diagrama.relaciones) == 1
    rel = diagrama.relaciones[0]
    # aggregation="composite" estaba en el extremo Pedido -> Pedido es la
    # parte -> debe quedar como destino (mismo criterio que el exportador).
    assert nombre_por_id[rel.id_clase_origen] == "Cliente"
    assert nombre_por_id[rel.id_clase_destino] == "Pedido"
    assert rel.tipo == TipoRelacion.COMPOSICION


_XMI_GENERALIZACION_SUELTA = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="Animal"/>
    <packagedElement xmi:type="uml:Class" xmi:id="c2" name="Perro"/>
    <packagedElement xmi:type="uml:Generalization" xmi:id="g1" specific="c2" general="c1"/>
  </uml:Model>
</xmi:XMI>
"""


def test_tolera_generalizacion_suelta_con_atributos_specific_general():
    resultado = importar_xmi(_XMI_GENERALIZACION_SUELTA.encode("utf-8"))
    assert resultado.advertencias == []
    diagrama = resultado.diagrama
    nombre_por_id = {c.id: c.nombre for c in diagrama.clases}
    assert len(diagrama.relaciones) == 1
    rel = diagrama.relaciones[0]
    assert rel.tipo == TipoRelacion.HERENCIA
    assert nombre_por_id[rel.id_clase_origen] == "Perro"
    assert nombre_por_id[rel.id_clase_destino] == "Animal"


_XMI_SIN_MEMBER_END = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="A"/>
    <packagedElement xmi:type="uml:Class" xmi:id="c2" name="B"/>
    <packagedElement xmi:type="uml:Association" xmi:id="assoc1" name="rel">
      <ownedEnd xmi:type="uml:Property" xmi:id="e1" type="c1"/>
      <ownedEnd xmi:type="uml:Property" xmi:id="e2" type="c2"/>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""


def test_tolera_asociacion_sin_memberend_usando_ownedend_anidado():
    resultado = importar_xmi(_XMI_SIN_MEMBER_END.encode("utf-8"))
    assert resultado.advertencias == []
    assert len(resultado.diagrama.relaciones) == 1
    assert resultado.diagrama.relaciones[0].etiqueta == "rel"


_XMI_MULTIPLICIDAD_NO_ESTANDAR = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="A"/>
    <packagedElement xmi:type="uml:Class" xmi:id="c2" name="B"/>
    <packagedElement xmi:type="uml:Association" xmi:id="assoc1" memberEnd="e1 e2">
      <ownedEnd xmi:type="uml:Property" xmi:id="e1" type="c1">
        <lowerValue xmi:type="uml:LiteralInteger" value="1"/>
        <upperValue xmi:type="uml:LiteralUnlimitedNatural" value="1"/>
      </ownedEnd>
      <ownedEnd xmi:type="uml:Property" xmi:id="e2" type="c2">
        <lowerValue xmi:type="uml:LiteralInteger" value="2"/>
        <upperValue xmi:type="uml:LiteralUnlimitedNatural" value="5"/>
      </ownedEnd>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""


def test_multiplicidad_no_representable_se_aproxima_con_advertencia():
    resultado = importar_xmi(_XMI_MULTIPLICIDAD_NO_ESTANDAR.encode("utf-8"))
    assert len(resultado.advertencias) == 1
    assert "no tiene equivalente exacto" in resultado.advertencias[0]
    rel = resultado.diagrama.relaciones[0]
    # lower=2 (no 0) -> el bucket "1..*" es la aproximación razonable.
    assert rel.multiplicidad_destino == "1..*"


_XMI_CLASE_SIN_NOMBRE = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="Valida"/>
    <packagedElement xmi:type="uml:Class" xmi:id="c2"/>
  </uml:Model>
</xmi:XMI>
"""


def test_clase_sin_nombre_se_omite_con_advertencia_en_vez_de_corromper():
    resultado = importar_xmi(_XMI_CLASE_SIN_NOMBRE.encode("utf-8"))
    assert len(resultado.diagrama.clases) == 1
    assert resultado.diagrama.clases[0].nombre == "Valida"
    assert any("se omitió una clase sin nombre" in a.lower() for a in resultado.advertencias)


_XMI_TIPO_NO_RESOLUBLE = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="Foo">
      <ownedAttribute xmi:type="uml:Property" xmi:id="a1" name="raro" type="no-existe-en-el-documento"/>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""


def test_tipo_de_atributo_no_resoluble_deja_advertencia_y_tipo_none():
    resultado = importar_xmi(_XMI_TIPO_NO_RESOLUBLE.encode("utf-8"))
    atributo = resultado.diagrama.clases[0].atributos[0]
    assert atributo.tipo is None
    assert any("no se pudo resolver" in a for a in resultado.advertencias)


_XMI_CON_OPERACION = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m1" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="Foo">
      <ownedOperation xmi:type="uml:Operation" xmi:id="op1" name="hacerAlgo"/>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""


def test_operaciones_no_se_importan_pero_se_advierte():
    resultado = importar_xmi(_XMI_CON_OPERACION.encode("utf-8"))
    assert resultado.diagrama.clases[0].atributos == []
    assert any("método" in a.lower() for a in resultado.advertencias)


def test_xml_invalido_levanta_xmi_invalido_error():
    with pytest.raises(XmiInvalidoError, match="no es XML válido"):
        importar_xmi(b"esto no es xml <<<")


def test_xml_valido_sin_clases_levanta_xmi_invalido_error():
    xml_sin_clases = b'<?xml version="1.0"?><raiz><algo/></raiz>'
    with pytest.raises(XmiInvalidoError, match="ninguna clase"):
        importar_xmi(xml_sin_clases)


_FIXTURE_EA = Path(__file__).parent / "fixtures" / "ea_pedidos.xmi"


def _relaciones_por_nombre(resultado):
    nombres = {c.id: c.nombre for c in resultado.diagrama.clases}
    return {
        (nombres[r.id_clase_origen], nombres[r.id_clase_destino]): (r.tipo, r.multiplicidad_origen, r.multiplicidad_destino)
        for r in resultado.diagrama.relaciones
    }


def test_archivo_real_exportado_por_enterprise_architect():
    """Archivo REAL exportado por Enterprise Architect (el diagrama de
    Pedidos de la usuaria, que a su vez salió de nuestro propio export).
    EA repite cada clase dentro de su `xmi:Extension` y escribe las
    referencias como hijos `<type xmi:idref>`/`<memberEnd xmi:idref>`: antes
    se importaba cada clase dos veces (409 por nombre duplicado) y, detrás
    de eso, se descartaban todas las relaciones."""
    resultado = importar_xmi(_FIXTURE_EA.read_bytes())

    nombres = [c.nombre for c in resultado.diagrama.clases]
    assert sorted(nombres) == ["Cliente", "ItemPedido", "Pedido", "Producto"]
    atributos = {c.nombre: [(a.nombre, a.tipo) for a in c.atributos] for c in resultado.diagrama.clases}
    assert atributos["Cliente"] == [("email", "String"), ("Nombre", "String"), ("telefono", "String")]
    assert atributos["ItemPedido"] == [("Cantidad", "String"), ("precioUnitario", "String")]

    assert _relaciones_por_nombre(resultado) == {
        ("Cliente", "Pedido"): (TipoRelacion.ASOCIACION, "1", "0..*"),
        # Rombo relleno del lado de Pedido (el todo), como en el diagrama de EA.
        ("Pedido", "ItemPedido"): (TipoRelacion.COMPOSICION, "1", "0..*"),
        ("ItemPedido", "Producto"): (TipoRelacion.ASOCIACION, "0..*", "1"),
    }
    assert resultado.advertencias == []


_XMI_EA_EXTENSION_E_IDREF_HIJOS = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="A" name="Animal"/>
    <packagedElement xmi:type="uml:Class" xmi:id="P" name="Perro">
      <generalization xmi:type="uml:Generalization" xmi:id="g1">
        <general xmi:idref="A"/>
      </generalization>
    </packagedElement>
    <packagedElement xmi:type="uml:Class" xmi:id="D" name="Duenio"/>
    <packagedElement xmi:type="uml:Association" xmi:id="as1" name="tiene">
      <memberEnd xmi:idref="e1"/>
      <memberEnd xmi:idref="e2"/>
    </packagedElement>
    <packagedElement xmi:type="uml:Package" xmi:id="pk" name="otro">
      <ownedMember xmi:type="uml:Property" xmi:id="e1" association="as1">
        <type xmi:idref="D"/>
      </ownedMember>
      <ownedMember xmi:type="uml:Property" xmi:id="e2" association="as1">
        <type xmi:idref="P"/>
        <upperValue xmi:type="uml:LiteralUnlimitedNatural" value="-1"/>
        <lowerValue xmi:type="uml:LiteralInteger" value="0"/>
      </ownedMember>
    </packagedElement>
  </uml:Model>
  <xmi:Extension extender="Enterprise Architect">
    <elements>
      <element xmi:idref="A" xmi:type="uml:Class" name="Animal"/>
      <element xmi:type="uml:Class" xmi:id="X" name="SoloEnLaExtension"/>
    </elements>
  </xmi:Extension>
</xmi:XMI>
"""


def test_clases_dentro_de_xmi_extension_se_ignoran():
    nombres = sorted(c.nombre for c in importar_xmi(_XMI_EA_EXTENSION_E_IDREF_HIJOS.encode("utf-8")).diagrama.clases)
    # Ni la referencia repetida (Animal) ni una "clase" que solo existe en la extensión.
    assert nombres == ["Animal", "Duenio", "Perro"]


def test_referencias_como_hijo_xmi_idref_y_member_end_como_hijos():
    resultado = importar_xmi(_XMI_EA_EXTENSION_E_IDREF_HIJOS.encode("utf-8"))
    assert _relaciones_por_nombre(resultado) == {
        # <general xmi:idref="A"/> como hijo de la generalización
        ("Perro", "Animal"): (TipoRelacion.HERENCIA, None, None),
        # memberEnd como hijos + <type xmi:idref> hijo de cada extremo
        ("Duenio", "Perro"): (TipoRelacion.ASOCIACION, None, "0..*"),
    }
    assert resultado.advertencias == []


def test_sanity_xmi_generado_es_parseable_por_elementtree():
    # No debería hacer falta, pero confirma que el fixture del round-trip
    # (usado por varios tests de arriba) es en sí mismo un XML bien formado.
    ET.fromstring(_xmi_biblioteca())
