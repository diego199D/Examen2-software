import { useCallback, useState } from 'react'
import { ReactFlowProvider } from 'reactflow'
import type { Connection, Edge } from 'reactflow'

import type { DiagramaData, Proyecto } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import { useSala } from '../../collab/useSala'
import { ChatGrupalPanel } from './ChatGrupalPanel'
import { AccionesRelacionContext } from './accionesRelacion'
import { CanvasArea } from './CanvasArea'
import { RelacionEditorModal } from './RelacionEditorModal'
import { Sidebar } from './Sidebar'
import { Toolbar } from './Toolbar'
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
  const { user } = useAuth()
  // Segundo parcial: chat grupal + Senior. El panel privado del asistente
  // (CU13) se reemplazó por este chat público (no hay canales privados con
  // la IA). Los cambios que aplica el Senior llegan por Yjs como cualquier
  // cambio remoto; el snapshot del evento solo se usa si Yjs no conectó.
  const { estadoConexion, importarDiagrama } = diagrama
  const onDiagramaIA = useCallback(
    (datos: DiagramaData) => {
      if (estadoConexion !== 'conectado') importarDiagrama(datos)
    },
    [estadoConexion, importarDiagrama],
  )
  const sala = useSala(project.id, onDiagramaIA)
  const [chatAbierto, setChatAbierto] = useState(true)
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

  // Clases que pueden ser "clase de asociación" de una relación: cualquiera
  // del diagrama salvo sus propios extremos.
  const clasesCandidatas = (origen: string | null, destino: string | null) =>
    diagrama.nodes
      .filter((n) => n.id !== origen && n.id !== destino && n.data.clase.nombre.trim())
      .map((n) => ({ id: n.id, nombre: n.data.clase.nombre }))

  return (
    <ReactFlowProvider>
      <div
        className={
          'app-shell' +
          (sidebarAbierto ? '' : ' app-shell--sidebar-colapsado') +
          (chatAbierto ? ' app-shell--agente-abierto' : '')
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
          agenteAbierto={chatAbierto}
          onToggleAgente={() => setChatAbierto((v) => !v)}
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
        {chatAbierto && <ChatGrupalPanel sala={sala} usuarioId={user?.id} proyectoId={project.id} />}
      </div>

      {modal?.tipo === 'relacion-nueva' && (
        <RelacionEditorModal
          titulo="Nueva relación"
          valorInicial={RELACION_DEFAULT}
          clasesCandidatas={clasesCandidatas(modal.conexion.source, modal.conexion.target)}
          onClose={cerrarModal}
          onGuardar={(detalles) => diagrama.crearRelacion(modal.conexion, detalles)}
        />
      )}

      {modal?.tipo === 'relacion-editar' && (
        <RelacionEditorModal
          titulo="Editar relación"
          valorInicial={modal.edge.data ?? RELACION_DEFAULT}
          clasesCandidatas={clasesCandidatas(modal.edge.source, modal.edge.target)}
          onClose={cerrarModal}
          onGuardar={(detalles, invertir) => diagrama.actualizarRelacion(modal.edge.id, detalles, invertir)}
          onEliminar={() => diagrama.eliminarRelacion(modal.edge.id)}
        />
      )}
    </ReactFlowProvider>
  )
}
