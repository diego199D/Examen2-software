import { api } from './client'
import type { Colaborador } from './types'

/** CU04 — colaboradores activos de un proyecto propio. */
export async function listColaboradores(proyectoId: number): Promise<Colaborador[]> {
  const { data } = await api.get<Colaborador[]>(`/proyectos/${proyectoId}/colaboradores`)
  return data
}

/** CU05 — agrega (o reactiva) por id de usuario, resuelto vía la búsqueda de CU06. */
export async function agregarColaborador(proyectoId: number, usuarioId: number): Promise<Colaborador> {
  const { data } = await api.post<Colaborador>(`/proyectos/${proyectoId}/colaboradores`, {
    usuario_id: usuarioId,
  })
  return data
}

/** CU05 — quita (soft-delete) por id de usuario, no por id de fila ProyectoColaborador. */
export async function quitarColaborador(proyectoId: number, usuarioId: number): Promise<void> {
  await api.delete(`/proyectos/${proyectoId}/colaboradores/${usuarioId}`)
}
