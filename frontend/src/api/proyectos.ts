import { api } from './client'
import type { Proyecto, ProyectoInput } from './types'

/** CU04 — proyectos que administra el usuario autenticado. */
export async function listProyectos(): Promise<Proyecto[]> {
  const { data } = await api.get<Proyecto[]>('/proyectos')
  return data
}

export async function createProyecto(input: ProyectoInput): Promise<Proyecto> {
  const { data } = await api.post<Proyecto>('/proyectos', input)
  return data
}

export async function updateProyecto(
  id: number,
  input: Partial<ProyectoInput>,
): Promise<Proyecto> {
  const { data } = await api.put<Proyecto>(`/proyectos/${id}`, input)
  return data
}

export async function deleteProyecto(id: number, confirmar = false): Promise<void> {
  await api.delete(`/proyectos/${id}`, {
    params: confirmar ? { confirmar: true } : undefined,
  })
}
