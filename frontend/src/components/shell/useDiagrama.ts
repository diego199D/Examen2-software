import { useCallback, useEffect, useRef, useState } from 'react'
import { useEdgesState, useNodesState } from 'reactflow'
import type { Connection, Edge, EdgeChange, Node, NodeChange } from 'reactflow'

import { getDiagrama, guardarDiagrama } from '../../api/diagrama'
import { getApiErrorMessage } from '../../api/errors'
import type { ClaseUml, DiagramaData, FormaRelacion, RelacionUml, TipoRelacion } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import { useColaboracion } from '../../collab/useColaboracion'
import type { ClassNodeData } from './ClassNode'
import { markerDeRelacion } from './umlFormat'

export type EdgeData = {
  tipo: TipoRelacion
  etiqueta: string | null
  multiplicidad_origen: string | null
  multiplicidad_destino: string | null
  forma: FormaRelacion | null
  desvio_x: number | null
  desvio_y: number | null
}

export type DetallesRelacion = {
  tipo: TipoRelacion
  etiqueta: string | null
  multiplicidad_origen: string | null
  multiplicidad_destino: string | null
  forma: FormaRelacion | null
}

export type Desvio = { x: number; y: number }

// Literal, no var(--edge-stroke): mismo motivo que STROKE en UmlMarkers.tsx
// (los estilos de SVG no resuelven var() de forma confiable) -- acá además
// se confirmó que rompe la exportación a PNG (CU07 "Imagen"): html-to-image
// clona el SVG de React Flow sin resolver custom properties para elementos
// SVG, así que un var() sin resolver cae al valor inicial de `stroke`
// (`none`) y la línea queda invisible en el archivo exportado. Mantener en
// sync con --edge-stroke en tokens.css si ese valor cambia.
const EDGE_STYLE = { stroke: '#4a5261' }
const DEBOUNCE_MS = 800

function nuevoId(): string {
  return crypto.randomUUID()
}

// Grilla (no diagonal): con el viejo offset de 60px, una clase de ~176px de
// ancho quedaba tapando casi por completo a la siguiente — imposible de
// distinguir o arrastrar por separado. 240x180 deja aire incluso entre
// clases con varios atributos/métodos.
const GRID_COLUMNAS = 4
const GRID_PASO_X = 240
const GRID_PASO_Y = 180

/** Clase en blanco para "Nueva clase" — posición en grilla según cuántas ya hay. */
export function nuevaClaseVacia(cantidadActual: number): ClaseUml {
  const columna = cantidadActual % GRID_COLUMNAS
  const fila = Math.floor(cantidadActual / GRID_COLUMNAS)
  return {
    id: nuevoId(),
    nombre: '',
    estereotipo: null,
    es_abstracta: false,
    pos_x: 80 + columna * GRID_PASO_X,
    pos_y: 80 + fila * GRID_PASO_Y,
    atributos: [],
    metodos: [],
  }
}

function construirNodos(
  clases: ClaseUml[],
  onCambiar: (clase: ClaseUml) => void,
): Node<ClassNodeData>[] {
  return clases.map((clase) => ({
    id: clase.id,
    type: 'classNode',
    position: { x: clase.pos_x, y: clase.pos_y },
    data: { clase, onCambiar },
  }))
}

type PosicionXY = { x: number; y: number }

/**
 * Fallback de render: cuando una relación no trae `handle_origen`/
 * `handle_destino` (reconocimiento de foto CU12, importación XMI, CU11 por
 * voz -- ninguno de los tres asigna un lado hoy), React Flow resuelve el
 * handle faltante SIEMPRE al primero de la lista (`SIDES` en ClassNode.tsx
 * empieza en `Position.Top`), así que todas las relaciones sin handle
 * explícito terminaban amontonadas en el mismo punto arriba de cada clase,
 * sin importar dónde esté la otra. Se calcula acá, en base a la posición
 * ACTUAL de ambas clases, el lado cardinal dominante de cada extremo -- es
 * deliberadamente una heurística simple (no un layout automático tipo
 * dagre, fuera de alcance) y NO se persiste de vuelta a la BD: es pura
 * decoración de render, recalculada cada vez a partir de `pos_x`/`pos_y`,
 * así que también se autocorrige sola si las clases se mueven después.
 */
export function calcularHandlesPorPosicion(
  posOrigen: PosicionXY,
  posDestino: PosicionXY,
): { origen: string; destino: string } {
  const dx = posDestino.x - posOrigen.x
  const dy = posDestino.y - posOrigen.y
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? { origen: 'right', destino: 'left' } : { origen: 'left', destino: 'right' }
  }
  return dy >= 0 ? { origen: 'bottom', destino: 'top' } : { origen: 'top', destino: 'bottom' }
}

function construirArista(r: RelacionUml, posicionesPorId: Map<string, PosicionXY>): Edge<EdgeData> {
  let sourceHandle = r.handle_origen ?? undefined
  let targetHandle = r.handle_destino ?? undefined
  if (!sourceHandle || !targetHandle) {
    const posOrigen = posicionesPorId.get(r.id_clase_origen)
    const posDestino = posicionesPorId.get(r.id_clase_destino)
    if (posOrigen && posDestino) {
      const calculados = calcularHandlesPorPosicion(posOrigen, posDestino)
      sourceHandle = sourceHandle ?? calculados.origen
      targetHandle = targetHandle ?? calculados.destino
    }
  }
  return {
    id: r.id,
    source: r.id_clase_origen,
    target: r.id_clase_destino,
    sourceHandle,
    targetHandle,
    type: 'relacion',
    label: r.etiqueta ?? undefined,
    style: EDGE_STYLE,
    data: {
      tipo: r.tipo,
      etiqueta: r.etiqueta,
      multiplicidad_origen: r.multiplicidad_origen,
      multiplicidad_destino: r.multiplicidad_destino,
      forma: r.forma ?? null,
      desvio_x: r.desvio_x ?? null,
      desvio_y: r.desvio_y ?? null,
    },
    ...markerDeRelacion(r.tipo),
  }
}

function posicionesPorIdDeClases(clases: ClaseUml[]): Map<string, PosicionXY> {
  return new Map(clases.map((c) => [c.id, { x: c.pos_x, y: c.pos_y }]))
}

function construirAristas(relaciones: RelacionUml[], clases: ClaseUml[]): Edge<EdgeData>[] {
  const posicionesPorId = posicionesPorIdDeClases(clases)
  return relaciones.map((r) => construirArista(r, posicionesPorId))
}

/**
 * CU10 — funde el estado remoto recibido del documento Yjs compartido con
 * los nodos locales actuales. No es un reemplazo ciego: una clase local sin
 * nombre todavía (fila "Nueva clase" en blanco, que el usuario está
 * escribiendo) nunca se mandó a Yjs -- mismo criterio que ya usa
 * `serializar()` para el autoguardado HTTP -- así que se conserva tal cual
 * en vez de borrarla por "no estar" del lado remoto. Un nodo que se está
 * arrastrando localmente (`dragging`) no se reposiciona con la posición
 * remota, para no pelear con el drag en curso.
 */
function mezclarNodosRemotos(
  actuales: Node<ClassNodeData>[],
  clasesRemotas: ClaseUml[],
  onCambiar: (clase: ClaseUml) => void,
): Node<ClassNodeData>[] {
  const remotasPorId = new Map(clasesRemotas.map((c) => [c.id, c]))
  const vistos = new Set<string>()
  const resultado: Node<ClassNodeData>[] = []

  for (const nodo of actuales) {
    const remota = remotasPorId.get(nodo.id)
    if (remota) {
      vistos.add(nodo.id)
      const posicionIgual = nodo.position.x === remota.pos_x && nodo.position.y === remota.pos_y
      const contenidoIgual = JSON.stringify(remota) === JSON.stringify(nodo.data.clase)
      if (posicionIgual && contenidoIgual) {
        resultado.push(nodo)
      } else {
        resultado.push({
          ...nodo,
          position: nodo.dragging ? nodo.position : { x: remota.pos_x, y: remota.pos_y },
          data: { ...nodo.data, clase: remota },
        })
      }
    } else if (!nodo.data.clase.nombre.trim()) {
      resultado.push(nodo) // clase local sin confirmar: nunca se sincronizó, se conserva
    }
    // si tenía nombre y ya no aparece remotamente: se borró en otro lado, se omite
  }

  for (const remota of clasesRemotas) {
    if (vistos.has(remota.id)) continue
    resultado.push({
      id: remota.id,
      type: 'classNode',
      position: { x: remota.pos_x, y: remota.pos_y },
      data: { clase: remota, onCambiar },
    })
  }

  return resultado
}

/** `idArrastrando`: arista cuyo punto de control se está arrastrando
 * localmente ahora mismo -- conserva su desvío local (mismo criterio que
 * `dragging` en mezclarNodosRemotos, para no pelear con el arrastre). */
function mezclarAristasRemotas(
  actuales: Edge<EdgeData>[],
  relacionesRemotas: RelacionUml[],
  clasesRemotas: ClaseUml[],
  idArrastrando: string | null = null,
): Edge<EdgeData>[] {
  const posicionesPorId = posicionesPorIdDeClases(clasesRemotas)
  const remotasPorId = new Map(relacionesRemotas.map((r) => [r.id, r]))
  const vistos = new Set<string>()
  const resultado: Edge<EdgeData>[] = []

  for (const arista of actuales) {
    const remota = remotasPorId.get(arista.id)
    if (!remota) continue // se borró en otro lado
    vistos.add(arista.id)
    const nueva = construirArista(remota, posicionesPorId)
    // Conservar la selección local: el punto de control arrastrable solo
    // se muestra con la arista seleccionada, y cualquier cambio remoto (o un
    // Ctrl+Z, que entra por este mismo camino) la deseleccionaría.
    nueva.selected = arista.selected
    if (arista.id === idArrastrando && arista.data && nueva.data) {
      nueva.data = { ...nueva.data, desvio_x: arista.data.desvio_x, desvio_y: arista.data.desvio_y }
    }
    resultado.push(nueva)
  }

  for (const remota of relacionesRemotas) {
    if (!vistos.has(remota.id)) resultado.push(construirArista(remota, posicionesPorId))
  }

  return resultado
}

function serializar(nodes: Node<ClassNodeData>[], edges: Edge<EdgeData>[]): DiagramaData {
  // Las clases sin nombre (recién creadas, el usuario todavía está
  // escribiéndolo) y las filas de atributo/método sin nombre son solo
  // renglones "en blanco" — el backend exige nombre no vacío en todos los
  // casos, así que se excluyen del guardado hasta que se confirmen con un
  // nombre real. Las relaciones que quedarían apuntando a una clase excluida
  // también se descartan para no romper la integridad del payload.
  const idsClasesValidas = new Set(
    nodes.filter((n) => n.data.clase.nombre.trim()).map((n) => n.id),
  )
  return {
    clases: nodes
      .filter((n) => idsClasesValidas.has(n.id))
      .map((n) => ({
        ...n.data.clase,
        pos_x: n.position.x,
        pos_y: n.position.y,
        atributos: n.data.clase.atributos.filter((a) => a.nombre.trim()),
        metodos: n.data.clase.metodos.filter((m) => m.nombre.trim()),
      })),
    relaciones: edges
      .filter((e) => idsClasesValidas.has(e.source) && idsClasesValidas.has(e.target))
      .map((e) => ({
        id: e.id,
        id_clase_origen: e.source,
        id_clase_destino: e.target,
        tipo: e.data?.tipo ?? 'ASOCIACION',
        etiqueta: e.data?.etiqueta ?? null,
        multiplicidad_origen: e.data?.multiplicidad_origen ?? null,
        multiplicidad_destino: e.data?.multiplicidad_destino ?? null,
        handle_origen: e.sourceHandle ?? null,
        handle_destino: e.targetHandle ?? null,
        forma: e.data?.forma ?? null,
        desvio_x: e.data?.desvio_x ?? null,
        desvio_y: e.data?.desvio_y ?? null,
      })),
  }
}

export function useDiagrama(proyectoId: number) {
  const { user } = useAuth()
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<ClassNodeData>([])
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<EdgeData>([])
  const [estado, setEstado] = useState<'cargando' | 'listo' | 'error'>('cargando')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [errorGuardado, setErrorGuardado] = useState<string | null>(null)
  const cargadoRef = useRef(false)
  // CU10 — una vez que el documento Yjs compartido sincronizó al menos una
  // vez, es la fuente de verdad (puede tener cambios de otros colaboradores
  // más nuevos que la última foto guardada en la BD); el GET inicial pasa a
  // ser solo el "primer pintado" mientras se conecta el WebSocket.
  const yjsSincronizadoRef = useRef(false)
  // Indirección para que `guardarAhora` (definido más abajo) pueda disparar
  // la sincronización con Yjs sin depender del orden de declaración —
  // mismo patrón que nodesRef/edgesRef.
  const colabPublicarRef = useRef<() => void>(() => {})
  // Arista cuyo punto de control se está arrastrando (ver moverPuntoRelacion).
  const arrastrandoAristaRef = useRef<string | null>(null)

  // Espejo siempre-actualizado de nodes/edges, para que el guardado diferido
  // (setTimeout) lea el estado más reciente sin importar cuándo se programó.
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])
  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

  // Guardado explícito con debounce, disparado solo desde puntos concretos
  // (crear/editar/eliminar clase o relación, soltar un arrastre, borrar con
  // teclado) — NO en cada tick de posición mientras se arrastra una clase.
  const guardarTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hayPendienteRef = useRef(false)

  const ejecutarGuardado = useCallback(() => {
    hayPendienteRef.current = false
    setGuardando(true)
    guardarDiagrama(proyectoId, serializar(nodesRef.current, edgesRef.current))
      .then(() => setErrorGuardado(null))
      .catch((err) => {
        // El usuario sigue editando localmente; el error queda visible en la
        // toolbar con opción de reintentar (no se pierde el cambio, solo no
        // está confirmado en el servidor todavía).
        setErrorGuardado(getApiErrorMessage(err, 'No se pudo guardar el diagrama'))
      })
      .finally(() => setGuardando(false))
  }, [proyectoId])

  const guardarAhora = useCallback(() => {
    if (!cargadoRef.current) return
    hayPendienteRef.current = true
    colabPublicarRef.current() // CU10 — al colaborador en vivo no le importa el debounce de 800ms del PUT
    if (guardarTimeoutRef.current) clearTimeout(guardarTimeoutRef.current)
    guardarTimeoutRef.current = setTimeout(ejecutarGuardado, DEBOUNCE_MS)
  }, [ejecutarGuardado])

  // Reintento manual (botón en la toolbar): salta el debounce y guarda ya.
  const reintentarGuardado = useCallback(() => {
    if (guardarTimeoutRef.current) clearTimeout(guardarTimeoutRef.current)
    ejecutarGuardado()
  }, [ejecutarGuardado])

  // Si el componente se desmonta (ej. el usuario navega a "← Proyectos") con
  // un guardado pendiente dentro de la ventana de debounce, se dispara de
  // inmediato en vez de perderse — cubre el caso de editar y salir rápido.
  useEffect(
    () => () => {
      if (guardarTimeoutRef.current) clearTimeout(guardarTimeoutRef.current)
      if (hayPendienteRef.current) ejecutarGuardado()
    },
    [ejecutarGuardado],
  )

  // Envuelve los change-handlers de React Flow: aplican el cambio como
  // siempre (selección, arrastre en vivo, dimensiones), pero solo disparan
  // guardado cuando el cambio es una eliminación (ej. tecla Delete/Backspace
  // sobre un nodo o arista seleccionada).
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChangeBase(changes)
      if (changes.some((c) => c.type === 'remove')) guardarAhora()
    },
    [onNodesChangeBase, guardarAhora],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChangeBase(changes)
      if (changes.some((c) => c.type === 'remove')) guardarAhora()
    },
    [onEdgesChangeBase, guardarAhora],
  )

  // Se dispara al soltar el arrastre de una clase: una sola vez por
  // movimiento, con la posición final ya aplicada por onNodesChange.
  const onNodeDragStop = useCallback(() => {
    guardarAhora()
  }, [guardarAhora])

  const actualizarClase = useCallback(
    (clase: ClaseUml) => {
      setNodes((nds) => nds.map((n) => (n.id === clase.id ? { ...n, data: { ...n.data, clase } } : n)))
      guardarAhora()
    },
    [setNodes, guardarAhora],
  )

  // CU10 — llega cuando el documento Yjs compartido sincronizó (al conectar,
  // o porque otro colaborador cambió algo): funde el estado remoto con el
  // local (ver mezclarNodosRemotos/mezclarAristasRemotas) y, si el GET
  // inicial todavía no terminó (o falló), esto solo alcanza para dar por
  // cargado el diagrama igual.
  const aplicarCambioRemoto = useCallback(
    (datos: DiagramaData) => {
      yjsSincronizadoRef.current = true
      setNodes((nds) => mezclarNodosRemotos(nds, datos.clases, actualizarClase))
      setEdges((eds) => mezclarAristasRemotas(eds, datos.relaciones, datos.clases, arrastrandoAristaRef.current))
      setEstado('listo')
      cargadoRef.current = true
    },
    [setNodes, setEdges, actualizarClase],
  )

  const usuarioColab = user ? { id: user.id, nombre_completo: user.nombre_completo } : null
  const { estadoConexion, colaboradores, cursores, publicarCursor, publicarCambioLocal, deshacer, rehacer } =
    useColaboracion(proyectoId, usuarioColab, aplicarCambioRemoto)

  const colabDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  colabPublicarRef.current = () => {
    if (colabDebounceRef.current) clearTimeout(colabDebounceRef.current)
    // Debounce corto (no los 800ms del PUT): solo lo justo para que
    // nodesRef/edgesRef ya reflejen el cambio recién hecho en este mismo
    // tick (se actualizan en un efecto, ver arriba), sin notarse como
    // demora para los demás colaboradores.
    colabDebounceRef.current = setTimeout(() => {
      publicarCambioLocal(serializar(nodesRef.current, edgesRef.current))
    }, 50)
  }

  useEffect(() => {
    let alive = true
    cargadoRef.current = false
    yjsSincronizadoRef.current = false
    setEstado('cargando')
    getDiagrama(proyectoId)
      .then((datos) => {
        if (!alive || yjsSincronizadoRef.current) return
        setNodes(construirNodos(datos.clases, actualizarClase))
        setEdges(construirAristas(datos.relaciones, datos.clases))
        setEstado('listo')
        cargadoRef.current = true
      })
      .catch((err) => {
        if (!alive || yjsSincronizadoRef.current) return
        setError(getApiErrorMessage(err, 'No se pudo cargar el diagrama'))
        setEstado('error')
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proyectoId])

  const eliminarClase = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id))
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id))
      guardarAhora()
    },
    [setNodes, setEdges, guardarAhora],
  )

  const agregarClase = useCallback(
    (clase: ClaseUml) => {
      setNodes((nds) => [
        ...nds.map((n) => ({ ...n, selected: false })),
        {
          id: clase.id,
          type: 'classNode',
          selected: true,
          position: { x: clase.pos_x, y: clase.pos_y },
          data: { clase, onCambiar: actualizarClase, autoEditarNombre: true },
        },
      ])
      guardarAhora()
    },
    [setNodes, guardarAhora, actualizarClase],
  )

  const seleccionarClase = useCallback(
    (id: string) => {
      setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === id })))
    },
    [setNodes],
  )

  // Importación XMI (CU09): el backend ya guardó `datos` en la BD (endpoint
  // POST .../importar-xmi) -- acá solo se refleja en el lienzo sin recargar
  // la página, con el mismo `guardarAhora()` que dispara el resto de
  // acciones (sincroniza a Yjs para cualquier otro colaborador conectado;
  // el PUT HTTP que dispara es redundante con lo que ya guardó el backend,
  // pero inofensivo, mismo patrón que el resto de acciones locales).
  const importarDiagrama = useCallback(
    (datos: DiagramaData) => {
      setNodes(construirNodos(datos.clases, actualizarClase))
      setEdges(construirAristas(datos.relaciones, datos.clases))
      guardarAhora()
    },
    [setNodes, setEdges, guardarAhora, actualizarClase],
  )

  // CU11 — un comando de voz puede crear varias clases, sumar atributos a
  // otras y relacionarlas: todo entra en un solo setNodes/setEdges + un solo
  // guardarAhora(), así es un único paso de Ctrl+Z y un solo push a Yjs. Los
  // lados de cada arista se calculan por posición (construirArista), porque
  // la voz no elige handles.
  const agregarLote = useCallback(
    (clasesNuevas: ClaseUml[], clasesActualizadas: ClaseUml[], relaciones: RelacionUml[]) => {
      const actualizadasPorId = new Map(clasesActualizadas.map((c) => [c.id, c]))
      setNodes((nds) => [
        ...nds.map((n) => {
          const clase = actualizadasPorId.get(n.id)
          return { ...n, selected: false, ...(clase ? { data: { ...n.data, clase } } : {}) }
        }),
        ...clasesNuevas.map((clase) => ({
          id: clase.id,
          type: 'classNode',
          position: { x: clase.pos_x, y: clase.pos_y },
          data: { clase, onCambiar: actualizarClase },
        })),
      ])
      const posicionesPorId = new Map<string, PosicionXY>(
        nodesRef.current.map((n) => [n.id, { x: n.position.x, y: n.position.y }]),
      )
      for (const clase of clasesNuevas) posicionesPorId.set(clase.id, { x: clase.pos_x, y: clase.pos_y })
      setEdges((eds) => [...eds, ...relaciones.map((r) => construirArista(r, posicionesPorId))])
      guardarAhora()
    },
    [setNodes, setEdges, guardarAhora, actualizarClase],
  )

  const crearRelacion = useCallback(
    (conexion: Connection, detalles: DetallesRelacion) => {
      if (!conexion.source || !conexion.target) return
      const id = nuevoId()
      setEdges((eds) => [
        ...eds,
        {
          id,
          source: conexion.source!,
          target: conexion.target!,
          sourceHandle: conexion.sourceHandle ?? undefined,
          targetHandle: conexion.targetHandle ?? undefined,
          type: 'relacion',
          label: detalles.etiqueta ?? undefined,
          style: EDGE_STYLE,
          data: { ...detalles, desvio_x: null, desvio_y: null },
          ...markerDeRelacion(detalles.tipo),
        },
      ])
      guardarAhora()
    },
    [setEdges, guardarAhora],
  )

  const actualizarRelacion = useCallback(
    (id: string, detalles: DetallesRelacion, invertir = false) => {
      setEdges((eds) =>
        eds.map((e) => {
          if (e.id !== id) return e
          // Invertir dirección: los tres pares (clases, handles,
          // multiplicidades) se intercambian juntos -- las multiplicidades
          // ya vienen swapeadas en `detalles` (el modal las invierte
          // localmente), acá solo falta swapear origen/destino y sus
          // handles para que sigan siendo el mismo par lógico.
          const base = invertir
            ? { ...e, source: e.target, target: e.source, sourceHandle: e.targetHandle, targetHandle: e.sourceHandle }
            : e
          // El desvío del punto de control se conserva (cambiar la forma o
          // invertir no lo borra: es relativo al punto medio entre ambos
          // extremos, que es el mismo en cualquier dirección).
          const data: EdgeData = {
            ...detalles,
            desvio_x: e.data?.desvio_x ?? null,
            desvio_y: e.data?.desvio_y ?? null,
          }
          return { ...base, label: detalles.etiqueta ?? undefined, data, ...markerDeRelacion(detalles.tipo) }
        }),
      )
      guardarAhora()
    },
    [setEdges, guardarAhora],
  )

  // Punto de control arrastrable de una relación (RelacionEdge.tsx): durante
  // el arrastre (`confirmar=false`) solo se actualiza el estado local, para
  // que sea fluido; al soltar (`confirmar=true`) se guarda y se publica a
  // Yjs una sola vez -- mismo criterio que onNodeDragStop, y un solo paso
  // de Ctrl+Z. `desvio=null` lo vuelve al punto medio (doble clic).
  const moverPuntoRelacion = useCallback(
    (id: string, desvio: Desvio | null, confirmar: boolean) => {
      arrastrandoAristaRef.current = confirmar ? null : id
      setEdges((eds) =>
        eds.map((e) =>
          e.id === id && e.data
            ? { ...e, data: { ...e.data, desvio_x: desvio?.x ?? null, desvio_y: desvio?.y ?? null } }
            : e,
        ),
      )
      if (confirmar) guardarAhora()
    },
    [setEdges, guardarAhora],
  )

  const eliminarRelacion = useCallback(
    (id: string) => {
      setEdges((eds) => eds.filter((e) => e.id !== id))
      guardarAhora()
    },
    [setEdges, guardarAhora],
  )

  return {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onNodeDragStop,
    estado,
    error,
    guardando,
    errorGuardado,
    reintentarGuardado,
    agregarClase,
    actualizarClase,
    seleccionarClase,
    eliminarClase,
    crearRelacion,
    agregarLote,
    actualizarRelacion,
    moverPuntoRelacion,
    eliminarRelacion,
    importarDiagrama,
    // CU10
    estadoConexion,
    colaboradores,
    cursores,
    publicarCursor,
    // Undo/redo (Y.UndoManager, ver useColaboracion) -- solo atajos de
    // teclado (CanvasArea), sin control visible en la toolbar a propósito.
    deshacer,
    rehacer,
  }
}
