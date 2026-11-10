from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.atributo import Atributo
from app.models.clase_uml import ClaseUml
from app.models.metodo import Metodo
from app.models.relacion import Relacion
from app.schemas.diagrama import DiagramaIO

# Deben coincidir con OPCIONES_MULTIPLICIDAD en el frontend (umlFormat.ts).
MULTIPLICIDADES_VALIDAS = {"1", "0..1", "0..*", "1..*"}


def validar_diagrama(datos: DiagramaIO) -> None:
    """Nombres de clase únicos (sin distinguir mayúsculas) y relaciones que
    solo referencien clases del propio payload — evita que una relación
    quede apuntando a una clase de otro proyecto."""
    nombres = [c.nombre.strip().casefold() for c in datos.clases]
    if len(nombres) != len(set(nombres)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hay clases con el mismo nombre en el diagrama",
        )

    ids_clases = {c.id for c in datos.clases}
    for r in datos.relaciones:
        if r.id_clase_origen not in ids_clases or r.id_clase_destino not in ids_clases:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Una relación referencia una clase que no está en el diagrama",
            )
        for multiplicidad in (r.multiplicidad_origen, r.multiplicidad_destino):
            if multiplicidad is not None and multiplicidad not in MULTIPLICIDADES_VALIDAS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Multiplicidad inválida: '{multiplicidad}'. "
                        f"Debe ser una de {sorted(MULTIPLICIDADES_VALIDAS)} o no especificarse."
                    ),
                )


def cargar_diagrama(proyecto_id: int, db: Session) -> DiagramaIO:
    clases = list(db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == proyecto_id)))
    relaciones = list(db.scalars(select(Relacion).where(Relacion.id_proyecto == proyecto_id)))
    return DiagramaIO(clases=clases, relaciones=relaciones)


def cargar_clases_y_relaciones(proyecto_id: int, db: Session) -> tuple[list[ClaseUml], list[Relacion]]:
    """Lectura cruda (objetos ORM, no el `DiagramaIO` de arriba) para los
    generadores/exportadores que parten del mismo diagrama guardado:
    reportes (CU07), generación de backend Spring Boot (CU08) y de frontend
    Flutter (CU15) — los tres arrancan de exactamente estas dos consultas,
    antes se repetían en cada router."""
    clases = list(db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == proyecto_id)))
    relaciones = list(db.scalars(select(Relacion).where(Relacion.id_proyecto == proyecto_id)))
    return clases, relaciones


def guardar_diagrama(proyecto_id: int, datos: DiagramaIO, db: Session) -> None:
    """Reemplazo completo: se borra todo lo existente y se reinserta lo
    recibido. Usada tanto por el autoguardado HTTP (PUT /diagrama, CU09)
    como por el guardado con debounce del room colaborativo (CU10) — ver
    app/services/yjs_rooms.py."""
    validar_diagrama(datos)

    # Los borrados son en bloque (no session.delete uno a uno), por lo que no
    # disparan el cascade de SQLAlchemy: los ondelete="CASCADE" a nivel de BD
    # son los que limpian atributos/métodos/relaciones huérfanos.
    db.execute(delete(Relacion).where(Relacion.id_proyecto == proyecto_id))
    db.execute(delete(ClaseUml).where(ClaseUml.id_proyecto == proyecto_id))

    for c in datos.clases:
        clase = ClaseUml(
            id=c.id,
            id_proyecto=proyecto_id,
            nombre=c.nombre,
            estereotipo=c.estereotipo,
            es_abstracta=c.es_abstracta,
            pos_x=c.pos_x,
            pos_y=c.pos_y,
        )
        clase.atributos = [Atributo(**a.model_dump()) for a in c.atributos]
        clase.metodos = [Metodo(**m.model_dump()) for m in c.metodos]
        db.add(clase)
    db.flush()  # las clases deben existir antes de insertar relaciones que las referencian

    for r in datos.relaciones:
        db.add(Relacion(id_proyecto=proyecto_id, **r.model_dump()))

    db.commit()
