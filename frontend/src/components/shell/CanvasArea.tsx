import { useEffect, useRef } from 'react'
import type { MouseEvent } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  useReactFlow,
} from 'reactflow'
import type {
  Connection,
  Edge,
  Node,
  OnEdgesChange,
  OnNodesChange,
} from 'reactflow'

import { CursoresRemotos } from '../../collab/CursoresRemotos'
import type { CursorRemoto } from '../../collab/useColaboracion'
import { ClassNode } from './ClassNode'
import type { ClassNodeData } from './ClassNode'
import { RelacionEdge } from './RelacionEdge'
import type { EdgeData } from './useDiagrama'
import { UmlMarkers } from './UmlMarkers'
import './diagram.css'

const nodeTypes = { classNode: ClassNode }
const edgeTypes = { relacion: RelacionEdge }

// CU10 — no hace falta publicar la posición del mouse en cada pixel; cada
// 40ms (~25/s) ya se ve fluido en el cursor remoto y es una fracción del
// tráfico de awareness.
const THROTTLE_CURSOR_MS = 40

type Props = {
  nodes: Node<ClassNodeData>[]
  edges: Edge<EdgeData>[]
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onNodeDragStop: () => void
  onConnect: (connection: Connection) => void
  onEdgeDoubleClick: (event: MouseEvent, edge: Edge<EdgeData>) => void
  cargando: boolean
  error: string | null
  cursores: CursorRemoto[]
  onPublicarCursor: (posicion: { x: number; y: number } | null) => void
  onDeshacer: () => void
  onRehacer: () => void
}

/** Un campo de texto en edición (nombre de clase, atributo, etc.) maneja su
 * propio Ctrl+Z nativo del navegador -- interceptarlo ahí rompería esa
 * edición en curso, así que el atajo de deshacer/rehacer del diagrama solo
 * actúa fuera de un campo editable. */
function enCampoEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
}

export function CanvasArea({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onNodeDragStop,
  onConnect,
  onEdgeDoubleClick,
  cargando,
  error,
  cursores,
  onPublicarCursor,
  onDeshacer,
  onRehacer,
}: Props) {
  const { fitView, screenToFlowPosition } = useReactFlow()
  const ultimoEnvioRef = useRef(0)

  // Ajusta la vista una vez que el diagrama terminó de cargar (fitView del
  // <ReactFlow> solo actúa en el montaje, y en el montaje aún no hay nodos).
  useEffect(() => {
    if (!cargando && !error && nodes.length > 0) {
      const t = setTimeout(() => fitView({ padding: 0.25 }), 0)
      return () => clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargando])

  // Ctrl+Z / Ctrl+Shift+Z (o Ctrl+Y) mientras se trabaja en el lienzo del
  // editor -- se escucha a nivel de ventana (no hace falta que el <main>
  // tenga foco propio, los nodos no son focuseables) pero se ignora si el
  // target es un campo de texto en edición, para no pisar su undo nativo.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || enCampoEditable(e.target)) return
      const tecla = e.key.toLowerCase()
      if (tecla === 'z' && e.shiftKey) {
        e.preventDefault()
        onRehacer()
      } else if (tecla === 'z') {
        e.preventDefault()
        onDeshacer()
      } else if (tecla === 'y') {
        e.preventDefault()
        onRehacer()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onDeshacer, onRehacer])

  // CU10 — posición del mouse local, en coordenadas de React Flow (no de
  // pantalla: así el cursor se ve en el lugar correcto para cualquier otro
  // colaborador sin importar su propio zoom/scroll). Con throttle para no
  // saturar el canal de awareness; se limpia al salir del lienzo.
  const handlePointerMove = (e: MouseEvent) => {
    const ahora = Date.now()
    if (ahora - ultimoEnvioRef.current < THROTTLE_CURSOR_MS) return
    ultimoEnvioRef.current = ahora
    onPublicarCursor(screenToFlowPosition({ x: e.clientX, y: e.clientY }))
  }

  return (
    <main className="app-canvas" onMouseMove={handlePointerMove} onMouseLeave={() => onPublicarCursor(null)}>
      <UmlMarkers />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        onEdgeDoubleClick={onEdgeDoubleClick}
        connectionMode={ConnectionMode.Loose}
        deleteKeyCode={['Backspace', 'Delete']}
        nodesFocusable={false}
      >
        <Background id="minor" variant={BackgroundVariant.Dots} gap={16} size={1} color="#d3d8e0" />
        <Background id="major" variant={BackgroundVariant.Lines} gap={96} lineWidth={1} color="#e7eaf0" />
        <Controls showInteractive={false} />
      </ReactFlow>

      <CursoresRemotos cursores={cursores} />

      {cargando && <div className="canvas-overlay">Cargando diagrama…</div>}
      {error && <div className="canvas-overlay canvas-overlay--error">{error}</div>}
      {!cargando && !error && nodes.length === 0 && (
        <div className="canvas-overlay canvas-overlay--hint">
          Este diagrama está vacío. Usa "Nueva clase" para empezar.
        </div>
      )}
    </main>
  )
}
