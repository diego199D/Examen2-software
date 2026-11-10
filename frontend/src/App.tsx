import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { AppChrome } from './components/layout/AppChrome'
import { EditorPage } from './pages/EditorPage'
import { LoginPage } from './pages/LoginPage'
import { PerfilPage } from './pages/PerfilPage'
import { ProyectosPage } from './pages/ProyectosPage'
import { RegistroPage } from './pages/RegistroPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/registro" element={<RegistroPage />} />

          <Route
            element={
              <RequireAuth>
                <AppChrome />
              </RequireAuth>
            }
          >
            <Route path="/" element={<ProyectosPage />} />
            <Route path="/perfil" element={<PerfilPage />} />
          </Route>

          <Route
            path="/proyectos/:id"
            element={
              <RequireAuth>
                <EditorPage />
              </RequireAuth>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
