export type RolUsuario = 'ADMINISTRADOR' | 'COLABORADOR'

export type Usuario = {
  id: number
  nombre_completo: string
  email: string
  rol: RolUsuario
  fecha_registro: string
}

export type PerfilUpdate = {
  nombre_completo?: string
  email?: string
  password_actual?: string
  password_nuevo?: string
}

export type Proyecto = {
  id: number
  nombre: string
  descripcion: string | null
  id_administrador: number
  fecha_creacion: string
  rol_en_proyecto: RolUsuario
}

export type ProyectoInput = {
  nombre: string
  descripcion?: string | null
}

export type RegistroInput = {
  nombre_completo: string
  email: string
  password: string
}

export type Colaborador = {
  id: number
  id_proyecto: number
  id_usuario: number
  fecha_asignacion: string
  activo: boolean
  usuario: Usuario
}

/** CU06 — resultado de búsqueda de usuarios (sin fecha_registro). */
export type UsuarioBusqueda = {
  id: number
  nombre_completo: string
  email: string
  rol: RolUsuario
}

export type Token = {
  access_token: string
  token_type: string
}

export type Visibilidad = 'PUBLICO' | 'PRIVADO' | 'PROTEGIDO' | 'PAQUETE'
export type TipoRelacion = 'ASOCIACION' | 'HERENCIA' | 'AGREGACION' | 'COMPOSICION'

export type AtributoUml = {
  id: string
  nombre: string
  tipo: string | null
  visibilidad: Visibilidad
  orden: number
}

export type MetodoUml = {
  id: string
  nombre: string
  parametros: string | null
  tipo_retorno: string | null
  visibilidad: Visibilidad
  orden: number
}

export type ClaseUml = {
  id: string
  nombre: string
  estereotipo: string | null
  es_abstracta: boolean
  pos_x: number
  pos_y: number
  atributos: AtributoUml[]
  metodos: MetodoUml[]
}

export type RelacionUml = {
  id: string
  id_clase_origen: string
  id_clase_destino: string
  tipo: TipoRelacion
  etiqueta: string | null
  multiplicidad_origen: string | null
  multiplicidad_destino: string | null
  handle_origen: string | null
  handle_destino: string | null
  // Solo visuales (ver RelacionEdge.tsx): forma de la línea (null = RECTA) y
  // corrimiento del punto de control respecto del punto medio entre extremos.
  forma?: FormaRelacion | null
  desvio_x?: number | null
  desvio_y?: number | null
}

export type FormaRelacion = 'RECTA' | 'L' | 'CURVA'

export type DiagramaData = {
  clases: ClaseUml[]
  relaciones: RelacionUml[]
}

// --- CU11 — comandos de voz --------------------------------------------

/** Atributo aún sin id: lo genera el cliente al aplicar la acción. */
export type AtributoNuevo = {
  nombre: string
  tipo: string | null
  visibilidad: Visibilidad
}

export type AccionCrearClase = {
  accion: 'crear_clase'
  nombre_clase: string
  atributos: AtributoNuevo[]
  resumen: string
}

export type AccionAgregarAtributo = {
  accion: 'agregar_atributo'
  id_clase: string
  nombre_clase: string
  atributo: AtributoNuevo
  resumen: string
}

export type AccionEliminarClase = {
  accion: 'eliminar_clase'
  id_clase: string
  nombre_clase: string
  resumen: string
}

export type AccionCrearRelacion = {
  accion: 'crear_relacion'
  id_clase_origen: string
  id_clase_destino: string
  nombre_clase_origen: string
  nombre_clase_destino: string
  tipo: TipoRelacion
  multiplicidad_origen: string | null
  multiplicidad_destino: string | null
  resumen: string
}

export type AccionRenombrarClase = {
  accion: 'renombrar_clase'
  id_clase: string
  nombre_anterior: string
  nombre_nuevo: string
  resumen: string
}

/** Extremo de una relación de `AccionModificarDiagrama`: `id_clase` si la
 * clase ya existe, `null` si es una de las `clases_nuevas` del mismo comando
 * (se resuelve por `nombre_clase` al aplicarla). */
export type ExtremoRelacionVoz = {
  id_clase: string | null
  nombre_clase: string
}

/** CU11 — comando en lenguaje natural: varias clases, atributos y
 * relaciones (con tipo/multiplicidad deducidos) de una sola vez. */
export type AccionModificarDiagrama = {
  accion: 'modificar_diagrama'
  clases_nuevas: { nombre: string; atributos: AtributoNuevo[] }[]
  atributos_agregados: { id_clase: string; nombre_clase: string; atributos: AtributoNuevo[] }[]
  relaciones: {
    origen: ExtremoRelacionVoz
    destino: ExtremoRelacionVoz
    tipo: TipoRelacion
    multiplicidad_origen: string | null
    multiplicidad_destino: string | null
    etiqueta: string | null
  }[]
  advertencias: string[]
  resumen: string
}

export type AccionVoz =
  | AccionCrearClase
  | AccionAgregarAtributo
  | AccionEliminarClase
  | AccionCrearRelacion
  | AccionRenombrarClase
  | AccionModificarDiagrama

// --- CU13 — agente conversacional ---------------------------------------

export type RolMensajeChat = 'usuario' | 'agente'

/** Mensaje mostrado en el panel del agente. `accion` (si vino) es para el
 * indicador visual de "acción aplicada"; `esError` distingue un mensaje de
 * error de red/servicio de una respuesta normal del agente. */
export type MensajeChat = {
  id: string
  rol: RolMensajeChat
  texto: string
  accion?: AccionVoz | null
  esError?: boolean
}

export type AgenteRespuesta = {
  texto: string
  accion: AccionVoz | null
}
