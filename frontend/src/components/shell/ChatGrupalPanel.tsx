import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

import { etiquetaModo } from '../../collab/useSala'
import type { MensajeSala, ModoIA, useSala } from '../../collab/useSala'

type Sala = ReturnType<typeof useSala>

const MODOS: { value: ModoIA; ayuda: string }[] = [
  { value: 'consultivo', ayuda: 'Solo explica y sugiere; no toca el diagrama.' },
  { value: 'con_confirmacion', ayuda: 'Propone cambios y el equipo decide si aplicarlos.' },
  { value: 'automatico', ayuda: 'Aplica los cambios directamente y los explica.' },
]

/** Markdown mínimo por si el modelo igual lo usa: **negrita** y `código`. */
function TextoRico({ texto }: { texto: string }) {
  const partes = texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return (
    <>
      {partes.map((p, i) =>
        p.startsWith('**') && p.endsWith('**') && p.length > 4 ? (
          <strong key={i}>{p.slice(2, -2)}</strong>
        ) : p.startsWith('`') && p.endsWith('`') && p.length > 2 ? (
          <code key={i}>{p.slice(1, -1)}</code>
        ) : (
          p
        ),
      )}
    </>
  )
}

function hora(fecha: string): string {
  const d = new Date(fecha)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function Propuesta({ mensaje, onDecidir }: { mensaje: MensajeSala; onDecidir: (aprobar: boolean) => void }) {
  const p = mensaje.propuesta
  if (!p) return null
  return (
    <div className={`chat-propuesta chat-propuesta--${p.estado}`}>
      <div className="chat-propuesta__titulo">
        {p.estado === 'pendiente' && 'Cambios propuestos'}
        {p.estado === 'aplicada' && `✓ Cambios aplicados${p.decidida_por ? ` por ${p.decidida_por}` : ''}`}
        {p.estado === 'rechazada' && `✕ Propuesta rechazada${p.decidida_por ? ` por ${p.decidida_por}` : ''}`}
        {p.estado === 'fallida' && '⚠ La propuesta ya no se pudo aplicar'}
      </div>
      <ul>
        {p.resumen.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      {p.estado === 'pendiente' && (
        <div className="chat-propuesta__acciones">
          <button type="button" className="chat-btn chat-btn--primario" onClick={() => onDecidir(true)}>
            Aplicar
          </button>
          <button type="button" className="chat-btn" onClick={() => onDecidir(false)}>
            Rechazar
          </button>
        </div>
      )}
    </div>
  )
}

function Mensaje({
  m,
  propio,
  proyectoActual,
  onDecidir,
}: {
  m: MensajeSala
  propio: boolean
  proyectoActual: number
  onDecidir: (a: boolean) => void
}) {
  if (m.tipo === 'sistema') return <div className="chat-sistema">{m.texto}</div>
  const esIA = m.tipo === 'senior_ai'
  const deOtroProyecto = m.proyecto?.id && m.proyecto.id !== proyectoActual
  return (
    <div className={'chat-msg' + (esIA ? ' chat-msg--ia' : propio ? ' chat-msg--propio' : '')}>
      <div className="chat-msg__meta">
        <span className="chat-msg__autor">{esIA ? 'Senior' : m.autor.nombre}</span>
        <span className={'chat-msg__badge' + (esIA ? ' chat-msg__badge--ia' : '')}>{esIA ? 'IA' : 'humano'}</span>
        <span className="chat-msg__hora">{hora(m.fecha)}</span>
      </div>
      {deOtroProyecto && (
        <div className="chat-msg__proyecto" title="Escrito desde otro proyecto del grupo">
          en {m.proyecto.nombre ?? 'otro proyecto'}
        </div>
      )}
      <div className="chat-msg__texto">
        <TextoRico texto={m.texto} />
      </div>
      {esIA && <Propuesta mensaje={m} onDecidir={onDecidir} />}
    </div>
  )
}

/**
 * Segundo parcial — chat GRUPAL y público de la sala (RF-IA-01/02): todos ven
 * los mismos mensajes, con autor, hora y si es humano o el Senior. La IA solo
 * responde si se la menciona (@senior / "Senior, ...") o con el toggle.
 */
export function ChatGrupalPanel({
  sala,
  usuarioId,
  proyectoId,
}: {
  sala: Sala
  usuarioId: number | undefined
  proyectoId: number
}) {
  const [texto, setTexto] = useState('')
  const [preguntar, setPreguntar] = useState(false)
  const listaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listaRef.current?.scrollTo({ top: listaRef.current.scrollHeight })
  }, [sala.mensajes, sala.seniorEscribiendo])

  const enviar = () => {
    if (!texto.trim()) return
    if (sala.enviarMensaje(texto.trim(), preguntar)) {
      setTexto('')
      setPreguntar(false)
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    enviar()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      enviar()
    }
  }

  return (
    <aside className="agente-panel chat-panel">
      <div className="chat-panel__header">
        <div className="chat-panel__titulo">
          <span>Chat del grupo{sala.grupo ? ` · ${sala.grupo}` : ''}</span>
          <span className={`chat-estado chat-estado--${sala.estado}`} title={`Conexión: ${sala.estado}`} />
        </div>
        <div className="chat-panel__presentes" title="Conectados ahora">
          {sala.presentes.map((u) => (
            <span key={u.id} className="chat-presente">
              ● {u.nombre}
              {u.proyecto && u.proyecto.id !== proyectoId && (
                <span className="chat-presente__donde"> · en {u.proyecto.nombre}</span>
              )}
            </span>
          ))}
        </div>
        <label className="chat-panel__modo">
          Modo del Senior:
          <select value={sala.modo} onChange={(e) => sala.cambiarModo(e.target.value as ModoIA)}>
            {MODOS.map((m) => (
              <option key={m.value} value={m.value} title={m.ayuda}>
                {etiquetaModo(m.value)}
              </option>
            ))}
          </select>
        </label>
        <p className="chat-panel__ayuda">
          {MODOS.find((m) => m.value === sala.modo)?.ayuda} Chat compartido por todos los proyectos del grupo.
        </p>
      </div>

      {sala.aviso && (
        <div className="chat-aviso" role="status">
          {sala.aviso}
          <button type="button" onClick={sala.descartarAviso} aria-label="Cerrar aviso">
            ×
          </button>
        </div>
      )}

      <div className="agente-panel__mensajes" ref={listaRef}>
        {sala.mensajes.length === 0 && (
          <p className="agente-panel__vacio">
            Escribile al equipo. Para preguntarle al Senior, mencionalo (“@senior ¿qué es un atributo derivado?”) o
            activá “Preguntar al Senior”.
          </p>
        )}
        {sala.mensajes.map((m) => (
          <Mensaje
            key={m.id}
            m={m}
            propio={m.autor.id === usuarioId}
            proyectoActual={proyectoId}
            onDecidir={(aprobar) => sala.decidirPropuesta(m.id, aprobar)}
          />
        ))}
        {sala.seniorEscribiendo && (
          <div className="chat-escribiendo">
            Senior está escribiendo{sala.seniorEscribiendo.para ? ` para ${sala.seniorEscribiendo.para}` : ''}…
            {sala.seniorEscribiendo.enCola > 0 && ` (${sala.seniorEscribiendo.enCola} en cola)`}
          </div>
        )}
      </div>

      <form className="agente-panel__form chat-panel__form" onSubmit={onSubmit}>
        <label className="chat-panel__toggle">
          <input type="checkbox" checked={preguntar} onChange={(e) => setPreguntar(e.target.checked)} />
          Preguntar al Senior
        </label>
        <div className="chat-panel__fila">
          <textarea
            className="agente-panel__input"
            rows={2}
            maxLength={2000}
            placeholder={preguntar ? 'Pregunta para el Senior…' : 'Mensaje al grupo (usá @senior para la IA)…'}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="submit" className="chat-btn chat-btn--primario" disabled={!texto.trim()}>
            Enviar
          </button>
        </div>
      </form>
    </aside>
  )
}
