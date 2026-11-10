import { useState } from 'react'
import type { FormEvent } from 'react'

import type { FormaRelacion, TipoRelacion } from '../../api/types'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { TextField } from '../ui/TextField'
import type { DetallesRelacion } from './useDiagrama'
import './diagramModals.css'
import { OPCIONES_FORMA_RELACION, OPCIONES_MULTIPLICIDAD, OPCIONES_TIPO_RELACION } from './umlFormat'

type Props = {
  titulo: string
  valorInicial: DetallesRelacion
  /** Clases elegibles como clase de asociación (todas menos los extremos). */
  clasesCandidatas?: { id: string; nombre: string }[]
  onClose: () => void
  onGuardar: (detalles: DetallesRelacion, invertir: boolean) => void
  onEliminar?: () => void
}

const PLURALES = new Set(['*', '0..*', '1..*'])

export function RelacionEditorModal({
  titulo,
  valorInicial,
  clasesCandidatas = [],
  onClose,
  onGuardar,
  onEliminar,
}: Props) {
  const [tipo, setTipo] = useState<TipoRelacion>(valorInicial.tipo)
  const [etiqueta, setEtiqueta] = useState(valorInicial.etiqueta ?? '')
  const [multOrigen, setMultOrigen] = useState(valorInicial.multiplicidad_origen ?? '')
  const [multDestino, setMultDestino] = useState(valorInicial.multiplicidad_destino ?? '')
  const [forma, setForma] = useState<FormaRelacion>(valorInicial.forma ?? 'RECTA')
  const [invertida, setInvertida] = useState(false)
  const [claseAsociacion, setClaseAsociacion] = useState(valorInicial.id_clase_asociacion ?? '')
  const [tablaIntermedia, setTablaIntermedia] = useState(valorInicial.tabla_intermedia ?? '')

  const esMuchosAMuchos = PLURALES.has(multOrigen) && PLURALES.has(multDestino)
  const admiteAsociacion = tipo !== 'HERENCIA'
  const tablaValida = !tablaIntermedia.trim() || /^[a-z_][a-z0-9_]{0,62}$/.test(tablaIntermedia.trim())

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!tablaValida) return
    onGuardar(
      {
        tipo,
        etiqueta: etiqueta.trim() || null,
        multiplicidad_origen: multOrigen.trim() || null,
        multiplicidad_destino: multDestino.trim() || null,
        forma,
        id_clase_asociacion: admiteAsociacion ? claseAsociacion || null : null,
        tabla_intermedia:
          esMuchosAMuchos && !claseAsociacion && tablaIntermedia.trim() ? tablaIntermedia.trim() : null,
      },
      invertida,
    )
    onClose()
  }

  // Swapea las multiplicidades ya en el propio formulario (feedback
  // inmediato) — el origen/destino de las clases y sus handles se
  // swapean recién al guardar (actualizarRelacion en useDiagrama.ts),
  // que es quien tiene el edge real de React Flow.
  const handleInvertir = () => {
    setMultOrigen(multDestino)
    setMultDestino(multOrigen)
    setInvertida((v) => !v)
  }

  const handleEliminar = () => {
    if (window.confirm('¿Eliminar esta relación?')) {
      onEliminar?.()
      onClose()
    }
  }

  return (
    <Modal
      title={titulo}
      onClose={onClose}
      footer={
        <>
          {onEliminar && (
            <Button variant="danger" onClick={handleEliminar}>
              Eliminar relación
            </Button>
          )}
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" form="relacion-form" type="submit">
            Guardar
          </Button>
        </>
      }
    >
      <form id="relacion-form" className="modal-form" onSubmit={handleSubmit}>
        <div className="field">
          <label className="field__label" htmlFor="relacion-tipo">
            Tipo de relación
          </label>
          <select
            id="relacion-tipo"
            className="field__input"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoRelacion)}
          >
            {OPCIONES_TIPO_RELACION.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="relacion-forma">
            Forma de la línea
          </label>
          <select
            id="relacion-forma"
            className="field__input"
            value={forma}
            onChange={(e) => setForma(e.target.value as FormaRelacion)}
          >
            {OPCIONES_FORMA_RELACION.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="field__hint">
            Seleccioná la línea en el lienzo y arrastrá el punto ● para moverla (doble clic sobre el punto la
            vuelve al centro).
          </p>
        </div>

        {onEliminar && (
          <Button type="button" onClick={handleInvertir}>
            {invertida ? '⇄ Dirección invertida' : '⇄ Invertir dirección'}
          </Button>
        )}

        <TextField
          label="Etiqueta"
          placeholder="ej. administra"
          maxLength={100}
          value={etiqueta}
          onChange={(e) => setEtiqueta(e.target.value)}
        />

        <div className="relacion-form__multiplicidades">
          <div className="field">
            <label className="field__label" htmlFor="relacion-mult-origen">
              Multiplicidad origen
            </label>
            <select
              id="relacion-mult-origen"
              className="field__input"
              value={multOrigen}
              onChange={(e) => setMultOrigen(e.target.value)}
            >
              {OPCIONES_MULTIPLICIDAD.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="relacion-mult-destino">
              Multiplicidad destino
            </label>
            <select
              id="relacion-mult-destino"
              className="field__input"
              value={multDestino}
              onChange={(e) => setMultDestino(e.target.value)}
            >
              {OPCIONES_MULTIPLICIDAD.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {esMuchosAMuchos && (
          <p className="field__hint">
            Muchos a muchos: el backend generado crea una tabla intermedia con PK compuesta y rutas para
            vincular/desvincular.
          </p>
        )}

        {admiteAsociacion && (
          <div className="field">
            <label className="field__label" htmlFor="relacion-clase-asociacion">
              Clase de asociación
            </label>
            <select
              id="relacion-clase-asociacion"
              className="field__input"
              value={claseAsociacion}
              onChange={(e) => setClaseAsociacion(e.target.value)}
            >
              <option value="">(ninguna)</option>
              {clasesCandidatas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
            <p className="field__hint">
              Para un vínculo con atributos propios (ej. Matricula con nota y fecha entre Estudiante y Curso):
              esa clase pasa a ser la tabla intermedia.
            </p>
          </div>
        )}

        {esMuchosAMuchos && !claseAsociacion && (
          <TextField
            label="Nombre de la tabla intermedia (opcional)"
            placeholder="por defecto: tablaA_tablaB en orden alfabético"
            maxLength={63}
            value={tablaIntermedia}
            onChange={(e) => setTablaIntermedia(e.target.value.toLowerCase())}
            error={tablaValida ? undefined : 'Solo minúsculas, dígitos y _, empezando por letra'}
          />
        )}
      </form>
    </Modal>
  )
}
