import { api } from './client'
import type { PerfilUpdate, Usuario, UsuarioBusqueda } from './types'

/** CU03 — perfil del usuario autenticado. */
export async function getMe(): Promise<Usuario> {
  const { data } = await api.get<Usuario>('/usuarios/me')
  return data
}

/**
 * CU06 — busca usuarios registrados por nombre o email (coincidencia
 * parcial). `proyectoId` es opcional: si se pasa, el backend excluye a
 * quienes ya son colaboradores activos de ese proyecto (y exige que quien
 * busca tenga acceso a él).
 */
export async function buscarUsuarios(q: string, proyectoId?: number): Promise<UsuarioBusqueda[]> {
  const { data } = await api.get<UsuarioBusqueda[]>('/usuarios/buscar', {
    params: { q, proyecto_id: proyectoId },
  })
  return data
}

/** CU03 — editar el perfil (nombre, email y/o contraseña). */
export async function updateMe(payload: PerfilUpdate): Promise<Usuario> {
  const { data } = await api.put<Usuario>('/usuarios/me', payload)
  return data
}
