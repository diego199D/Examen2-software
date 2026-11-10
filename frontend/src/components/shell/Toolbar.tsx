import { useRef, useState } from 'react'
import type { ChangeEvent, CSSProperties, ReactNode } from 'react'
import { toPng } from 'html-to-image'
import { getNodesBounds, getViewportForBounds, useReactFlow } from 'reactflow'
import { Link, useNavigate } from 'react-router-dom'

import { importarDiagramaXmi } from '../../api/diagrama'
import { descargarArchivo, generarBackend } from '../../api/generacion'
import { generarReportePdf, generarReporteXmi } from '../../api/reportes'
import { getApiErrorMessage } from '../../api/errors'
import type { DiagramaData, Proyecto } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import type { ColaboradorPresencia, EstadoConexion } from '../../collab/useColaboracion'
import '../../collab/cursores.css'
import { iniciales } from '../../lib/format'
import { ColaboradoresModal } from '../../pages/ColaboradoresModal'
import { GenerarFrontendModal } from './GenerarFrontendModal'
import type { FormatoReporte } from './MenuArchivo'
import { MenuArchivo } from './MenuArchivo'
import { ReconocimientoFotoModal } from './ReconocimientoFotoModal'
import type { useComandoVoz } from './useComandoVoz'

const MENSAJE_SIN_CONTENIDO = 'No hay contenido disponible para exportar. Agrega al menos una clase al diagrama.'

/** Nombre de archivo seguro (sin acentos ni caracteres especiales) a partir del nombre del proyecto. */
function slugNombreArchivo(nombre: string): string {
  const limpio = nombre
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
  return limpio || 'diagrama'
}

function descargarDataUrl(dataUrl: string, nombreArchivo: string): void {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = nombreArchivo
  document.body.appendChild(a)
  a.click()
  a.remove()
}

type ToolButtonProps = {
  children: ReactNode
  icon?: ReactNode
  primary?: boolean
  disabled?: boolean
  onClick?: () => void
  title?: string
}

function ToolButton({ children, icon, primary, disabled, onClick, title }: ToolButtonProps) {
  return (
    <button
      type="button"
      className={primary ? 'tool-btn tool-btn--primary' : 'tool-btn'}
      disabled={disabled}
      onClick={onClick}
      title={title}
    >
      {icon}
      {children}
    </button>
  )
}

function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function IconFit() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2 5V2h3M12 5V2H9M2 9v3h3M12 9v3H9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconUsers() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M5 6.5a2 2 0 100-4 2 2 0 000 4zM1.5 12c0-2 1.5-3.5 3.5-3.5S8.5 10 8.5 12M9.5 4a1.8 1.8 0 110 3.6M9 8.7c1.6.1 2.9 1.5 3 3.3"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** CU11 — ícono de micrófono, mismo lenguaje visual (trazo currentColor,
 * strokeWidth 1.5) que el resto de los íconos de la toolbar. Pensado para
 * convivir con un futuro botón de cámara (CU12) bajo la misma clase
 * `.tool-btn--icon-circular`. */
function IconMic() {
  return (
    <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="5" y="1" width="4" height="7" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M2.5 6.5v.5a4.5 4.5 0 009 0v-.5M7 11.5v1.5M4.5 13h5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconStop() {
  return (
    <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor" />
    </svg>
  )
}

const ETIQUETA_CONEXION: Record<EstadoConexion, string> = {
  conectado: 'En vivo',
  conectando: 'Conectando…',
  desconectado: 'Sin conexión — reintentando…',
}

/** CU10 — punto de estado discreto del WebSocket de colaboración. */
function IndicadorConexion({ estado }: { estado: EstadoConexion }) {
  return (
    <span
      className={`app-toolbar__conexion app-toolbar__conexion--${estado}`}
      title="Colaboración en tiempo real"
    >
      <span className="app-toolbar__conexion-punto" aria-hidden="true" />
      {ETIQUETA_CONEXION[estado]}
    </span>
  )
}

/** CU10 — quién más está viendo/editando este diagrama ahora mismo. */
function Presencia({ colaboradores }: { colaboradores: ColaboradorPresencia[] }) {
  if (colaboradores.length === 0) return null
  return (
    <span className="app-toolbar__presencia" title={colaboradores.map((c) => c.nombre).join(', ')}>
      {colaboradores.map((c) => (
        <span
          key={c.clientId}
          className="app-toolbar__avatar-colaborador"
          style={{ '--colaborador-color': c.color } as CSSProperties}
        >
          {iniciales(c.nombre)}
        </span>
      ))}
    </span>
  )
}

type ToolbarProps = {
  project: Proyecto
  onNuevaClase: () => void
  guardando: boolean
  errorGuardado: string | null
  onReintentarGuardado: () => void
  estadoConexion: EstadoConexion
  colaboradores: ColaboradorPresencia[]
  diagramaVacio: boolean
  onDiagramaReemplazado: (datos: DiagramaData) => void
  comandoVoz: ReturnType<typeof useComandoVoz>
  agenteAbierto: boolean
  onToggleAgente: () => void
}

/** CU13 — ícono de burbuja de chat para el botón "Asistente". */
function IconChat() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M1.5 3.5A1.5 1.5 0 013 2h8a1.5 1.5 0 011.5 1.5v5A1.5 1.5 0 0111 10H5.5L2.5 12v-2H3a1.5 1.5 0 01-1.5-1.5v-5z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * CU11 — botón circular de comando por voz. Estados: idle (outline),
 * escuchando (relleno + anillo pulsante, ícono de stop) y procesando
 * (disabled). La escucha no se corta sola con los silencios: sigue hasta que
 * se vuelve a presionar el botón (stop), y recién ahí se envía el comando.
 * La clase `.tool-btn--icon-circular` es la base compartida con el botón de
 * cámara de CU12 -- mismo tamaño/forma/tratamiento de estados.
 */
function BotonComandoVoz({ comandoVoz }: { comandoVoz: ReturnType<typeof useComandoVoz> }) {
  const { soportado, escuchando, procesando, transcripcionParcial, alternarEscucha } = comandoVoz
  const titulo = !soportado
    ? 'Tu navegador no soporta reconocimiento de voz'
    : escuchando
      ? 'Detener y enviar el comando'
      : procesando
        ? 'Interpretando el comando…'
        : 'Comando de voz'
  const textoEnVivo = transcripcionParcial ? `Escuchando: ${transcripcionParcial}` : 'Escuchando…'

  return (
    <>
      <button
        type="button"
        className={
          'tool-btn--icon-circular' +
          (escuchando ? ' tool-btn--icon-circular-activo' : '') +
          (procesando ? ' tool-btn--icon-circular-procesando' : '')
        }
        disabled={!soportado || procesando}
        title={titulo}
        aria-label={titulo}
        onClick={alternarEscucha}
      >
        {escuchando ? <IconStop /> : <IconMic />}
      </button>
      {escuchando && (
        <span className="app-toolbar__transcripcion-voz" title={textoEnVivo} aria-live="polite">
          {textoEnVivo}
        </span>
      )}
    </>
  )
}

export function Toolbar({
  project,
  onNuevaClase,
  guardando,
  errorGuardado,
  onReintentarGuardado,
  estadoConexion,
  colaboradores,
  diagramaVacio,
  onDiagramaReemplazado,
  comandoVoz,
  agenteAbierto,
  onToggleAgente,
}: ToolbarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { fitView, getNodes } = useReactFlow()
  const [mostrarColaboradores, setMostrarColaboradores] = useState(false)
  const [mostrarModalFrontend, setMostrarModalFrontend] = useState(false)
  const [generandoBackend, setGenerandoBackend] = useState(false)
  const [errorGeneracion, setErrorGeneracion] = useState<string | null>(null)
  const [generandoReporte, setGenerandoReporte] = useState(false)
  const [errorReporte, setErrorReporte] = useState<string | null>(null)
  const [importandoXmi, setImportandoXmi] = useState(false)
  const [errorImportacion, setErrorImportacion] = useState<string | null>(null)
  const [advertenciasImportacion, setAdvertenciasImportacion] = useState<string[]>([])
  const [archivoFotoSeleccionado, setArchivoFotoSeleccionado] = useState<File | null>(null)
  const inputArchivoXmiRef = useRef<HTMLInputElement>(null)
  const inputArchivoFotoRef = useRef<HTMLInputElement>(null)
  const esAdministrador = user?.id === project.id_administrador

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const handleGenerarBackend = async () => {
    setErrorGeneracion(null)
    setGenerandoBackend(true)
    try {
      const { blob, nombreArchivo } = await generarBackend(project.id)
      descargarArchivo(blob, nombreArchivo)
    } catch (err) {
      setErrorGeneracion(getApiErrorMessage(err, 'No se pudo generar el backend'))
    } finally {
      setGenerandoBackend(false)
    }
  }

  // CU09 — importar XMI: solo habilitado con el lienzo vacío (ver
  // `diagramaVacio`, calculado en AppShell a partir del estado real de
  // React Flow, no de un chequeo imperativo en el momento del click). El
  // backend ya valida esto también (409) -- este chequeo es solo para no
  // ofrecer un botón habilitado que va a fallar seguro.
  const handleArchivoXmiSeleccionado = async (e: ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0]
    e.target.value = '' // permite volver a elegir el mismo archivo si hace falta reintentar
    if (!archivo) return

    setErrorImportacion(null)
    setAdvertenciasImportacion([])
    setImportandoXmi(true)
    try {
      const resultado = await importarDiagramaXmi(project.id, archivo)
      onDiagramaReemplazado(resultado.diagrama)
      setAdvertenciasImportacion(resultado.advertencias)
    } catch (err) {
      setErrorImportacion(getApiErrorMessage(err, 'No se pudo importar el archivo XMI'))
    } finally {
      setImportandoXmi(false)
    }
  }

  // CU12 — reconocer diagrama desde foto: el archivo elegido se pasa al
  // modal (ReconocimientoFotoModal), que se encarga de subirlo, mostrar la
  // vista previa y confirmar -- este handler solo abre el modal.
  const handleArchivoFotoSeleccionado = (e: ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''
    if (archivo) setArchivoFotoSeleccionado(archivo)
  }

  // CU07 — el PDF se pide al backend (formato técnico: clases, atributos,
  // métodos, relaciones); la imagen se exporta enteramente en el navegador
  // capturando el lienzo de React Flow tal cual está, sin llamar al backend.
  const handleExportarReporte = async (formato: FormatoReporte) => {
    setErrorReporte(null)
    if (getNodes().length === 0) {
      setErrorReporte(MENSAJE_SIN_CONTENIDO)
      return
    }

    setGenerandoReporte(true)
    try {
      if (formato === 'pdf' || formato === 'xmi') {
        const generar = formato === 'pdf' ? generarReportePdf : generarReporteXmi
        const { blob, nombreArchivo } = await generar(project.id)
        descargarArchivo(blob, nombreArchivo)
      } else {
        const viewportEl = document.querySelector('.react-flow__viewport') as HTMLElement | null
        if (!viewportEl) throw new Error('No se pudo capturar el lienzo')

        const ancho = 1400
        const alto = 900
        const bounds = getNodesBounds(getNodes())
        const viewport = getViewportForBounds(bounds, ancho, alto, 0.1, 2, 0.1)

        // <UmlMarkers /> (los <marker> de triángulo/rombo) se monta como
        // hermano de <ReactFlow>, fuera de .react-flow__viewport -- html-to-
        // image solo clona lo que le pasamos, así que sin esto los
        // `url(#uml-generalization)` etc. de cada arista apuntan a nada y
        // ni siquiera se ve la línea (el navegador no dibuja un <path> cuyo
        // marker referenciado no existe en el documento clonado). Se
        // inserta una copia temporal DENTRO del nodo capturado y se saca
        // apenas termina, para no alterar el lienzo en vivo.
        const marcadoresEl = document.querySelector('.uml-markers')
        const marcadoresClon = marcadoresEl?.cloneNode(true) as SVGElement | undefined
        if (marcadoresClon) viewportEl.appendChild(marcadoresClon)

        try {
          const dataUrl = await toPng(viewportEl, {
            backgroundColor: '#ffffff',
            width: ancho,
            height: alto,
            style: {
              width: `${ancho}px`,
              height: `${alto}px`,
              transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
            },
          })
          descargarDataUrl(dataUrl, `${slugNombreArchivo(project.nombre)}-reporte.png`)
        } finally {
          marcadoresClon?.remove()
        }
      }
    } catch (err) {
      setErrorReporte(getApiErrorMessage(err, 'No se pudo exportar el reporte'))
    } finally {
      setGenerandoReporte(false)
    }
  }

  return (
    <header className="app-toolbar">
      <div className="app-toolbar__brand">
        <Link to="/" className="app-toolbar__back">
          ← Proyectos
        </Link>
        <span className="app-toolbar__divider" aria-hidden="true" />
        <span className="app-toolbar__project">{project.nombre}</span>
      </div>

      <div className="app-toolbar__group">
        <ToolButton primary icon={<IconPlus />} onClick={onNuevaClase}>
          Nueva clase
        </ToolButton>
        <ToolButton icon={<IconFit />} onClick={() => fitView({ padding: 0.25 })}>
          Ajustar vista
        </ToolButton>
        <BotonComandoVoz comandoVoz={comandoVoz} />
        <ToolButton icon={<IconChat />} primary={agenteAbierto} onClick={onToggleAgente}>
          Asistente
        </ToolButton>
        <MenuArchivo
          onImportarXmi={() => inputArchivoXmiRef.current?.click()}
          importarXmiDeshabilitado={!diagramaVacio}
          importarXmiTooltip={
            !diagramaVacio
              ? 'El diagrama ya tiene clases -- elimínalas manualmente para poder importar un XMI'
              : undefined
          }
          importandoXmi={importandoXmi}
          onReconocerFoto={() => inputArchivoFotoRef.current?.click()}
          onGenerarBackend={handleGenerarBackend}
          generandoBackend={generandoBackend}
          mostrarGenerarFrontend={esAdministrador}
          onGenerarFrontend={() => setMostrarModalFrontend(true)}
          mostrarExportarReporte={esAdministrador}
          generandoReporte={generandoReporte}
          onExportarReporte={handleExportarReporte}
        />
        <input
          ref={inputArchivoXmiRef}
          type="file"
          accept=".xmi,.xml,text/xml,application/xml"
          className="app-toolbar__input-archivo"
          onChange={handleArchivoXmiSeleccionado}
        />
        <input
          ref={inputArchivoFotoRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="app-toolbar__input-archivo"
          onChange={handleArchivoFotoSeleccionado}
        />
        {esAdministrador && (
          <ToolButton icon={<IconUsers />} onClick={() => setMostrarColaboradores(true)}>
            Colaboradores
          </ToolButton>
        )}
        {guardando && <span className="app-toolbar__guardando">Guardando…</span>}
        {!guardando && errorGuardado && (
          <span className="app-toolbar__error">
            {errorGuardado}
            <button type="button" className="app-toolbar__reintentar" onClick={onReintentarGuardado}>
              Reintentar
            </button>
          </span>
        )}
        {errorGeneracion && (
          <span className="app-toolbar__error">
            {errorGeneracion}
            <button type="button" className="app-toolbar__reintentar" onClick={() => setErrorGeneracion(null)}>
              Cerrar
            </button>
          </span>
        )}
        {errorReporte && (
          <span className="app-toolbar__error">
            {errorReporte}
            <button type="button" className="app-toolbar__reintentar" onClick={() => setErrorReporte(null)}>
              Cerrar
            </button>
          </span>
        )}
        {errorImportacion && (
          <span className="app-toolbar__error">
            {errorImportacion}
            <button type="button" className="app-toolbar__reintentar" onClick={() => setErrorImportacion(null)}>
              Cerrar
            </button>
          </span>
        )}
        {comandoVoz.error && (
          <span className="app-toolbar__error">
            {comandoVoz.error}
            <button type="button" className="app-toolbar__reintentar" onClick={comandoVoz.cerrarError}>
              Cerrar
            </button>
          </span>
        )}
        {comandoVoz.mensajeConfirmacion && (
          <span className="app-toolbar__confirmacion-voz">
            {comandoVoz.mensajeConfirmacion}
            <button type="button" className="app-toolbar__reintentar" onClick={comandoVoz.cerrarConfirmacion}>
              Cerrar
            </button>
          </span>
        )}
        {advertenciasImportacion.length > 0 && (
          <span className="app-toolbar__error" title={advertenciasImportacion.join('\n')}>
            Se importó con {advertenciasImportacion.length} advertencia
            {advertenciasImportacion.length === 1 ? '' : 's'} (pasa el mouse para ver el detalle)
            <button
              type="button"
              className="app-toolbar__reintentar"
              onClick={() => setAdvertenciasImportacion([])}
            >
              Cerrar
            </button>
          </span>
        )}
      </div>

      <div className="app-toolbar__user">
        <IndicadorConexion estado={estadoConexion} />
        <Presencia colaboradores={colaboradores} />
        {user && (
          <span className="app-toolbar__chip">
            <span className="app-toolbar__avatar" aria-hidden="true">
              {iniciales(user.nombre_completo)}
            </span>
            {user.nombre_completo}
          </span>
        )}
        <button type="button" className="app-toolbar__logout" onClick={handleLogout}>
          Salir
        </button>
      </div>

      {mostrarColaboradores && (
        <ColaboradoresModal proyectoId={project.id} onClose={() => setMostrarColaboradores(false)} />
      )}
      {mostrarModalFrontend && (
        <GenerarFrontendModal proyectoId={project.id} onClose={() => setMostrarModalFrontend(false)} />
      )}
      {archivoFotoSeleccionado && (
        <ReconocimientoFotoModal
          proyectoId={project.id}
          archivo={archivoFotoSeleccionado}
          onClose={() => setArchivoFotoSeleccionado(null)}
          onAplicado={onDiagramaReemplazado}
        />
      )}
    </header>
  )
}
