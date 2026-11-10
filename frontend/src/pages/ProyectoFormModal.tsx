import { useState } from 'react'
import type { FormEvent } from 'react'

import { getApiErrorMessage, getApiErrorStatus } from '../api/errors'
import { createProyecto, updateProyecto } from '../api/proyectos'
import type { Proyecto } from '../api/types'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { TextField } from '../components/ui/TextField'

type Props = {
  proyecto?: Proyecto
  onClose: () => void
  onSaved: () => void
}

export function ProyectoFormModal({ proyecto, onClose, onSaved }: Props) {
  const editando = proyecto !== undefined
  const [nombre, setNombre] = useState(proyecto?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(proyecto?.descripcion ?? '')
  const [nombreError, setNombreError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setNombreError(null)

    const nombreLimpio = nombre.trim()
    if (!nombreLimpio) {
      setNombreError('El nombre es obligatorio')
      return
    }

    setSubmitting(true)
    try {
      const payload = { nombre: nombreLimpio, descripcion: descripcion.trim() || null }
      if (editando) {
        await updateProyecto(proyecto.id, payload)
      } else {
        await createProyecto(payload)
      }
      onSaved()
    } catch (err) {
      if (getApiErrorStatus(err) === 409) {
        setNombreError(getApiErrorMessage(err))
      } else {
        setError(getApiErrorMessage(err))
      }
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={editando ? 'Editar proyecto' : 'Nuevo proyecto'}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={submitting}>
            Cancelar
          </Button>
          <Button variant="primary" form="proyecto-form" type="submit" loading={submitting}>
            {editando ? 'Guardar' : 'Crear'}
          </Button>
        </>
      }
    >
      <form id="proyecto-form" className="modal-form" onSubmit={handleSubmit}>
        {error && <Banner>{error}</Banner>}
        <TextField
          label="Nombre"
          required
          maxLength={150}
          value={nombre}
          error={nombreError ?? undefined}
          onChange={(e) => setNombre(e.target.value)}
        />
        <div className="field">
          <label className="field__label" htmlFor="proyecto-descripcion">
            Descripción
          </label>
          <textarea
            id="proyecto-descripcion"
            className="field__textarea"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        </div>
      </form>
    </Modal>
  )
}
