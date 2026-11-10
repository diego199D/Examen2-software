import { memo, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, RefObject } from 'react'
import { Handle, Position } from 'reactflow'
import type { NodeProps } from 'reactflow'

import type { ClaseUml } from '../../api/types'
import { formatAtributo, formatMetodo, parsearAtributo, parsearMetodo } from './umlFormat'

export type ClassNodeData = {
  clase: ClaseUml
  onCambiar: (clase: ClaseUml) => void
  /** Une sola vez: enfoca el nombre apenas se crea la clase (sin modal). */
  autoEditarNombre?: boolean
}

const SIDES = [Position.Top, Position.Right, Position.Bottom, Position.Left]

/**
 * React Flow remonta el contenido de un nodo con `visibility: hidden` para
 * remedir su tamaño (al crearlo, o cuando cambian sus dimensiones — ej. al
 * agregar una fila) antes de mostrarlo; un `focus()` disparado en ese
 * instante falla en silencio, y a veces el <input> se reemplaza por uno
 * nuevo en el proceso. Por eso se reconsulta el elemento en cada intento
 * (en vez de reusar una referencia que puede quedar desconectada) y se
 * reintenta por varios frames hasta que el foco realmente "pegue".
 */
function enfocarConReintento(obtenerElemento: () => HTMLElement | null, intentos = 20) {
  if (intentos <= 0) return
  const el = obtenerElemento()
  if (el) {
    el.focus()
    if (document.activeElement === el) return
  }
  // El elemento aún no existe (primer render sin montar) o el focus no
  // "pegó" todavía (medición con visibility:hidden en curso) — reintenta.
  requestAnimationFrame(() => enfocarConReintento(obtenerElemento, intentos - 1))
}

/**
 * Confirma la edición al hacer clic fuera del campo. Los divs del nodo no
 * son focuseables, así que `onBlur` NO se dispara al clickear la mayoría de
 * la interfaz (nombre, estereotipo, otras filas) — solo cuando el destino
 * del clic es a su vez otro elemento focuseable. Por eso se escucha a nivel
 * de documento en vez de depender de blur.
 *
 * Se escucha en fase de CAPTURA (el 3er argumento `true`): los controles
 * interactivos del nodo llevan `onMouseDown={e => e.stopPropagation()}`
 * para que React Flow no intercepte el clic como intento de arrastre — eso
 * frena la burbuja normal, así que un listener en fase de burbuja nunca se
 * enteraría. La fase de captura corre ANTES de que el destino (y su
 * stopPropagation) entre en juego, así que sí lo ve.
 */
function useCerrarAlClickAfuera(
  activo: boolean,
  ref: RefObject<HTMLElement | null>,
  onAfuera: () => void,
) {
  const onAfueraRef = useRef(onAfuera)
  useEffect(() => {
    onAfueraRef.current = onAfuera
  })

  useEffect(() => {
    if (!activo) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onAfueraRef.current()
    }
    document.addEventListener('mousedown', handler, true)
    return () => document.removeEventListener('mousedown', handler, true)
  }, [activo, ref])
}

function reordenar<T extends { orden: number }>(items: T[]): T[] {
  return items.map((it, i) => ({ ...it, orden: i }))
}

type MiembroListaProps<T extends { id: string }> = {
  items: T[]
  formatear: (item: T) => string
  parsear: (texto: string, anterior: T) => T
  crearNuevo: () => T
  onCambiar: (items: T[]) => void
  placeholder: string
}

function MiembroLista<T extends { id: string; orden: number }>({
  items,
  formatear,
  parsear,
  crearNuevo,
  onCambiar,
  placeholder,
}: MiembroListaProps<T>) {
  const [editandoId, setEditandoId] = useState<string | null>(null)
  const [texto, setTexto] = useState('')
  const esNuevaRef = useRef(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editandoId !== null) enfocarConReintento(() => inputRef.current)
  }, [editandoId])

  const confirmar = (id: string) => {
    const actual = items.find((i) => i.id === id)
    if (!actual) return
    const t = texto.trim()
    if (!t) onCambiar(reordenar(items.filter((i) => i.id !== id)))
    else onCambiar(reordenar(items.map((i) => (i.id === id ? parsear(t, i) : i))))
    setEditandoId(null)
  }

  useCerrarAlClickAfuera(editandoId !== null, inputRef, () => {
    if (editandoId !== null) confirmar(editandoId)
  })

  const agregarTrasDeId = (despuesDeId?: string) => {
    const nuevo = crearNuevo()
    const idx = despuesDeId ? items.findIndex((i) => i.id === despuesDeId) : items.length - 1
    onCambiar(reordenar([...items.slice(0, idx + 1), nuevo, ...items.slice(idx + 1)]))
    setEditandoId(nuevo.id)
    setTexto('')
    esNuevaRef.current = true
  }

  // Enter confirma la fila actual Y agrega una nueva en un solo cambio: si
  // fueran dos llamadas a onCambiar seguidas (confirmar + agregar), la
  // segunda partiría del mismo `items` desactualizado de la primera (misma
  // closure) y pisaría el texto recién parseado.
  const confirmarYAgregar = (id: string) => {
    const actual = items.find((i) => i.id === id)
    if (!actual) return
    const t = texto.trim()
    const base = t ? items.map((i) => (i.id === id ? parsear(t, i) : i)) : items.filter((i) => i.id !== id)
    const idx = base.findIndex((i) => i.id === id)
    const posInsercion = idx === -1 ? base.length : idx + 1
    const nuevo = crearNuevo()
    onCambiar(reordenar([...base.slice(0, posInsercion), nuevo, ...base.slice(posInsercion)]))
    setEditandoId(nuevo.id)
    setTexto('')
    esNuevaRef.current = true
  }

  const empezarEdicion = (item: T) => {
    setEditandoId(item.id)
    setTexto(formatear(item))
    esNuevaRef.current = false
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>, id: string) => {
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      confirmarYAgregar(id)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      if (esNuevaRef.current) onCambiar(reordenar(items.filter((i) => i.id !== id)))
      setEditandoId(null)
    } else if (e.key === 'Backspace' && texto === '') {
      e.preventDefault()
      onCambiar(reordenar(items.filter((i) => i.id !== id)))
      setEditandoId(null)
    }
  }

  return (
    <ul className="class-node__compartment">
      {items.map((item) =>
        editandoId === item.id ? (
          <li key={item.id}>
            <input
              ref={inputRef}
              className="nodrag class-node__miembro-input"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => handleKeyDown(e, item.id)}
            />
          </li>
        ) : (
          // La acción va en onMouseDown (no onClick): el "clic afuera" de un
          // campo hermano (nombre/estereotipo) reacciona al mousedown y
          // puede re-renderizar el nodo antes de que el navegador entregue
          // el click posterior — a veces ese click nunca llega a su target.
          // Disparando la acción ya en el mousedown, cae en el mismo batch
          // síncrono que ese cierre, sin depender del click.
          <li
            key={item.id}
            className="class-node__miembro nodrag"
            onMouseDown={(e) => {
              e.stopPropagation()
              empezarEdicion(item)
            }}
          >
            <span>{formatear(item)}</span>
            <button
              type="button"
              className="class-node__miembro-quitar nodrag"
              aria-label="Quitar"
              onMouseDown={(e) => {
                e.stopPropagation()
                onCambiar(reordenar(items.filter((i) => i.id !== item.id)))
              }}
            >
              ×
            </button>
          </li>
        ),
      )}
      <li
        className="class-node__miembro-agregar nodrag"
        onMouseDown={(e) => {
          e.stopPropagation()
          agregarTrasDeId()
        }}
      >
        + {placeholder}
      </li>
    </ul>
  )
}

function ClassNodeComponent({ data, selected }: NodeProps<ClassNodeData>) {
  const { clase, onCambiar, autoEditarNombre } = data

  const [editandoNombre, setEditandoNombre] = useState(Boolean(autoEditarNombre))
  const [nombreTmp, setNombreTmp] = useState(clase.nombre)
  const [editandoEstereotipo, setEditandoEstereotipo] = useState(false)
  const [estereotipoTmp, setEstereotipoTmp] = useState(clase.estereotipo ?? '')
  const nombreInputRef = useRef<HTMLInputElement>(null)
  const estereotipoInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editandoNombre) enfocarConReintento(() => nombreInputRef.current)
  }, [editandoNombre])

  useEffect(() => {
    if (editandoEstereotipo) enfocarConReintento(() => estereotipoInputRef.current)
  }, [editandoEstereotipo])

  const confirmarNombre = () => {
    const n = nombreTmp.trim()
    if (n && n !== clase.nombre) onCambiar({ ...clase, nombre: n })
    else if (!n) setNombreTmp(clase.nombre)
    setEditandoNombre(false)
  }

  const confirmarEstereotipo = () => {
    const e = estereotipoTmp.trim() || null
    if (e !== clase.estereotipo) onCambiar({ ...clase, estereotipo: e })
    setEditandoEstereotipo(false)
  }

  useCerrarAlClickAfuera(editandoNombre, nombreInputRef, confirmarNombre)
  useCerrarAlClickAfuera(editandoEstereotipo, estereotipoInputRef, confirmarEstereotipo)

  return (
    <div className={selected ? 'class-node class-node--selected' : 'class-node'}>
      {SIDES.map((side) => (
        <Handle key={side} type="source" position={side} id={side} className="class-node__handle" />
      ))}

      <div className="class-node__drag-handle" title="Arrastrar para mover la clase">
        <span />
        <span />
        <span />
      </div>

      <div className="class-node__header">
        <button
          type="button"
          className="nodrag class-node__abstract-toggle"
          aria-pressed={clase.es_abstracta}
          title="Marcar como clase abstracta"
          onMouseDown={(e) => {
            e.stopPropagation()
            onCambiar({ ...clase, es_abstracta: !clase.es_abstracta })
          }}
        >
          A
        </button>

        {editandoEstereotipo ? (
          <input
            ref={estereotipoInputRef}
            className="nodrag class-node__stereotype-input"
            placeholder="estereotipo"
            value={estereotipoTmp}
            onChange={(e) => setEstereotipoTmp(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === 'Tab') {
                if (e.key === 'Enter') e.preventDefault()
                confirmarEstereotipo()
              } else if (e.key === 'Escape') {
                setEstereotipoTmp(clase.estereotipo ?? '')
                setEditandoEstereotipo(false)
              }
            }}
          />
        ) : (
          <div
            className={
              clase.estereotipo
                ? 'nodrag class-node__stereotype'
                : 'nodrag class-node__stereotype class-node__stereotype--vacio'
            }
            onMouseDown={(e) => {
              e.stopPropagation()
              setEstereotipoTmp(clase.estereotipo ?? '')
              setEditandoEstereotipo(true)
            }}
          >
            {clase.estereotipo ? `«${clase.estereotipo}»` : '+ estereotipo'}
          </div>
        )}

        {editandoNombre ? (
          <input
            ref={nombreInputRef}
            className="nodrag class-node__name-input"
            value={nombreTmp}
            onChange={(e) => setNombreTmp(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === 'Tab') {
                if (e.key === 'Enter') e.preventDefault()
                confirmarNombre()
              } else if (e.key === 'Escape') {
                setNombreTmp(clase.nombre)
                setEditandoNombre(false)
              }
            }}
          />
        ) : (
          <div
            className={
              clase.es_abstracta
                ? 'nodrag class-node__name class-node__name--abstract'
                : 'nodrag class-node__name'
            }
            onMouseDown={(e) => {
              e.stopPropagation()
              setNombreTmp(clase.nombre)
              setEditandoNombre(true)
            }}
          >
            {clase.nombre || 'Sin nombre'}
          </div>
        )}
      </div>

      <MiembroLista
        items={clase.atributos}
        formatear={formatAtributo}
        parsear={parsearAtributo}
        crearNuevo={() => ({
          id: crypto.randomUUID(),
          nombre: '',
          tipo: null,
          visibilidad: 'PRIVADO' as const,
          orden: clase.atributos.length,
        })}
        onCambiar={(atributos) => onCambiar({ ...clase, atributos })}
        placeholder="agregar atributo"
      />

      <MiembroLista
        items={clase.metodos}
        formatear={formatMetodo}
        parsear={parsearMetodo}
        crearNuevo={() => ({
          id: crypto.randomUUID(),
          nombre: '',
          parametros: null,
          tipo_retorno: null,
          visibilidad: 'PUBLICO' as const,
          orden: clase.metodos.length,
        })}
        onCambiar={(metodos) => onCambiar({ ...clase, metodos })}
        placeholder="agregar método"
      />
    </div>
  )
}

export const ClassNode = memo(ClassNodeComponent)
