import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/TextField'
import './LoginPage.css'

type LocationState = { from?: string }

export function LoginPage() {
  const { status, login, loginGrupo } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // Segundo parcial: por defecto se entra con nombre personal + nombre de grupo.
  const [modo, setModo] = useState<'grupo' | 'email'>('grupo')
  const [nombre, setNombre] = useState('')
  const [grupo, setGrupo] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (modo === 'grupo') await loginGrupo(nombre.trim(), grupo.trim(), password)
      else await login(email.trim(), password)
      const dest = (location.state as LocationState | null)?.from ?? '/'
      navigate(dest, { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo iniciar sesión'))
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={handleSubmit}>
        <div className="login__head">
          <h1 className="login__title">Diagramador UML</h1>
          <p className="login__subtitle">Iniciar sesión</p>
        </div>

        {error && <Banner>{error}</Banner>}

        <div className="login__modos" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={modo === 'grupo'}
            className={'login__modo' + (modo === 'grupo' ? ' login__modo--activo' : '')}
            onClick={() => setModo('grupo')}
          >
            Nombre y grupo
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={modo === 'email'}
            className={'login__modo' + (modo === 'email' ? ' login__modo--activo' : '')}
            onClick={() => setModo('email')}
          >
            Email
          </button>
        </div>

        {modo === 'grupo' ? (
          <>
            <TextField
              label="Nombre personal"
              autoComplete="username"
              required
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
            />
            <TextField
              label="Nombre del grupo"
              required
              value={grupo}
              onChange={(e) => setGrupo(e.target.value)}
            />
          </>
        ) : (
          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <Button type="submit" variant="primary" block loading={submitting}>
          Entrar
        </Button>

        <p className="login__footer">
          ¿No tienes cuenta? <Link to="/registro">Regístrate</Link>
        </p>
      </form>
    </div>
  )
}
