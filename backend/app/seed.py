"""Crea un usuario administrador inicial para poder probar el login (CU01).

Uso (desde backend/, con el venv activado):

    python -m app.seed
"""

from sqlalchemy import select

from app.core.security import hashear_password
from app.db.session import SessionLocal
import app.models  # noqa: F401  (registra todos los modelos)
from app.models.usuario import RolUsuario, Usuario
from app.services.grupos import obtener_o_crear_grupo

ADMIN_NOMBRE = "Administrador"
ADMIN_EMAIL = "admin@diagramador.com"
ADMIN_PASSWORD = "admin12345"
GRUPO_DEMO = "Grupo Demo"


def main() -> None:
    db = SessionLocal()
    try:
        existente = db.scalar(select(Usuario).where(Usuario.email == ADMIN_EMAIL))
        if existente is not None:
            if existente.id_grupo is None:
                existente.grupo = obtener_o_crear_grupo(GRUPO_DEMO, db)
                db.commit()
                print(f"El usuario {ADMIN_EMAIL} ya existía; se lo asignó al grupo {GRUPO_DEMO}.")
            else:
                print(f"El usuario {ADMIN_EMAIL} ya existe (id={existente.id}).")
            return

        usuario = Usuario(
            nombre_completo=ADMIN_NOMBRE,
            email=ADMIN_EMAIL,
            password_hash=hashear_password(ADMIN_PASSWORD),
            rol=RolUsuario.ADMINISTRADOR,
        )
        usuario.grupo = obtener_o_crear_grupo(GRUPO_DEMO, db)
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        print(f"Usuario creado (id={usuario.id}): {ADMIN_EMAIL} / {ADMIN_PASSWORD} — grupo {GRUPO_DEMO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
