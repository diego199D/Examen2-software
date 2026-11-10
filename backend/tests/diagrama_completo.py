"""Diagrama de prueba con todos los casos de relación (lo usan los tests del
generador y la verificación manual con Maven + newman)."""

from types import SimpleNamespace

from app.models.atributo import Atributo, VisibilidadMiembro
from app.models.clase_uml import ClaseUml
from app.models.relacion import Relacion, TipoRelacion


def _clase(id_, nombre, *atributos, abstracta=False):
    c = ClaseUml(id=id_, id_proyecto=1, nombre=nombre, es_abstracta=abstracta, pos_x=0, pos_y=0)
    c.atributos = [
        Atributo(id=f"{id_}-{i}", nombre=n, tipo=t, visibilidad=VisibilidadMiembro.PRIVADO, orden=i)
        for i, (n, t) in enumerate(atributos)
    ]
    c.metodos = []
    return c


def _rel(id_, o, d, tipo, mo=None, md=None, **extra):
    return Relacion(
        id=id_, id_proyecto=1, id_clase_origen=o, id_clase_destino=d, tipo=tipo,
        multiplicidad_origen=mo, multiplicidad_destino=md, **extra,
    )


def diagrama_completo():
    clases = [
        _clase("persona", "Persona", ("ci", "String"), ("nombre", "String"), abstracta=True),
        _clase("estudiante", "Estudiante", ("carnet", "int")),
        _clase("docente", "Docente", ("especialidad", "String")),
        _clase("curso", "Curso", ("sigla", "String"), ("creditos", "int")),
        _clase("taller", "Taller", ("titulo", "String")),
        _clase("inscripcion", "Inscripcion", ("nota", "double"), ("fecha", "date")),
        _clase("cliente", "Cliente", ("razonSocial", "String")),
        _clase("factura", "Factura", ("numero", "int"), ("fecha", "date"), ("total", "decimal")),
        _clase("detalle", "DetalleFactura", ("cantidad", "int"), ("precio", "double")),
        _clase("equipo", "Equipo", ("nombre", "String")),
        _clase("jugador", "Jugador", ("dorsal", "int")),
        _clase("usuario", "Usuario", ("email", "String"), ("activo", "boolean")),
        _clase("perfil", "Perfil", ("bio", "String")),
    ]
    relaciones = [
        _rel("r01", "estudiante", "persona", TipoRelacion.HERENCIA),
        _rel("r02", "docente", "persona", TipoRelacion.HERENCIA),
        _rel("r03", "estudiante", "curso", TipoRelacion.ASOCIACION, "*", "*"),
        _rel("r04", "docente", "curso", TipoRelacion.ASOCIACION, "1", "0..*"),
        _rel("r05", "estudiante", "taller", TipoRelacion.ASOCIACION, "0..*", "1..*", id_clase_asociacion="inscripcion"),
        _rel("r06", "cliente", "factura", TipoRelacion.ASOCIACION, "1", "0..*"),
        _rel("r07", "factura", "detalle", TipoRelacion.COMPOSICION, "1", "1..*"),
        _rel("r08", "equipo", "jugador", TipoRelacion.AGREGACION, "0..1", "*"),
        _rel("r09", "usuario", "perfil", TipoRelacion.ASOCIACION, "1", "1"),
    ]
    proyecto = SimpleNamespace(nombre="Prueba Completa")
    return proyecto, clases, relaciones
