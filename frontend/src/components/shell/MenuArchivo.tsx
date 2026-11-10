import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

/**
 * Menú desplegable "Archivo" de la Toolbar del editor (estilo draw.io):
 * agrupa las 4 acciones relacionadas a archivo (Importar XMI, Generar
 * backend, Generar frontend, Exportar reporte) que antes competían por
 * espacio horizontal como botones sueltos. Cada item conserva exactamente
 * la misma lógica de visibilidad/deshabilitado que tenía como botón
 * independiente -- este componente solo cambia CÓMO se presentan, no las
 * reglas de negocio (esas siguen viviendo en Toolbar.tsx, que las pasa acá
 * como props).
 *
 * No se agregó ninguna librería de menús: es un `<div>` posicionado
 * absoluto + un listener de `mousedown` a nivel de documento para cerrar al
 * clickear afuera (mismo patrón que ya usa `useCerrarAlClickAfuera` en
 * ClassNode.tsx para las ediciones inline).
 */

function IconChevronDown() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
      <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconChevronRight() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
      <path d="M3.5 2L6.5 5L3.5 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconUpload() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M7 8.5v-7m0 0L4 4.5M7 1.5l3 3M2 10.5v1.5a1 1 0 001 1h8a1 1 0 001-1v-1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconDownload() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M7 1.5v7m0 0L4 5.5M7 8.5l3-3M2 10.5v1.5a1 1 0 001 1h8a1 1 0 001-1v-1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** CU12 — ícono de cámara para "Reconocer desde foto". */
function IconCamera() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M1.5 4.5A1 1 0 012.5 3.5h1l.6-1h4.8l.6 1h1a1 1 0 011 1v6a1 1 0 01-1 1h-9a1 1 0 01-1-1v-6z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <circle cx="7" cy="7.5" r="2.2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

type ItemMenuProps = {
  icon?: ReactNode
  children: ReactNode
  disabled?: boolean
  title?: string
  onClick: () => void
}

function ItemMenu({ icon, children, disabled, title, onClick }: ItemMenuProps) {
  return (
    <button
      type="button"
      role="menuitem"
      className="menu-archivo__item"
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      {icon}
      <span>{children}</span>
    </button>
  )
}

export type FormatoReporte = 'pdf' | 'imagen' | 'xmi'

const ETIQUETA_FORMATO: Record<FormatoReporte, string> = {
  pdf: 'PDF',
  imagen: 'Imagen',
  xmi: 'XMI',
}

export type MenuArchivoProps = {
  onImportarXmi: () => void
  importarXmiDeshabilitado: boolean
  importarXmiTooltip?: string
  importandoXmi: boolean

  onReconocerFoto: () => void

  onGenerarBackend: () => void
  generandoBackend: boolean

  mostrarGenerarFrontend: boolean
  onGenerarFrontend: () => void

  mostrarExportarReporte: boolean
  generandoReporte: boolean
  onExportarReporte: (formato: FormatoReporte) => void
}

export function MenuArchivo({
  onImportarXmi,
  importarXmiDeshabilitado,
  importarXmiTooltip,
  importandoXmi,
  onReconocerFoto,
  onGenerarBackend,
  generandoBackend,
  mostrarGenerarFrontend,
  onGenerarFrontend,
  mostrarExportarReporte,
  generandoReporte,
  onExportarReporte,
}: MenuArchivoProps) {
  const [abierto, setAbierto] = useState(false)
  const [submenuReporteAbierto, setSubmenuReporteAbierto] = useState(false)
  const contenedorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto) return
    const handler = (e: MouseEvent) => {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false)
        setSubmenuReporteAbierto(false)
      }
    }
    // Fase de CAPTURA (3er argumento `true`): el lienzo de React Flow hace
    // `stopPropagation()` en su propio mousedown (para iniciar el paneo),
    // así que un listener en fase de burbuja nunca vería un click ahí --
    // mismo problema (y misma solución) que `useCerrarAlClickAfuera` ya
    // documenta en ClassNode.tsx.
    document.addEventListener('mousedown', handler, true)
    return () => document.removeEventListener('mousedown', handler, true)
  }, [abierto])

  const cerrar = () => {
    setAbierto(false)
    setSubmenuReporteAbierto(false)
  }

  return (
    <div className="menu-archivo" ref={contenedorRef}>
      <button
        type="button"
        className="tool-btn menu-archivo__trigger"
        aria-haspopup="true"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        Archivo
        <IconChevronDown />
      </button>

      {abierto && (
        <div className="menu-archivo__lista" role="menu">
          <ItemMenu
            icon={<IconUpload />}
            disabled={importarXmiDeshabilitado || importandoXmi}
            title={importarXmiTooltip}
            onClick={() => {
              onImportarXmi()
              cerrar()
            }}
          >
            {importandoXmi ? 'Importando…' : 'Importar XMI'}
          </ItemMenu>

          <ItemMenu
            icon={<IconCamera />}
            onClick={() => {
              onReconocerFoto()
              cerrar()
            }}
          >
            Reconocer desde foto
          </ItemMenu>

          <ItemMenu
            icon={<IconDownload />}
            disabled={generandoBackend}
            onClick={() => {
              onGenerarBackend()
              cerrar()
            }}
          >
            {generandoBackend ? 'Generando…' : 'Generar backend'}
          </ItemMenu>

          {mostrarGenerarFrontend && (
            <ItemMenu
              icon={<IconDownload />}
              onClick={() => {
                onGenerarFrontend()
                cerrar()
              }}
            >
              Generar frontend
            </ItemMenu>
          )}

          {mostrarExportarReporte && (
            <div className="menu-archivo__submenu-wrapper">
              <button
                type="button"
                role="menuitem"
                className="menu-archivo__item"
                aria-haspopup="true"
                aria-expanded={submenuReporteAbierto}
                disabled={generandoReporte}
                onClick={() => setSubmenuReporteAbierto((v) => !v)}
              >
                <IconDownload />
                <span>{generandoReporte ? 'Exportando…' : 'Exportar reporte'}</span>
                <IconChevronRight />
              </button>
              {submenuReporteAbierto && (
                <div className="menu-archivo__submenu" role="menu">
                  {(['pdf', 'imagen', 'xmi'] as FormatoReporte[]).map((formato) => (
                    <button
                      key={formato}
                      type="button"
                      role="menuitem"
                      className="menu-archivo__item"
                      disabled={generandoReporte}
                      onClick={() => {
                        onExportarReporte(formato)
                        cerrar()
                      }}
                    >
                      {ETIQUETA_FORMATO[formato]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
