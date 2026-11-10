import { useState } from 'react'
import type { FormEvent } from 'react'

import { descargarArchivo, generarFrontend } from '../../api/generacion'
import { getApiErrorMessage } from '../../api/errors'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { TextField } from '../ui/TextField'

type Props = {
  proyectoId: number
  onClose: () => void
}

function esUrlValida(valor: string): boolean {
  try {
    const url = new URL(valor.trim())
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

/** CU15 — pide la URL base del backend antes de generar el frontend Flutter. */
export function GenerarFrontendModal({ proyectoId, onClose }: Props) {
  const [urlBase, setUrlBase] = useState('')
  const [tocado, setTocado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [generando, setGenerando] = useState(false)

  const urlValida = esUrlValida(urlBase)
  const mostrarErrorUrl = tocado && urlBase.trim() !== '' && !urlValida

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setTocado(true)
    if (!urlValida) return

    setError(null)
    setGenerando(true)
    try {
      const { blob, nombreArchivo } = await generarFrontend(proyectoId, urlBase.trim())
      descargarArchivo(blob, nombreArchivo)
      onClose()
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo generar el frontend'))
    } finally {
      setGenerando(false)
    }
  }

  return (
    <Modal
      title="Generar frontend Flutter"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={generando}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            form="generar-frontend-form"
            type="submit"
            loading={generando}
            disabled={!urlValida}
          >
            Generar
          </Button>
        </>
      }
    >
      <form id="generar-frontend-form" className="modal-form" onSubmit={handleSubmit}>
        {error && <Banner>{error}</Banner>}
        <TextField
          label="URL base del backend"
          placeholder="http://localhost:8080"
          hint="La app Flutter generada va a consumir el backend en esta URL (rutas /api/{plural}, ej. las que genera 'Generar backend')."
          value={urlBase}
          error={mostrarErrorUrl ? 'Ingresa una URL válida, ej. http://localhost:8080' : undefined}
          onChange={(e) => setUrlBase(e.target.value)}
          onBlur={() => setTocado(true)}
        />
      </form>
    </Modal>
  )
}
