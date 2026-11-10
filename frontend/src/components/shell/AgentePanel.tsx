import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

import type { MensajeChat } from '../../api/types'

type Props = {
  mensajes: MensajeChat[]
  enviando: boolean
  onEnviar: (texto: string) => void
}

function IconCheck() {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2.5 6.5l2.5 2.5 4.5-5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Burbuja({ mensaje }: { mensaje: MensajeChat }) {
  const clase =
    'agente-panel__burbuja' +
    (mensaje.rol === 'usuario'
      ? ' agente-panel__burbuja--usuario'
      : mensaje.esError
        ? ' agente-panel__burbuja--error'
        : ' agente-panel__burbuja--agente')

  return (
    <div className={clase}>
      {mensaje.texto}
      {mensaje.accion && (
        <span className="agente-panel__accion-aplicada">
          <IconCheck /> Acción aplicada
        </span>
      )}
    </div>
  )
}

export function AgentePanel({ mensajes, enviando, onEnviar }: Props) {
  const [texto, setTexto] = useState('')
  const listaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listaRef.current?.scrollTo({ top: listaRef.current.scrollHeight })
  }, [mensajes, enviando])

  const enviar = () => {
    if (!texto.trim() || enviando) return
    onEnviar(texto)
    setTexto('')
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    enviar()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      enviar()
    }
  }

  return (
    <aside className="agente-panel">
      <div className="agente-panel__header">Asistente</div>

      <div className="agente-panel__mensajes" ref={listaRef}>
        {mensajes.length === 0 && (
          <p className="agente-panel__vacio">
            Pedile que edite el diagrama ("crea una clase Cliente con un atributo nombre") o preguntale sobre UML
            ("¿qué diferencia hay entre agregación y composición?").
          </p>
        )}
        {mensajes.map((m) => (
          <Burbuja key={m.id} mensaje={m} />
        ))}
        {enviando && <div className="agente-panel__burbuja agente-panel__burbuja--agente">Pensando…</div>}
      </div>

      <form className="agente-panel__form" onSubmit={handleSubmit}>
        <textarea
          className="agente-panel__input"
          placeholder="Escribí un mensaje…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
        />
        <button type="submit" className="tool-btn tool-btn--primary" disabled={enviando || !texto.trim()}>
          Enviar
        </button>
      </form>
    </aside>
  )
}
