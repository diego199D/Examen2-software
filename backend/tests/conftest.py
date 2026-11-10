import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import Base, get_db
from app.core.security import crear_access_token, hashear_password
from app.models.usuario import RolUsuario, Usuario
from app.models.proyecto import Proyecto
from app.models.proyecto_colaborador import ProyectoColaborador


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _activar_fk(conexion_dbapi, _):
        conexion_dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def crear_usuario(db_session):
    contador = {"n": 0}

    def _crear(rol: RolUsuario = RolUsuario.ADMINISTRADOR) -> Usuario:
        contador["n"] += 1
        usuario = Usuario(
            nombre_completo=f"Usuario {contador['n']}",
            email=f"usuario{contador['n']}@test.com",
            password_hash=hashear_password("clave12345"),
            rol=rol,
        )
        db_session.add(usuario)
        db_session.commit()
        db_session.refresh(usuario)
        return usuario

    return _crear


@pytest.fixture()
def crear_proyecto(db_session):
    def _crear(admin: Usuario, nombre: str = "Proyecto de prueba") -> Proyecto:
        proyecto = Proyecto(nombre=nombre, id_administrador=admin.id)
        db_session.add(proyecto)
        db_session.commit()
        db_session.refresh(proyecto)
        return proyecto

    return _crear


@pytest.fixture()
def agregar_colaborador(db_session):
    def _agregar(proyecto: Proyecto, usuario: Usuario, activo: bool = True) -> ProyectoColaborador:
        colaborador = ProyectoColaborador(
            id_proyecto=proyecto.id, id_usuario=usuario.id, activo=activo
        )
        db_session.add(colaborador)
        db_session.commit()
        return colaborador

    return _agregar


@pytest.fixture()
def headers():
    def _headers(usuario: Usuario) -> dict[str, str]:
        token = crear_access_token(subject=usuario.id)
        return {"Authorization": f"Bearer {token}"}

    return _headers
