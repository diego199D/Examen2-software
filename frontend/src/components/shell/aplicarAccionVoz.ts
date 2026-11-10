import type {
  AccionModificarDiagrama,
  AccionVoz,
  AtributoNuevo,
  AtributoUml,
  ExtremoRelacionVoz,
  RelacionUml,
} from '../../api/types'
import type { useDiagrama } from './useDiagrama'
import { nuevaClaseVacia } from './useDiagrama'

type Diagrama = ReturnType<typeof useDiagrama>

/**
 * Traduce una `AccionVoz` (ids ya resueltos por el backend, ver CU11) a
 * llamadas concretas sobre `useDiagrama` -- extraído del switch que antes
 * vivía inline en `useComandoVoz.ts` (CU11) para que CU13 (agente
 * conversacional) lo reutilice tal cual, sin duplicar los casos.
 * `modificar_diagrama` hoy solo lo produce la voz (CU11).
 */
export function aplicarAccionVoz(accion: AccionVoz, diagrama: Diagrama): void {
  switch (accion.accion) {
    case 'crear_clase': {
      const clase = nuevaClaseVacia(diagrama.nodes.length)
      clase.nombre = accion.nombre_clase
      clase.atributos = accion.atributos.map((a) => ({
        id: crypto.randomUUID(),
        nombre: a.nombre,
        tipo: a.tipo,
        visibilidad: a.visibilidad,
        orden: 0,
      }))
      diagrama.agregarClase(clase)
      break
    }
    case 'agregar_atributo': {
      const nodo = diagrama.nodes.find((n) => n.id === accion.id_clase)
      if (nodo) {
        const nuevoAtributo: AtributoUml = {
          id: crypto.randomUUID(),
          nombre: accion.atributo.nombre,
          tipo: accion.atributo.tipo,
          visibilidad: accion.atributo.visibilidad,
          orden: nodo.data.clase.atributos.length,
        }
        diagrama.actualizarClase({ ...nodo.data.clase, atributos: [...nodo.data.clase.atributos, nuevoAtributo] })
      }
      break
    }
    case 'eliminar_clase': {
      diagrama.eliminarClase(accion.id_clase)
      break
    }
    case 'crear_relacion': {
      diagrama.crearRelacion(
        {
          source: accion.id_clase_origen,
          target: accion.id_clase_destino,
          sourceHandle: null,
          targetHandle: null,
        },
        {
          tipo: accion.tipo,
          etiqueta: null,
          multiplicidad_origen: accion.multiplicidad_origen,
          multiplicidad_destino: accion.multiplicidad_destino,
          forma: null,
        },
      )
      break
    }
    case 'renombrar_clase': {
      const nodo = diagrama.nodes.find((n) => n.id === accion.id_clase)
      if (nodo) diagrama.actualizarClase({ ...nodo.data.clase, nombre: accion.nombre_nuevo })
      break
    }
    case 'modificar_diagrama': {
      aplicarModificacion(accion, diagrama)
      break
    }
  }
}

function nuevosAtributos(atributos: AtributoNuevo[], ordenInicial: number): AtributoUml[] {
  return atributos.map((a, i) => ({
    id: crypto.randomUUID(),
    nombre: a.nombre,
    tipo: a.tipo,
    visibilidad: a.visibilidad,
    orden: ordenInicial + i,
  }))
}

/** CU11 — comando en lenguaje natural: las clases nuevas se ubican en la
 * grilla a continuación de las existentes, y los extremos de relación sin
 * `id_clase` (clases nuevas del mismo comando) se resuelven por nombre --
 * el backend devuelve el nombre exacto con el que viene en `clases_nuevas`. */
function aplicarModificacion(accion: AccionModificarDiagrama, diagrama: Diagrama): void {
  const clasesNuevas = accion.clases_nuevas.map((c, i) => {
    const clase = nuevaClaseVacia(diagrama.nodes.length + i)
    clase.nombre = c.nombre
    clase.atributos = nuevosAtributos(c.atributos, 0)
    return clase
  })
  const idPorNombreNuevo = new Map(clasesNuevas.map((c) => [c.nombre, c.id]))

  const clasesActualizadas = accion.atributos_agregados.flatMap((grupo) => {
    const nodo = diagrama.nodes.find((n) => n.id === grupo.id_clase)
    if (!nodo) return []
    const clase = nodo.data.clase
    return [{ ...clase, atributos: [...clase.atributos, ...nuevosAtributos(grupo.atributos, clase.atributos.length)] }]
  })

  const resolver = (extremo: ExtremoRelacionVoz) => extremo.id_clase ?? idPorNombreNuevo.get(extremo.nombre_clase)
  const relaciones: RelacionUml[] = accion.relaciones.flatMap((r) => {
    const origen = resolver(r.origen)
    const destino = resolver(r.destino)
    if (!origen || !destino) return []
    return [
      {
        id: crypto.randomUUID(),
        id_clase_origen: origen,
        id_clase_destino: destino,
        tipo: r.tipo,
        etiqueta: r.etiqueta,
        multiplicidad_origen: r.multiplicidad_origen,
        multiplicidad_destino: r.multiplicidad_destino,
        handle_origen: null,
        handle_destino: null,
        forma: null,
      },
    ]
  })

  diagrama.agregarLote(clasesNuevas, clasesActualizadas, relaciones)
}
