import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getApiErrorMessage } from '../api/errors'
import { listProyectos } from '../api/proyectos'
import type { Proyecto } from '../api/types'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { formatFecha } from '../lib/format'
import { EliminarProyectoDialog } from './EliminarProyectoDialog'
import { ProyectoFormModal } from './ProyectoFormModal'
import './pages.css'

type Estado = 'cargando' | 'listo' | 'error'
type Dialogo =
  | { tipo: 'crear' }
  | { tipo: 'editar'; proyecto: Proyecto }
  | { tipo: 'eliminar'; proyecto: Proyecto }
  | null

export function ProyectosPage() {
  const [proyectos, setProyectos] = useState<Proyecto[]>([])
  const [estado, setEstado] = useState<Estado>('cargando')
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [dialogo, setDialogo] = useState<Dialogo>(null)

  useEffect(() => {
    let alive = true
    listProyectos()
      .then((data) => {
        if (!alive) return
        setProyectos(data)
        setEstado('listo')
      })
      .catch((err) => {
        if (!alive) return
        setError(getApiErrorMessage(err, 'No se pudieron cargar los proyectos'))
        setEstado('error')
      })
    return () => {
      alive = false
    }
  }, [tick])

  const recargar = useCallback(() => {
    setEstado('cargando')
    setError(null)
    setTick((t) => t + 1)
  }, [])

  const cerrarDialogo = () => setDialogo(null)
  const trasGuardar = () => {
    setDialogo(null)
    recargar()
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Proyectos</h1>
        <Button variant="primary" onClick={() => setDialogo({ tipo: 'crear' })}>
          Nuevo proyecto
        </Button>
      </header>

      {estado === 'cargando' && <p className="page__muted">Cargando proyectos…</p>}

      {estado === 'error' && (
        <div className="page__stack">
          <Banner>{error}</Banner>
          <Button onClick={recargar}>Reintentar</Button>
        </div>
      )}

      {estado === 'listo' && proyectos.length === 0 && (
        <div className="empty">
          <p className="empty__title">Aún no tienes proyectos</p>
          <p className="page__muted">Crea el primero para empezar a modelar.</p>
        </div>
      )}

      {estado === 'listo' && proyectos.length > 0 && (
        <ul className="proyecto-list">
          {proyectos.map((p) => (
            <li key={p.id} className="proyecto-row">
              <div className="proyecto-row__info">
                <div className="proyecto-row__titulo">
                  <Link to={`/proyectos/${p.id}`} className="proyecto-row__nombre">
                    {p.nombre}
                  </Link>
                  <span className={`rol-badge rol-badge--${p.rol_en_proyecto.toLowerCase()}`}>
                    {p.rol_en_proyecto === 'ADMINISTRADOR' ? 'Administrador' : 'Colaborador'}
                  </span>
                </div>
                {p.descripcion && <p className="proyecto-row__desc">{p.descripcion}</p>}
                <p className="proyecto-row__meta">Creado el {formatFecha(p.fecha_creacion)}</p>
              </div>
              <div className="proyecto-row__actions">
                <Link className="btn btn--secondary" to={`/proyectos/${p.id}`}>
                  Abrir
                </Link>
                {p.rol_en_proyecto === 'ADMINISTRADOR' && (
                  <>
                    <Button onClick={() => setDialogo({ tipo: 'editar', proyecto: p })}>
                      Editar
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => setDialogo({ tipo: 'eliminar', proyecto: p })}
                    >
                      Eliminar
                    </Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {dialogo?.tipo === 'crear' && (
        <ProyectoFormModal onClose={cerrarDialogo} onSaved={trasGuardar} />
      )}
      {dialogo?.tipo === 'editar' && (
        <ProyectoFormModal
          proyecto={dialogo.proyecto}
          onClose={cerrarDialogo}
          onSaved={trasGuardar}
        />
      )}
      {dialogo?.tipo === 'eliminar' && (
        <EliminarProyectoDialog
          proyecto={dialogo.proyecto}
          onClose={cerrarDialogo}
          onDeleted={trasGuardar}
        />
      )}
    </section>
  )
}
