import { api } from './client'
import type { RegistroInput, Token } from './types'

/** CU01 — inicio de sesión. El backend espera form-urlencoded con `username` = email. */
export async function loginRequest(email: string, password: string): Promise<string> {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)

  const { data } = await api.post<Token>('/auth/login', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data.access_token
}

/** Segundo parcial — inicio de sesión con nombre personal + nombre de grupo. */
export async function loginGrupoRequest(nombreCompleto: string, nombreGrupo: string, password: string): Promise<string> {
  const { data } = await api.post<Token>('/auth/login-grupo', {
    nombre_completo: nombreCompleto,
    nombre_grupo: nombreGrupo,
    password,
  })
  return data.access_token
}

/** Registro público: el usuario nuevo queda como ADMINISTRADOR de sus propios proyectos. */
export async function registroRequest(datos: RegistroInput): Promise<string> {
  const { data } = await api.post<Token>('/auth/registro', datos)
  return data.access_token
}
