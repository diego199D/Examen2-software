import { api } from './client'
import type { DiagramaData, TipoRelacion } from './types'

export type AtributoDetectado = { nombre: string; tipo: string | null }
export type MetodoDetectado = { nombre: string; tipo_retorno: string | null }
export type ClaseDetectada = { nombre: string; atributos: AtributoDetectado[]; metodos: MetodoDetectado[] }
export type RelacionDetectada = {
  clase_origen: string
  clase_destino: string
  tipo: TipoRelacion
  etiqueta?: string | null
  multiplicidad_origen: string | null
  multiplicidad_destino: string | null
}

/** CU12 — vista previa devuelta por el reconocimiento (sin aplicar todavía)
 * y también el body que espera `/confirmar` -- mismo JSON de ida y vuelta,
 * el usuario puede revisarlo en el frontend antes de confirmar. */
export type ReconocimientoFotoResultado = {
  reconocido: boolean
  mensaje: string
  clases: ClaseDetectada[]
  relaciones: RelacionDetectada[]
  /** Correcciones automáticas del backend sobre lo que devolvió el modelo
   * (p. ej. una composición sin rombo dibujado tomada como asociación). */
  advertencias?: string[]
}

export type ConfirmarReconocimientoResultado = {
  diagrama: DiagramaData
  advertencias: string[]
}

/** Nunca aplica nada -- es la vista previa. 400 si el archivo no es una
 * imagen válida o no se reconoce ningún diagrama en ella. */
export async function reconocerDiagramaFoto(proyectoId: number, archivo: File): Promise<ReconocimientoFotoResultado> {
  const formData = new FormData()
  formData.append('archivo', archivo)
  const { data } = await api.post<ReconocimientoFotoResultado>(
    `/proyectos/${proyectoId}/reconocimiento-foto`,
    formData,
  )
  return data
}

/** Aplica la vista previa (ya revisada por el usuario) al diagrama --
 * AGREGA sobre lo que ya exista, no requiere que el diagrama esté vacío. */
export async function confirmarReconocimientoFoto(
  proyectoId: number,
  resultado: ReconocimientoFotoResultado,
): Promise<ConfirmarReconocimientoResultado> {
  const { data } = await api.post<ConfirmarReconocimientoResultado>(
    `/proyectos/${proyectoId}/reconocimiento-foto/confirmar`,
    resultado,
  )
  return data
}
