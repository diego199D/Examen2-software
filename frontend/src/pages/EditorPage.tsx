import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getApiErrorMessage } from '../api/errors'
import { listProyectos } from '../api/proyectos'
import type { Proyecto } from '../api/types'
import { AppShell } from '../components/shell/AppShell'
import { Banner } from '../components/ui/Banner'
import './pages.css'

type Estado =
  | { fase: 'cargando' }
  | { fase: 'listo'; proyecto: Proyecto }
  | { fase: 'no-encontrado' }
  | { fase: 'error'; mensaje: string }

export function EditorPage() {
  const { id } = useParams<{ id: string }>()
  const proyectoId = Number(id)
  const idValido = Number.isInteger(proyectoId) && proyectoId > 0
  const [estado, setEstado] = useState<Estado>(
    idValido ? { fase: 'cargando' } : { fase: 'no-encontrado' },
  )

  useEffect(() => {
    if (!idValido) return
    let alive = true
    // No hay GET /proyectos/{id}: se busca en la lista del usuario.
    listProyectos()
      .then((lista) => {
        if (!alive) return
        const encontrado = lista.find((p) => p.id === proyectoId)
        setEstado(encontrado ? { fase: 'listo', proyecto: encontrado } : { fase: 'no-encontrado' })
      })
      .catch((err) => {
        if (alive) setEstado({ fase: 'error', mensaje: getApiErrorMessage(err) })
      })
    return () => {
      alive = false
    }
  }, [proyectoId, idValido])

  if (estado.fase === 'cargando') {
    return <div className="editor-fallback">Cargando proyecto…</div>
  }

  if (estado.fase === 'listo') {
    return <AppShell project={estado.proyecto} />
  }

  return (
    <div className="editor-fallback editor-fallback--stack">
      {estado.fase === 'error' ? (
        <Banner>{estado.mensaje}</Banner>
      ) : (
        <p>Este proyecto no existe o no tienes acceso.</p>
      )}
      <Link className="btn btn--secondary" to="/">
        ← Volver a proyectos
      </Link>
    </div>
  )
}
