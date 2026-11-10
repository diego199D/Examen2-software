import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/TextField'
import './LoginPage.css'

export function RegistroPage() {
  const { status, registro } = useAuth()
  const navigate = useNavigate()

  const [nombreCompleto, setNombreCompleto] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmarPassword, setConfirmarPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (password !== confirmarPassword) {
      setError('Las contraseñas no coinciden')
      return
    }

    setSubmitting(true)
    try {
      await registro({ nombre_completo: nombreCompleto.trim(), email: email.trim(), password })
      navigate('/', { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo crear la cuenta'))
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={handleSubmit}>
        <div className="login__head">
          <h1 className="login__title">Diagramador UML</h1>
          <p className="login__subtitle">Crear cuenta</p>
        </div>

        {error && <Banner>{error}</Banner>}

        <TextField
          label="Nombre completo"
          required
          maxLength={150}
          value={nombreCompleto}
          onChange={(e) => setNombreCompleto(e.target.value)}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Confirmar contraseña"
          type="password"
          autoComplete="new-password"
          required
          value={confirmarPassword}
          onChange={(e) => setConfirmarPassword(e.target.value)}
        />

        <Button type="submit" variant="primary" block loading={submitting}>
          Crear cuenta
        </Button>

        <p className="login__footer">
          ¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link>
        </p>
      </form>
    </div>
  )
}
