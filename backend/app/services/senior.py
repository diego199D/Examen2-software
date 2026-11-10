"""
Segundo parcial (RF-IA-01 a RF-IA-12) — la IA como Desarrollador Senior del
equipo, dentro del chat grupal público de la sala.

Este módulo arma el contexto y habla con Gemini; NO maneja sockets (eso es
`app/services/sala.py`). Puntos clave:

- **Cuándo responde**: si el mensaje la menciona (`@senior`, "Senior, ...",
  "oye senior ...") o se envió con el toggle "Preguntar al Senior"
  (`menciona_al_senior`). Los mensajes entre humanos no la disparan.
- **Contexto de cada llamada**: system prompt (§6.3, `PROMPT_SISTEMA`) +
  nombre del grupo + JSON actual del diagrama (con ids) + resumen de los
  mensajes viejos + últimos `HISTORIAL_N` mensajes como `[Autor]: texto` +
  nombre e id de quien pregunta. Así "¿y si le agregamos teléfono a la clase
  anterior?" se resuelve mirando la conversación.
- **Siempre se dirige a quien preguntó por su nombre** (RF-IA-04): se pide
  en el prompt y además `asegurar_saludo` lo verifica y antepone `@Nombre,`
  si el modelo no lo hizo.
- **Mutaciones**: herramienta `apply_diagram_mutations` (ver
  `app/services/mutaciones.py`). En modo `consultivo` no se le ofrece la
  herramienta: solo explica y sugiere.
- **Historial largo**: los mensajes que quedan fuera de la ventana se
  resumen (Gemini) y el resumen se guarda en el proyecto, en vez de cortarlos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.models.relacion import TipoRelacion
from app.schemas.diagrama import DiagramaIO
from app.services.ai import gemini_client
from app.services.mutaciones import ESQUEMA_HERRAMIENTA, TIPOS_CANONICOS
from app.services.nombres import normalizar_nombre

NOMBRE_SENIOR = "Senior"
HISTORIAL_N = 30
# Cuando hay más de este número de mensajes sin resumir, los que quedan
# fuera de la ventana de HISTORIAL_N se resumen.
UMBRAL_RESUMEN = 60
MODOS = ("consultivo", "con_confirmacion", "automatico")

_MENCION = re.compile(r"(^|[^\w@])@senior\b|^\s*[¡!¿?]*\s*(hola|oye|ey|che|buenas)?[\s,]*senior\b", re.IGNORECASE)


def menciona_al_senior(texto: str) -> bool:
    return bool(_MENCION.search(texto or ""))


def asegurar_saludo(texto: str, nombre: str) -> str:
    """RF-IA-04: la respuesta empieza dirigiéndose a quien preguntó."""
    texto = (texto or "").strip()
    primer_nombre = (nombre or "").split()[0] if (nombre or "").split() else nombre
    inicio = normalizar_nombre(re.sub(r"[^\w\s]", " ", texto[:60])).split()
    if primer_nombre and normalizar_nombre(primer_nombre) in inicio[:3]:
        return texto
    return f"@{primer_nombre}, {texto}" if texto else f"@{primer_nombre}"


PROMPT_SISTEMA = """Sos "Senior", un desarrollador de software senior que acompaña a un equipo de estudiantes \
mientras modelan un diagrama de clases UML en una herramienta colaborativa. Participás en el chat GRUPAL y \
público del equipo: todos leen lo que respondés. Hablás en español (Bolivia/Latinoamérica), con tono cercano \
y profesional.

Reglas obligatorias:
1. Empezá SIEMPRE tu respuesta dirigiéndote por su nombre a la persona que te preguntó (ej. "Juan, ..."). \
Respondé solo a esa persona; si en el historial hay preguntas de otros, no las mezcles.
2. Preguntas teóricas (qué es un atributo derivado, agregación vs composición, multiplicidad, herencia, \
clase de asociación, normalización, etc.): dá una definición clara y SIEMPRE un ejemplo concreto, de \
preferencia usando las clases del diagrama actual del equipo (si no hay clases que sirvan, inventá un ejemplo \
breve del mismo dominio).
3. Revisá el diseño como un senior: si ves problemas (relaciones mal dirigidas, multiplicidades dudosas, \
atributos que deberían ser relaciones, N:M que necesita clase de asociación), mencionalos brevemente.
4. "La clase anterior", "esa clase", "la que creaste" = la ÚLTIMA clase mencionada, creada o modificada en \
los últimos mensajes del chat (no la primera del diagrama). Releé el historial de abajo hacia arriba.
5. Modificá el diagrama SOLO si te lo piden explícitamente (agregar, crear, quitar, cambiar, relacionar...). \
Ante preguntas teóricas o de opinión NO uses la herramienta: explicá y, si querés, sugerí el cambio con palabras.
6. Sé conciso: no más de ~180 palabras salvo que pidan detalle. Texto plano: sin Markdown (nada de ** ni `), usá guiones para listas.

Convenciones del diagrama:
- Relaciones: association, inheritance (sourceId = subclase, targetId = superclase, sin cardinalidades), \
aggregation y composition (sourceId = el TODO, targetId = la PARTE; ej. Factura 1 ◆── 1..* DetalleFactura: \
sourceId Factura con sourceCardinality 1, targetId DetalleFactura con targetCardinality 1..*).
- Cardinalidades válidas: 1, 0..1, *, 0..*, 1..*. Muchos a muchos = ambos extremos plurales (*, 0..*, 1..*). \
Si el vínculo N:M tiene atributos propios (nota, fecha...), creá una clase de asociación y referenciala con \
associationClassId.
- Tipos de atributo válidos: {tipos}.
- Nombres de clase en PascalCase y de atributo en camelCase. No agregues un atributo "id": el generador lo crea.
"""

_INSTRUCCIONES_MODO = {
    "consultivo": (
        "MODO CONSULTIVO: NO podés modificar el diagrama. Si te piden un cambio, explicá exactamente qué "
        "habría que cambiar (clases, atributos, relaciones y cardinalidades) para que el equipo lo haga."
    ),
    "con_confirmacion": (
        "MODO CON CONFIRMACIÓN: si te piden un cambio, usá la herramienta apply_diagram_mutations. El cambio "
        "NO se aplica todavía: el equipo lo verá como propuesta y decidirá si aplicarlo. En `mensaje` explicá "
        "la propuesta en condicional o futuro (\"te propongo...\", \"agregaría...\"), nunca como algo ya hecho, "
        "dirigiéndote a quien preguntó."
    ),
    "automatico": (
        "MODO AUTOMÁTICO: si te piden un cambio, usá la herramienta apply_diagram_mutations; se aplica "
        "directamente. En `mensaje` explicá lo que hiciste dirigiéndote a quien preguntó."
    ),
}


@dataclass
class MensajeHistorial:
    autor: str
    es_ia: bool
    texto: str


@dataclass
class ContextoSenior:
    grupo: str
    modo: str
    diagrama: DiagramaIO
    historial: list[MensajeHistorial]
    resumen: str | None
    autor_id: int
    autor_nombre: str
    pregunta: str


@dataclass
class RespuestaSenior:
    texto: str
    acciones: list[dict] | None = None
    extra: dict = field(default_factory=dict)


_TIPO_EN = {
    TipoRelacion.ASOCIACION: "association",
    TipoRelacion.HERENCIA: "inheritance",
    TipoRelacion.AGREGACION: "aggregation",
    TipoRelacion.COMPOSICION: "composition",
}


def diagrama_para_prompt(diagrama: DiagramaIO) -> str:
    nombres = {c.id: c.nombre for c in diagrama.clases}
    datos = {
        "entities": [
            {
                "id": c.id,
                "name": c.nombre,
                "isAbstract": c.es_abstracta,
                "attributes": [{"id": a.id, "name": a.nombre, "type": a.tipo} for a in c.atributos],
            }
            for c in diagrama.clases
        ],
        "relationships": [
            {
                "id": r.id,
                "type": _TIPO_EN[r.tipo],
                "source": nombres.get(r.id_clase_origen),
                "sourceCardinality": r.multiplicidad_origen,
                "target": nombres.get(r.id_clase_destino),
                "targetCardinality": r.multiplicidad_destino,
                "label": r.etiqueta,
                "associationClass": nombres.get(r.id_clase_asociacion) if r.id_clase_asociacion else None,
            }
            for r in diagrama.relaciones
        ],
    }
    return json.dumps(datos, ensure_ascii=False)


def construir_prompt(ctx: ContextoSenior) -> tuple[str, str]:
    system = PROMPT_SISTEMA.format(tipos=", ".join(TIPOS_CANONICOS)) + "\n" + _INSTRUCCIONES_MODO[ctx.modo]
    partes = [
        f"Grupo: {ctx.grupo}",
        f"Diagrama actual (JSON):\n{diagrama_para_prompt(ctx.diagrama)}",
    ]
    if ctx.resumen:
        partes.append(f"Resumen de la conversación anterior:\n{ctx.resumen}")
    if ctx.historial:
        lineas = [f"[{NOMBRE_SENIOR if m.es_ia else m.autor}]: {m.texto}" for m in ctx.historial]
        partes.append("Últimos mensajes del chat del grupo:\n" + "\n".join(lineas))
    partes.append(
        f"Pregunta ACTUAL de {ctx.autor_nombre} (id de usuario {ctx.autor_id}), a quien tenés que "
        f"responderle por su nombre:\n[{ctx.autor_nombre}]: {ctx.pregunta}"
    )
    return system, "\n\n".join(partes)


def consultar_senior(ctx: ContextoSenior) -> RespuestaSenior:
    """Único punto con red de este módulo (se mockea en los tests)."""
    system, texto = construir_prompt(ctx)
    tools = [] if ctx.modo == "consultivo" else [ESQUEMA_HERRAMIENTA]
    respuesta = gemini_client.chat_with_tools(system, [("user", texto)], tools)
    for llamada in respuesta.llamadas:
        if llamada.nombre == "apply_diagram_mutations":
            args = llamada.argumentos or {}
            acciones = [dict(a) for a in (args.get("acciones") or [])]
            return RespuestaSenior(texto=str(args.get("mensaje") or ""), acciones=acciones)
    return RespuestaSenior(texto=respuesta.texto or "")


PROMPT_RESUMEN = (
    "Resumí en español, en no más de 12 viñetas, la conversación de un equipo que diseña un diagrama de clases "
    "con ayuda de un desarrollador Senior. Conservá decisiones de diseño, cambios hechos al diagrama, dudas "
    "abiertas y quién dijo qué cuando importe. Si hay un resumen previo, integralo."
)


def resumir(resumen_previo: str | None, mensajes: list[MensajeHistorial]) -> str:
    texto = ""
    if resumen_previo:
        texto += f"Resumen previo:\n{resumen_previo}\n\n"
    texto += "Mensajes:\n" + "\n".join(f"[{NOMBRE_SENIOR if m.es_ia else m.autor}]: {m.texto}" for m in mensajes)
    return gemini_client.generate_text(PROMPT_RESUMEN, texto).strip()
