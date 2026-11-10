import { useState } from 'react'

import { getApiErrorMessage, getApiErrorStatus } from '../api/errors'
import { deleteProyecto } from '../api/proyectos'
import type { Proyecto } from '../api/types'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'

type Props = {
  proyecto: Proyecto
  onClose: () => void
  onDeleted: () => void
}

export function EliminarProyectoDialog({ proyecto, onClose, onDeleted }: Props) {
  const [necesitaConfirmar, setNecesitaConfirmar] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const eliminar = async (confirmar: boolean) => {
    setError(null)
    setSubmitting(true)
    try {
      await deleteProyecto(proyecto.id, confirmar)
      onDeleted()
    } catch (err) {
      if (getApiErrorStatus(err) === 409 && !confirmar) {
        setNecesitaConfirmar(true)
        setAviso(getApiErrorMessage(err))
      } else {
        setError(getApiErrorMessage(err))
      }
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="Eliminar proyecto"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={submitting}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            loading={submitting}
            onClick={() => eliminar(necesitaConfirmar)}
          >
            {necesitaConfirmar ? 'Eliminar de todos modos' : 'Eliminar'}
          </Button>
        </>
      }
    >
      {error && <Banner>{error}</Banner>}
      {necesitaConfirmar && aviso ? (
        <Banner kind="error">{aviso}</Banner>
      ) : (
        <p>
          ¿Seguro que quieres eliminar el proyecto <strong>{proyecto.nombre}</strong>? Esta
          acción no se puede deshacer.
        </p>
      )}
    </Modal>
  )
}
