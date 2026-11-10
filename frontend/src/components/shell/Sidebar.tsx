import type { ReactNode } from 'react'

type ClaseResumen = { id: string; nombre: string }

type Props = {
  clases: ClaseResumen[]
  seleccionadas: string[]
  onSeleccionar: (id: string) => void
  onCrear: () => void
  abierto: boolean
  onToggle: () => void
}

function IconPlus() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M6 2v8M2 6h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

/**
 * Ícono tipo "layout sidebar" (Tabler ti-layout-sidebar): un panel con una
 * línea vertical que lo divide en una sección angosta y una ancha. La
 * sección angosta cambia de lado según el estado para reforzar qué va a
 * pasar al hacer click (colapsar vs expandir).
 */
function IconSidebarToggle({ colapsado }: { colapsado: boolean }) {
  const divisor = colapsado ? 7.5 : 4.5
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <rect x="1.5" y="2" width="9" height="8" rx="1.3" stroke="currentColor" strokeWidth="1.3" />
      <line x1={divisor} y1="2" x2={divisor} y2="10" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  )
}

function SectionHeader({ label, actions }: { label: string; actions?: ReactNode }) {
  return (
    <div className="sidebar__section-header">
      <span>{label}</span>
      {actions && <div className="sidebar__header-actions">{actions}</div>}
    </div>
  )
}

export function Sidebar({ clases, seleccionadas, onSeleccionar, onCrear, abierto, onToggle }: Props) {
  if (!abierto) {
    return (
      <aside className="app-sidebar app-sidebar--colapsado">
        <div className="sidebar__topbar-colapsado">
          <button
            type="button"
            className="sidebar__add"
            aria-label="Expandir panel de clases"
            aria-expanded={false}
            onClick={onToggle}
          >
            <IconSidebarToggle colapsado />
          </button>
        </div>
      </aside>
    )
  }

  return (
    <aside className="app-sidebar">
      <div className="sidebar__section sidebar__section--grow">
        <SectionHeader
          label="Clases"
          actions={
            <>
              <button type="button" className="sidebar__add" aria-label="Añadir a Clases" onClick={onCrear}>
                <IconPlus />
              </button>
              <button
                type="button"
                className="sidebar__add"
                aria-label="Colapsar panel de clases"
                aria-expanded={true}
                onClick={onToggle}
              >
                <IconSidebarToggle colapsado={false} />
              </button>
            </>
          }
        />
        <ul className="sidebar__list">
          {clases.length === 0 && <li className="sidebar__empty">Sin clases todavía</li>}
          {clases.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={
                  seleccionadas.includes(c.id) ? 'sidebar__item sidebar__item--active' : 'sidebar__item'
                }
                onClick={() => onSeleccionar(c.id)}
              >
                {c.nombre || 'Sin nombre'}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="sidebar__section">
        <SectionHeader label="Diagramas" />
        <ul className="sidebar__list">
          <li>
            <button type="button" className="sidebar__item sidebar__item--sans sidebar__item--active">
              Diagrama de clases
            </button>
          </li>
        </ul>
      </div>
    </aside>
  )
}
