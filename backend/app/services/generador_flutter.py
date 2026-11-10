"""
Generador de un proyecto Flutter (modelos, servicios HTTP, pantallas de
listado/formulario) a partir del diagrama de clases guardado de un proyecto
(CU15) — el mismo diagrama que ya consume el generador de backend Spring
Boot (CU08, `app/services/generador_spring.py`), pensado para consumir
exactamente ese backend generado: mismas rutas `/api/{plural}`, mismos
nombres de campo en el JSON.

Reutiliza de `generador_spring.py` las funciones de formateo de
identificadores (`nombre_clase_java`, `nombre_campo_java`, `a_snake_case`,
`pluralizar`, `slug_paquete`) y la constante `MULTIPLICIDADES_PLURALES` en
vez de reimplementarlas — a pesar del nombre "_java", son transformaciones
de texto agnósticas del lenguaje (PascalCase/camelCase/snake_case/plural a
partir de texto libre en español) y **tienen que** dar el mismo resultado
que el lado Spring Boot: si "Orden de compra" se convierte a una ruta
distinta en cada generador, la app Flutter generada le pega a un endpoint
que no existe. Por la misma razón, también reutiliza
`resolver_nombres_relaciones` para el nombre de campo/clave JSON de cada
relación: si el diagrama tiene más de una relación entre el mismo par de
clases (ej. "Miembro presta Libro" y "Miembro reserva Libro" en un sistema
de biblioteca — un patrón razonablemente común, no un caso de laboratorio),
el campo del lado "muchos" en Dart tiene que numerarse exactamente igual
que el campo Java correspondiente, porque ambos apuntan a la misma clave
JSON.

Limitaciones conocidas:
- Solo se genera un campo de referencia (`{campo}Id`, un id escalar) para
  relaciones **uno-a-uno** y **uno-a-muchos** — exactamente el lado que en
  CU08 termina con la FK (`@ManyToOne`/`@OneToOne` dueño). Relaciones
  **muchos-a-muchos** (multiplicidad plural en ambos extremos) no generan
  ningún campo: un id escalar no alcanza para representarlas, y una lista
  de ids con su propio widget de selección múltiple quedaba fuera del
  alcance de "un DropdownButtonFormField por relación" que pide la ficha.
- El lado "uno" de una relación no recibe un campo de lista con los
  objetos relacionados (a diferencia de CU08, que sí genera el
  `List<X>` inverso en la entidad JPA) — la ficha de CU15 solo pide el
  campo de referencia en el lado "muchos", no una vista maestro-detalle.
- El JSON que produce/espera el backend generado por CU08 representa una
  relación como el objeto anidado completo bajo el nombre de campo del
  lado dueño (Jackson por defecto), no como un id plano — ej.
  `{"direccion": {"id": 3}}`, no `{"direccionId": 3}`. El modelo Dart
  generado expone el campo como `int? direccionId` (más simple para el
  dropdown/formulario) pero `toJson`/`fromJson` empaquetan/desempaquetan
  ese id dentro del objeto anidado, para interoperar de verdad con el
  backend de CU08 sin tener que tocarlo.
- Los métodos UML (`Metodo`) no se reflejan en el modelo generado, igual
  que en CU08 — el CRUD estándar ya cubre listar/crear/editar/eliminar.
- Un atributo del diagrama llamado "id" se ignora al generar campos, por
  la misma razón que en CU08 (el modelo ya tiene su propio `int? id`).
- La app generada no incluye autenticación/JWT: pega directo a las rutas
  `/api/...` del backend de CU08, que tampoco lo tiene (ver limitaciones
  de CU08). Mejora futura pendiente si algún día CU08 suma seguridad.
- Todos los campos del modelo son nulleables (`String?`, `int?`, etc.), sin
  validación de obligatoriedad en el formulario — simplifica el
  constructor (no hay que resolver qué combinación de atributos es
  "requerida" a partir de un diagrama que no declara nulabilidad) y evita
  que datos incompletos que ya estén en el backend rompan el parseo.

El zip generado incluye la carpeta `android/` completa y lista para
correr (`flutter pub get` + `flutter run`, sin pasar por `flutter create .`
a mano) — ver la sección "Carpeta android/ generada" más abajo. **Es a
propósito solo Android**: no se genera `ios/`/`web`/desktop.

CU14 — modo offline (agrega capa de datos local a lo ya descrito arriba):
- Almacenamiento local: `sqflite` (SQLite embebido) — no necesita
  codegen/build_runner (a diferencia de Hive/Isar/Drift), lo que sería
  incómodo de generar como texto plano desde Python. Conectividad:
  `connectivity_plus`.
- Cada clase tiene una tabla SQLite propia. **Identidad local**: `localId`
  (uuid generado en el cliente) es la clave primaria local, siempre
  presente; `id` (el id numérico del backend) es nulo hasta sincronizar.
  **Las columnas de relación guardan siempre el `localId` del padre**,
  nunca su `id` de backend — la resolución a un id real ocurre solo al
  armar el pedido de sincronización, leyendo el `id` actual de la fila
  padre en ese momento. Si el padre todavía no sincronizó, el hijo se
  salta esa pasada y se reintenta solo (sin esperar un nuevo evento de
  conectividad: `SyncManager` repite pasadas hasta que una no logra
  ningún progreso).
- **Sin tabla de "cola" de operaciones separada** — el estado de
  sincronización vive como columnas en la propia fila de cada registro
  (`estadoSync` ∈ `sincronizado | pendienteCrear | pendienteActualizar |
  pendienteEliminar | fallidoCrear | fallidoActualizar | fallidoEliminar`,
  `errorSync`): una fila = un registro = a lo sumo una operación
  pendiente. Evita un log de eventos a reproducir (evita duplicar
  operaciones si el usuario edita el mismo registro varias veces
  offline) — el precio es que no hay historial: "Descartar" una
  actualización/eliminación fallida vuelve a pedir el registro real al
  backend (`obtenerPorId`) y sobrescribe la fila local con esa verdad, en
  vez de deshacer al valor anterior exacto; "Descartar" una creación
  fallida simplemente borra la fila local (nunca existió en el backend).
  Las filas `fallido*` NO se reintentan solas en cada sync (para no
  insistir con algo que ya se sabe que el backend rechaza) — el usuario
  las revisa en `SincronizacionScreen` ("Reintentar"/"Descartar").
- **Orden de sincronización entre clases**: calculado en Python
  (`_orden_topologico`, mismo criterio `_propietario_relacion` de arriba)
  y hardcodeado como el orden de llamadas en `sync_manager.dart` — las
  clases referenciadas ("uno") sincronizan antes que las que las
  referencian ("muchos", dueñas de la FK). Un ciclo real entre clases cae
  al orden de declaración original (no se resuelve automáticamente).
- Un atributo del diagrama llamado exactamente `localId`, `estadoSync` o
  `errorSync` (case-sensitive) chocaría con estos campos reservados — no
  se previene explícitamente, es un caso extremo no contemplado.
- Limitación de `refrescarDesdeRed`: solo hace upsert de lo que devuelve
  el backend contra el cache local — no borra localmente un registro que
  otro usuario haya borrado en el servidor (sin tombstones/reconciliación
  completa). El registro reaparecería recién si alguien más lo modifica y
  el próximo refresh lo vuelve a traer con datos distintos.

Carpeta android/ generada (pensada para poder probar la app sin más que
`flutter pub get` + `flutter run`):
- La mayor parte de la carpeta (Gradle, AGP, Kotlin, manifests, temas,
  ícono) es texto/binario 100% genérico, idéntico en cualquier proyecto
  Flutter recién creado — se vendorea tal cual, vino de un `flutter
  create` real hecho en esta máquina (`mobile/android/`, el proyecto
  Flutter de referencia que ya existía en este repo). Los únicos 3
  archivos con un dato específico del proyecto (`android/app/build.gradle.kts`
  namespace/applicationId, `MainActivity.kt` con su paquete/ruta de
  carpetas, y `AndroidManifest.xml` con `android:label`) se arman
  reemplazando un placeholder sobre una plantilla de texto (no con
  f-strings: el contenido real es Kotlin/XML lleno de `{`/`}` propios del
  lenguaje, que chocarían con la interpolación de Python).
- Lo único verdaderamente binario (`gradle-wrapper.jar`, ~53 KB, y los 5
  íconos `ic_launcher.png` por densidad — el ícono azul de Flutter por
  defecto, sin branding propio) no se puede generar como texto: se
  vendorea como archivos reales en `backend/app/services/plantillas_android/`
  y se leen con `Path.read_bytes()` al armar el zip.
- **No se bundlea `android/local.properties`** (tiene rutas absolutas de
  la máquina donde se generó, `sdk.dir`/`flutter.sdk`) — Flutter lo
  regenera solo, apuntando al Android SDK de quien lo use, la primera vez
  que corre `flutter run`/`flutter build`. Tampoco se bundlea `.gradle/`
  (caché) ni `GeneratedPluginRegistrant.java` (lo recrea el propio plugin
  de Gradle de Flutter en cada build) — ninguno de los dos existe en un
  `flutter create` recién hecho tampoco, tal como confirma el `.gitignore`
  vendoreado en `android/.gitignore`.
- Limitación conocida: Gradle 8.14 / AGP 8.11.1 / Kotlin 2.2.20 / JDK 17
  quedan **fijos** a lo que tenía instalado esta máquina al vendorear la
  plantilla — no se invoca `flutter create` en el servidor (cambio de
  infraestructura mucho mayor), así que si más adelante se actualiza el
  Flutter SDK local a algo bastante más nuevo, el scaffold generado podría
  no ser exactamente el que produciría un `flutter create .` fresco en
  ese momento. No debería impedir que compile/corra, solo podría no ser
  la combinación "más nueva posible".
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as _escapar_xml

from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion
from app.services.generador_spring import (
    MULTIPLICIDADES_PLURALES,
    a_snake_case,
    nombre_campo_java,
    nombre_clase_java,
    pluralizar,
    resolver_nombres_relaciones,
    slug_paquete,
)

# --------------------------------------------------------------------------
# Mapeo de tipos UML (texto libre en Atributo.tipo) a tipos Dart. Mismo
# criterio y mismo default seguro que MAPEO_TIPOS_JAVA en generador_spring.py
# — sinónimos en español/inglés que ya se aceptaban ahí.
# --------------------------------------------------------------------------

MAPEO_TIPOS_DART: dict[str, str] = {
    "string": "String",
    "str": "String",
    "texto": "String",
    "char": "String",
    "int": "int",
    "integer": "int",
    "entero": "int",
    "long": "int",
    "float": "double",
    "double": "double",
    "decimal": "double",
    "bigdecimal": "double",
    "boolean": "bool",
    "bool": "bool",
    "date": "DateTime",
    "fecha": "DateTime",
    "datetime": "DateTime",
    "fechahora": "DateTime",
    "timestamp": "DateTime",
    "uuid": "String",
}
TIPO_DART_POR_DEFECTO = "String"

# Expresión Dart para el `keyboardType:` de cada TextFormField, según el
# tipo Dart del atributo (la ficha pide "un campo de texto ... con el tipo
# de teclado apropiado", no un widget distinto por tipo — así que hasta
# bool y DateTime son TextFormField, con teclado/parseo acorde).
TECLADO_POR_TIPO_DART: dict[str, str] = {
    "String": "TextInputType.text",
    "int": "TextInputType.number",
    "double": "const TextInputType.numberWithOptions(decimal: true)",
    "bool": "TextInputType.text",
    "DateTime": "TextInputType.datetime",
}


# CU14 — tipo de columna SQLite para cada tipo Dart ya mapeado arriba. bool
# se guarda como INTEGER (0/1, sqflite no tiene tipo booleano nativo);
# DateTime como TEXT (ISO 8601), igual criterio que ya usa toJson/fromJson
# para la red.
TIPO_SQLITE_POR_TIPO_DART: dict[str, str] = {
    "String": "TEXT",
    "int": "INTEGER",
    "double": "REAL",
    "bool": "INTEGER",
    "DateTime": "TEXT",
}


def tipo_sqlite(tipo_dart: str) -> str:
    return TIPO_SQLITE_POR_TIPO_DART.get(tipo_dart, "TEXT")


def mapear_tipo_dart(tipo_uml: str | None) -> str:
    if not tipo_uml:
        return TIPO_DART_POR_DEFECTO
    return MAPEO_TIPOS_DART.get(tipo_uml.strip().lower(), TIPO_DART_POR_DEFECTO)


def tipo_no_reconocido(tipo_uml: str | None) -> bool:
    """True si se escribió un tipo que no está en MAPEO_TIPOS_DART (typo,
    tipo custom no soportado, etc.) — no cuenta no especificar tipo, igual
    que su equivalente en generador_spring.py."""
    return bool(tipo_uml) and tipo_uml.strip().lower() not in MAPEO_TIPOS_DART


# --------------------------------------------------------------------------
# Representación intermedia de una clase antes de renderizar sus 4 archivos
# Dart (modelo/servicio/lista/formulario).
# --------------------------------------------------------------------------


@dataclass
class CampoAtributo:
    nombre_campo: str
    tipo_dart: str
    aviso: str | None = None


@dataclass
class CampoRelacion:
    nombre_campo: str  # "direccionId" — el campo Dart (siempre int?, referencia por id)
    nombre_base: str  # "direccion" — sin el sufijo "Id", para nombrar variables (_direccionService, no _direccionIdService)
    nombre_json: str  # "direccion" — la clave anidada que espera/produce el backend de CU08
    clase_relacionada: str  # "Direccion" (nombre Dart de la clase referenciada)
    archivo_relacionado: str  # "direccion" (para el import del modelo/servicio relacionado)
    etiqueta: str  # texto para el label del Dropdown en el formulario


@dataclass
class DatosClase:
    clase: ClaseUml
    nombre_dart: str
    archivo: str  # snake_case, sin extensión — nombre base de los 4 archivos
    ruta_api: str  # "personas" — igual a como CU08 nombra la ruta REST
    atributos: list[CampoAtributo] = field(default_factory=list)
    relaciones: list[CampoRelacion] = field(default_factory=list)


def _es_plural(multiplicidad: str | None) -> bool:
    return multiplicidad in MULTIPLICIDADES_PLURALES


def _propietario_relacion(
    r: Relacion, clases_por_id: dict[str, ClaseUml]
) -> tuple[ClaseUml, ClaseUml] | None:
    """Determina qué lado de la relación guarda la referencia escalar por
    id, con el mismo criterio que decide quién tiene la FK (`@ManyToOne`/
    `@OneToOne` dueño) en generador_spring.py:
    - 1 a 1: el origen es el dueño.
    - 1 a muchos / muchos a 1: el lado "muchos" es el dueño.
    - muchos a muchos: ningún lado tiene una FK escalar simple — se
      devuelve None (ver limitación en el encabezado del módulo).

    Devuelve (clase_propietaria, clase_referenciada), o None.
    """
    origen = clases_por_id.get(r.id_clase_origen)
    destino = clases_por_id.get(r.id_clase_destino)
    if origen is None or destino is None:
        return None  # payload inconsistente — ya se valida al guardar el diagrama (CU09)

    origen_plural = _es_plural(r.multiplicidad_origen)
    destino_plural = _es_plural(r.multiplicidad_destino)

    if not origen_plural and not destino_plural:
        return origen, destino
    if not origen_plural and destino_plural:
        return destino, origen
    if origen_plural and not destino_plural:
        return origen, destino
    return None  # muchos a muchos


def _procesar_relaciones(
    clases: list[ClaseUml], relaciones: list[Relacion]
) -> dict[str, list[CampoRelacion]]:
    clases_por_id = {c.id: c for c in clases}
    campos_por_clase: dict[str, list[CampoRelacion]] = {c.id: [] for c in clases}
    # Mismo resolver que usa generador_spring.py para el lado Java: si hay
    # más de una relación entre el mismo par de clases, el nombre de campo
    # (y por lo tanto la clave JSON) tiene que numerarse exactamente igual
    # en los dos generadores — ver encabezado del módulo.
    nombres_relaciones = resolver_nombres_relaciones(clases, relaciones)

    for r in relaciones:
        propietario = _propietario_relacion(r, clases_por_id)
        if propietario is None:
            continue  # muchos a muchos
        dueño, referenciada = propietario
        nombres = nombres_relaciones.get(r.id)
        if nombres is None:
            continue  # payload inconsistente — ya se valida al guardar el diagrama (CU09)

        nombre_dart_referenciada = nombre_clase_java(referenciada.nombre)
        campos_por_clase[dueño.id].append(
            CampoRelacion(
                nombre_campo=nombres.dueño + "Id",
                nombre_base=nombres.dueño,
                nombre_json=nombres.dueño,
                clase_relacionada=nombre_dart_referenciada,
                archivo_relacionado=a_snake_case(nombre_dart_referenciada),
                etiqueta=nombre_dart_referenciada,
            )
        )

    return campos_por_clase


def _orden_topologico(
    clases_datos: list[DatosClase], clases: list[ClaseUml], relaciones: list[Relacion]
) -> list[DatosClase]:
    """CU14 — orden en el que `sync_manager.dart` sincroniza cada tabla: las
    clases referenciadas ("uno") antes que las que las referencian
    ("muchos", dueñas de la FK) — mismo criterio `_propietario_relacion` de
    arriba. Un ciclo real entre clases cae al orden de declaración original
    para lo que quede sin resolver (limitación documentada en el
    encabezado del módulo)."""
    clases_por_id = {c.id: c for c in clases}

    dependencias: dict[str, set[str]] = {d.clase.id: set() for d in clases_datos}
    for r in relaciones:
        propietario = _propietario_relacion(r, clases_por_id)
        if propietario is None:
            continue
        dueño, referenciada = propietario
        if dueño.id in dependencias and referenciada.id in dependencias:
            dependencias[dueño.id].add(referenciada.id)

    resueltos: list[DatosClase] = []
    resueltos_ids: set[str] = set()
    restantes = list(clases_datos)

    while restantes:
        listos = [d for d in restantes if dependencias[d.clase.id] <= resueltos_ids]
        if not listos:
            resueltos.extend(restantes)  # ciclo real -- orden de declaración para el resto
            break
        resueltos.extend(listos)
        resueltos_ids.update(d.clase.id for d in listos)
        restantes = [d for d in restantes if d not in listos]

    return resueltos


# --------------------------------------------------------------------------
# Ayudas para parsear el texto de un TextFormField de vuelta al tipo Dart
# del atributo (al guardar) y para precargarlo como texto (al editar).
# --------------------------------------------------------------------------


def _expresion_parseo(tipo_dart: str, variable_controller: str) -> str:
    texto = f"{variable_controller}.text.trim()"
    if tipo_dart == "int":
        return f"int.tryParse({texto})"
    if tipo_dart == "double":
        return f"double.tryParse({texto})"
    if tipo_dart == "bool":
        return f"{texto}.toLowerCase() == 'true'"
    if tipo_dart == "DateTime":
        return f"DateTime.tryParse({texto})"
    return texto  # String


def _expresion_precarga(tipo_dart: str, campo_item: str) -> str:
    if tipo_dart == "String":
        return f"{campo_item} ?? ''"
    if tipo_dart == "DateTime":
        return f"{campo_item}?.toIso8601String() ?? ''"
    return f"{campo_item}?.toString() ?? ''"  # int, double, bool


# --------------------------------------------------------------------------
# Renderizado de cada archivo Dart.
# --------------------------------------------------------------------------


def _renderizar_modelo(datos: DatosClase) -> str:
    nombre = datos.nombre_dart

    lineas_campos = ["  int? id;"]
    for a in datos.atributos:
        if a.aviso:
            lineas_campos.append(f"  // {a.aviso}")
        lineas_campos.append(f"  {a.tipo_dart}? {a.nombre_campo};")
    for r in datos.relaciones:
        lineas_campos.append(f"  int? {r.nombre_campo};")
    # CU14 — además del id de backend, se guarda el localId del padre: las
    # FKs locales SIEMPRE referencian por localId (nunca por id de backend),
    # para poder enlazar registros creados offline antes de que sincronicen
    # (ver encabezado del módulo).
    for r in datos.relaciones:
        lineas_campos.append(f"  String? {r.nombre_base}LocalId;")
    lineas_campos.append("  String localId;")
    lineas_campos.append("  String estadoSync;")
    lineas_campos.append("  String? errorSync;")

    parametros_constructor = ["    String? localId,", "    this.id,"]
    parametros_constructor += [f"    this.{a.nombre_campo}," for a in datos.atributos]
    parametros_constructor += [f"    this.{r.nombre_campo}," for r in datos.relaciones]
    parametros_constructor += [f"    this.{r.nombre_base}LocalId," for r in datos.relaciones]
    parametros_constructor += ["    this.estadoSync = 'sincronizado',", "    this.errorSync,"]

    lineas_from_json = ["      id: json['id'] as int?,"]
    for a in datos.atributos:
        if a.tipo_dart == "DateTime":
            lineas_from_json.append(
                f"      {a.nombre_campo}: json['{a.nombre_campo}'] != null"
                f" ? DateTime.parse(json['{a.nombre_campo}'] as String) : null,"
            )
        else:
            lineas_from_json.append(
                f"      {a.nombre_campo}: json['{a.nombre_campo}'] as {a.tipo_dart}?,"
            )
    for r in datos.relaciones:
        # El backend generado por CU08 serializa la relación como el objeto
        # anidado completo (Jackson), no como un id plano -- ver limitación
        # documentada en el encabezado del módulo.
        lineas_from_json.append(
            f"      {r.nombre_campo}: json['{r.nombre_json}'] != null"
            f" ? (json['{r.nombre_json}'] as Map<String, dynamic>)['id'] as int? : null,"
        )

    lineas_to_json: list[str] = ["      if (id != null) 'id': id,"]
    for a in datos.atributos:
        if a.tipo_dart == "DateTime":
            valor = f"{a.nombre_campo}!.toIso8601String()"
        else:
            valor = a.nombre_campo
        lineas_to_json.append(f"      if ({a.nombre_campo} != null) '{a.nombre_campo}': {valor},")
    for r in datos.relaciones:
        lineas_to_json.append(
            f"      if ({r.nombre_campo} != null) '{r.nombre_json}': {{'id': {r.nombre_campo}}},"
        )

    # CU14 — fromRow/toRow (SQLite local), independientes de fromJson/toJson
    # (red): bool se guarda como 0/1 (sqflite no tiene tipo booleano), y las
    # relaciones guardan el localId del padre (no su id de backend).
    lineas_from_row = ["      localId: fila['localId'] as String,", "      id: fila['id'] as int?,"]
    for a in datos.atributos:
        if a.tipo_dart == "bool":
            lineas_from_row.append(
                f"      {a.nombre_campo}: fila['{a.nombre_campo}'] == null"
                f" ? null : (fila['{a.nombre_campo}'] as int) == 1,"
            )
        elif a.tipo_dart == "DateTime":
            lineas_from_row.append(
                f"      {a.nombre_campo}: fila['{a.nombre_campo}'] != null"
                f" ? DateTime.parse(fila['{a.nombre_campo}'] as String) : null,"
            )
        else:
            lineas_from_row.append(f"      {a.nombre_campo}: fila['{a.nombre_campo}'] as {a.tipo_dart}?,")
    for r in datos.relaciones:
        lineas_from_row.append(f"      {r.nombre_campo}: fila['{r.nombre_campo}'] as int?,")
        lineas_from_row.append(f"      {r.nombre_base}LocalId: fila['{r.nombre_base}LocalId'] as String?,")
    lineas_from_row.append("      estadoSync: fila['estadoSync'] as String,")
    lineas_from_row.append("      errorSync: fila['errorSync'] as String?,")

    lineas_to_row = ["      'localId': localId,", "      'id': id,"]
    for a in datos.atributos:
        if a.tipo_dart == "bool":
            lineas_to_row.append(
                f"      '{a.nombre_campo}': {a.nombre_campo} == null ? null : ({a.nombre_campo}! ? 1 : 0),"
            )
        elif a.tipo_dart == "DateTime":
            lineas_to_row.append(f"      '{a.nombre_campo}': {a.nombre_campo}?.toIso8601String(),")
        else:
            lineas_to_row.append(f"      '{a.nombre_campo}': {a.nombre_campo},")
    for r in datos.relaciones:
        lineas_to_row.append(f"      '{r.nombre_campo}': {r.nombre_campo},")
        lineas_to_row.append(f"      '{r.nombre_base}LocalId': {r.nombre_base}LocalId,")
    lineas_to_row.append("      'estadoSync': estadoSync,")
    lineas_to_row.append("      'errorSync': errorSync,")

    return f"""// Generado automáticamente (CU15) a partir del diagrama de clases.
import 'package:uuid/uuid.dart';

class {nombre} {{
{chr(10).join(lineas_campos)}

  {nombre}({{
{chr(10).join(parametros_constructor)}
  }}) : localId = localId ?? const Uuid().v4();

  factory {nombre}.fromJson(Map<String, dynamic> json) {{
    return {nombre}(
{chr(10).join(lineas_from_json)}
    );
  }}

  Map<String, dynamic> toJson() {{
    return {{
{chr(10).join(lineas_to_json)}
    }};
  }}

  // CU14 — offline: lectura/escritura contra la tabla SQLite local.
  factory {nombre}.fromRow(Map<String, dynamic> fila) {{
    return {nombre}(
{chr(10).join(lineas_from_row)}
    );
  }}

  Map<String, dynamic> toRow() {{
    return {{
{chr(10).join(lineas_to_row)}
    }};
  }}
}}
"""


def _renderizar_servicio(datos: DatosClase) -> str:
    nombre = datos.nombre_dart
    var = nombre_campo_java(nombre)
    return f"""// Generado automáticamente (CU15).
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/{datos.archivo}.dart';

class {nombre}Service {{
  final String _urlBase = '${{Config.urlBase}}/api/{datos.ruta_api}';

  Future<List<{nombre}>> listar() async {{
    final respuesta = await http.get(Uri.parse(_urlBase));
    if (respuesta.statusCode != 200) {{
      throw Exception('No se pudo listar {datos.ruta_api} (${{respuesta.statusCode}})');
    }}
    final List<dynamic> datos = jsonDecode(respuesta.body) as List<dynamic>;
    return datos.map((e) => {nombre}.fromJson(e as Map<String, dynamic>)).toList();
  }}

  Future<{nombre}> obtenerPorId(int id) async {{
    final respuesta = await http.get(Uri.parse('$_urlBase/$id'));
    if (respuesta.statusCode != 200) {{
      throw Exception('No se pudo obtener {var} ${{id}} (${{respuesta.statusCode}})');
    }}
    return {nombre}.fromJson(jsonDecode(respuesta.body) as Map<String, dynamic>);
  }}

  Future<{nombre}> crear({nombre} {var}) async {{
    final respuesta = await http.post(
      Uri.parse(_urlBase),
      headers: {{'Content-Type': 'application/json'}},
      body: jsonEncode({var}.toJson()),
    );
    if (respuesta.statusCode != 200 && respuesta.statusCode != 201) {{
      throw Exception('No se pudo crear {var} (${{respuesta.statusCode}})');
    }}
    return {nombre}.fromJson(jsonDecode(respuesta.body) as Map<String, dynamic>);
  }}

  Future<{nombre}> actualizar(int id, {nombre} {var}) async {{
    final respuesta = await http.put(
      Uri.parse('$_urlBase/$id'),
      headers: {{'Content-Type': 'application/json'}},
      body: jsonEncode({var}.toJson()),
    );
    if (respuesta.statusCode != 200) {{
      throw Exception('No se pudo actualizar {var} ${{id}} (${{respuesta.statusCode}})');
    }}
    return {nombre}.fromJson(jsonDecode(respuesta.body) as Map<String, dynamic>);
  }}

  Future<void> eliminar(int id) async {{
    final respuesta = await http.delete(Uri.parse('$_urlBase/$id'));
    if (respuesta.statusCode != 200 && respuesta.statusCode != 204) {{
      throw Exception('No se pudo eliminar {var} ${{id}} (${{respuesta.statusCode}})');
    }}
  }}
}}
"""


# --------------------------------------------------------------------------
# CU14 — capa offline: base local (db.dart), conectividad, repositorio por
# clase (lectura/escritura local + sincronización) y el orquestador
# (SyncManager) que llama a cada repositorio en orden topológico.
# --------------------------------------------------------------------------


def _renderizar_offline_db(slug: str, clases_datos: list[DatosClase]) -> str:
    tablas = []
    for d in clases_datos:
        columnas = ["            localId TEXT PRIMARY KEY", "            id INTEGER"]
        for a in d.atributos:
            columnas.append(f"            {a.nombre_campo} {tipo_sqlite(a.tipo_dart)}")
        for r in d.relaciones:
            columnas.append(f"            {r.nombre_campo} INTEGER")
            columnas.append(f"            {r.nombre_base}LocalId TEXT")
        columnas.append("            estadoSync TEXT NOT NULL DEFAULT 'sincronizado'")
        columnas.append("            errorSync TEXT")
        cuerpo_columnas = ",\n".join(columnas)
        tablas.append(
            f"        await db.execute('''\n"
            f"          CREATE TABLE {d.archivo} (\n"
            f"{cuerpo_columnas}\n"
            f"          )\n"
            f"        ''');"
        )
    cuerpo_tablas = "\n".join(tablas)

    return f"""// Generado automáticamente (CU14) — base SQLite local, una tabla por
// clase del diagrama. `localId` (generado en el cliente) es la clave local;
// `id` es el id del backend, nulo hasta que el registro sincroniza. Las
// columnas de relación guardan el `localId` del padre (nunca su `id` de
// backend) -- ver `sync_manager.dart` para la resolución al sincronizar.
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

class OfflineDb {{
  static Database? _db;

  static Future<Database> instancia() async {{
    if (_db != null) return _db!;
    final ruta = join(await getDatabasesPath(), '{slug}_offline.db');
    _db = await openDatabase(
      ruta,
      version: 1,
      onCreate: (db, version) async {{
{cuerpo_tablas}
      }},
    );
    return _db!;
  }}
}}
"""


def _renderizar_conectividad() -> str:
    return """// Generado automáticamente (CU14).
import 'package:connectivity_plus/connectivity_plus.dart';

class Conectividad {
  static bool _conectadoAnteriormente = true;

  static Future<bool> estaConectado() async {
    final resultados = await Connectivity().checkConnectivity();
    return _algunaConexionReal(resultados);
  }

  static bool _algunaConexionReal(List<ConnectivityResult> resultados) {
    return resultados.any((r) => r != ConnectivityResult.none);
  }

  /// Llama a `alReconectar` cada vez que el dispositivo pasa de sin-conexión
  /// a con-conexión (no en cada evento de conectividad suelto).
  static void escucharReconexion(Future<void> Function() alReconectar) {
    Connectivity().onConnectivityChanged.listen((resultados) {
      final conectadoAhora = _algunaConexionReal(resultados);
      if (conectadoAhora && !_conectadoAnteriormente) {
        alReconectar();
      }
      _conectadoAnteriormente = conectadoAhora;
    });
  }
}
"""


def _renderizar_repositorio(datos: DatosClase) -> str:
    nombre = datos.nombre_dart
    tabla = datos.archivo
    var = nombre_campo_java(nombre)

    # La resolución de FKs (abajo) trabaja con `db.query(...)` crudo (solo
    # necesita el nombre de tabla de la clase relacionada, un string) -- no
    # instancia ni importa su modelo/servicio, así que no hace falta
    # importar `../models/{relacionada}.dart` acá.

    # Resolución de FKs al sincronizar: busca el id de backend de la clase
    # referenciada a partir del localId guardado en este registro -- si el
    # padre todavía no sincronizó (sigue sin id), esta fila se salta en esta
    # pasada (su estado no cambia, se reintenta solo en la próxima).
    bloques_fk = []
    for r in datos.relaciones:
        bloques_fk.append(
            f"        if (objeto.{r.nombre_base}LocalId != null) {{\n"
            f"          final filasPadre = await db.query(\n"
            f"            '{r.archivo_relacionado}',\n"
            f"            where: 'localId = ?',\n"
            f"            whereArgs: [objeto.{r.nombre_base}LocalId],\n"
            f"          );\n"
            f"          if (filasPadre.isEmpty || filasPadre.first['id'] == null) {{\n"
            f"            continue; // el padre todavía no sincronizó\n"
            f"          }}\n"
            f"          objeto.{r.nombre_campo} = filasPadre.first['id'] as int;\n"
            f"        }}"
        )
    cuerpo_resolucion_fks = "\n".join(bloques_fk) if bloques_fk else "        // sin relaciones que resolver"

    return f"""// Generado automáticamente (CU14) — capa offline-first de {nombre}: lee y
// escribe siempre contra la tabla SQLite local; sincroniza con el backend
// cuando hay conexión (orquestado por lib/offline/sync_manager.dart).
import '../models/{tabla}.dart';
import '../services/{tabla}_service.dart';
import 'db.dart';

class {nombre}Repositorio {{
  final {nombre}Service _service = {nombre}Service();

  Future<List<{nombre}>> listar() async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}');
    return filas.map((f) => {nombre}.fromRow(f)).toList();
  }}

  /// Trae la lista real del backend y actualiza el cache local (solo pisa
  /// registros ya sincronizados -- nunca un cambio local pendiente). Falla
  /// en silencio si no hay conexión: el cache local sigue disponible.
  Future<void> refrescarDesdeRed() async {{
    try {{
      final remotos = await _service.listar();
      final db = await OfflineDb.instancia();
      for (final r in remotos) {{
        final existentes = await db.query('{tabla}', where: 'id = ?', whereArgs: [r.id]);
        if (existentes.isNotEmpty) {{
          final fila = existentes.first;
          if (fila['estadoSync'] == 'sincronizado') {{
            r.localId = fila['localId'] as String;
            await db.update('{tabla}', r.toRow(), where: 'localId = ?', whereArgs: [r.localId]);
          }}
        }} else {{
          await db.insert('{tabla}', r.toRow());
        }}
      }}
    }} catch (_) {{
      // sin conexión o backend no disponible -- se sigue mostrando el cache local
    }}
  }}

  Future<{nombre}> crear({nombre} {var}) async {{
    {var}.estadoSync = 'pendienteCrear';
    final db = await OfflineDb.instancia();
    await db.insert('{tabla}', {var}.toRow());
    return {var};
  }}

  Future<{nombre}> actualizar({nombre} {var}) async {{
    if ({var}.estadoSync != 'pendienteCrear') {{
      {var}.estadoSync = 'pendienteActualizar';
    }}
    {var}.errorSync = null;
    final db = await OfflineDb.instancia();
    await db.update('{tabla}', {var}.toRow(), where: 'localId = ?', whereArgs: [{var}.localId]);
    return {var};
  }}

  Future<void> eliminar(String localId) async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}', where: 'localId = ?', whereArgs: [localId]);
    if (filas.isEmpty) return;
    if (filas.first['estadoSync'] == 'pendienteCrear') {{
      await db.delete('{tabla}', where: 'localId = ?', whereArgs: [localId]);
    }} else {{
      await db.update(
        '{tabla}',
        {{'estadoSync': 'pendienteEliminar', 'errorSync': null}},
        where: 'localId = ?',
        whereArgs: [localId],
      );
    }}
  }}

  /// Descarta una operación fallida: para una creación, borra la fila local
  /// (nunca existió en el backend); para una actualización/eliminación,
  /// vuelve a pedir el registro real al backend y sobrescribe la fila local
  /// con esa verdad (si tampoco se puede, borra la fila local).
  Future<void> descartar(String localId) async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}', where: 'localId = ?', whereArgs: [localId]);
    if (filas.isEmpty) return;
    final fila = filas.first;
    if (fila['id'] == null) {{
      await db.delete('{tabla}', where: 'localId = ?', whereArgs: [localId]);
      return;
    }}
    try {{
      final real = await _service.obtenerPorId(fila['id'] as int);
      real.localId = localId;
      await db.update('{tabla}', real.toRow(), where: 'localId = ?', whereArgs: [localId]);
    }} catch (_) {{
      await db.delete('{tabla}', where: 'localId = ?', whereArgs: [localId]);
    }}
  }}

  /// Procesa las filas pendientes de esta tabla contra el backend. Devuelve
  /// true si al menos una operación se completó con éxito (lo usa
  /// SyncManager para decidir si vale la pena repetir otra pasada, por si
  /// esto desbloqueó una FK pendiente en otra tabla).
  Future<bool> sincronizar() async {{
    final db = await OfflineDb.instancia();
    final pendientes = await db.query(
      '{tabla}',
      where: "estadoSync IN ('pendienteCrear', 'pendienteActualizar', 'pendienteEliminar')",
    );
    var huboProgreso = false;

    for (final fila in pendientes) {{
      final objeto = {nombre}.fromRow(fila);
      final estado = fila['estadoSync'] as String;

      if (estado != 'pendienteEliminar') {{
{cuerpo_resolucion_fks}
      }}

      try {{
        if (estado == 'pendienteCrear') {{
          final creado = await _service.crear(objeto);
          await db.update(
            '{tabla}',
            {{'id': creado.id, 'estadoSync': 'sincronizado', 'errorSync': null}},
            where: 'localId = ?',
            whereArgs: [objeto.localId],
          );
          huboProgreso = true;
        }} else if (estado == 'pendienteActualizar') {{
          await _service.actualizar(objeto.id!, objeto);
          await db.update(
            '{tabla}',
            {{'estadoSync': 'sincronizado', 'errorSync': null}},
            where: 'localId = ?',
            whereArgs: [objeto.localId],
          );
          huboProgreso = true;
        }} else if (estado == 'pendienteEliminar') {{
          await _service.eliminar(objeto.id!);
          await db.delete('{tabla}', where: 'localId = ?', whereArgs: [objeto.localId]);
          huboProgreso = true;
        }}
      }} catch (e) {{
        final estadoFallido = estado == 'pendienteCrear'
            ? 'fallidoCrear'
            : estado == 'pendienteActualizar'
                ? 'fallidoActualizar'
                : 'fallidoEliminar';
        await db.update(
          '{tabla}',
          {{'estadoSync': estadoFallido, 'errorSync': e.toString()}},
          where: 'localId = ?',
          whereArgs: [objeto.localId],
        );
      }}
    }}

    return huboProgreso;
  }}

  /// Vuelve a poner en cola una operación marcada como fallida.
  Future<void> reintentar(String localId) async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}', where: 'localId = ?', whereArgs: [localId]);
    if (filas.isEmpty) return;
    final actual = filas.first['estadoSync'] as String;
    await db.update(
      '{tabla}',
      {{'estadoSync': actual.replaceFirst('fallido', 'pendiente'), 'errorSync': null}},
      where: 'localId = ?',
      whereArgs: [localId],
    );
  }}

  Future<List<{nombre}>> fallidas() async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}', where: "estadoSync LIKE 'fallido%'");
    return filas.map((f) => {nombre}.fromRow(f)).toList();
  }}

  Future<int> contarPendientes() async {{
    final db = await OfflineDb.instancia();
    final filas = await db.query('{tabla}', where: "estadoSync != 'sincronizado'");
    return filas.length;
  }}
}}
"""


def _renderizar_sync_manager(clases_ordenadas: list[DatosClase]) -> str:
    imports = "\n".join(f"import '{d.archivo}_repositorio.dart';" for d in clases_ordenadas)
    variables = [(nombre_campo_java(d.nombre_dart), d.nombre_dart) for d in clases_ordenadas]
    instancias = "\n".join(
        f"final {var}Repositorio = {nombre}Repositorio();" for var, nombre in variables
    )
    llamadas = "\n".join(
        f"      final resultado{i} = await {var}Repositorio.sincronizar();\n"
        f"      if (resultado{i}) progreso = true;"
        for i, (var, _) in enumerate(variables)
    )
    return f"""// Generado automáticamente (CU14). Orden de sincronización calculado a
// partir de las relaciones del diagrama: las clases referenciadas
// sincronizan antes que las que las referencian (dueñas de la FK), para
// poder resolver el id real del padre antes de mandar al hijo. Repite
// pasadas hasta que una no logra ningún progreso (resuelve cadenas de
// dependencia de varios niveles sin esperar un nuevo evento de conexión).
import 'conectividad.dart';
{imports}

{instancias}

class SyncManager {{
  static Future<void> sincronizarTodo() async {{
    if (!await Conectividad.estaConectado()) return;
    for (var intento = 0; intento < 3; intento++) {{
      var progreso = false;
{llamadas}
      if (!progreso) break;
    }}
  }}
}}
"""


def _renderizar_sincronizacion_screen(clases_datos: list[DatosClase]) -> str:
    """CU14 — pantalla de revisión: una sección por clase con sus
    operaciones fallidas (mensaje de error + "Reintentar"/"Descartar"). Sin
    reflexión en tiempo de ejecución en Dart, cada clase se enumera
    explícitamente (mismo criterio que ya usa `_renderizar_main` para el
    listado de `HomeScreen`)."""
    imports = "\n".join(
        f"import '../models/{d.archivo}.dart';\nimport '../offline/{d.archivo}_repositorio.dart';"
        for d in clases_datos
    )

    campos_estado = "\n".join(
        f"  final {d.nombre_dart}Repositorio _{d.archivo}Repositorio = {d.nombre_dart}Repositorio();\n"
        f"  List<{d.nombre_dart}> _{d.archivo}Fallidas = [];"
        for d in clases_datos
    )

    carga = "\n".join(
        f"    _{d.archivo}Fallidas = await _{d.archivo}Repositorio.fallidas();" for d in clases_datos
    )

    condicion_vacio = " && ".join(f"_{d.archivo}Fallidas.isEmpty" for d in clases_datos) or "true"

    secciones = "\n".join(
        f"""                    ..._seccion(
                      '{d.nombre_dart}',
                      _{d.archivo}Fallidas,
                      _{d.archivo}Repositorio,
                    ),"""
        for d in clases_datos
    )

    return f"""// Generado automáticamente (CU14) — revisión de operaciones que el
// backend rechazó al sincronizar: mensaje de error y opción de
// reintentarlas o descartarlas (ver limitaciones de "descartar" en el
// encabezado de generador_flutter.py).
import 'package:flutter/material.dart';

{imports}
import '../offline/sync_manager.dart';

class SincronizacionScreen extends StatefulWidget {{
  const SincronizacionScreen({{super.key}});

  @override
  State<SincronizacionScreen> createState() => _SincronizacionScreenState();
}}

class _SincronizacionScreenState extends State<SincronizacionScreen> {{
{campos_estado}
  bool _cargando = true;

  @override
  void initState() {{
    super.initState();
    _cargar();
  }}

  Future<void> _cargar() async {{
    setState(() => _cargando = true);
{carga}
    if (mounted) setState(() => _cargando = false);
  }}

  List<Widget> _seccion(String titulo, List<dynamic> fallidas, dynamic repositorio) {{
    if (fallidas.isEmpty) return const [];
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
        child: Text(titulo, style: const TextStyle(fontWeight: FontWeight.bold)),
      ),
      ...fallidas.map(
        (item) => ListTile(
          title: Text('${{titulo}} -- ${{item.estadoSync}}'),
          subtitle: Text(item.errorSync ?? ''),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextButton(
                onPressed: () async {{
                  await repositorio.reintentar(item.localId as String);
                  await SyncManager.sincronizarTodo();
                  _cargar();
                }},
                child: const Text('Reintentar'),
              ),
              TextButton(
                onPressed: () async {{
                  await repositorio.descartar(item.localId as String);
                  _cargar();
                }},
                child: const Text('Descartar'),
              ),
            ],
          ),
        ),
      ),
    ];
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('Sincronización')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : ({condicion_vacio})
              ? const Center(child: Text('No hay operaciones pendientes de revisión.'))
              : ListView(
                  children: [
{secciones}
                  ],
                ),
    );
  }}
}}
"""


def _texto_item_lista(datos: DatosClase) -> tuple[str, str]:
    """Título y subtítulo (expresiones Dart de interpolación de string) para
    cada fila de la pantalla de listado, a partir de los atributos de la
    clase (no hay un campo "principal" declarado en el diagrama, así que se
    usa el primero como título y el resto como subtítulo)."""
    etiquetas = [f"{a.nombre_campo}: ${{item.{a.nombre_campo}}}" for a in datos.atributos]
    if not datos.atributos:
        return "'ID ${item.id}'", "''"
    titulo = f"'${{item.{datos.atributos[0].nombre_campo}}}'"
    resto = etiquetas[1:]
    subtitulo = f"'{', '.join(resto)}'" if resto else "'ID ${item.id}'"
    return titulo, subtitulo


def _icono_estado_sync(variable_estado: str) -> str:
    """CU14 — indicador visual del estado de sincronización de un registro
    en la pantalla de listado: nube tachada = pendiente, alerta = fallido,
    nada = ya sincronizado."""
    return (
        f"{variable_estado}.startsWith('fallido')\n"
        f"                    ? const Icon(Icons.error_outline, color: Colors.red)\n"
        f"                    : {variable_estado} != 'sincronizado'\n"
        f"                        ? const Icon(Icons.cloud_upload_outlined, color: Colors.grey)\n"
        f"                        : null"
    )


def _renderizar_list_screen(datos: DatosClase) -> str:
    nombre = datos.nombre_dart
    titulo, subtitulo = _texto_item_lista(datos)
    icono_estado = _icono_estado_sync("item.estadoSync")
    return f"""// Generado automáticamente (CU15/CU14).
import 'package:flutter/material.dart';

import '../models/{datos.archivo}.dart';
import '../offline/{datos.archivo}_repositorio.dart';
import '../offline/sync_manager.dart';
import '{datos.archivo}_form_screen.dart';

class {nombre}ListScreen extends StatefulWidget {{
  const {nombre}ListScreen({{super.key}});

  @override
  State<{nombre}ListScreen> createState() => _{nombre}ListScreenState();
}}

class _{nombre}ListScreenState extends State<{nombre}ListScreen> {{
  final {nombre}Repositorio _repositorio = {nombre}Repositorio();
  late Future<List<{nombre}>> _futuro;

  @override
  void initState() {{
    super.initState();
    _futuro = _repositorio.listar();
    _sincronizarYRecargar();
  }}

  // CU14 — lee siempre del cache local primero (instantáneo, funciona
  // offline); si hay conexión, refresca el cache desde el backend y drena
  // las operaciones pendientes en segundo plano, y recarga al terminar.
  Future<void> _sincronizarYRecargar() async {{
    await _repositorio.refrescarDesdeRed();
    await SyncManager.sincronizarTodo();
    if (mounted) _recargar();
  }}

  void _recargar() {{
    setState(() {{
      _futuro = _repositorio.listar();
    }});
  }}

  Future<void> _eliminar({nombre} item) async {{
    await _repositorio.eliminar(item.localId);
    await SyncManager.sincronizarTodo();
    _recargar();
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{nombre}')),
      body: FutureBuilder<List<{nombre}>>(
        future: _futuro,
        builder: (context, snapshot) {{
          if (snapshot.connectionState != ConnectionState.done) {{
            return const Center(child: CircularProgressIndicator());
          }}
          if (snapshot.hasError) {{
            return Center(child: Text('Error: ${{snapshot.error}}'));
          }}
          final items = snapshot.data ?? [];
          if (items.isEmpty) {{
            return const Center(child: Text('Sin registros todavía.'));
          }}
          return ListView.builder(
            itemCount: items.length,
            itemBuilder: (context, index) {{
              final item = items[index];
              return ListTile(
                leading: {icono_estado},
                title: Text({titulo}),
                subtitle: Text({subtitulo}),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.edit),
                      onPressed: () async {{
                        await Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => {nombre}FormScreen(item: item)),
                        );
                        _recargar();
                      }},
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete),
                      onPressed: () => _eliminar(item),
                    ),
                  ],
                ),
              );
            }},
          );
        }},
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {{
          await Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const {nombre}FormScreen()),
          );
          _recargar();
        }},
        child: const Icon(Icons.add),
      ),
    );
  }}
}}
"""


def _renderizar_form_screen(datos: DatosClase) -> str:
    nombre = datos.nombre_dart

    imports_relaciones = "\n".join(
        f"import '../models/{r.archivo_relacionado}.dart';\n"
        f"import '../offline/{r.archivo_relacionado}_repositorio.dart';"
        for r in datos.relaciones
    )

    controllers = "\n".join(
        f"  final TextEditingController _{a.nombre_campo}Controller = TextEditingController();"
        for a in datos.atributos
    )

    # CU14 — el estado del dropdown de cada relación es el localId del
    # padre elegido (no su id de backend, que puede no existir todavía si
    # el padre se creó offline y no sincronizó).
    estado_relaciones = "\n".join(
        f"  final {r.clase_relacionada}Repositorio _{r.nombre_base}Repositorio = {r.clase_relacionada}Repositorio();\n"
        f"  List<{r.clase_relacionada}> _{r.nombre_base}Opciones = [];\n"
        f"  String? _{r.nombre_base}LocalId;"
        for r in datos.relaciones
    )

    precarga_atributos = "\n".join(
        f"      _{a.nombre_campo}Controller.text = {_expresion_precarga(a.tipo_dart, f'item.{a.nombre_campo}')};"
        for a in datos.atributos
    )
    precarga_relaciones = "\n".join(
        f"      _{r.nombre_base}LocalId = item.{r.nombre_base}LocalId;" for r in datos.relaciones
    )

    dispose_controllers = "\n".join(
        f"    _{a.nombre_campo}Controller.dispose();" for a in datos.atributos
    )

    carga_relaciones = (
        "\n".join(
            f"    final opciones{i} = await _{r.nombre_base}Repositorio.listar();"
            for i, r in enumerate(datos.relaciones)
        )
        + ("\n" if datos.relaciones else "")
        + "\n".join(
            f"    _{r.nombre_base}Opciones = opciones{i};" for i, r in enumerate(datos.relaciones)
        )
    )

    campos_constructor_atributos = "\n".join(
        f"      {a.nombre_campo}: {_expresion_parseo(a.tipo_dart, f'_{a.nombre_campo}Controller')},"
        for a in datos.atributos
    )
    campos_constructor_relaciones = "\n".join(
        f"      {r.nombre_base}LocalId: _{r.nombre_base}LocalId," for r in datos.relaciones
    )

    campos_formulario: list[str] = []
    for a in datos.atributos:
        teclado = TECLADO_POR_TIPO_DART.get(a.tipo_dart, "TextInputType.text")
        campos_formulario.append(
            "                    TextFormField(\n"
            f"                      controller: _{a.nombre_campo}Controller,\n"
            f"                      keyboardType: {teclado},\n"
            f"                      decoration: const InputDecoration(labelText: '{a.nombre_campo}'),\n"
            "                    ),"
        )
    for r in datos.relaciones:
        campos_formulario.append(
            f"                    DropdownButtonFormField<String>(\n"
            f"                      value: _{r.nombre_base}LocalId,\n"
            f"                      decoration: const InputDecoration(labelText: '{r.etiqueta}'),\n"
            f"                      items: _{r.nombre_base}Opciones\n"
            f"                          .map((o) => DropdownMenuItem<String>(\n"
            f"                                value: o.localId,\n"
            f"                                child: Text(o.id == null ? 'Pendiente de sincronizar' : 'ID ${{o.id}}'),\n"
            f"                              ))\n"
            f"                          .toList(),\n"
            f"                      onChanged: (valor) => setState(() => _{r.nombre_base}LocalId = valor),\n"
            "                    ),"
        )
    cuerpo_campos = "\n".join(campos_formulario)

    return f"""// Generado automáticamente (CU15/CU14).
import 'package:flutter/material.dart';

import '../models/{datos.archivo}.dart';
import '../offline/{datos.archivo}_repositorio.dart';
import '../offline/sync_manager.dart';
{imports_relaciones}

class {nombre}FormScreen extends StatefulWidget {{
  final {nombre}? item;

  const {nombre}FormScreen({{super.key, this.item}});

  @override
  State<{nombre}FormScreen> createState() => _{nombre}FormScreenState();
}}

class _{nombre}FormScreenState extends State<{nombre}FormScreen> {{
  final _formKey = GlobalKey<FormState>();
  final {nombre}Repositorio _repositorio = {nombre}Repositorio();
{controllers}
{estado_relaciones}
  bool _cargandoRelaciones = true;

  @override
  void initState() {{
    super.initState();
    final item = widget.item;
    if (item != null) {{
{precarga_atributos}
{precarga_relaciones}
    }}
    _cargarOpcionesRelaciones();
  }}

  Future<void> _cargarOpcionesRelaciones() async {{
{carga_relaciones}
    setState(() {{
      _cargandoRelaciones = false;
    }});
  }}

  @override
  void dispose() {{
{dispose_controllers}
    super.dispose();
  }}

  Future<void> _guardar() async {{
    if (!_formKey.currentState!.validate()) return;
    final objeto = {nombre}(
      localId: widget.item?.localId,
      id: widget.item?.id,
{campos_constructor_atributos}
{campos_constructor_relaciones}
    );
    if (widget.item == null) {{
      await _repositorio.crear(objeto);
    }} else {{
      await _repositorio.actualizar(objeto);
    }}
    await SyncManager.sincronizarTodo();
    if (mounted) Navigator.pop(context);
  }}

  @override
  Widget build(BuildContext context) {{
    final editando = widget.item != null;
    return Scaffold(
      appBar: AppBar(title: Text(editando ? 'Editar {nombre}' : 'Nueva {nombre}')),
      body: _cargandoRelaciones
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _formKey,
                child: ListView(
                  children: [
{cuerpo_campos}
                    const SizedBox(height: 24),
                    ElevatedButton(
                      onPressed: _guardar,
                      child: const Text('Guardar'),
                    ),
                  ],
                ),
              ),
            ),
    );
  }}
}}
"""


def _renderizar_config(url_base: str) -> str:
    url_limpia = url_base.strip().rstrip("/").replace("'", r"\'")
    return f"""// Generado automáticamente (CU15) — URL base del backend Spring Boot
// generado por CU08 (o cualquier otro que siga la misma convención de
// rutas /api/{{plural}}). Único lugar donde se configura: los servicios la
// importan de acá, no queda hardcodeada en cada uno.
class Config {{
  static const String urlBase = '{url_limpia}';
}}
"""


def _renderizar_main(nombre_proyecto: str, clases_datos: list[DatosClase]) -> str:
    imports_list_screens = "\n".join(f"import 'screens/{d.archivo}_list_screen.dart';" for d in clases_datos)
    items = "\n".join(
        f"""          Card(
            child: ListTile(
              title: const Text('{d.nombre_dart}'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const {d.nombre_dart}ListScreen()),
              ),
            ),
          ),"""
        for d in clases_datos
    )
    # CU14 — conteo de operaciones pendientes/fallidas de TODAS las clases,
    # para el aviso en la pantalla principal (cada clase se enumera
    # explícitamente, Dart no tiene reflexión para iterarlas genéricamente).
    conteos = ",\n".join(
        f"      {nombre_campo_java(d.nombre_dart)}Repositorio.contarPendientes()" for d in clases_datos
    )
    return f"""// Generado automáticamente (CU15/CU14).
import 'package:flutter/material.dart';

import 'offline/conectividad.dart';
import 'offline/db.dart';
import 'offline/sync_manager.dart';
import 'screens/sincronizacion_screen.dart';
{imports_list_screens}

void main() async {{
  WidgetsFlutterBinding.ensureInitialized();
  await OfflineDb.instancia();
  // CU14 — sincroniza automáticamente al reconectar, y una vez al abrir la
  // app por si quedaron operaciones pendientes de una sesión anterior y ya
  // hay conexión.
  Conectividad.escucharReconexion(() => SyncManager.sincronizarTodo());
  SyncManager.sincronizarTodo();
  runApp(const GeneratedApp());
}}

class GeneratedApp extends StatelessWidget {{
  const GeneratedApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: '{nombre_proyecto}',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const HomeScreen(),
    );
  }}
}}

class HomeScreen extends StatelessWidget {{
  const HomeScreen({{super.key}});

  Future<int> _contarPendientesTotal() async {{
    final conteos = await Future.wait<int>([
{conteos}
    ]);
    return conteos.fold<int>(0, (acumulado, c) => acumulado + c);
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(
        title: const Text('{nombre_proyecto}'),
        actions: [
          FutureBuilder<bool>(
            future: Conectividad.estaConectado(),
            builder: (context, snapshot) {{
              final conectado = snapshot.data ?? true;
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Icon(
                  conectado ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
                  size: 20,
                ),
              );
            }},
          ),
        ],
      ),
      body: Column(
        children: [
          FutureBuilder<int>(
            future: _contarPendientesTotal(),
            builder: (context, snapshot) {{
              final pendientes = snapshot.data ?? 0;
              return ListTile(
                leading: const Icon(Icons.sync),
                title: const Text('Sincronización'),
                subtitle: Text(
                  pendientes == 0 ? 'Todo sincronizado' : '$pendientes operación(es) pendiente(s)',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const SincronizacionScreen()),
                ),
              );
            }},
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(8),
              children: [
{items}
              ],
            ),
          ),
        ],
      ),
    );
  }}
}}
"""


# --------------------------------------------------------------------------
# Carpeta android/ — plantillas de texto vendoreadas desde un `flutter
# create` real (mobile/android/, ver encabezado del módulo). Son strings
# planos (NO f-strings): el contenido es Kotlin/XML/shell lleno de sus
# propios `{`/`}`/`$`, así que la interpolación de los 3 valores
# específicos del proyecto se hace con `.replace()` sobre un placeholder,
# no con f-strings.
# --------------------------------------------------------------------------

_DIR_PLANTILLAS_ANDROID = Path(__file__).parent / "plantillas_android"

_DENSIDADES_ICONO = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")


def _leer_asset_android(nombre_relativo: str) -> bytes:
    return (_DIR_PLANTILLAS_ANDROID / nombre_relativo).read_bytes()


_ANDROID_SETTINGS_GRADLE = """pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            file("local.properties").inputStream().use { properties.load(it) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "8.11.1" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
}

include(":app")
"""

_ANDROID_BUILD_GRADLE_RAIZ = """allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
"""

_ANDROID_GRADLE_PROPERTIES = """org.gradle.jvmargs=-Xmx8G -XX:MaxMetaspaceSize=4G -XX:ReservedCodeCacheSize=512m -XX:+HeapDumpOnOutOfMemoryError
android.useAndroidX=true
"""

# Gradle 8.14 -- si se actualiza acá, actualizar también el .jar vendoreado
# en plantillas_android/gradle-wrapper.jar (tiene que ser la misma versión).
_ANDROID_GRADLE_WRAPPER_PROPERTIES = """distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.14-all.zip
"""

_ANDROID_BUILD_GRADLE_APP = """plugins {
    id("com.android.application")
    id("kotlin-android")
    // El plugin de Gradle de Flutter tiene que aplicarse después de los de Android y Kotlin.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "__PAQUETE__"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "__PAQUETE__"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // Firmado con las claves de debug por ahora, para que `flutter run --release` funcione.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}
"""

_ANDROID_MAIN_ACTIVITY = """package __PAQUETE__

import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity()
"""

_ANDROID_MANIFEST_PRINCIPAL = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:label="__NOMBRE_APP__"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:taskAffinity=""
            android:theme="@style/LaunchTheme"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustResize">
            <meta-data
              android:name="io.flutter.embedding.android.NormalTheme"
              android:resource="@style/NormalTheme"
              />
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>
    <queries>
        <intent>
            <action android:name="android.intent.action.PROCESS_TEXT"/>
            <data android:mimeType="text/plain"/>
        </intent>
    </queries>
</manifest>
"""

# Idéntico en debug y profile -- el único permiso que Flutter necesita en
# builds no-release para hot reload/depuración.
_ANDROID_MANIFEST_DEBUG_PROFILE = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- The INTERNET permission is required for development. Specifically,
         the Flutter tool needs it to communicate with the running application
         to allow setting breakpoints, to provide hot reload, etc.
    -->
    <uses-permission android:name="android.permission.INTERNET"/>
</manifest>
"""

_ANDROID_STYLES_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- Theme applied to the Android Window while the process is starting when the OS's Dark Mode setting is off -->
    <style name="LaunchTheme" parent="@android:style/Theme.Light.NoTitleBar">
        <!-- Show a splash screen on the activity. Automatically removed when
             the Flutter engine draws its first frame -->
        <item name="android:windowBackground">@drawable/launch_background</item>
    </style>
    <!-- Theme applied to the Android Window as soon as the process has started.
         This theme determines the color of the Android Window while your
         Flutter UI initializes, as well as behind your Flutter UI while its
         running.

         This Theme is only used starting with V2 of Flutter's Android embedding. -->
    <style name="NormalTheme" parent="@android:style/Theme.Light.NoTitleBar">
        <item name="android:windowBackground">?android:colorBackground</item>
    </style>
</resources>
"""

_ANDROID_STYLES_NIGHT_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- Theme applied to the Android Window while the process is starting when the OS's Dark Mode setting is on -->
    <style name="LaunchTheme" parent="@android:style/Theme.Black.NoTitleBar">
        <!-- Show a splash screen on the activity. Automatically removed when
             the Flutter engine draws its first frame -->
        <item name="android:windowBackground">@drawable/launch_background</item>
    </style>
    <!-- Theme applied to the Android Window as soon as the process has started.
         This theme determines the color of the Android Window while your
         Flutter UI initializes, as well as behind your Flutter UI while its
         running.

         This Theme is only used starting with V2 of Flutter's Android embedding. -->
    <style name="NormalTheme" parent="@android:style/Theme.Black.NoTitleBar">
        <item name="android:windowBackground">?android:colorBackground</item>
    </style>
</resources>
"""

_ANDROID_LAUNCH_BACKGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- Modify this file to customize your launch splash screen -->
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@android:color/white" />

    <!-- You can insert your own image assets here -->
    <!-- <item>
        <bitmap
            android:gravity="center"
            android:src="@mipmap/launch_image" />
    </item> -->
</layer-list>
"""

_ANDROID_LAUNCH_BACKGROUND_V21_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- Modify this file to customize your launch splash screen -->
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="?android:colorBackground" />

    <!-- You can insert your own image assets here -->
    <!-- <item>
        <bitmap
            android:gravity="center"
            android:src="@mipmap/launch_image" />
    </item> -->
</layer-list>
"""

_ANDROID_GITIGNORE = """gradle-wrapper.jar
/.gradle
/captures/
/gradlew
/gradlew.bat
/local.properties
GeneratedPluginRegistrant.java
.cxx/

# Remember to never publicly share your keystore.
# See https://flutter.dev/to/reference-keystore
key.properties
**/*.keystore
**/*.jks
"""

# Scripts genéricos del Gradle Wrapper (no tienen nada específico del
# proyecto) -- copiados tal cual de mobile/android/gradlew(.bat), que no
# están en git ahí (excluidos por mobile/android/.gitignore) pero sí
# existen en el disco de la máquina donde se armó esta plantilla.
_ANDROID_GRADLEW = """#!/usr/bin/env bash

##############################################################################
##
##  Gradle start up script for UN*X
##
##############################################################################

# Add default JVM options here. You can also use JAVA_OPTS and GRADLE_OPTS to pass JVM options to this script.
DEFAULT_JVM_OPTS=""

APP_NAME="Gradle"
APP_BASE_NAME=`basename "$0"`

# Use the maximum available, or set MAX_FD != -1 to use that value.
MAX_FD="maximum"

warn ( ) {
    echo "$*"
}

die ( ) {
    echo
    echo "$*"
    echo
    exit 1
}

# OS specific support (must be 'true' or 'false').
cygwin=false
msys=false
darwin=false
case "`uname`" in
  CYGWIN* )
    cygwin=true
    ;;
  Darwin* )
    darwin=true
    ;;
  MINGW* )
    msys=true
    ;;
esac

# Attempt to set APP_HOME
# Resolve links: $0 may be a link
PRG="$0"
# Need this for relative symlinks.
while [ -h "$PRG" ] ; do
    ls=`ls -ld "$PRG"`
    link=`expr "$ls" : '.*-> \\(.*\\)$'`
    if expr "$link" : '/.*' > /dev/null; then
        PRG="$link"
    else
        PRG=`dirname "$PRG"`"/$link"
    fi
done
SAVED="`pwd`"
cd "`dirname \\"$PRG\\"`/" >/dev/null
APP_HOME="`pwd -P`"
cd "$SAVED" >/dev/null

CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar

# Determine the Java command to use to start the JVM.
if [ -n "$JAVA_HOME" ] ; then
    if [ -x "$JAVA_HOME/jre/sh/java" ] ; then
        # IBM's JDK on AIX uses strange locations for the executables
        JAVACMD="$JAVA_HOME/jre/sh/java"
    else
        JAVACMD="$JAVA_HOME/bin/java"
    fi
    if [ ! -x "$JAVACMD" ] ; then
        die "ERROR: JAVA_HOME is set to an invalid directory: $JAVA_HOME

Please set the JAVA_HOME variable in your environment to match the
location of your Java installation."
    fi
else
    JAVACMD="java"
    which java >/dev/null 2>&1 || die "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.

Please set the JAVA_HOME variable in your environment to match the
location of your Java installation."
fi

# Increase the maximum file descriptors if we can.
if [ "$cygwin" = "false" -a "$darwin" = "false" ] ; then
    MAX_FD_LIMIT=`ulimit -H -n`
    if [ $? -eq 0 ] ; then
        if [ "$MAX_FD" = "maximum" -o "$MAX_FD" = "max" ] ; then
            MAX_FD="$MAX_FD_LIMIT"
        fi
        ulimit -n $MAX_FD
        if [ $? -ne 0 ] ; then
            warn "Could not set maximum file descriptor limit: $MAX_FD"
        fi
    else
        warn "Could not query maximum file descriptor limit: $MAX_FD_LIMIT"
    fi
fi

# For Darwin, add options to specify how the application appears in the dock
if $darwin; then
    GRADLE_OPTS="$GRADLE_OPTS \\"-Xdock:name=$APP_NAME\\" \\"-Xdock:icon=$APP_HOME/media/gradle.icns\\""
fi

# For Cygwin, switch paths to Windows format before running java
if $cygwin ; then
    APP_HOME=`cygpath --path --mixed "$APP_HOME"`
    CLASSPATH=`cygpath --path --mixed "$CLASSPATH"`
    JAVACMD=`cygpath --unix "$JAVACMD"`

    # We build the pattern for arguments to be converted via cygpath
    ROOTDIRSRAW=`find -L / -maxdepth 1 -mindepth 1 -type d 2>/dev/null`
    SEP=""
    for dir in $ROOTDIRSRAW ; do
        ROOTDIRS="$ROOTDIRS$SEP$dir"
        SEP="|"
    done
    OURCYGPATTERN="(^($ROOTDIRS))"
    # Add a user-defined pattern to the cygpath arguments
    if [ "$GRADLE_CYGPATTERN" != "" ] ; then
        OURCYGPATTERN="$OURCYGPATTERN|($GRADLE_CYGPATTERN)"
    fi
    # Now convert the arguments - kludge to limit ourselves to /bin/sh
    i=0
    for arg in "$@" ; do
        CHECK=`echo "$arg"|egrep -c "$OURCYGPATTERN" -`
        CHECK2=`echo "$arg"|egrep -c "^-"`                                 ### Determine if an option

        if [ $CHECK -ne 0 ] && [ $CHECK2 -eq 0 ] ; then                    ### Added a condition
            eval `echo args$i`=`cygpath --path --ignore --mixed "$arg"`
        else
            eval `echo args$i`="\\"$arg\\""
        fi
        i=$((i+1))
    done
    case $i in
        (0) set -- ;;
        (1) set -- "$args0" ;;
        (2) set -- "$args0" "$args1" ;;
        (3) set -- "$args0" "$args1" "$args2" ;;
        (4) set -- "$args0" "$args1" "$args2" "$args3" ;;
        (5) set -- "$args0" "$args1" "$args2" "$args3" "$args4" ;;
        (6) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" ;;
        (7) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" ;;
        (8) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" "$args7" ;;
        (9) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" "$args7" "$args8" ;;
    esac
fi

# Split up the JVM_OPTS And GRADLE_OPTS values into an array, following the shell quoting and substitution rules
function splitJvmOpts() {
    JVM_OPTS=("$@")
}
eval splitJvmOpts $DEFAULT_JVM_OPTS $JAVA_OPTS $GRADLE_OPTS
JVM_OPTS[${#JVM_OPTS[*]}]="-Dorg.gradle.appname=$APP_BASE_NAME"

exec "$JAVACMD" "${JVM_OPTS[@]}" -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
"""

_ANDROID_GRADLEW_BAT = """@if "%DEBUG%" == "" @echo off
@rem ##########################################################################
@rem
@rem  Gradle startup script for Windows
@rem
@rem ##########################################################################

@rem Set local scope for the variables with windows NT shell
if "%OS%"=="Windows_NT" setlocal

@rem Add default JVM options here. You can also use JAVA_OPTS and GRADLE_OPTS to pass JVM options to this script.
set DEFAULT_JVM_OPTS=

set DIRNAME=%~dp0
if "%DIRNAME%" == "" set DIRNAME=.
set APP_BASE_NAME=%~n0
set APP_HOME=%DIRNAME%

@rem Find java.exe
if defined JAVA_HOME goto findJavaFromJavaHome

set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if "%ERRORLEVEL%" == "0" goto init

echo.
echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
echo.
echo Please set the JAVA_HOME variable in your environment to match the
echo location of your Java installation.

goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe

if exist "%JAVA_EXE%" goto init

echo.
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME%
echo.
echo Please set the JAVA_HOME variable in your environment to match the
echo location of your Java installation.

goto fail

:init
@rem Get command-line arguments, handling Windowz variants

if not "%OS%" == "Windows_NT" goto win9xME_args
if "%@eval[2+2]" == "4" goto 4NT_args

:win9xME_args
@rem Slurp the command line arguments.
set CMD_LINE_ARGS=
set _SKIP=2

:win9xME_args_slurp
if "x%~1" == "x" goto execute

set CMD_LINE_ARGS=%*
goto execute

:4NT_args
@rem Get arguments from the 4NT Shell from JP Software
set CMD_LINE_ARGS=%$

:execute
@rem Setup the command line

set CLASSPATH=%APP_HOME%\\gradle\\wrapper\\gradle-wrapper.jar

@rem Execute Gradle
"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% "-Dorg.gradle.appname=%APP_BASE_NAME%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %CMD_LINE_ARGS%

:end
@rem End local scope for the variables with windows NT shell
if "%ERRORLEVEL%"=="0" goto mainEnd

:fail
rem Set variable GRADLE_EXIT_CONSOLE if you need the _script_ return code instead of
rem the _cmd.exe /c_ return code!
if  not "" == "%GRADLE_EXIT_CONSOLE%" exit 1
exit /b 1

:mainEnd
if "%OS%"=="Windows_NT" endlocal

:omega
"""

# .gitignore de raíz del proyecto Flutter generado -- recorte del que
# produce `flutter create` (sin las secciones de plataformas que acá no se
# generan: ios/, web/, linux/, macos/, windows/, coverage/).
_RAIZ_GITIGNORE = """# Miscellaneous
*.class
*.log
*.pyc
*.swp
.DS_Store
.atom/
.buildlog/
.history
.svn/
migrate_working_dir/

# IntelliJ related
*.iml
*.ipr
*.iws
.idea/

# The .vscode folder contains launch configuration and tasks you configure in
# VS Code which you may wish to be included in version control, so this line
# is commented out by default.
#.vscode/

# Flutter/Dart/Pub related
**/doc/api/
.dart_tool/
.flutter-plugins
.flutter-plugins-dependencies
.pub-cache/
.pub/
/build/

# Android related
android/.gradle/
android/local.properties
android/**/GeneratedPluginRegistrant.java
"""


def _renderizar_android_build_gradle(paquete: str) -> str:
    return _ANDROID_BUILD_GRADLE_APP.replace("__PAQUETE__", paquete)


def _renderizar_main_activity(paquete: str) -> str:
    return _ANDROID_MAIN_ACTIVITY.replace("__PAQUETE__", paquete)


def _renderizar_android_manifest(nombre_app: str) -> str:
    # android:label es un atributo XML -- escapar &/</>/" para que un
    # nombre de proyecto con esos caracteres no rompa el manifest.
    return _ANDROID_MANIFEST_PRINCIPAL.replace(
        "__NOMBRE_APP__", _escapar_xml(nombre_app, {'"': "&quot;"})
    )


def _agregar_carpeta_android(zf: zipfile.ZipFile, raiz: str, paquete: str, nombre_app: str) -> None:
    base = f"{raiz}/android"
    paquete_dir = paquete.replace(".", "/")

    zf.writestr(f"{base}/.gitignore", _ANDROID_GITIGNORE)
    zf.writestr(f"{base}/settings.gradle.kts", _ANDROID_SETTINGS_GRADLE)
    zf.writestr(f"{base}/build.gradle.kts", _ANDROID_BUILD_GRADLE_RAIZ)
    zf.writestr(f"{base}/gradle.properties", _ANDROID_GRADLE_PROPERTIES)
    zf.writestr(f"{base}/gradle/wrapper/gradle-wrapper.properties", _ANDROID_GRADLE_WRAPPER_PROPERTIES)
    zf.writestr(f"{base}/app/build.gradle.kts", _renderizar_android_build_gradle(paquete))
    zf.writestr(
        f"{base}/app/src/main/kotlin/{paquete_dir}/MainActivity.kt",
        _renderizar_main_activity(paquete),
    )
    zf.writestr(f"{base}/app/src/main/AndroidManifest.xml", _renderizar_android_manifest(nombre_app))
    zf.writestr(f"{base}/app/src/debug/AndroidManifest.xml", _ANDROID_MANIFEST_DEBUG_PROFILE)
    zf.writestr(f"{base}/app/src/profile/AndroidManifest.xml", _ANDROID_MANIFEST_DEBUG_PROFILE)
    zf.writestr(f"{base}/app/src/main/res/values/styles.xml", _ANDROID_STYLES_XML)
    zf.writestr(f"{base}/app/src/main/res/values-night/styles.xml", _ANDROID_STYLES_NIGHT_XML)
    zf.writestr(f"{base}/app/src/main/res/drawable/launch_background.xml", _ANDROID_LAUNCH_BACKGROUND_XML)
    zf.writestr(
        f"{base}/app/src/main/res/drawable-v21/launch_background.xml", _ANDROID_LAUNCH_BACKGROUND_V21_XML
    )
    for densidad in _DENSIDADES_ICONO:
        zf.writestr(
            f"{base}/app/src/main/res/mipmap-{densidad}/ic_launcher.png",
            _leer_asset_android(f"mipmap-{densidad}/ic_launcher.png"),
        )
    zf.writestr(f"{base}/gradle/wrapper/gradle-wrapper.jar", _leer_asset_android("gradle-wrapper.jar"))

    # gradlew es un script Unix -- el bit ejecutable no importa en Windows,
    # pero así el zip queda correcto también si se prueba en Mac/Linux.
    info_gradlew = zipfile.ZipInfo(f"{base}/gradlew")
    info_gradlew.external_attr = 0o755 << 16
    zf.writestr(info_gradlew, _ANDROID_GRADLEW)
    zf.writestr(f"{base}/gradlew.bat", _ANDROID_GRADLEW_BAT)


def _renderizar_readme(nombre_proyecto: str, slug: str, paquete: str, clases_datos: list[DatosClase]) -> str:
    filas_clases = "\n".join(f"- `{d.nombre_dart}` -> `/api/{d.ruta_api}`" for d in clases_datos)

    return f"""# {slug} (frontend Flutter generado - CU15)

App Flutter generada automáticamente a partir del diagrama de clases UML
del proyecto **"{nombre_proyecto}"**. Pensada para consumir el backend
Spring Boot generado por CU08 (mismas rutas `/api/{{plural}}`).

## Requisitos previos

- **Flutter SDK** instalado (cualquier versión estable reciente).
- **Android SDK** configurado (Android Studio, o las cmdline-tools solas)
  con al menos un emulador creado o un dispositivo Android conectado por
  USB con depuración habilitada.
- **JDK 17** — si ya corriste el backend generado por CU08 en esta misma
  máquina, ya lo tenés instalado.

Este proyecto **incluye solo la plataforma Android** (no iOS/web/desktop).

## Antes de correrla: el backend tiene que estar corriendo

Esta app le pega a la URL configurada en `lib/config.dart` al generarla.
Generá y corré el backend de CU08 primero (trae su propio `README.md` con
los pasos) — si necesitás cambiar la URL después, es la única línea para
editar a mano en `lib/config.dart`.

## Cómo ejecutar

Desde la raíz de este proyecto (donde está `pubspec.yaml`):

```
flutter pub get
flutter run
```

Elegí un emulador Android o un dispositivo conectado cuando `flutter run`
lo pida. **No hace falta correr `flutter create .`** ni nada más — la
carpeta `android/` ya viene lista (Gradle 8.14, AGP 8.11.1, Kotlin 2.2.20,
paquete `{paquete}`).

## Qué trae y qué no

- CRUD completo (crear, editar, listar, eliminar) por cada clase, contra
  el backend generado. Arranca **sin datos de ejemplo** — las tablas
  están vacías hasta que cargues algo desde la app.
- **Modo offline** (CU14): guarda los cambios localmente (SQLite) y
  sincroniza solo cuando hay conexión — revisá la pantalla
  "Sincronización" si algo falla al sincronizar.
- Sin autenticación/JWT — igual que el backend generado.
- Solo Android: no se genera `ios/`, `web/` ni desktop.

Clases de este proyecto:

{filas_clases}
"""


def _renderizar_pubspec(slug: str) -> str:
    return f"""name: {slug}
description: Frontend Flutter generado automáticamente a partir del diagrama de clases (CU15).
publish_to: 'none'
version: 1.0.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0
  sqflite: ^2.4.1
  path: ^1.9.1
  connectivity_plus: ^6.1.0
  uuid: ^4.5.1

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0

flutter:
  uses-material-design: true
"""


# --------------------------------------------------------------------------
# Punto de entrada: arma el .zip completo.
# --------------------------------------------------------------------------


def generar_zip_frontend(
    proyecto: Proyecto, clases: list[ClaseUml], relaciones: list[Relacion], url_base: str
) -> bytes:
    slug = slug_paquete(proyecto.nombre)
    campos_relacion_por_clase = _procesar_relaciones(clases, relaciones)

    clases_datos: list[DatosClase] = []
    for c in clases:
        nombre_dart = nombre_clase_java(c.nombre)
        atributos = [
            CampoAtributo(
                nombre_campo=nombre_campo_java(a.nombre),
                tipo_dart=mapear_tipo_dart(a.tipo),
                aviso=(
                    f'tipo UML "{a.tipo}" no reconocido, se usó String por defecto'
                    if tipo_no_reconocido(a.tipo)
                    else None
                ),
            )
            for a in sorted(c.atributos, key=lambda a: a.orden)
            # El modelo ya tiene su propio `int? id` — mismo criterio que CU08.
            if nombre_campo_java(a.nombre).lower() != "id"
        ]
        clases_datos.append(
            DatosClase(
                clase=c,
                nombre_dart=nombre_dart,
                archivo=a_snake_case(nombre_dart),
                ruta_api=pluralizar(nombre_dart).lower(),
                atributos=atributos,
                relaciones=campos_relacion_por_clase.get(c.id, []),
            )
        )

    # CU14 — orden de sincronización entre clases (padres antes que hijos).
    clases_ordenadas = _orden_topologico(clases_datos, clases, relaciones)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        raiz = slug
        paquete = f"com.generado.{slug}"
        zf.writestr(f"{raiz}/pubspec.yaml", _renderizar_pubspec(slug))
        zf.writestr(f"{raiz}/README.md", _renderizar_readme(proyecto.nombre, slug, paquete, clases_datos))
        zf.writestr(f"{raiz}/.gitignore", _RAIZ_GITIGNORE)
        _agregar_carpeta_android(zf, raiz, paquete, proyecto.nombre)
        zf.writestr(f"{raiz}/lib/config.dart", _renderizar_config(url_base))
        zf.writestr(f"{raiz}/lib/main.dart", _renderizar_main(proyecto.nombre, clases_datos))
        zf.writestr(f"{raiz}/lib/offline/db.dart", _renderizar_offline_db(slug, clases_datos))
        zf.writestr(f"{raiz}/lib/offline/conectividad.dart", _renderizar_conectividad())
        zf.writestr(
            f"{raiz}/lib/offline/sync_manager.dart", _renderizar_sync_manager(clases_ordenadas)
        )
        zf.writestr(
            f"{raiz}/lib/screens/sincronizacion_screen.dart",
            _renderizar_sincronizacion_screen(clases_datos),
        )

        for datos in clases_datos:
            zf.writestr(f"{raiz}/lib/models/{datos.archivo}.dart", _renderizar_modelo(datos))
            zf.writestr(
                f"{raiz}/lib/services/{datos.archivo}_service.dart", _renderizar_servicio(datos)
            )
            zf.writestr(
                f"{raiz}/lib/offline/{datos.archivo}_repositorio.dart",
                _renderizar_repositorio(datos),
            )
            zf.writestr(
                f"{raiz}/lib/screens/{datos.archivo}_list_screen.dart",
                _renderizar_list_screen(datos),
            )
            zf.writestr(
                f"{raiz}/lib/screens/{datos.archivo}_form_screen.dart",
                _renderizar_form_screen(datos),
            )

    return buffer.getvalue()
