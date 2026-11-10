import { useContext } from 'react'

import { AuthContext } from './authContext'
import type { AuthState } from './authContext'

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return ctx
}
