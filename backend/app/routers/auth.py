from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    crear_access_token,
    decodificar_access_token,
    hashear_password,
    verificar_password,
)
from app.db.session import get_db
from app.models.usuario import RolUsuario, Usuario
from app.schemas.usuario import Token, UsuarioRegistro

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """CU01 - Inicio de sesión. El campo `username` del formulario es el email."""
    usuario = db.scalar(select(Usuario).where(Usuario.email == form_data.username))
    if usuario is None or not verificar_password(form_data.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=crear_access_token(subject=usuario.id))


@router.post("/registro", response_model=Token, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    datos: UsuarioRegistro,
    db: Session = Depends(get_db),
) -> Token:
    """Registro público. Todo usuario que se registra queda como ADMINISTRADOR,
    puede crear/ver sus propios proyectos y además ser colaborador en otros."""
    existente = db.scalar(select(Usuario).where(Usuario.email == datos.email))
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El email ya está registrado",
        )

    usuario = Usuario(
        nombre_completo=datos.nombre_completo,
        email=datos.email,
        password_hash=hashear_password(datos.password),
        rol=RolUsuario.ADMINISTRADOR,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return Token(access_token=crear_access_token(subject=usuario.id))


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """Dependencia reutilizable: valida el JWT y devuelve el usuario autenticado."""
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    sub = decodificar_access_token(token)
    if sub is None:
        raise credenciales_invalidas
    try:
        usuario_id = int(sub)
    except ValueError:
        raise credenciales_invalidas
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise credenciales_invalidas
    return usuario
