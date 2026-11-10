import { api } from './client'
import type { AccionVoz } from './types'

/**
 * CU11 — interpreta un comando de voz ya transcrito por el navegador (Web
 * Speech API) y devuelve la acción estructurada correspondiente (ids ya
 * resueltos contra el diagrama actual). No persiste nada del lado del
 * backend -- quien aplica la acción es el frontend, ver `useComandoVoz.ts`.
 */
export async function interpretarComandoVoz(proyectoId: number, texto: string): Promise<AccionVoz> {
  const { data } = await api.post<AccionVoz>(`/proyectos/${proyectoId}/comandos-voz`, { texto })
  return data
}
