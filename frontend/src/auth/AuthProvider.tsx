import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { loginRequest, registroRequest } from '../api/auth'
import { setUnauthorizedHandler } from '../api/client'
import { getMe } from '../api/usuarios'
import type { RegistroInput, Usuario } from '../api/types'
import { AuthContext } from './authContext'
import type { AuthStatus } from './authContext'
import { clearToken, getToken, setToken } from './tokenStorage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null)
  const [status, setStatus] = useState<AuthStatus>(() =>
    getToken() ? 'loading' : 'anonymous',
  )

  // Reacción global a un 401 en cualquier petición autenticada.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      setStatus('anonymous')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  // Hidratación inicial: si hay token, recuperar el usuario.
  useEffect(() => {
    if (!getToken()) return
    let alive = true
    getMe()
      .then((u) => {
        if (!alive) return
        setUser(u)
        setStatus('authenticated')
      })
      .catch(() => {
        if (!alive) return
        clearToken()
        setUser(null)
        setStatus('anonymous')
      })
    return () => {
      alive = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginRequest(email, password)
    setToken(token)
    const u = await getMe()
    setUser(u)
    setStatus('authenticated')
  }, [])

  const registro = useCallback(async (datos: RegistroInput) => {
    const token = await registroRequest(datos)
    setToken(token)
    const u = await getMe()
    setUser(u)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const refreshUser = useCallback(async () => {
    setUser(await getMe())
  }, [])

  return (
    <AuthContext.Provider value={{ user, status, login, registro, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}
