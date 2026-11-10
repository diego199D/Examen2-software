const fechaLarga = new Intl.DateTimeFormat('es', { dateStyle: 'medium' })

/** Formatea una fecha ISO del backend a texto en español; cadena vacía si no es válida. */
export function formatFecha(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : fechaLarga.format(d)
}

/** Iniciales para el avatar (una o dos letras). */
export function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  if (partes.length === 1) return partes[0].slice(0, 1).toUpperCase()
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase()
}
