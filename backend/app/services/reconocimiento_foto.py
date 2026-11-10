"""CU12 — reconocimiento de diagrama de clases a partir de una fotografía.

Reutiliza la infraestructura de OpenAI ya construida en CU11/CU13
(`OPENAI_API_KEY` de `app/core/config.py` -- pero con su propio modelo,
`OPENAI_VISION_MODEL`, ver la tercera vuelta más abajo --, la misma
`ComandoVozNoDisponibleError` de `app/services/comandos_voz.py` para
errores de red/API -- mismo significado, no se crea una excepción hermana
solo por prolijidad cosmética) pero con dos diferencias de fondo respecto a
CU11/CU13:

1. No es function calling sobre acciones del editor -- es una extracción
   estructurada de una sola vez (`response_format` con JSON Schema en modo
   `strict`, para forzar una salida parseable en vez de texto libre a
   interpretar con regex) a partir de una imagen (input de visión).
2. El resultado NUNCA se aplica solo -- `reconocer_diagrama` es de solo
   lectura (no persiste nada); recién `aplicar_reconocimiento` escribe en la
   base de datos, y solo cuando el usuario confirmó la vista previa en el
   frontend.

`aplicar_reconocimiento` reutiliza `guardar_diagrama` (mismo patrón que el
importador XMI de CU09) pero, a diferencia de XMI, **agrega** al diagrama
existente en vez de exigir que esté vacío: carga el diagrama actual,
construye las clases/relaciones nuevas con ids frescos (`uuid4`, igual que
el resto del proyecto -- nunca se reusan ids externos) y guarda la unión.

Criterio de colisión de nombres (ver `_nombre_disponible`): si una clase
detectada en la foto tiene el mismo nombre (sin distinguir mayúsculas ni tildes, ver `normalizar_nombre`) que una que ya
existe en el proyecto -- o que otra clase de la misma foto -- se le agrega
un sufijo numérico (" 2", " 3", ...) hasta encontrar uno libre, y se deja
una advertencia. Se eligió renombrar en vez de rechazar la clase para no
perder información ya interpretada de la imagen (atributos/relaciones), y en
vez de fusionar con la clase existente porque decidir qué atributos son
"nuevos" de forma automática es ambiguo y arriesgado (podría pisar datos
reales). Las relaciones detectadas solo pueden conectar clases DETECTADAS EN
LA MISMA FOTO (nunca a una clase preexistente del proyecto) -- si el modelo
devuelve una relación que referencia un nombre que no está entre las clases
de esa misma foto, se descarta con advertencia en vez de intentar adivinar a
qué clase preexistente se refería.

**Segunda vuelta -- dirección de HERENCIA/AGREGACION/COMPOSICION seguía
saliendo al revés en casos reales** incluso con `clase_extremo_marcado` (el
campo redundante de la vuelta anterior, ver `_corregir_direccion_por_extremo_marcado`):
probado con una foto real (herencia de `Persona` con `Estudiante`/`Profesor`,
triángulo dibujado junto a `Persona`), el reconocimiento la devolvía
invertida. La causa más probable no es la lógica de corrección en sí (es
pura y ya tiene tests) sino que `clase_extremo_marcado` se extrae en la
MISMA llamada única que arma el resto de un JSON grande (clases, atributos,
métodos, multiplicidades, origen/destino) -- un detalle visual fino (dónde
termina exactamente un triángulo delgado a mano alzada) compite por
atención del modelo con todo lo demás. Se agregaron dos mejoras, ninguna
garantiza 100% (sigue siendo un modelo de visión sobre una foto
potencialmente ambigua), pero suben la confiabilidad real:

1. `_llamar_openai_reconocimiento` ahora pide el `image_url` con
   `"detail": "high"` (antes no se especificaba, así que usaba el default
   `"auto"` de la API, que puede achicar la imagen y perder el detalle fino
   de un trazo delgado).
2. `_verificar_extremos_marcados`: una segunda llamada a OpenAI, con la
   MISMA imagen, pero con un prompt mucho más chico y enfocado -- solo le
   pasa al modelo los dos nombres de clase de cada relación dirigida y le
   pregunta, sin el resto del diagrama de por medio, en cuál de esas dos
   clases está el marcador. `reconocer_diagrama` la llama después de la
   pasada principal (solo si hay alguna relación dirigida -- nunca gasta una
   llamada extra si todas son ASOCIACION) y sobreescribe
   `clase_extremo_marcado` con el resultado verificado antes de devolver la
   vista previa. No hizo falta tocar `aplicar_reconocimiento` ni
   `_corregir_direccion_por_extremo_marcado`: siguen igual, ahora reciben un
   `clase_extremo_marcado` más confiable. Defensivo en ambas puntas: un
   valor verificado que no coincide con ninguna de las dos clases de esa
   relación se ignora (se deja el original), y si la llamada de verificación
   falla entera (red, rate limit, JSON inválido) se degrada con gracia --
   nunca tira abajo la vista previa completa por este chequeo opcional.

**Tercera vuelta -- medido contra la API real, no a ojo** (2026-09-22, una
captura limpia de un diagrama de 7 clases/7 asociaciones con líneas que se
cruzan, 3 intentos por variante y por modelo, comparados contra la verdad
del diagrama):

- Multiplicidades invertidas de forma SISTEMÁTICA (casi todas las
  relaciones, en todos los intentos): la causa era nuestra, no del modelo --
  los campos `multiplicidad_origen`/`multiplicidad_destino` no decían de qué
  extremo es cada número. Ahora el esquema los llama
  `multiplicidad_junto_a_clase_origen`/`..._destino`, cada uno ubicado
  INMEDIATAMENTE después del nombre de su clase, y el prompt da un ejemplo
  concreto; `_relacion_desde_modelo` los traduce de vuelta al shape de
  `RelacionDetectadaIO` (el contrato de la API no cambia). El orden importó
  tanto como el nombre: con los nombres nuevos pero las dos multiplicidades
  al final (después de ambas clases y del tipo), gpt-4o las siguió
  invirtiendo (hasta 4 de 7, contradiciendo el ejemplo del prompt); con el
  orden intercalado, 0 invertidas en 3 de 3 intentos.
- Guía de cómo leer las líneas en el prompt (dos extremos por línea, una
  línea puede pasar por detrás de una caja, los textos en medio de una línea
  son etiquetas y no atributos): con ella no se perdió ninguna clase en las
  variantes medidas (sin ella, gpt-4o-mini perdía una clase en 2 de 3).
- Probada también una extracción en dos pasadas (inventario de clases y
  después relaciones con los nombres restringidos a esa lista): NO mejoró
  nada medible respecto de una sola llamada con lo anterior -- se descartó.
- Composición/agregación "inventada" (visto en pruebas: el modelo infiere
  un todo-parte por el significado de las clases sin que haya un rombo
  dibujado): el prompt describe el símbolo exacto de cada tipo con la regla
  "sin rombo claro → ASOCIACION", y además la verificación enfocada de
  arriba ahora responde si de verdad hay un marcador dibujado -- si ve una
  línea simple, `_aplicar_verificacion` baja la relación a ASOCIACION en
  código y lo avisa en `ReconocimientoFotoResultado.advertencias`.
- `_sin_multiplicidad_en_herencia`: una herencia nunca lleva multiplicidad,
  se limpia en código (no se confía solo en el prompt).
- Modelo: gpt-4o-mini fue inestable en todas las variantes (según el
  intento perdía una clase entera, escribía mal nombres como "Membrisia", o
  inventaba relaciones distintas); gpt-4o, con todo lo anterior, dio el
  resultado perfecto en 2 de 3 intentos y nunca perdió clases ni invirtió
  multiplicidades. Por eso CU12 usa su propio `OPENAI_VISION_MODEL`
  (default gpt-4o) en vez del `OPENAI_MODEL` compartido con CU11/CU13.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass
from uuid import uuid4

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.relacion import TipoRelacion
from app.schemas.diagrama import AtributoIO, ClaseIO, DiagramaIO, MetodoIO, RelacionIO
from app.schemas.reconocimiento_foto import (
    ClaseDetectadaIO,
    ConfirmarReconocimientoResultado,
    ReconocimientoFotoResultado,
    RelacionDetectadaIO,
)
from app.services.comandos_voz import ComandoVozNoDisponibleError
from app.services.deduccion_fk import clases_referenciadas_no_detectadas, revisar_con_fk
from app.services.diagrama import MULTIPLICIDADES_VALIDAS, cargar_diagrama, guardar_diagrama
from app.services.nombres import normalizar_nombre

logger = logging.getLogger(__name__)

TIPOS_IMAGEN_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANIO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10MB

# Misma grilla que useDiagrama.ts/importador_xmi.py -- las clases nuevas no
# se amontonan todas en el mismo punto, siguen la grilla desde donde queda
# el diagrama actual (no desde 0, a diferencia de XMI que siempre parte de
# un diagrama vacío).
_GRID_COLUMNAS = 4
_GRID_PASO_X = 240
_GRID_PASO_Y = 180


def _posicion_en_grilla(indice: int) -> tuple[float, float]:
    columna = indice % _GRID_COLUMNAS
    fila = indice // _GRID_COLUMNAS
    return 80 + columna * _GRID_PASO_X, 80 + fila * _GRID_PASO_Y


class ImagenInvalidaError(Exception):
    """Archivo de imagen inválido (tipo/tamaño no permitido, vacío) o la
    imagen no contiene ningún diagrama de clases UML reconocible -- el
    router lo traduce a 400. Nunca se inventa una clase genérica para
    "rellenar" cuando no se reconoce nada."""


_PROMPT_SISTEMA = (
    "Sos un intérprete de diagramas de clases UML a partir de imágenes "
    "(fotos de un pizarrón/papel a mano, o capturas de otra herramienta "
    "UML). Tu tarea es devolver una estructura JSON con las clases, "
    "atributos, métodos (si son claramente visibles) y relaciones que "
    "identifiques.\n\n"
    "Reglas estrictas:\n"
    "- Si la imagen no contiene ningún diagrama de clases UML reconocible "
    "(por ejemplo es una foto sin relación con UML, o está demasiado "
    "borrosa/incompleta para identificar ni una sola clase), poné "
    '"reconocido": false, dejá "clases" y "relaciones" vacíos, y explicá '
    'brevemente por qué en "mensaje". NUNCA inventes clases genéricas '
    "(\"Clase1\", \"Entidad\", etc.) para rellenar cuando no hay nada "
    "reconocible.\n"
    "- Si reconocés al menos una clase, poné \"reconocido\": true y un "
    'resumen breve en "mensaje" (ej. "Se detectaron 2 clases y 1 '
    'relación.").\n'
    "- Recorré la imagen caja por caja y listá TODAS las cajas/rectángulos "
    "de clase, sin omitir ninguna, con los atributos y métodos tal como "
    "están escritos DENTRO de cada caja.\n"
    "- Los nombres de clase/atributo/método deben ser tal como aparecen en "
    "la imagen (sin traducir ni normalizar mayúsculas).\n\n"
    "Tipo de relación -- guiate SOLO por el símbolo gráfico dibujado, nunca "
    "por lo que las clases 'parecen' significar:\n"
    "- HERENCIA: triángulo hueco (sin relleno) en un extremo, del lado de la "
    "superclase (el padre). Nunca lleva multiplicidad.\n"
    "- COMPOSICION: rombo RELLENO (sólido) en un extremo, del lado del \"todo\".\n"
    "- AGREGACION: rombo HUECO (sin relleno) en un extremo, del lado del \"todo\".\n"
    "- ASOCIACION: línea simple, sin triángulo ni rombo en ninguno de sus "
    "extremos (puede tener multiplicidades y una etiqueta).\n"
    "- Composición, agregación y asociación se distinguen ÚNICAMENTE por la "
    "presencia y el relleno del rombo. Si no ves un rombo con claridad, es "
    "ASOCIACION. No reportes COMPOSICION ni AGREGACION 'por si acaso' ni "
    "porque las clases parezcan tener una relación todo-parte (ej. Pedido y "
    "LineaPedido): si la línea es simple, es ASOCIACION. Si hay un rombo "
    "pero no se distingue si está relleno, usá AGREGACION.\n"
    "- Una línea punteada (dependencia) reportala como ASOCIACION.\n\n"
    "Orden de \"clase_origen\"/\"clase_destino\" en relaciones dirigidas "
    "(sigue esta convención fija, no la del sentido de la flecha dibujada):\n"
    "- HERENCIA: \"clase_origen\" es la SUBCLASE (el extremo sin marcador) y "
    "\"clase_destino\" es la SUPERCLASE (el extremo donde está el triángulo).\n"
    "- AGREGACION y COMPOSICION: \"clase_origen\" es el \"todo\" (el extremo "
    "donde está el rombo) y \"clase_destino\" es la \"parte\".\n"
    "- ASOCIACION no tiene un lado fijo.\n"
    "- Además, completá \"clase_extremo_marcado\" con el nombre de la clase "
    "donde está dibujado el marcador (el triángulo o el rombo); null para "
    "ASOCIACION.\n\n"
    "Cómo leer las líneas:\n"
    "- Cada línea tiene exactamente dos extremos, y cada extremo toca el "
    "borde de UNA caja. Reportá una relación por cada línea dibujada.\n"
    "- Una línea puede cruzarse con otras o pasar por DETRÁS de otra caja: si "
    "entra por un lado de una caja y sale por el otro siguiendo la misma "
    "trayectoria recta, es UNA sola línea que conecta las dos cajas de sus "
    "extremos, NO dos relaciones con la caja del medio.\n"
    "- Las multiplicidades (\"1\", \"0..1\", \"0..*\", \"1..*\") están "
    "escritas PEGADAS al extremo de la línea, al lado de la caja que toca ese "
    "extremo. En \"multiplicidad_junto_a_clase_origen\" va la que está "
    "escrita junto a la clase origen, y en "
    "\"multiplicidad_junto_a_clase_destino\" la que está junto a la clase "
    "destino -- nunca las cruces. Ejemplo: en "
    "\"Gimnasio 1 ————— 0..* Entrenador\" con clase_origen=Gimnasio, "
    "multiplicidad_junto_a_clase_origen es \"1\" y "
    "multiplicidad_junto_a_clase_destino es \"0..*\". Si no hay nada escrito "
    "junto a un extremo, null -- no inventes una multiplicidad.\n"
    "- Los textos escritos en medio de una línea (ej. \"emplea\") son la "
    "etiqueta de la relación: no son clases ni atributos, aunque queden "
    "dibujados cerca o encima de una caja. Completá \"etiqueta\" con ese "
    "texto tal cual, o null si la línea no tiene ninguno."
)

_ESQUEMA_ATRIBUTO = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string"},
        "tipo": {"type": ["string", "null"], "description": "Tipo de dato tal como aparece, o null si no se indica."},
    },
    "required": ["nombre", "tipo"],
    "additionalProperties": False,
}

_ESQUEMA_METODO = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string"},
        "tipo_retorno": {"type": ["string", "null"]},
    },
    "required": ["nombre", "tipo_retorno"],
    "additionalProperties": False,
}

_ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "reconocido": {
            "type": "boolean",
            "description": "true si la imagen contiene al menos una clase UML identificable.",
        },
        "mensaje": {"type": "string"},
        "clases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "atributos": {"type": "array", "items": _ESQUEMA_ATRIBUTO},
                    "metodos": {"type": "array", "items": _ESQUEMA_METODO},
                },
                "required": ["nombre", "atributos", "metodos"],
                "additionalProperties": False,
            },
        },
        "relaciones": {
            "type": "array",
            "items": {
                "type": "object",
                # El ORDEN de las propiedades importa (el modelo genera la
                # respuesta campo por campo, en este orden): cada
                # multiplicidad va inmediatamente después del nombre de SU
                # clase, y con un nombre explícito ("junto a la clase X").
                # Con "clase_origen, clase_destino, tipo, multiplicidad_origen,
                # multiplicidad_destino" el modelo volvía a razonar por el
                # significado ("un gimnasio tiene muchos entrenadores") y las
                # devolvía invertidas de forma sistemática -- medido con una
                # imagen real, ver docstring del módulo.
                "properties": {
                    "clase_origen": {"type": "string"},
                    "multiplicidad_junto_a_clase_origen": {"type": ["string", "null"], "enum": [*sorted(MULTIPLICIDADES_VALIDAS), None]},
                    "clase_destino": {"type": "string"},
                    "multiplicidad_junto_a_clase_destino": {"type": ["string", "null"], "enum": [*sorted(MULTIPLICIDADES_VALIDAS), None]},
                    "tipo": {"type": "string", "enum": [t.value for t in TipoRelacion]},
                    "etiqueta": {"type": ["string", "null"]},
                    "clase_extremo_marcado": {"type": ["string", "null"]},
                },
                "required": [
                    "clase_origen",
                    "multiplicidad_junto_a_clase_origen",
                    "clase_destino",
                    "multiplicidad_junto_a_clase_destino",
                    "tipo",
                    "etiqueta",
                    "clase_extremo_marcado",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reconocido", "mensaje", "clases", "relaciones"],
    "additionalProperties": False,
}

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "reconocimiento_diagrama", "schema": _ESQUEMA_RESPUESTA, "strict": True},
}


def _mismo_nombre(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and normalizar_nombre(a) == normalizar_nombre(b)


# Con `"detail": "high"`, la API de OpenAI encaja la imagen en 2048x2048 y
# después la reduce hasta que su lado corto mida 768px, pero NUNCA la
# agranda: una captura chica (p. ej. 660x440) llega con muy pocos píxeles
# por número de multiplicidad o por trazo de línea. Se agranda acá hasta ese
# lado corto de 768 (más no sirve, la API la volvería a achicar). Medido con
# una captura real de 660x440: agrandada, los atributos salieron perfectos
# en 3 de 3 intentos.
_LADO_CORTO_OBJETIVO = 768
_LADO_LARGO_MAXIMO = 2048


def _preparar_imagen(contenido: bytes, content_type: str) -> tuple[bytes, str]:
    """Devuelve la imagen a mandar al modelo: agrandada si es chica (ver
    arriba), o la original sin tocar si ya alcanza. Lanza
    `ImagenInvalidaError` si el archivo no es una imagen legible (antes se
    mandaba igual a OpenAI y fallaba recién ahí, gastando la llamada)."""
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen.load()
            ancho, alto = imagen.size
            factor = min(_LADO_CORTO_OBJETIVO / min(ancho, alto), _LADO_LARGO_MAXIMO / max(ancho, alto))
            if factor <= 1:
                return contenido, content_type
            agrandada = imagen.convert("RGB").resize(
                (round(ancho * factor), round(alto * factor)), Image.Resampling.LANCZOS
            )
    except (UnidentifiedImageError, OSError, ValueError, ZeroDivisionError) as err:
        raise ImagenInvalidaError("No se pudo leer la imagen. Probá con otro archivo JPG, PNG o WEBP.") from err

    salida = io.BytesIO()
    agrandada.save(salida, format="PNG")
    return salida.getvalue(), "image/png"


def _validar_imagen(contenido: bytes, content_type: str | None) -> None:
    if content_type not in TIPOS_IMAGEN_PERMITIDOS:
        raise ImagenInvalidaError(
            f'Formato de imagen no soportado ("{content_type or "desconocido"}"). Usa JPG, PNG o WEBP.'
        )
    if not contenido:
        raise ImagenInvalidaError("El archivo está vacío.")
    if len(contenido) > TAMANIO_MAXIMO_BYTES:
        raise ImagenInvalidaError("La imagen es demasiado grande (máximo 10MB).")


def _relacion_desde_modelo(crudo: dict) -> dict:
    """Traduce una relación tal como la devuelve el modelo (con los nombres
    de campo explícitos de `_ESQUEMA_RESPUESTA`) al shape de
    `RelacionDetectadaIO` que usa el resto del sistema (vista previa,
    confirmación, frontend) -- el contrato de la API no cambia."""
    return {
        "clase_origen": crudo["clase_origen"],
        "clase_destino": crudo["clase_destino"],
        "tipo": crudo["tipo"],
        "etiqueta": (crudo.get("etiqueta") or "").strip() or None,
        "multiplicidad_origen": crudo["multiplicidad_junto_a_clase_origen"],
        "multiplicidad_destino": crudo["multiplicidad_junto_a_clase_destino"],
        "clase_extremo_marcado": crudo.get("clase_extremo_marcado"),
    }


def _llamar_openai_reconocimiento(contenido: bytes, content_type: str) -> ReconocimientoFotoResultado:
    """Llamada principal (extracción completa) al SDK de OpenAI -- junto con
    `_verificar_extremos_marcados` de más abajo, son los dos únicos puntos
    que le pegan a la API real; ambos se monkeypatchean en los tests, mismo
    patrón que `comandos_voz._llamar_openai`/`agente._llamar_openai_agente`."""
    if not settings.OPENAI_API_KEY:
        raise ComandoVozNoDisponibleError("OPENAI_API_KEY no está configurada en el servidor.")

    data_url = f"data:{content_type};base64,{base64.b64encode(contenido).decode('ascii')}"
    cliente = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=settings.OPENAI_VISION_MODEL,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Interpretá el diagrama de clases UML de esta imagen."},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                },
            ],
            response_format=_RESPONSE_FORMAT,
        )
    except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as err:
        raise ComandoVozNoDisponibleError(str(err)) from err

    contenido_json = respuesta.choices[0].message.content
    try:
        crudo = json.loads(contenido_json)
        crudo["relaciones"] = [_relacion_desde_modelo(r) for r in crudo.get("relaciones", [])]
        return ReconocimientoFotoResultado(**crudo)
    except (json.JSONDecodeError, ValidationError, TypeError, KeyError, AttributeError) as err:
        raise ComandoVozNoDisponibleError(f"Respuesta inesperada del modelo de reconocimiento: {err}") from err


_PROMPT_VERIFICACION_EXTREMOS = (
    "Vas a revisar de nuevo la misma imagen de un diagrama de clases UML, "
    "pero esta vez SOLO te importa el marcador de cada relación de la lista "
    "de abajo -- el triángulo hueco si es HERENCIA, el rombo (hueco o "
    "relleno) si es AGREGACION/COMPOSICION. Mirá con cuidado los dos "
    "extremos exactos de la línea que une esas dos clases; no te guíes por "
    "ninguna convención ni por lo que las clases parezcan significar.\n\n"
    "Para cada relación respondé:\n"
    "- \"marcador_visible\": \"SI\" si en alguno de los dos extremos de esa "
    "línea hay dibujado un triángulo o un rombo; \"NO\" si la línea es "
    "simple (termina sin ningún símbolo en ambos extremos); \"NO_SE\" si de "
    "verdad no se distingue.\n"
    "- \"clase_extremo_marcado\": el nombre EXACTO (tal cual está escrito) "
    "de la clase donde está el marcador, o null si no hay marcador o no se "
    "puede determinar. Nunca respondas un nombre que no sea una de las dos "
    "clases de esa misma relación."
)

_ESQUEMA_VERIFICACION_EXTREMOS = {
    "type": "object",
    "properties": {
        "extremos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indice": {"type": "integer"},
                    "marcador_visible": {"type": "string", "enum": ["SI", "NO", "NO_SE"]},
                    "clase_extremo_marcado": {"type": ["string", "null"]},
                },
                "required": ["indice", "marcador_visible", "clase_extremo_marcado"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["extremos"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ExtremoVerificado:
    """Resultado de `_verificar_extremos_marcados` para una relación
    dirigida: la clase donde está el marcador (None si no se pudo
    determinar) y si de verdad hay un marcador dibujado (None si no se
    sabe) -- ver `_aplicar_verificacion`."""

    clase: str | None
    marcador_visible: bool | None = None


_SIN_VERIFICAR = ExtremoVerificado(clase=None, marcador_visible=None)


def _verificar_extremos_marcados(
    contenido: bytes, content_type: str, relaciones: list[RelacionDetectadaIO]
) -> list[ExtremoVerificado]:
    """Segunda pasada de OpenAI, enfocada solo en el marcador (triángulo o
    rombo) de cada relación dirigida -- ver el docstring del módulo para el
    porqué. Devuelve una lista paralela a `relaciones`: el nombre de clase
    verificado (None si el modelo no lo pudo determinar, alucinó un nombre
    que no pertenece a esa relación, o la llamada falló entera) y si hay un
    marcador dibujado de verdad (None si no se sabe). Nunca
    lanza hacia arriba: cualquier falla acá degrada a "no se pudo verificar"
    (el caller se queda con el valor de la primera pasada), no es un error
    fatal para la vista previa completa."""
    lista = [
        {"indice": i, "clase_a": r.clase_origen, "clase_b": r.clase_destino, "tipo": r.tipo.value}
        for i, r in enumerate(relaciones)
    ]
    data_url = f"data:{content_type};base64,{base64.b64encode(contenido).decode('ascii')}"
    cliente = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=settings.OPENAI_VISION_MODEL,
            messages=[
                {"role": "system", "content": _PROMPT_VERIFICACION_EXTREMOS},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Relaciones a revisar: {json.dumps(lista, ensure_ascii=False)}",
                        },
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "verificacion_extremos", "schema": _ESQUEMA_VERIFICACION_EXTREMOS, "strict": True},
            },
        )
        crudo = json.loads(respuesta.choices[0].message.content)
    except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError, json.JSONDecodeError, TypeError, KeyError):
        return [_SIN_VERIFICAR] * len(relaciones)

    por_indice: dict[int, dict] = {}
    for item in crudo.get("extremos", []):
        indice = item.get("indice")
        if isinstance(indice, int) and 0 <= indice < len(relaciones):
            por_indice[indice] = item

    resultado: list[ExtremoVerificado] = []
    for i, r in enumerate(relaciones):
        item = por_indice.get(i, {})
        valor = item.get("clase_extremo_marcado")
        # Se devuelve con la grafía de la propia relación (no la que usó el
        # modelo al verificar), para que coincida con el resto del resultado.
        clase = next((n for n in (r.clase_origen, r.clase_destino) if _mismo_nombre(valor, n)), None)
        resultado.append(
            ExtremoVerificado(
                clase=clase,
                marcador_visible={"SI": True, "NO": False}.get(item.get("marcador_visible")),
            )
        )
    return resultado


def _sin_clases_duplicadas(clases: list[ClaseDetectadaIO]) -> list[ClaseDetectadaIO]:
    """El modelo de visión ocasionalmente repite una clase idéntica dos
    veces en el mismo resultado (mismo nombre y mismos atributos/métodos --
    verificado empíricamente, ver limitaciones documentadas). Un duplicado
    EXACTO nunca es información real (un diagrama no tiene dos clases con el
    mismo nombre y los mismos atributos), así que se colapsa acá antes de
    mostrar la vista previa. Dos clases con el mismo nombre pero atributos
    distintos NO se tocan -- eso sí podría ser una ambigüedad real de la
    imagen, y el usuario la revisa en la vista previa."""
    vistas: set[tuple] = set()
    resultado = []
    for c in clases:
        clave = (
            normalizar_nombre(c.nombre),
            tuple((normalizar_nombre(a.nombre), a.tipo) for a in c.atributos),
            tuple((normalizar_nombre(m.nombre), m.tipo_retorno) for m in c.metodos),
        )
        if clave in vistas:
            continue
        vistas.add(clave)
        resultado.append(c)
    return resultado


def reconocer_diagrama(contenido: bytes, content_type: str | None) -> ReconocimientoFotoResultado:
    """Solo lectura -- nunca persiste nada. Devuelve la vista previa que el
    frontend muestra antes de confirmar."""
    _validar_imagen(contenido, content_type)
    contenido, content_type = _preparar_imagen(contenido, content_type)
    resultado = _llamar_openai_reconocimiento(contenido, content_type)
    resultado.clases = _sin_clases_duplicadas(resultado.clases)

    if not resultado.reconocido or not resultado.clases:
        raise ImagenInvalidaError(
            resultado.mensaje or "No se reconoció ningún diagrama de clases UML en la imagen."
        )

    resultado.relaciones = _sin_relaciones_duplicadas(resultado.relaciones)
    _revisar_relaciones_con_fk(contenido, content_type, resultado)
    _sin_multiplicidad_en_herencia(resultado.relaciones)

    relaciones_dirigidas =[r for r in resultado.relaciones if r.tipo != TipoRelacion.ASOCIACION]
    if relaciones_dirigidas:
        # `_verificar_extremos_marcados` ya atrapa las fallas esperables de
        # la llamada a OpenAI (red, rate limit, JSON inválido) y devuelve
        # puros `None` en ese caso -- este try/except es una segunda red de
        # seguridad por si algo *inesperado* la hace fallar igual (ej. un
        # cambio futuro que se le escape a esa lista de excepciones): la
        # verificación es un chequeo opcional, nunca puede tirar abajo la
        # vista previa completa.
        try:
            verificados = _verificar_extremos_marcados(contenido, content_type, relaciones_dirigidas)
        except Exception:
            verificados = [_SIN_VERIFICAR] * len(relaciones_dirigidas)
        for relacion, verificado in zip(relaciones_dirigidas, verificados):
            advertencia = _aplicar_verificacion(relacion, verificado)
            if advertencia:
                resultado.advertencias.append(advertencia)

    resultado.mensaje = _mensaje_resumen(resultado)
    return resultado


def _sin_multiplicidad_en_herencia(relaciones: list[RelacionDetectadaIO]) -> None:
    """Una generalización UML no tiene multiplicidad: si el modelo le puso
    alguna (p. ej. leyó un número de otra línea cercana), se descarta acá en
    código -- no se confía solo en la regla del prompt."""
    for r in relaciones:
        if r.tipo == TipoRelacion.HERENCIA:
            r.multiplicidad_origen = None
            r.multiplicidad_destino = None


def _aplicar_verificacion(relacion: RelacionDetectadaIO, verificado: ExtremoVerificado) -> str | None:
    """Aplica a una relación dirigida el resultado de la verificación
    enfocada. Devuelve una advertencia para la vista previa si se le cambió
    el tipo, o None.

    - Si la verificación vio una línea SIMPLE (`marcador_visible=False`), la
      relación se baja a ASOCIACION. Es el caso de una composición/
      agregación "inventada" por la pasada principal: el modelo infiere un
      todo-parte por el significado de las clases sin que haya ningún rombo
      dibujado (visto en pruebas reales). Se baja y no al revés a propósito:
      una asociación de más es un error menor y visible, una composición
      inventada cambia el borrado en cascada del backend generado (CU08).
    - "No se sabe" (`None`) nunca cambia el tipo: queda lo de la pasada
      principal, que ya aplicó la regla "sin rombo claro → ASOCIACION".
    - El nombre verificado se revalida acá también (no solo dentro de
      `_verificar_extremos_marcados`): defensa en profundidad, nunca se
      aplica un nombre que no pertenezca a esta relación."""
    if verificado.marcador_visible is False:
        tipo_anterior = relacion.tipo
        relacion.tipo = TipoRelacion.ASOCIACION
        relacion.clase_extremo_marcado = None
        return (
            f"La relación {relacion.clase_origen} – {relacion.clase_destino} se detectó como "
            f"{tipo_anterior.value.lower()}, pero al revisarla no se ve ningún rombo ni triángulo "
            "dibujado: se tomó como asociación."
        )
    if _mismo_nombre(verificado.clase, relacion.clase_origen) or _mismo_nombre(verificado.clase, relacion.clase_destino):
        relacion.clase_extremo_marcado = verificado.clase
    return None


def _sin_relaciones_duplicadas(relaciones: list[RelacionDetectadaIO]) -> list[RelacionDetectadaIO]:
    """El modelo a veces reporta la misma línea dos veces, incluso con las
    clases en orden inverso (medido: "Clase–Inscripcion" e
    "Inscripcion–Clase" en la misma respuesta) -- aplicado tal cual, quedaría
    una línea duplicada en el diagrama. Se colapsa: mismo par de clases (sin
    importar el orden), mismo tipo y misma etiqueta. La etiqueta es lo que
    distingue dos relaciones REALES entre el mismo par (ej. "Miembro presta
    Libro" y "Miembro reserva Libro"): solo se colapsan si las etiquetas son
    iguales o si alguna de las dos no tiene. Del duplicado se aprovechan las
    multiplicidades que le falten a la que se conserva, ancladas por nombre
    de clase (no por posición, porque puede venir en orden inverso)."""
    conservadas: list[RelacionDetectadaIO] = []
    for r in relaciones:
        par = frozenset((normalizar_nombre(r.clase_origen), normalizar_nombre(r.clase_destino)))
        igual = next(
            (
                c
                for c in conservadas
                if c.tipo == r.tipo
                and frozenset((normalizar_nombre(c.clase_origen), normalizar_nombre(c.clase_destino))) == par
                and (not c.etiqueta or not r.etiqueta or normalizar_nombre(c.etiqueta) == normalizar_nombre(r.etiqueta))
            ),
            None,
        )
        if igual is None:
            conservadas.append(r)
            continue
        junto_a = {
            normalizar_nombre(r.clase_origen): r.multiplicidad_origen,
            normalizar_nombre(r.clase_destino): r.multiplicidad_destino,
        }
        igual.multiplicidad_origen = igual.multiplicidad_origen or junto_a.get(normalizar_nombre(igual.clase_origen))
        igual.multiplicidad_destino = igual.multiplicidad_destino or junto_a.get(normalizar_nombre(igual.clase_destino))
        igual.etiqueta = igual.etiqueta or r.etiqueta
    return conservadas


_PROMPT_VERIFICACION_LINEAS = (
    "Vas a revisar de nuevo la misma imagen de un diagrama de clases UML. "
    "Para cada par de clases de la lista de abajo, SOLO te importa una "
    "pregunta: ¿hay una línea dibujada cuyos DOS extremos tocan exactamente "
    "esas dos cajas?\n\n"
    "- \"existe\": \"SI\" si hay una línea que empieza en una de esas cajas y "
    "termina en la otra. \"NO\" si no la hay. No cuenta una línea que solo "
    "pasa cerca o por detrás de una de las dos cajas y en realidad termina "
    "en una tercera caja: seguí cada línea de punta a punta, sobre todo "
    "donde se cruza con otras. \"NO_SE\" si de verdad no se distingue.\n"
    "- Si existe: las multiplicidades escritas PEGADAS al extremo de esa "
    "línea junto a cada clase (null si no hay nada escrito), el tipo de "
    "relación según el símbolo dibujado (sin rombo ni triángulo claro es "
    "ASOCIACION) y el texto escrito en medio de la línea como etiqueta (o "
    "null). Si no existe, dejá esos campos en null y el tipo en ASOCIACION.\n"
    "- En \"clase_a\"/\"clase_b\" repetí los nombres del par tal cual te "
    "llegaron."
)

_ESQUEMA_VERIFICACION_LINEAS = {
    "type": "object",
    "properties": {
        "lineas": {
            "type": "array",
            "items": {
                "type": "object",
                # Mismo criterio de orden que `_ESQUEMA_RESPUESTA`: cada
                # multiplicidad inmediatamente después del nombre de su clase.
                "properties": {
                    "indice": {"type": "integer"},
                    "existe": {"type": "string", "enum": ["SI", "NO", "NO_SE"]},
                    "clase_a": {"type": "string"},
                    "multiplicidad_junto_a_clase_a": {"type": ["string", "null"], "enum": [*sorted(MULTIPLICIDADES_VALIDAS), None]},
                    "clase_b": {"type": "string"},
                    "multiplicidad_junto_a_clase_b": {"type": ["string", "null"], "enum": [*sorted(MULTIPLICIDADES_VALIDAS), None]},
                    "tipo": {"type": "string", "enum": [t.value for t in TipoRelacion]},
                    "etiqueta": {"type": ["string", "null"]},
                },
                "required": [
                    "indice",
                    "existe",
                    "clase_a",
                    "multiplicidad_junto_a_clase_a",
                    "clase_b",
                    "multiplicidad_junto_a_clase_b",
                    "tipo",
                    "etiqueta",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lineas"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LineaVerificada:
    """Resultado de `_verificar_lineas` para un par de clases. `existe` es
    None si no se sabe (o la verificación falló)."""

    existe: bool | None
    tipo: TipoRelacion = TipoRelacion.ASOCIACION
    etiqueta: str | None = None
    # multiplicidad escrita junto a cada clase, por nombre normalizado
    multiplicidades: tuple[tuple[str, str | None], ...] = ()

    def multiplicidad_junto_a(self, clase: str) -> str | None:
        return dict(self.multiplicidades).get(normalizar_nombre(clase))


_LINEA_SIN_VERIFICAR = LineaVerificada(existe=None)


def _verificar_lineas(contenido: bytes, content_type: str, pares: list[tuple[str, str]]) -> list[LineaVerificada]:
    """Pregunta enfocada sobre la imagen (tercera llamada, solo si hace
    falta): para cada par de clases, ¿hay una línea que las una
    directamente? La usa `_revisar_relaciones_con_fk` para confirmar o
    descartar lo que sugieren los atributos clave foránea -- ver
    `app/services/deduccion_fk.py`. Mismo criterio defensivo que
    `_verificar_extremos_marcados`: nunca lanza, cualquier falla es "no se
    sabe" y no cambia nada."""
    lista = [{"indice": i, "clase_a": a, "clase_b": b} for i, (a, b) in enumerate(pares)]
    data_url = f"data:{content_type};base64,{base64.b64encode(contenido).decode('ascii')}"
    cliente = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=settings.OPENAI_VISION_MODEL,
            messages=[
                {"role": "system", "content": _PROMPT_VERIFICACION_LINEAS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Pares a revisar: {json.dumps(lista, ensure_ascii=False)}"},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "verificacion_lineas", "schema": _ESQUEMA_VERIFICACION_LINEAS, "strict": True},
            },
        )
        crudo = json.loads(respuesta.choices[0].message.content)
    except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError, json.JSONDecodeError, TypeError, KeyError):
        return [_LINEA_SIN_VERIFICAR] * len(pares)

    por_indice = {
        item.get("indice"): item
        for item in crudo.get("lineas", [])
        if isinstance(item.get("indice"), int) and 0 <= item["indice"] < len(pares)
    }
    resultado: list[LineaVerificada] = []
    for i, (a, b) in enumerate(pares):
        item = por_indice.get(i)
        if item is None:
            resultado.append(_LINEA_SIN_VERIFICAR)
            continue
        # Multiplicidades ancladas por el nombre que el modelo repitió al
        # lado de cada una (no por posición): si invirtió el par, igual
        # quedan junto a la clase correcta. Un nombre que no es de este par
        # se ignora.
        multiplicidades = tuple(
            (normalizar_nombre(item.get(clave_clase) or ""), item.get(clave_mult))
            for clave_clase, clave_mult in (
                ("clase_a", "multiplicidad_junto_a_clase_a"),
                ("clase_b", "multiplicidad_junto_a_clase_b"),
            )
            if _mismo_nombre(item.get(clave_clase), a) or _mismo_nombre(item.get(clave_clase), b)
        )
        try:
            tipo = TipoRelacion(item.get("tipo"))
        except ValueError:
            tipo = TipoRelacion.ASOCIACION
        resultado.append(
            LineaVerificada(
                existe={"SI": True, "NO": False}.get(item.get("existe")),
                tipo=tipo,
                etiqueta=(item.get("etiqueta") or "").strip() or None,
                multiplicidades=multiplicidades,
            )
        )
    return resultado


def _revisar_relaciones_con_fk(contenido: bytes, content_type: str, resultado: ReconocimientoFotoResultado) -> None:
    """Contrasta las relaciones que vio el modelo con los atributos clave
    foránea del propio diagrama (ver `app/services/deduccion_fk.py`):

    - relación SOSPECHOSA (las dos clases declaran claves foráneas pero
      ninguna referencia a la otra, y no es herencia) → se quita, sin
      preguntarle a la imagen: medido contra la API real, una línea que pasa
      por detrás de una caja engaña también a la pregunta enfocada (ver el
      docstring de `deduccion_fk.py`). Decisión de la usuaria.
    - relación FALTANTE (un `id_x` sin su línea reportada) → se le pregunta
      a la imagen (`_verificar_lineas`), y solo se agrega si confirma que la
      línea existe (de ahí salen sus multiplicidades). "No sé" o una falla
      de la verificación no agregan nada.

    Cada cambio queda en `resultado.advertencias` y en el log."""
    for pista in clases_referenciadas_no_detectadas(resultado.clases):
        resultado.advertencias.append(
            f'"{pista.clase}" tiene el atributo "{pista.atributo}", pero no se detectó ninguna clase '
            f'"{pista.referenciada}": revisá si falta en la imagen.'
        )

    revision = revisar_con_fk(resultado.clases, resultado.relaciones)

    for indice in revision.sospechosas:
        relacion = resultado.relaciones[indice]
        mensaje = (
            f"Se quitó la relación {relacion.clase_origen} – {relacion.clase_destino}: las dos clases declaran "
            "sus claves foráneas (atributos id_...) pero ninguna referencia a la otra, así que es casi seguro "
            "una línea mal leída. Si la relación era real, agregala a mano."
        )
        logger.info("CU12: %s", mensaje)
        resultado.advertencias.append(mensaje)
    quitar = set(revision.sospechosas)
    resultado.relaciones = [r for i, r in enumerate(resultado.relaciones) if i not in quitar]

    if not revision.faltantes:
        return
    pares = [(p.referenciada, p.clase) for p in revision.faltantes]
    # Mismo criterio que la verificación de marcadores: una falla inesperada
    # nunca tira abajo la vista previa, simplemente no se agrega nada.
    try:
        verificadas = _verificar_lineas(contenido, content_type, pares)
    except Exception:
        logger.exception("CU12: falló la verificación de líneas por claves foráneas")
        return

    agregadas: list[RelacionDetectadaIO] = []
    for pista, linea in zip(revision.faltantes, verificadas):
        if linea.existe is True:
            agregadas.append(
                RelacionDetectadaIO(
                    clase_origen=pista.referenciada,
                    clase_destino=pista.clase,
                    tipo=linea.tipo,
                    etiqueta=linea.etiqueta,
                    multiplicidad_origen=linea.multiplicidad_junto_a(pista.referenciada),
                    multiplicidad_destino=linea.multiplicidad_junto_a(pista.clase),
                )
            )
            mensaje = (
                f"Se agregó la relación {pista.referenciada} – {pista.clase}: no se había detectado, pero "
                f'"{pista.clase}" tiene el atributo "{pista.atributo}" y al revisar la imagen sí hay una línea '
                "que las une."
            )
            logger.info("CU12: %s", mensaje)
            resultado.advertencias.append(mensaje)
        elif linea.existe is False:
            resultado.advertencias.append(
                f'"{pista.clase}" tiene el atributo "{pista.atributo}", pero no se encontró ninguna línea '
                f"hacia {pista.referenciada}: revisá si falta esa relación."
            )

    resultado.relaciones = resultado.relaciones + agregadas


def _mensaje_resumen(resultado: ReconocimientoFotoResultado) -> str:
    """El resumen lo arma el código, no el modelo: después de colapsar
    duplicados y de la revisión por claves foráneas, los números que dio el
    modelo ya no son los que se muestran."""
    n_clases, n_rel = len(resultado.clases), len(resultado.relaciones)
    return (
        f"Se detectaron {n_clases} {'clase' if n_clases == 1 else 'clases'} y "
        f"{n_rel} {'relación' if n_rel == 1 else 'relaciones'}."
    )


def _corregir_direccion_por_extremo_marcado(
    tipo: TipoRelacion, origen_id: str, destino_id: str, extremo_marcado_id: str | None
) -> tuple[str, str, bool]:
    """Corrige de forma determinística el origen/destino de una relación
    dirigida a partir de `clase_extremo_marcado` (la clase donde el modelo
    vio el triángulo/rombo) -- una pregunta mucho más simple y directamente
    observable para un modelo de visión que "acordate cuál nombre va
    primero según la convención origen/destino", que es probabilística y
    puede fallar (ver encabezado del módulo). Si `extremo_marcado_id` es
    None, o no coincide con ninguna de las dos clases de la relación (el
    modelo no lo completó, o alucinó un tercer nombre), se deja el orden
    tal cual vino -- nunca se inventa nada. El tercer valor devuelto indica
    si se invirtió el orden, para que el caller invierta también las
    multiplicidades (van pegadas a cada extremo, no pueden quedar sueltas)."""
    if extremo_marcado_id is None:
        return origen_id, destino_id, False
    if tipo == TipoRelacion.HERENCIA:
        # destino = superclase = extremo marcado (triángulo).
        if extremo_marcado_id == origen_id:
            return destino_id, origen_id, True
        return origen_id, destino_id, False
    if tipo in (TipoRelacion.AGREGACION, TipoRelacion.COMPOSICION):
        # origen = "todo" = extremo marcado (rombo).
        if extremo_marcado_id == destino_id:
            return destino_id, origen_id, True
        return origen_id, destino_id, False
    return origen_id, destino_id, False


def _nombre_disponible(nombre: str, tomados: set[str]) -> str:
    base = nombre.strip()
    candidato = base
    sufijo = 2
    while normalizar_nombre(candidato) in tomados:
        candidato = f"{base} {sufijo}"
        sufijo += 1
    return candidato


def aplicar_reconocimiento(proyecto_id: int, resultado: ReconocimientoFotoResultado, db: Session) -> ConfirmarReconocimientoResultado:
    """Persiste las clases/relaciones de `resultado` AGREGÁNDOLAS al
    diagrama actual del proyecto (nunca lo reemplaza ni exige que esté
    vacío, a diferencia de la importación XMI de CU09) reutilizando
    `guardar_diagrama`. Ver criterio de colisión de nombres en el docstring
    del módulo."""
    clases_validas = [c for c in resultado.clases if c.nombre.strip()]
    if not clases_validas:
        raise ImagenInvalidaError("No hay clases para agregar al diagrama.")

    diagrama_actual = cargar_diagrama(proyecto_id, db)
    nombres_tomados = {normalizar_nombre(c.nombre) for c in diagrama_actual.clases}
    advertencias: list[str] = []

    # Construcción envuelta en un único try/except: si algún campo detectado
    # excede las validaciones de Pydantic (nombre/tipo demasiado largo), se
    # traduce a un 400 claro en vez de dejar escapar un 500 crudo.
    try:
        nuevas_clases: list[ClaseIO] = []
        mapa_nombre_a_id: dict[str, str] = {}
        indice_base = len(diagrama_actual.clases)

        for i, c in enumerate(clases_validas):
            nombre_final = _nombre_disponible(c.nombre, nombres_tomados)
            if normalizar_nombre(nombre_final) != normalizar_nombre(c.nombre):
                advertencias.append(
                    f'Se renombró "{c.nombre}" a "{nombre_final}" porque ya existía una clase con ese nombre.'
                )
            nombres_tomados.add(normalizar_nombre(nombre_final))

            nueva_id = str(uuid4())
            # Clave normalizada: una relación que escribe el nombre con otra
            # tilde/mayúscula ("Prestamo" vs "Préstamo") igual se conecta.
            mapa_nombre_a_id[normalizar_nombre(c.nombre)] = nueva_id
            pos_x, pos_y = _posicion_en_grilla(indice_base + i)
            nuevas_clases.append(
                ClaseIO(
                    id=nueva_id,
                    nombre=nombre_final,
                    pos_x=pos_x,
                    pos_y=pos_y,
                    atributos=[
                        AtributoIO(id=str(uuid4()), nombre=a.nombre, tipo=a.tipo, orden=idx)
                        for idx, a in enumerate(c.atributos)
                        if a.nombre.strip()
                    ],
                    metodos=[
                        MetodoIO(id=str(uuid4()), nombre=m.nombre, tipo_retorno=m.tipo_retorno, orden=idx)
                        for idx, m in enumerate(c.metodos)
                        if m.nombre.strip()
                    ],
                )
            )

        nuevas_relaciones: list[RelacionIO] = []
        for r in resultado.relaciones:
            origen_id = mapa_nombre_a_id.get(normalizar_nombre(r.clase_origen))
            destino_id = mapa_nombre_a_id.get(normalizar_nombre(r.clase_destino))
            if origen_id is None or destino_id is None:
                advertencias.append(
                    f'Se descartó una relación porque no se pudo identificar "{r.clase_origen}" o '
                    f'"{r.clase_destino}" entre las clases detectadas en la imagen.'
                )
                continue

            extremo_marcado_id = (
                mapa_nombre_a_id.get(normalizar_nombre(r.clase_extremo_marcado)) if r.clase_extremo_marcado else None
            )
            origen_id, destino_id, invertido = _corregir_direccion_por_extremo_marcado(
                r.tipo, origen_id, destino_id, extremo_marcado_id
            )
            multiplicidad_origen_raw = r.multiplicidad_destino if invertido else r.multiplicidad_origen
            multiplicidad_destino_raw = r.multiplicidad_origen if invertido else r.multiplicidad_destino

            mult_origen = multiplicidad_origen_raw if multiplicidad_origen_raw in MULTIPLICIDADES_VALIDAS else None
            if multiplicidad_origen_raw and mult_origen is None:
                advertencias.append(f'Multiplicidad "{multiplicidad_origen_raw}" no reconocida, se omitió.')
            mult_destino = multiplicidad_destino_raw if multiplicidad_destino_raw in MULTIPLICIDADES_VALIDAS else None
            if multiplicidad_destino_raw and mult_destino is None:
                advertencias.append(f'Multiplicidad "{multiplicidad_destino_raw}" no reconocida, se omitió.')

            nuevas_relaciones.append(
                RelacionIO(
                    id=str(uuid4()),
                    id_clase_origen=origen_id,
                    id_clase_destino=destino_id,
                    tipo=r.tipo,
                    # La columna es String(100); una etiqueta mal leída más
                    # larga se recorta en vez de hacer fallar el guardado.
                    etiqueta=(r.etiqueta or "").strip()[:100] or None,
                    multiplicidad_origen=mult_origen,
                    multiplicidad_destino=mult_destino,
                )
            )

        diagrama_final = DiagramaIO(
            clases=diagrama_actual.clases + nuevas_clases,
            relaciones=diagrama_actual.relaciones + nuevas_relaciones,
        )
    except ValidationError as err:
        raise ImagenInvalidaError(
            "Algunos datos detectados en la imagen no son válidos para el diagrama (nombre o tipo demasiado largo)."
        ) from err

    guardar_diagrama(proyecto_id, diagrama_final, db)
    return ConfirmarReconocimientoResultado(diagrama=cargar_diagrama(proyecto_id, db), advertencias=advertencias)
