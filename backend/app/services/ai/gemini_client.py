"""
Cliente único de Google Gemini (SDK oficial `google-genai`) para todo el
sistema. Es el ÚNICO módulo que importa el SDK y el único que toca la red
de un proveedor de IA:

- `chat_with_tools`: conversación multi-turno con function calling (agente
  Senior del chat grupal y comandos de texto/voz).
- `parse_command`: un comando suelto -> una llamada a función obligatoria
  (CU11, voz/texto).
- `image_to_diagram`: imagen + esquema de respuesta JSON -> dict (CU12).
- `generate_json`: texto + esquema de respuesta JSON -> dict (resúmenes,
  usos varios).

No hay `transcribe_audio`: el reconocimiento de voz se hace en el
navegador (Web Speech API, `useComandoVoz.ts`), al servidor solo llega
texto.

Esquemas: Gemini acepta un subconjunto de OpenAPI 3 (`types.Schema`). Las
herramientas se siguen declarando en el resto del código como JSON Schema
"estilo function-calling clásico" (más legible y ya probado), y `esquema_gemini()` las
traduce: `type: [X, "null"]` -> `type: X` + `nullable`, se quitan
`additionalProperties`/`strict`/`$ref`/`oneOf`, `None` se saca de los
`enum`. Un objeto sin `properties` lanza `ValueError` acá mismo (Gemini lo
rechaza en tiempo de ejecución con un error poco claro).

Errores: 429 (cuota) y 5xx (modelo saturado) se reintentan con backoff
exponencial; si el modelo principal sigue saturado se prueba
`GEMINI_FALLBACK_MODEL`. Agotados los intentos se lanza
`IANoDisponibleError` con un mensaje apto para mostrar al usuario. Una
API key ausente también es `IANoDisponibleError`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Intentos por modelo y espera inicial del backoff (se duplica cada vez).
REINTENTOS = 3
ESPERA_INICIAL_SEGUNDOS = 1.5

MENSAJE_CUOTA = (
    "El servicio de IA (Gemini) alcanzó su límite de uso o está saturado en este momento. "
    "Espera unos segundos y vuelve a intentarlo."
)
MENSAJE_SIN_KEY = "GEMINI_API_KEY no está configurada en el servidor."


class IANoDisponibleError(Exception):
    """Falta la API key, la red falló, o Gemini respondió 429/5xx incluso
    después de los reintentos. Los routers lo traducen a 503 con el mensaje
    tal cual (ya es apto para el usuario)."""


class IARespuestaInvalidaError(Exception):
    """Gemini respondió, pero el contenido no es el JSON esperado."""


@dataclass
class LlamadaFuncion:
    nombre: str
    argumentos: dict


@dataclass
class RespuestaChat:
    texto: str | None = None
    llamadas: list[LlamadaFuncion] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------

_CLAVES_DESCARTADAS = {"additionalProperties", "strict", "$schema", "title", "default"}


def esquema_gemini(esquema: dict) -> dict:
    """JSON Schema (estilo function-calling clásico) -> esquema OpenAPI aceptado por Gemini."""
    if not isinstance(esquema, dict):
        return esquema
    for prohibida in ("oneOf", "$ref", "allOf"):
        if prohibida in esquema:
            raise ValueError(f"Gemini no admite '{prohibida}' en esquemas de funciones")

    resultado: dict[str, Any] = {}
    tipo = esquema.get("type")
    nullable = False
    if isinstance(tipo, list):
        no_nulos = [t for t in tipo if t != "null"]
        nullable = len(no_nulos) != len(tipo)
        tipo = no_nulos[0] if no_nulos else "string"
    if tipo:
        resultado["type"] = str(tipo).upper()
    if nullable or esquema.get("nullable"):
        resultado["nullable"] = True

    for clave, valor in esquema.items():
        if clave in _CLAVES_DESCARTADAS or clave in ("type", "nullable"):
            continue
        if clave == "properties":
            resultado["properties"] = {k: esquema_gemini(v) for k, v in valor.items()}
            # Gemini respeta el orden de propiedades si se declara: importa
            # (lección de CU12: cada multiplicidad junto a su clase).
            resultado["property_ordering"] = list(valor.keys())
        elif clave == "items":
            resultado["items"] = esquema_gemini(valor)
        elif clave == "enum":
            valores = [v for v in valor if v is not None]
            if len(valores) != len(valor):
                resultado["nullable"] = True
            resultado["enum"] = [str(v) for v in valores]
        else:
            resultado[clave] = valor

    if resultado.get("type") == "OBJECT" and not resultado.get("properties"):
        raise ValueError("Gemini no admite objetos sin 'properties' en esquemas de funciones")
    if resultado.get("enum") and resultado.get("type") not in (None, "STRING"):
        # Gemini solo admite enum sobre strings.
        resultado.pop("enum")
    return resultado


def _declaraciones(tools: list[dict]):
    """Acepta herramientas en formato clásico (`{"type": "function", "function": {...}}`)
    o directamente `{"name", "description", "parameters"}`."""
    from google.genai import types

    declaraciones = []
    for t in tools:
        f = t.get("function", t)
        declaraciones.append(
            types.FunctionDeclaration(
                name=f["name"],
                description=f.get("description", ""),
                parameters=types.Schema.model_validate(esquema_gemini(f["parameters"])),
            )
        )
    return [types.Tool(function_declarations=declaraciones)]


# ---------------------------------------------------------------------------
# Transporte (único punto con red)
# ---------------------------------------------------------------------------


def _cliente():
    if not settings.GEMINI_API_KEY:
        raise IANoDisponibleError(MENSAJE_SIN_KEY)
    from google import genai
    from google.genai import types

    # Los reintentos los maneja `_generar` (para poder cambiar de modelo);
    # se desactivan los del SDK para no multiplicar la espera.
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=120_000, retry_options=types.HttpRetryOptions(attempts=1)),
    )


def _es_reintentable(err: Exception) -> bool:
    codigo = getattr(err, "code", None)
    return codigo in (408, 429, 500, 502, 503, 504)


def _generar(modelo: str, contents, config):
    """Llama a `generate_content` con backoff y modelo de respaldo."""
    from google.genai import errors

    cliente = _cliente()
    modelos = [modelo]
    if settings.GEMINI_FALLBACK_MODEL and settings.GEMINI_FALLBACK_MODEL != modelo:
        modelos.append(settings.GEMINI_FALLBACK_MODEL)

    ultimo: Exception | None = None
    for m in modelos:
        espera = ESPERA_INICIAL_SEGUNDOS
        for intento in range(REINTENTOS):
            try:
                return cliente.models.generate_content(model=m, contents=contents, config=config)
            except errors.APIError as err:
                ultimo = err
                if not _es_reintentable(err):
                    if getattr(err, "code", None) == 404:
                        break  # modelo inexistente para esta key -> probar el de respaldo
                    raise IANoDisponibleError(f"Gemini rechazó la solicitud ({err.code}).") from err
                logger.warning("Gemini %s respondió %s (intento %d)", m, err.code, intento + 1)
                if intento < REINTENTOS - 1:
                    time.sleep(espera)
                    espera *= 2
            except Exception as err:  # red, timeout
                ultimo = err
                logger.warning("Error de red con Gemini %s: %s", m, err)
                if intento < REINTENTOS - 1:
                    time.sleep(espera)
                    espera *= 2
    raise IANoDisponibleError(MENSAJE_CUOTA) from ultimo


def _contenidos(mensajes: list[tuple[str, str]]):
    """`mensajes`: lista de (rol, texto) con rol 'user' | 'model'."""
    from google.genai import types

    return [types.Content(role=rol, parts=[types.Part.from_text(text=texto)]) for rol, texto in mensajes]


def _extraer_respuesta(respuesta) -> RespuestaChat:
    llamadas = [
        LlamadaFuncion(nombre=fc.name, argumentos=dict(fc.args or {})) for fc in (respuesta.function_calls or [])
    ]
    texto = None
    if not llamadas:
        try:
            texto = respuesta.text
        except Exception:  # respuesta bloqueada / sin partes de texto
            texto = None
    return RespuestaChat(texto=texto, llamadas=llamadas)


def _parsear_json(respuesta) -> dict:
    parsed = getattr(respuesta, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    try:
        texto = respuesta.text or ""
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        raise IARespuestaInvalidaError(f"La IA devolvió un JSON inválido: {err}") from err


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def chat_with_tools(
    system: str,
    mensajes: list[tuple[str, str]],
    tools: list[dict],
    *,
    forzar_herramienta: bool = False,
    modelo: str | None = None,
) -> RespuestaChat:
    """Conversación con herramientas. `mensajes` en orden cronológico como
    (rol, texto) con rol 'user'/'model'. Devuelve texto o llamadas."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=_declaraciones(tools) if tools else None,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY" if forzar_herramienta else "AUTO")
        )
        if tools
        else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    respuesta = _generar(modelo or settings.GEMINI_MODEL, _contenidos(mensajes), config)
    return _extraer_respuesta(respuesta)


def parse_command(texto: str, system: str, tools: list[dict], *, modelo: str | None = None) -> LlamadaFuncion | None:
    """Un comando en lenguaje natural -> la primera llamada a función (obligatoria)."""
    respuesta = chat_with_tools(system, [("user", texto)], tools, forzar_herramienta=True, modelo=modelo)
    return respuesta.llamadas[0] if respuesta.llamadas else None


def generate_json(system: str, texto: str, schema: dict, *, modelo: str | None = None) -> dict:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=types.Schema.model_validate(esquema_gemini(schema)),
    )
    respuesta = _generar(modelo or settings.GEMINI_MODEL, _contenidos([("user", texto)]), config)
    return _parsear_json(respuesta)


def image_to_diagram(
    *, imagen: bytes, mime: str, system: str, prompt: str, schema: dict, modelo: str | None = None
) -> dict:
    """Imagen + instrucción -> dict que respeta `schema` (salida JSON estructurada)."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=types.Schema.model_validate(esquema_gemini(schema)),
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    )
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_bytes(data=imagen, mime_type=mime), types.Part.from_text(text=prompt)],
        )
    ]
    respuesta = _generar(modelo or settings.GEMINI_VISION_MODEL, contents, config)
    return _parsear_json(respuesta)
