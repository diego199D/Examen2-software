import * as Y from 'yjs'

import type { AtributoUml, ClaseUml, DiagramaData, MetodoUml, RelacionUml } from '../api/types'

/**
 * Estructura del documento Yjs — debe coincidir exactamente con lo que arma
 * el backend en `app/services/yjs_rooms.py` (mismo mapeo, mismos nombres de
 * campo, Y.Map anidados reales, no blobs JSON):
 *
 *   doc.getMap('clases')     -> Map[clase_id -> Map{
 *                                    id, nombre, estereotipo, es_abstracta,
 *                                    pos_x, pos_y,
 *                                    atributos: Map[attr_id -> Map{...}],
 *                                    metodos:   Map[met_id  -> Map{...}],
 *                                }]
 *   doc.getMap('relaciones') -> Map[relacion_id -> Map{...}]
 */

/** Marca las transacciones locales para que el propio observer las distinga
 * de los cambios que llegaron de otro colaborador (ver useColaboracion). */
export const ORIGEN_LOCAL = Symbol('diagrama-local')

function miembroAYMap(item: AtributoUml | MetodoUml): Y.Map<unknown> {
  const mapa = new Y.Map<unknown>()
  for (const [clave, valor] of Object.entries(item)) mapa.set(clave, valor)
  return mapa
}

export function claseAYMap(clase: ClaseUml): Y.Map<unknown> {
  const atributos = new Y.Map<Y.Map<unknown>>()
  for (const a of clase.atributos) atributos.set(a.id, miembroAYMap(a))
  const metodos = new Y.Map<Y.Map<unknown>>()
  for (const m of clase.metodos) metodos.set(m.id, miembroAYMap(m))

  const mapa = new Y.Map<unknown>()
  mapa.set('id', clase.id)
  mapa.set('nombre', clase.nombre)
  mapa.set('estereotipo', clase.estereotipo)
  mapa.set('es_abstracta', clase.es_abstracta)
  mapa.set('pos_x', clase.pos_x)
  mapa.set('pos_y', clase.pos_y)
  mapa.set('atributos', atributos)
  mapa.set('metodos', metodos)
  return mapa
}

export function relacionAYMap(relacion: RelacionUml): Y.Map<unknown> {
  const mapa = new Y.Map<unknown>()
  for (const [clave, valor] of Object.entries(relacion)) mapa.set(clave, valor)
  return mapa
}

function yMapAClase(id: string, mapa: Y.Map<unknown>): ClaseUml {
  const plano = mapa.toJSON() as Record<string, unknown>
  return {
    id,
    nombre: (plano.nombre as string) ?? '',
    estereotipo: (plano.estereotipo as string | null) ?? null,
    es_abstracta: Boolean(plano.es_abstracta),
    pos_x: Number(plano.pos_x) || 0,
    pos_y: Number(plano.pos_y) || 0,
    atributos: Object.values((plano.atributos as Record<string, AtributoUml>) ?? {}),
    metodos: Object.values((plano.metodos as Record<string, MetodoUml>) ?? {}),
  }
}

function yMapARelacion(id: string, mapa: Y.Map<unknown>): RelacionUml {
  const plano = mapa.toJSON() as Omit<RelacionUml, 'id'>
  return { ...plano, id }
}

/** Lee el estado actual y completo del documento compartido. */
export function leerDiagramaDeYjs(doc: Y.Doc): DiagramaData {
  const clasesMap = doc.getMap<Y.Map<unknown>>('clases')
  const relacionesMap = doc.getMap<Y.Map<unknown>>('relaciones')

  const clases: ClaseUml[] = []
  clasesMap.forEach((mapa, id) => clases.push(yMapAClase(id, mapa)))

  const relaciones: RelacionUml[] = []
  relacionesMap.forEach((mapa, id) => relaciones.push(yMapARelacion(id, mapa)))

  return { clases, relaciones }
}

/**
 * Vuelca el snapshot local actual (mismo shape que ya arma `serializar()`
 * para el autoguardado HTTP) al documento compartido: agrega/actualiza cada
 * clase/relación por id y borra las que ya no están. No es un
 * "clear + reinsertar todo": cada entrada es una operación de Yjs
 * independiente, así que ediciones concurrentes a clases *distintas* nunca
 * pisan nada — solo dos ediciones a la MISMA clase al mismo tiempo se
 * resuelven last-write-wins (mismo límite ya documentado del lado del
 * backend para el room colaborativo).
 */
export function sincronizarLocalAYjs(doc: Y.Doc, datos: DiagramaData): void {
  const clasesMap = doc.getMap<Y.Map<unknown>>('clases')
  const relacionesMap = doc.getMap<Y.Map<unknown>>('relaciones')

  const idsClases = new Set(datos.clases.map((c) => c.id))
  const idsRelaciones = new Set(datos.relaciones.map((r) => r.id))

  doc.transact(() => {
    for (const clase of datos.clases) clasesMap.set(clase.id, claseAYMap(clase))
    for (const id of Array.from(clasesMap.keys())) {
      if (!idsClases.has(id)) clasesMap.delete(id)
    }

    for (const relacion of datos.relaciones) relacionesMap.set(relacion.id, relacionAYMap(relacion))
    for (const id of Array.from(relacionesMap.keys())) {
      if (!idsRelaciones.has(id)) relacionesMap.delete(id)
    }
  }, ORIGEN_LOCAL)
}
