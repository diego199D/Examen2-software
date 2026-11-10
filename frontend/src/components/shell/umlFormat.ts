import type { AtributoUml, FormaRelacion, MetodoUml, TipoRelacion, Visibilidad } from '../../api/types'

/** Símbolo UML estándar por nivel de visibilidad. */
export function simboloVisibilidad(v: Visibilidad): string {
  switch (v) {
    case 'PUBLICO':
      return '+'
    case 'PRIVADO':
      return '-'
    case 'PROTEGIDO':
      return '#'
    case 'PAQUETE':
      return '~'
  }
}

export const OPCIONES_VISIBILIDAD: { value: Visibilidad; label: string }[] = [
  { value: 'PUBLICO', label: '+ Público' },
  { value: 'PRIVADO', label: '- Privado' },
  { value: 'PROTEGIDO', label: '# Protegido' },
  { value: 'PAQUETE', label: '~ Paquete' },
]

/** Línea de compartimento tipo "- nombre: Tipo". */
export function formatAtributo(a: AtributoUml): string {
  const tipo = a.tipo ? `: ${a.tipo}` : ''
  return `${simboloVisibilidad(a.visibilidad)} ${a.nombre}${tipo}`
}

/** Línea de compartimento tipo "+ nombre(params): Tipo". */
export function formatMetodo(m: MetodoUml): string {
  const tipo = m.tipo_retorno ? `: ${m.tipo_retorno}` : ''
  return `${simboloVisibilidad(m.visibilidad)} ${m.nombre}(${m.parametros ?? ''})${tipo}`
}

const SIMBOLO_A_VISIBILIDAD: Record<string, Visibilidad> = {
  '+': 'PUBLICO',
  '-': 'PRIVADO',
  '#': 'PROTEGIDO',
  '~': 'PAQUETE',
}

/** Interpreta una línea escrita a mano (ej. "- edad: int") de vuelta a campos. */
export function parsearAtributo(texto: string, anterior: AtributoUml): AtributoUml {
  const m = texto.trim().match(/^([+\-#~])?\s*([^:]+?)\s*(?::\s*(.+))?$/)
  if (!m) return { ...anterior, nombre: texto.trim() }
  const [, simbolo, nombre, tipo] = m
  return {
    ...anterior,
    visibilidad: simbolo ? SIMBOLO_A_VISIBILIDAD[simbolo] : anterior.visibilidad,
    nombre: nombre.trim(),
    tipo: tipo?.trim() || null,
  }
}

/** Interpreta una línea escrita a mano (ej. "+ saludar(): String") de vuelta a campos. */
export function parsearMetodo(texto: string, anterior: MetodoUml): MetodoUml {
  const conParens = texto.trim().match(/^([+\-#~])?\s*([^(:]+?)\s*\(([^)]*)\)\s*(?::\s*(.+))?$/)
  if (conParens) {
    const [, simbolo, nombre, parametros, retorno] = conParens
    return {
      ...anterior,
      visibilidad: simbolo ? SIMBOLO_A_VISIBILIDAD[simbolo] : anterior.visibilidad,
      nombre: nombre.trim(),
      parametros: parametros.trim() || null,
      tipo_retorno: retorno?.trim() || null,
    }
  }
  // Sin paréntesis: se completan solas cuando el usuario los agregue después.
  const sinParens = texto.trim().match(/^([+\-#~])?\s*([^:]+?)\s*(?::\s*(.+))?$/)
  if (!sinParens) return { ...anterior, nombre: texto.trim() }
  const [, simbolo2, nombre2, retorno2] = sinParens
  return {
    ...anterior,
    visibilidad: simbolo2 ? SIMBOLO_A_VISIBILIDAD[simbolo2] : anterior.visibilidad,
    nombre: nombre2.trim(),
    tipo_retorno: retorno2?.trim() || null,
  }
}

/** Multiplicidades UML estándar — deben coincidir con MULTIPLICIDADES_VALIDAS en el backend (diagramas.py). */
export const OPCIONES_MULTIPLICIDAD: { value: string; label: string }[] = [
  { value: '', label: '(sin especificar)' },
  { value: '1', label: '1' },
  { value: '0..1', label: '0..1' },
  { value: '0..*', label: '0..*' },
  { value: '1..*', label: '1..*' },
]

export const OPCIONES_FORMA_RELACION: { value: FormaRelacion; label: string }[] = [
  { value: 'RECTA', label: 'Recta' },
  { value: 'L', label: 'En L (ángulos rectos)' },
  { value: 'CURVA', label: 'Curva' },
]

export const OPCIONES_TIPO_RELACION: { value: TipoRelacion; label: string }[] = [
  { value: 'ASOCIACION', label: 'Asociación' },
  { value: 'HERENCIA', label: 'Herencia' },
  { value: 'AGREGACION', label: 'Agregación' },
  { value: 'COMPOSICION', label: 'Composición' },
]

export function etiquetaTipoRelacion(tipo: TipoRelacion): string {
  return OPCIONES_TIPO_RELACION.find((o) => o.value === tipo)?.label ?? tipo
}

/**
 * Marcador SVG (definidos en UmlMarkers.tsx) según el tipo de relación UML.
 * React Flow v11 espera solo el ID del <marker> (él arma `url(#id)` por su
 * cuenta) — pasarle ya el `url(#...)` completo hace que lo envuelva dos
 * veces (`url('#url(#id)')`, un id inexistente) y el marcador no se vea.
 * Siempre se devuelven AMBAS claves (una en `undefined`) para que al hacer
 * spread sobre una arista existente se limpie el marcador del tipo anterior
 * en vez de dejarlo pegado (ej. al cambiar de Composición a Asociación).
 */
export function markerDeRelacion(tipo: TipoRelacion): { markerStart?: string; markerEnd?: string } {
  switch (tipo) {
    case 'HERENCIA':
      return { markerStart: undefined, markerEnd: 'uml-generalization' }
    case 'ASOCIACION':
      // Línea simple entre clases, sin punta de flecha (no es una relación
      // dirigida) -- ver UmlMarkers.tsx, no existe un marker 'uml-association'.
      return { markerStart: undefined, markerEnd: undefined }
    case 'AGREGACION':
      return { markerStart: 'uml-aggregation', markerEnd: undefined }
    case 'COMPOSICION':
      return { markerStart: 'uml-composition', markerEnd: undefined }
  }
}
