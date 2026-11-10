"""CU13 — agente conversacional integrado.

A diferencia de CU11 (comando de voz suelto, sin memoria, "no se entendió"
= error 422), acá hay una conversación con historial: el usuario puede
pedir una edición (una de las mismas 5 acciones de CU11, reutilizadas de
`app/services/comandos_voz.py` sin duplicar nada) o hacer una pregunta sobre
el diagrama actual o sobre UML en general. En AMBOS casos "no se pudo
interpretar" es una respuesta conversacional normal (200, `accion=None`),
nunca un error HTTP -- solo un fallo real de OpenAI (red/timeout/rate limit)
sigue siendo un error HTTP (503), igual que CU11 (se reutiliza la misma
`ComandoVozNoDisponibleError`, mismo significado).

Este módulo tampoco persiste nada -- igual que CU11, quien aplica la acción
es el frontend con las funciones ya existentes de `useDiagrama.ts`.
"""

from __future__ import annotations

import json

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion
from app.schemas.agente import AgenteRespuesta, MensajeChatIO
from app.schemas.diagrama import DiagramaIO
from app.services.comandos_voz import (
    ComandoVozInvalidoError,
    ComandoVozNoDisponibleError,
    construir_tools,
    resolver_accion,
    resumen_diagrama,
)
from app.services.diagrama import MULTIPLICIDADES_VALIDAS, cargar_diagrama

_ROL_OPENAI = {"usuario": "user", "agente": "assistant"}


def _prompt_sistema_agente(diagrama: DiagramaIO) -> str:
    visibilidades = ", ".join(v.value for v in VisibilidadMiembro)
    tipos_relacion = ", ".join(t.value for t in TipoRelacion)
    multiplicidades = ", ".join(sorted(MULTIPLICIDADES_VALIDAS))
    return (
        "Sos el asistente conversacional integrado en el Diagramador UML, una "
        "herramienta web de modelado de diagramas de clases. Hablás en español "
        "(Bolivia/Latinoamérica) y cumplís dos roles: (1) ejecutar ediciones "
        "sobre el diagrama actual del proyecto cuando el usuario te lo pide en "
        "lenguaje natural, y (2) responder preguntas sobre el diagrama actual o "
        "sobre conceptos de UML en general (herencia, agregación vs composición, "
        "multiplicidad, etc.), funcionando como guía/tutor dentro de la "
        "herramienta.\n\n"
        f"Estado ACTUAL del diagrama de este proyecto:\n{resumen_diagrama(diagrama)}\n\n"
        "Tenés disponibles funciones para ejecutar 5 acciones de edición: crear "
        "una clase (con atributos opcionales), agregar un atributo a una clase "
        "existente, eliminar una clase, crear una relación entre dos clases "
        "existentes, y renombrar una clase.\n\n"
        "Cómo responder a cada mensaje del usuario:\n"
        "- Si es una instrucción de edición que corresponde a una de esas 5 "
        "acciones y tenés toda la información necesaria, llamá la función "
        "correspondiente. Nunca inventes un nombre de clase que no exista en el "
        "estado de arriba cuando la acción lo requiere (agregar atributo, "
        "eliminar clase, crear relación, renombrar).\n"
        "- Si es una pregunta sobre el diagrama actual o sobre UML en general, "
        "respondé en texto plano, claro y conciso, SIN llamar ninguna función "
        "(no debe cambiar el diagrama).\n"
        "- Si la instrucción es ambigua, le falta información esencial, o no "
        "corresponde a ninguna de las 5 acciones soportadas, NO llames ninguna "
        "función: respondé en una o dos frases explicando qué no quedó claro y "
        "sugiriendo cómo reformular el pedido.\n"
        f"- Los únicos tipos de relación válidos son: {tipos_relacion}.\n"
        f"- Las únicas multiplicidades válidas son: {multiplicidades}, o ninguna "
        "si no se especificó.\n"
        f"- Las únicas visibilidades válidas son: {visibilidades} (si no se "
        "especifica, usa PRIVADO).\n"
        "- Nunca llames más de una función por mensaje.\n"
        "- No pidas confirmación antes de ejecutar una acción clara: ejecutala "
        "directamente y confirmá qué hiciste en tu respuesta."
    )


def _llamar_openai_agente(mensajes: list[dict]) -> tuple[str | None, dict | None, str | None]:
    """Devuelve (nombre_tool, argumentos, texto) -- exactamente uno de
    (nombre_tool, argumentos) o texto viene poblado, nunca ambos."""
    if not settings.OPENAI_API_KEY:
        raise ComandoVozNoDisponibleError("OPENAI_API_KEY no está configurada en el servidor.")

    cliente = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=mensajes,
            tools=construir_tools(),
            tool_choice="auto",
            parallel_tool_calls=False,
        )
    except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as err:
        raise ComandoVozNoDisponibleError(str(err)) from err

    mensaje = respuesta.choices[0].message
    tool_calls = mensaje.tool_calls
    if not tool_calls:
        return None, None, mensaje.content or ""

    llamada = tool_calls[0]
    try:
        argumentos = json.loads(llamada.function.arguments)
    except json.JSONDecodeError:
        return None, None, "No pude interpretar completamente ese pedido. ¿Podrías reformularlo?"
    return llamada.function.name, argumentos, None


def _mapear_historial(historial: list[MensajeChatIO]) -> list[dict]:
    return [{"role": _ROL_OPENAI[m.rol], "content": m.texto} for m in historial]


def responder_mensaje(proyecto_id: int, historial: list[MensajeChatIO], mensaje: str, db: Session) -> AgenteRespuesta:
    diagrama = cargar_diagrama(proyecto_id, db)
    mensajes = [
        {"role": "system", "content": _prompt_sistema_agente(diagrama)},
        *_mapear_historial(historial),
        {"role": "user", "content": mensaje},
    ]
    nombre_tool, argumentos, texto = _llamar_openai_agente(mensajes)

    if nombre_tool is None:
        return AgenteRespuesta(texto=texto or "No pude interpretar ese pedido. ¿Podrías reformularlo?", accion=None)

    try:
        accion = resolver_accion(nombre_tool, argumentos, diagrama.clases)
    except ComandoVozInvalidoError as err:
        return AgenteRespuesta(texto=f"{err} Intenta reformular el pedido.", accion=None)

    return AgenteRespuesta(texto=accion.resumen, accion=accion)
