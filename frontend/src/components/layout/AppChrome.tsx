import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/useAuth'
import { iniciales } from '../../lib/format'
import './AppChrome.css'

export function AppChrome() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-chrome">
      <header className="chrome-bar">
        <span className="chrome-bar__app">Diagramador UML</span>

        <nav className="chrome-bar__nav">
          <NavLink to="/" end className="chrome-bar__link">
            Proyectos
          </NavLink>
          <NavLink to="/perfil" className="chrome-bar__link">
            Perfil
          </NavLink>
        </nav>

        <div className="chrome-bar__user">
          {user && (
            <span className="chrome-bar__chip">
              <span className="chrome-bar__avatar" aria-hidden="true">
                {iniciales(user.nombre_completo)}
              </span>
              {user.nombre_completo}
            </span>
          )}
          <button type="button" className="chrome-bar__logout" onClick={handleLogout}>
            Salir
          </button>
        </div>
      </header>

      <main className="app-page">
        <Outlet />
      </main>
    </div>
  )
}
