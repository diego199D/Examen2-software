import { useState } from 'react'
import type { FormEvent } from 'react'

import { getApiErrorMessage } from '../api/errors'
import { updateMe } from '../api/usuarios'
import { useAuth } from '../auth/useAuth'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/TextField'
import { formatFecha } from '../lib/format'
import './pages.css'

export function PerfilPage() {
  const { user, refreshUser } = useAuth()

  if (!user) return null

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Perfil</h1>
      </header>

      <div className="perfil-meta">
        <span className={`rol-badge rol-badge--${user.rol.toLowerCase()}`}>{user.rol}</span>
        <span className="page__muted">Miembro desde {formatFecha(user.fecha_registro)}</span>
      </div>

      <DatosForm
        key={`datos-${user.id}-${user.email}`}
        nombreInicial={user.nombre_completo}
        emailInicial={user.email}
        onSaved={refreshUser}
      />
      <PasswordForm />
    </section>
  )
}

function DatosForm({
  nombreInicial,
  emailInicial,
  onSaved,
}: {
  nombreInicial: string
  emailInicial: string
  onSaved: () => Promise<void>
}) {
  const [nombre, setNombre] = useState(nombreInicial)
  const [email, setEmail] = useState(emailInicial)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const sinCambios = nombre.trim() === nombreInicial && email.trim() === emailInicial

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setOk(false)
    setSubmitting(true)
    try {
      await updateMe({ nombre_completo: nombre.trim(), email: email.trim() })
      await onSaved()
      setOk(true)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="card-form" onSubmit={handleSubmit}>
      <h2 className="card-form__title">Datos</h2>
      {error && <Banner>{error}</Banner>}
      {ok && <Banner kind="success">Perfil actualizado</Banner>}
      <TextField
        label="Nombre completo"
        required
        maxLength={150}
        value={nombre}
        onChange={(e) => setNombre(e.target.value)}
      />
      <TextField
        label="Email"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <div className="card-form__actions">
        <Button type="submit" variant="primary" loading={submitting} disabled={sinCambios}>
          Guardar cambios
        </Button>
      </div>
    </form>
  )
}

function PasswordForm() {
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [campoError, setCampoError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setCampoError(null)
    setOk(false)

    if (nueva.length < 8) {
      setCampoError('La nueva contraseña debe tener al menos 8 caracteres')
      return
    }
    if (nueva !== repetir) {
      setCampoError('Las contraseñas no coinciden')
      return
    }

    setSubmitting(true)
    try {
      await updateMe({ password_actual: actual, password_nuevo: nueva })
      setActual('')
      setNueva('')
      setRepetir('')
      setOk(true)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="card-form" onSubmit={handleSubmit}>
      <h2 className="card-form__title">Cambiar contraseña</h2>
      {error && <Banner>{error}</Banner>}
      {ok && <Banner kind="success">Contraseña actualizada</Banner>}
      <TextField
        label="Contraseña actual"
        type="password"
        autoComplete="current-password"
        required
        value={actual}
        onChange={(e) => setActual(e.target.value)}
      />
      <TextField
        label="Nueva contraseña"
        type="password"
        autoComplete="new-password"
        required
        value={nueva}
        error={campoError ?? undefined}
        onChange={(e) => setNueva(e.target.value)}
      />
      <TextField
        label="Repetir nueva contraseña"
        type="password"
        autoComplete="new-password"
        required
        value={repetir}
        onChange={(e) => setRepetir(e.target.value)}
      />
      <div className="card-form__actions">
        <Button type="submit" variant="primary" loading={submitting}>
          Actualizar contraseña
        </Button>
      </div>
    </form>
  )
}
