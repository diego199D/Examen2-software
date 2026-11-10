import axios from 'axios'

type ValidationItem = { msg?: string }

/** Mensaje legible a partir de cualquier error de la API. */
export function getApiErrorMessage(err: unknown, fallback = 'Ocurrió un error inesperado'): string {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const detail = (err.response.data as { detail?: unknown } | undefined)?.detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        const msgs = (detail as ValidationItem[]).map((d) => d.msg).filter(Boolean)
        if (msgs.length > 0) return msgs.join(', ')
      }
    }
    if (err.code === 'ERR_NETWORK') return 'No se pudo conectar con el servidor'
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

/** Código de estado HTTP del error, si lo hay. */
export function getApiErrorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined
}
