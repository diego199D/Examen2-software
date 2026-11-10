import { createContext } from 'react'

import type { RegistroInput, Usuario } from '../api/types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export type AuthState = {
  user: Usuario | null
  status: AuthStatus
  login: (email: string, password: string) => Promise<void>
  registro: (datos: RegistroInput) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)
