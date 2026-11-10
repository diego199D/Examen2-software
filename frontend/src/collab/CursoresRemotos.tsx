import type { CSSProperties } from 'react'
import { useReactFlow } from 'reactflow'

import type { CursorRemoto } from './useColaboracion'
import './cursores.css'

function IconoCursor({ color }: { color: string }) {
  return (
    <svg width="16" height="18" viewBox="0 0 16 18" fill="none" aria-hidden="true">
      <path
        d="M1 1l5.5 14.5 2.2-5.8 5.8-2.2z"
        fill={color}
        stroke="white"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * CU10 — dibuja el cursor + nombre de cada colaborador conectado en su
 * posición actual. Las coordenadas que trae `cursores` son en espacio de
 * React Flow (ver useColaboracion/CanvasArea), así que se convierten de
 * vuelta a coordenadas de pantalla con `flowToScreenPosition` — esas SÍ
 * coinciden con `position: fixed` sin ningún offset extra (ambas se miden
 * desde el borde del `<div class="react-flow">`, ver la implementación de
 * screenToFlowPosition/flowToScreenPosition en @reactflow/core).
 */
export function CursoresRemotos({ cursores }: { cursores: CursorRemoto[] }) {
  const { flowToScreenPosition } = useReactFlow()

  if (cursores.length === 0) return null

  return (
    <div className="cursores-overlay" aria-hidden="true">
      {cursores.map((c) => {
        const pos = flowToScreenPosition({ x: c.x, y: c.y })
        const estilo = { left: pos.x, top: pos.y, '--cursor-color': c.color } as CSSProperties
        return (
          <div key={c.clientId} className="cursor-remoto" style={estilo}>
            <IconoCursor color={c.color} />
            <span className="cursor-remoto__etiqueta">{c.nombre}</span>
          </div>
        )
      })}
    </div>
  )
}
