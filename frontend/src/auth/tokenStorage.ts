/**
 * Token JWT de la sesión, POR PESTAÑA.
 *
 * Antes vivía solo en localStorage, que comparten todas las pestañas: si en
 * una pestaña había un usuario y en otra se entraba con otro, el token se
 * pisaba y la primera seguía mostrando su encabezado pero pedía los datos con
 * el token del otro (veía proyectos ajenos). Ahora cada pestaña usa su propio
 * sessionStorage; localStorage solo guarda "el último login" para que una
 * pestaña NUEVA (o reabrir el navegador) arranque con esa sesión. Una vez
 * que la pestaña adoptó un token, ya no cambia aunque otra pestaña inicie
 * sesión con otro usuario -- así se pueden probar dos usuarios del mismo
 * grupo en dos pestañas del mismo navegador.
 */
const KEY = 'diagramador_token'

function leer(storage: Storage): string | null {
  try {
    return storage.getItem(KEY)
  } catch {
    return null
  }
}

export function getToken(): string | null {
  const propio = leer(sessionStorage)
  if (propio) return propio
  const ultimo = leer(localStorage)
  if (ultimo) {
    try {
      sessionStorage.setItem(KEY, ultimo)
    } catch {
      /* sin sessionStorage: se usa el compartido */
    }
  }
  return ultimo
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token)
  } catch {
    /* ignorar */
  }
  try {
    localStorage.setItem(KEY, token)
  } catch {
    /* localStorage no disponible (modo privado, etc.) */
  }
}

export function clearToken(): void {
  const propio = leer(sessionStorage)
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* ignorar */
  }
  // Solo se borra el "último login" compartido si es el de esta pestaña: cerrar
  // sesión acá no tiene que echar a otra pestaña con otro usuario.
  try {
    if (!propio || localStorage.getItem(KEY) === propio) localStorage.removeItem(KEY)
  } catch {
    /* ignorar */
  }
}
