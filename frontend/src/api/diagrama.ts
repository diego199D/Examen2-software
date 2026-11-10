import { api } from './client'
import type { DiagramaData } from './types'

/** CU09 — diagrama de clases de un proyecto propio o colaborado. */
export async function getDiagrama(proyectoId: number): Promise<DiagramaData> {
  const { data } = await api.get<DiagramaData>(`/proyectos/${proyectoId}/diagrama`)
  return data
}

/** Reemplaza el diagrama completo (autoguardado). */
export async function guardarDiagrama(
  proyectoId: number,
  datos: DiagramaData,
): Promise<DiagramaData> {
  const { data } = await api.put<DiagramaData>(`/proyectos/${proyectoId}/diagrama`, datos)
  return data
}

export type ImportacionXmiResultado = {
  diagrama: DiagramaData
  advertencias: string[]
}

/**
 * CU09 — importa un archivo .xmi como el diagrama de clases del proyecto.
 * Solo se admite sobre un diagrama todavía vacío (el backend responde 409
 * si el proyecto ya tiene clases, 400 si el archivo no es XML válido o no
 * contiene ninguna clase UML reconocible) — ver `app/services/importador_xmi.py`.
 */
export async function importarDiagramaXmi(
  proyectoId: number,
  archivo: File,
): Promise<ImportacionXmiResultado> {
  const formData = new FormData()
  formData.append('archivo', archivo)
  const { data } = await api.post<ImportacionXmiResultado>(
    `/proyectos/${proyectoId}/diagrama/importar-xmi`,
    formData,
  )
  return data
}
