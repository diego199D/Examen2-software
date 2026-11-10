from pydantic import BaseModel, Field


class GenerarFrontendInput(BaseModel):
    """CU15 — body de `POST /proyectos/{id}/generar-frontend`: la URL base
    del backend contra la que va a apuntar la app Flutter generada (no hay
    forma de que el backend la infiera solo — puede ser localhost en dev, o
    un dominio real ya desplegado)."""

    url_base: str = Field(min_length=1)
