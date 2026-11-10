import axios from 'axios'

import { api } from './client'

type BackendGenerado = {
  blob: Blob
  nombreArchivo: string
}

function nombreDesdeContentDisposition(disposition: string | undefined, nombrePorDefecto: string): string {
  const match = disposition?.match(/filename="?([^";]+)"?/)
  return match?.[1] ?? nombrePorDefecto
}

/**
 * CU08 — genera el backend Spring Boot del proyecto y devuelve el .zip listo
 * para descargar. Si el backend responde con un error (ej. sin clases en el
 * diagrama), lo relanza como Error normal con el mensaje ya extraído: al
 * pedir `responseType: 'blob'`, axios también entrega el cuerpo de error
 * como Blob en vez de JSON parseado, así que hay que leerlo a mano.
 */
export async function generarBackend(proyectoId: number): Promise<BackendGenerado> {
  try {
    const resp = await api.post(`/proyectos/${proyectoId}/generar-backend`, undefined, {
      responseType: 'blob',
    })
    return {
      blob: resp.data as Blob,
      nombreArchivo: nombreDesdeContentDisposition(resp.headers['content-disposition'], `backend-${proyectoId}.zip`),
    }
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
      const texto = await err.response.data.text()
      let detalle: string | undefined
      try {
        detalle = (JSON.parse(texto) as { detail?: string }).detail
      } catch {
        /* el cuerpo del error no era JSON */
      }
      if (detalle) throw new Error(detalle)
    }
    throw err
  }
}

/**
 * CU15 — genera el frontend Flutter del proyecto (apuntando a `urlBase`) y
 * devuelve el .zip listo para descargar. Mismo manejo de error que
 * `generarBackend` (blob de error leído a mano para extraer el `detail`,
 * ej. "no hay contenido disponible para exportar" si el diagrama no tiene
 * clases, o el 403 si quien pide no es el administrador dueño).
 */
export async function generarFrontend(proyectoId: number, urlBase: string): Promise<BackendGenerado> {
  try {
    const resp = await api.post(
      `/proyectos/${proyectoId}/generar-frontend`,
      { url_base: urlBase },
      { responseType: 'blob' },
    )
    return {
      blob: resp.data as Blob,
      nombreArchivo: nombreDesdeContentDisposition(resp.headers['content-disposition'], `frontend-${proyectoId}.zip`),
    }
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
      const texto = await err.response.data.text()
      let detalle: string | undefined
      try {
        detalle = (JSON.parse(texto) as { detail?: string }).detail
      } catch {
        /* el cuerpo del error no era JSON */
      }
      if (detalle) throw new Error(detalle)
    }
    throw err
  }
}

/** Dispara la descarga de un Blob en el navegador con el nombre dado. */
export function descargarArchivo(blob: Blob, nombreArchivo: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombreArchivo
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
