import { useState } from 'react'
import { ReactFlowProvider } from 'reactflow'
import type { Connection, Edge } from 'reactflow'

import type { Proyecto } from '../../api/types'
import { AgentePanel } from './AgentePanel'
import { AccionesRelacionContext } from './accionesRelacion'
import { CanvasArea } from './CanvasArea'
import { RelacionEditorModal } from './RelacionEditorModal'
import { Sidebar } from './Sidebar'
import { Toolbar } from './Toolbar'
import { useAgente } from './useAgente'
import { useComandoVoz } from './useComandoVoz'
import type { EdgeData } from './useDiagrama'
import { nuevaClaseVacia, useDiagrama } from './useDiagrama'
import './shell.css'

type ModalDiagrama =
  | { tipo: 'relacion-nueva'; conexion: Connection }
  | { tipo: 'relacion-editar'; edge: Edge<EdgeData> }
  | null

const RELACION_DEFAULT = {
  tipo: 'ASOCIACION' as const,
  etiqueta: null,
  multiplicidad_origen: null,
  multiplicidad_destino: null,
  forma: null,
}

export function AppShell({ project }: { project: Proyecto }) {
  const diagrama = useDiagrama(project.id)
  const comandoVoz = useComandoVoz(project.id, diagrama)
  const agente = useAgente(project.id, diagrama)
  const [modal, setModal] = useState<ModalDiagrama>(null)
  const [sidebarAbierto, setSidebarAbierto] = useState(true)

  const cerrarModal = () => setModal(null)

  const abrirNuevaClase = () => {
    diagrama.agregarClase(nuevaClaseVacia(diagrama.nodes.length))
  }

  const onConnect = (conexion: Connection) => {
    if (!conexion.source || !conexion.target) return
    setModal({ tipo: 'relacion-nueva', conexion })
  }

  return (
    <ReactFlowProvider>
      <div
        className={
          'app-shell' +
          (sidebarAbierto ? '' : ' app-shell--sidebar-colapsado') +
          (agente.abierto ? ' app-shell--agente-abierto' : '')
        }
      >
        <Toolbar
          project={project}
          onNuevaClase={abrirNuevaClase}
          guardando={diagrama.guardando}
          errorGuardado={diagrama.errorGuardado}
          onReintentarGuardado={diagrama.reintentarGuardado}
          estadoConexion={diagrama.estadoConexion}
          colaboradores={diagrama.colaboradores}
          diagramaVacio={diagrama.estado === 'listo' && diagrama.nodes.length === 0}
          onDiagramaReemplazado={diagrama.importarDiagrama}
          comandoVoz={comandoVoz}
          agenteAbierto={agente.abierto}
          onToggleAgente={agente.toggleAbierto}
        />
        <Sidebar
          clases={diagrama.nodes.map((n) => ({ id: n.id, nombre: n.data.clase.nombre }))}
          seleccionadas={diagrama.nodes.filter((n) => n.selected).map((n) => n.id)}
          onSeleccionar={diagrama.seleccionarClase}
          onCrear={abrirNuevaClase}
          abierto={sidebarAbierto}
          onToggle={() => setSidebarAbierto((v) => !v)}
        />
        <AccionesRelacionContext.Provider value={diagrama.moverPuntoRelacion}>
        <CanvasArea
          nodes={diagrama.nodes}
          edges={diagrama.edges}
          onNodesChange={diagrama.onNodesChange}
          onEdgesChange={diagrama.onEdgesChange}
          onNodeDragStop={diagrama.onNodeDragStop}
          onConnect={onConnect}
          onEdgeDoubleClick={(_e, edge) => setModal({ tipo: 'relacion-editar', edge })}
          cargando={diagrama.estado === 'cargando'}
          error={diagrama.estado === 'error' ? diagrama.error : null}
          cursores={diagrama.cursores}
          onPublicarCursor={diagrama.publicarCursor}
          onDeshacer={diagrama.deshacer}
          onRehacer={diagrama.rehacer}
        />
        </AccionesRelacionContext.Provider>
        {agente.abierto && (
          <AgentePanel mensajes={agente.mensajes} enviando={agente.enviando} onEnviar={agente.enviarMensaje} />
        )}
      </div>

      {modal?.tipo === 'relacion-nueva' && (
        <RelacionEditorModal
          titulo="Nueva relación"
          valorInicial={RELACION_DEFAULT}
          onClose={cerrarModal}
          onGuardar={(detalles) => diagrama.crearRelacion(modal.conexion, detalles)}
        />
      )}

      {modal?.tipo === 'relacion-editar' && (
        <RelacionEditorModal
          titulo="Editar relación"
          valorInicial={modal.edge.data ?? RELACION_DEFAULT}
          onClose={cerrarModal}
          onGuardar={(detalles, invertir) => diagrama.actualizarRelacion(modal.edge.id, detalles, invertir)}
          onEliminar={() => diagrama.eliminarRelacion(modal.edge.id)}
        />
      )}
    </ReactFlowProvider>
  )
}
