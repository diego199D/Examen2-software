import { useEffect, useRef, useState } from 'react'

import { agregarColaborador, listColaboradores, quitarColaborador } from '../api/colaboradores'
import { getApiErrorMessage } from '../api/errors'
import type { Colaborador, UsuarioBusqueda } from '../api/types'
import { buscarUsuarios } from '../api/usuarios'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { TextField } from '../components/ui/TextField'
import { iniciales } from '../lib/format'

type Props = {
  proyectoId: number
  onClose: () => void
}

type Carga = 'cargando' | 'listo' | 'error'

const DEBOUNCE_BUSQUEDA_MS = 300

export function ColaboradoresModal({ proyectoId, onClose }: Props) {
  const [carga, setCarga] = useState<Carga>('cargando')
  const [colaboradores, setColaboradores] = useState<Colaborador[]>([])
  const [cargaError, setCargaError] = useState<string | null>(null)

  const [busqueda, setBusqueda] = useState('')
  const [resultados, setResultados] = useState<UsuarioBusqueda[]>([])
  const [buscando, setBuscando] = useState(false)
  const [agregandoId, setAgregandoId] = useState<number | null>(null)
  const [quitandoId, setQuitandoId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Evita pisar resultados si una búsqueda vieja resuelve después de una nueva.
  const busquedaIdRef = useRef(0)

  // Sin setState directo en el cuerpo: solo dentro de then/catch (async), así
  // el efecto de montaje no dispara "setState síncrono en un efecto" — el
  // estado inicial ya es 'cargando' vía useState.
  const cargarColaboradores = () => {
    listColaboradores(proyectoId)
      .then((data) => {
        setColaboradores(data)
        setCarga('listo')
      })
      .catch((err) => {
        setCargaError(getApiErrorMessage(err, 'No se pudieron cargar los colaboradores'))
        setCarga('error')
      })
  }

  const recargarColaboradores = () => {
    setCarga('cargando')
    cargarColaboradores()
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(cargarColaboradores, [proyectoId])

  // Búsqueda con debounce: espera a que la usuaria deje de escribir. El
  // "Buscando…" se activa desde el propio onChange (evento real), no acá,
  // para no disparar setState síncrono dentro del efecto.
  useEffect(() => {
    const termino = busqueda.trim()
    if (!termino) return

    const idDeEstaBusqueda = ++busquedaIdRef.current
    const timeout = setTimeout(() => {
      buscarUsuarios(termino, proyectoId)
        .then((data) => {
          if (busquedaIdRef.current !== idDeEstaBusqueda) return // llegó una búsqueda más nueva primero
          setResultados(data)
        })
        .catch((err) => {
          if (busquedaIdRef.current !== idDeEstaBusqueda) return
          setError(getApiErrorMessage(err, 'No se pudo buscar usuarios'))
          setResultados([])
        })
        .finally(() => {
          if (busquedaIdRef.current === idDeEstaBusqueda) setBuscando(false)
        })
    }, DEBOUNCE_BUSQUEDA_MS)

    return () => clearTimeout(timeout)
  }, [busqueda, proyectoId])

  const handleBusquedaChange = (valor: string) => {
    setBusqueda(valor)
    if (valor.trim()) setBuscando(true)
    else {
      setBuscando(false)
      setResultados([])
    }
  }

  const handleAgregar = async (usuario: UsuarioBusqueda) => {
    setError(null)
    setAgregandoId(usuario.id)
    try {
      await agregarColaborador(proyectoId, usuario.id)
      setBusqueda('')
      setResultados([])
      recargarColaboradores()
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo agregar al colaborador'))
    } finally {
      setAgregandoId(null)
    }
  }

  const handleQuitar = async (colaborador: Colaborador) => {
    setError(null)
    setQuitandoId(colaborador.usuario.id)
    try {
      await quitarColaborador(proyectoId, colaborador.usuario.id)
      setColaboradores((actual) => actual.filter((c) => c.usuario.id !== colaborador.usuario.id))
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo quitar al colaborador'))
    } finally {
      setQuitandoId(null)
    }
  }

  return (
    <Modal title="Colaboradores del proyecto" onClose={onClose} footer={<Button onClick={onClose}>Cerrar</Button>}>
      {error && (
        <Banner>
          <span className="colaborador-banner__mensaje">{error}</span>
          <button type="button" className="colaborador-banner__cerrar" onClick={() => setError(null)}>
            Cerrar
          </button>
        </Banner>
      )}

      <div className="colaborador-buscador">
        <TextField
          label="Agregar colaborador"
          placeholder="Buscar por nombre o email…"
          value={busqueda}
          onChange={(e) => handleBusquedaChange(e.target.value)}
        />

        {busqueda.trim() && (
          <div className="colaborador-buscador__resultados">
            {buscando && <p className="page__muted">Buscando…</p>}
            {!buscando && resultados.length === 0 && (
              <p className="page__muted">Sin resultados para "{busqueda.trim()}".</p>
            )}
            {!buscando && resultados.length > 0 && (
              <ul className="colaborador-resultados-list">
                {resultados.map((u) => (
                  <li key={u.id}>
                    <button
                      type="button"
                      className="colaborador-resultado"
                      disabled={agregandoId !== null}
                      onClick={() => handleAgregar(u)}
                    >
                      <span className="app-toolbar__chip">
                        <span className="app-toolbar__avatar" aria-hidden="true">
                          {iniciales(u.nombre_completo)}
                        </span>
                        {u.nombre_completo}
                      </span>
                      <span className="proyecto-row__meta">{u.email}</span>
                      <span className="colaborador-resultado__accion">
                        {agregandoId === u.id ? 'Agregando…' : 'Agregar'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {carga === 'cargando' && <p className="page__muted">Cargando colaboradores…</p>}
      {carga === 'error' && <Banner>{cargaError}</Banner>}
      {carga === 'listo' && colaboradores.length === 0 && (
        <p className="page__muted">Este proyecto todavía no tiene colaboradores.</p>
      )}

      {carga === 'listo' && colaboradores.length > 0 && (
        <ul className="proyecto-list">
          {colaboradores.map((c) => (
            <li key={c.id} className="proyecto-row">
              <div className="proyecto-row__info">
                <span className="app-toolbar__chip">
                  <span className="app-toolbar__avatar" aria-hidden="true">
                    {iniciales(c.usuario.nombre_completo)}
                  </span>
                  {c.usuario.nombre_completo}
                </span>
                <p className="proyecto-row__meta">{c.usuario.email}</p>
              </div>
              <div className="proyecto-row__actions">
                <Button
                  variant="danger"
                  loading={quitandoId === c.usuario.id}
                  onClick={() => handleQuitar(c)}
                >
                  Quitar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
