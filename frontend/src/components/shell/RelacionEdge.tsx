import { useContext, useRef } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { BaseEdge, EdgeLabelRenderer, Position, getSmoothStepPath, useReactFlow, useStore } from 'reactflow'
import type { EdgeProps, Node, ReactFlowState } from 'reactflow'

import { AccionesRelacionContext } from './accionesRelacion'
import { calcularHandlesPorPosicion } from './useDiagrama'
import type { EdgeData } from './useDiagrama'

type Lado = 'top' | 'right' | 'bottom' | 'left'
type Punto = { x: number; y: number }

const LADO_A_POSITION: Record<Lado, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
}

/** Dirección hacia afuera de la clase, por lado. */
const NORMAL: Record<Lado, Punto> = {
  top: { x: 0, y: -1 },
  right: { x: 1, y: 0 },
  bottom: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
}

/** Distancia (px) del extremo a la que va la etiqueta de multiplicidad. */
const DISTANCIA_MULTIPLICIDAD = 24

function medido(nodo: Node | undefined): nodo is Node {
  return !!nodo?.width && !!nodo?.height
}

function centroDe(nodo: Node): Punto {
  const { x, y } = nodo.positionAbsolute ?? nodo.position
  return { x: x + (nodo.width ?? 0) / 2, y: y + (nodo.height ?? 0) / 2 }
}

/** Lado de `nodo` que mira hacia `otro` (mismo criterio que el fallback de
 * handles de useDiagrama.ts). */
function ladoHacia(nodo: Node, otro: Node): Lado {
  return calcularHandlesPorPosicion(centroDe(nodo), centroDe(otro)).origen as Lado
}

/** Punto sobre el lado `lado` de `nodo`, en la posición `indice` de `total`
 * líneas que comparten ese mismo lado: se reparten a lo largo del lado en
 * (indice+1)/(total+1) en vez de salir todas del punto medio. */
function puntoDeConexion(nodo: Node, lado: Lado, indice: number, total: number): Punto {
  const { x, y } = nodo.positionAbsolute ?? nodo.position
  const ancho = nodo.width ?? 0
  const alto = nodo.height ?? 0
  const f = (indice + 1) / (total + 1)
  switch (lado) {
    case 'top':
      return { x: x + ancho * f, y }
    case 'bottom':
      return { x: x + ancho * f, y: y + alto }
    case 'left':
      return { x, y: y + alto * f }
    case 'right':
      return { x: x + ancho, y: y + alto * f }
  }
}

/** Para el extremo `idNodo` de la arista `idArista`: qué lado usa y en qué
 * posición va entre todas las aristas que salen/llegan por ese mismo lado de
 * esa misma clase. Se ordenan por la coordenada de la clase del otro extremo
 * (X para arriba/abajo, Y para izquierda/derecha; el id desempata, p. ej.
 * dos relaciones entre el mismo par de clases) -- así las líneas no se
 * cruzan entre sí justo al salir de la clase. */
function repartoEnExtremo(store: ReactFlowState, idArista: string, idNodo: string, idOtro: string) {
  const nodo = store.nodeInternals.get(idNodo)
  const otro = store.nodeInternals.get(idOtro)
  if (!medido(nodo) || !medido(otro)) return null
  const lado = ladoHacia(nodo, otro)
  const eje = lado === 'top' || lado === 'bottom' ? 'x' : 'y'

  const hermanas: { id: string; clave: number }[] = []
  for (const e of store.edges) {
    if (e.source === e.target) continue
    const idVecino = e.source === idNodo ? e.target : e.target === idNodo ? e.source : null
    if (!idVecino) continue
    const vecino = store.nodeInternals.get(idVecino)
    if (!medido(vecino) || ladoHacia(nodo, vecino) !== lado) continue
    hermanas.push({ id: e.id, clave: centroDe(vecino)[eje] })
  }
  hermanas.sort((a, b) => a.clave - b.clave || a.id.localeCompare(b.id))
  const indice = hermanas.findIndex((h) => h.id === idArista)
  const punto = puntoDeConexion(nodo, lado, Math.max(indice, 0), Math.max(hermanas.length, 1))
  return { lado, x: punto.x, y: punto.y }
}

type Extremos = {
  sLado: Lado
  sx: number
  sy: number
  tLado: Lado
  tx: number
  ty: number
} | null

/** Selector de useStore: devuelve solo números (no objetos nuevos en cada
 * render), así la arista se redibuja únicamente cuando cambian SUS extremos
 * -- p. ej. al arrastrar una clase, o al sumarse otra línea al mismo lado. */
function selectorExtremos(id: string, source: string, target: string) {
  return (store: ReactFlowState): Extremos => {
    const s = repartoEnExtremo(store, id, source, target)
    const t = repartoEnExtremo(store, id, target, source)
    if (!s || !t) return null
    return { sLado: s.lado, sx: s.x, sy: s.y, tLado: t.lado, tx: t.x, ty: t.y }
  }
}

function extremosIguales(a: Extremos, b: Extremos): boolean {
  if (a === null || b === null) return a === b
  return (
    a.sLado === b.sLado && a.sx === b.sx && a.sy === b.sy && a.tLado === b.tLado && a.tx === b.tx && a.ty === b.ty
  )
}

function mas(a: Punto, b: Punto, k = 1): Punto {
  return { x: a.x + b.x * k, y: a.y + b.y * k }
}

/** Punto sobre el segmento a→b a `distancia` px de `a`, sin pasar del 40%
 * del camino (en líneas muy cortas, que las dos multiplicidades no se pisen). */
function puntoCercaDe(a: Punto, b: Punto, distancia: number): Punto {
  const largo = Math.hypot(b.x - a.x, b.y - a.y) || 1
  const t = Math.min(distancia / largo, 0.4)
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }
}

type Trazado = {
  path: string
  /** Dónde va el punto arrastrable y la etiqueta central (siempre sobre la línea). */
  control: Punto
  /** Dónde va la multiplicidad de cada extremo (sobre el primer tramo real). */
  multOrigen: Punto
  multDestino: Punto
}

/**
 * Traza la línea según su forma. `desvio` es el corrimiento del punto de
 * control respecto del punto medio M entre los dos extremos (se guarda
 * relativo, no absoluto: si se mueve una clase la línea conserva su forma).
 */
function trazar(forma: string, s: Punto, sLado: Lado, t: Punto, tLado: Lado, desvio: Punto): Trazado {
  const m = { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 }
  const p = mas(m, desvio)

  if (forma === 'L') {
    const multOrigen = mas(s, NORMAL[sLado], DISTANCIA_MULTIPLICIDAD)
    const multDestino = mas(t, NORMAL[tLado], DISTANCIA_MULTIPLICIDAD)
    // Con lados izquierda/derecha el tramo "del medio" es vertical; con
    // arriba/abajo, horizontal. Se trabaja en un eje genérico: `a` es el eje
    // en el que salen las líneas de la clase y `b` el perpendicular.
    const horizontal = sLado === 'left' || sLado === 'right'
    const a = (q: Punto) => (horizontal ? q.x : q.y)
    const b = (q: Punto) => (horizontal ? q.y : q.x)
    const punto = (va: number, vb: number): Punto => (horizontal ? { x: va, y: vb } : { x: vb, y: va })
    const pb = b(p)

    if (pb >= Math.min(b(s), b(t)) && pb <= Math.max(b(s), b(t))) {
      // Caso normal: un solo tramo del medio, y arrastrar el punto a lo
      // largo del eje `a` decide dónde dobla la línea. El punto se muestra
      // siempre sobre ese tramo, no flotando fuera de la línea.
      const control = punto(a(p), b(m))
      const [path] = getSmoothStepPath({
        sourceX: s.x,
        sourceY: s.y,
        sourcePosition: LADO_A_POSITION[sLado],
        targetX: t.x,
        targetY: t.y,
        targetPosition: LADO_A_POSITION[tLado],
        centerX: control.x,
        centerY: control.y,
        borderRadius: 6,
      })
      return { path, control, multOrigen, multDestino }
    }

    // Punto arrastrado por fuera de ambos extremos (p. ej. por debajo de una
    // clase que se interpone): la línea "rodea" -- sale un tramo corto de
    // cada clase, va hasta la altura del punto y cruza por ahí. Es lo que
    // permite desviar una línea que atraviesa otra clase.
    const salida = 20
    const a1 = a(s) + a(NORMAL[sLado]) * salida
    const a2 = a(t) + a(NORMAL[tLado]) * salida
    const puntos = [s, punto(a1, b(s)), punto(a1, pb), punto(a2, pb), punto(a2, b(t)), t]
    const control = punto(Math.min(Math.max(a(p), Math.min(a1, a2)), Math.max(a1, a2)), pb)
    return {
      path: `M ${puntos.map((q) => `${q.x},${q.y}`).join(' L ')}`,
      control,
      multOrigen,
      multDestino,
    }
  }

  if (forma === 'CURVA') {
    // Bezier cúbica que sale perpendicular a cada clase. Sumando 4/3 del
    // desvío a ambos puntos de control, el punto de la curva en t=0.5 cae
    // exactamente en M + desvío -- la curva pasa por el punto que se arrastra.
    const distancia = Math.hypot(t.x - s.x, t.y - s.y)
    const k = Math.max(30, distancia * 0.35)
    const c1 = mas(mas(s, NORMAL[sLado], k), desvio, 4 / 3)
    const c2 = mas(mas(t, NORMAL[tLado], k), desvio, 4 / 3)
    const control = {
      x: (s.x + 3 * c1.x + 3 * c2.x + t.x) / 8,
      y: (s.y + 3 * c1.y + 3 * c2.y + t.y) / 8,
    }
    return {
      path: `M ${s.x},${s.y} C ${c1.x},${c1.y} ${c2.x},${c2.y} ${t.x},${t.y}`,
      control,
      multOrigen: puntoCercaDe(s, c1, DISTANCIA_MULTIPLICIDAD),
      multDestino: puntoCercaDe(t, c2, DISTANCIA_MULTIPLICIDAD),
    }
  }

  // RECTA: sin desvío, un segmento; con desvío, dos segmentos que pasan por el punto.
  const quebrada = desvio.x !== 0 || desvio.y !== 0
  return {
    path: quebrada ? `M ${s.x},${s.y} L ${p.x},${p.y} L ${t.x},${t.y}` : `M ${s.x},${s.y} L ${t.x},${t.y}`,
    control: p,
    multOrigen: puntoCercaDe(s, quebrada ? p : t, DISTANCIA_MULTIPLICIDAD),
    multDestino: puntoCercaDe(t, quebrada ? p : s, DISTANCIA_MULTIPLICIDAD),
  }
}

/**
 * Arista UML con hasta 3 etiquetas (multiplicidad en cada extremo y la
 * etiqueta libre en el medio) -- React Flow no ofrece esto en sus edges de
 * fábrica.
 *
 * Extremos "flotantes": en vez de las props `sourceX/sourceY/...` (que React
 * Flow resuelve a partir de un handle fijo), se lee del store la posición y
 * tamaño EN VIVO de ambas clases y se recalcula en cada render:
 *   1. el lado de cada clase que mira hacia la otra, y
 *   2. el punto dentro de ese lado -- las líneas que comparten el mismo lado
 *      de la misma clase se reparten a lo largo de él (ver `repartoEnExtremo`)
 *      en vez de salir todas del punto medio, que era lo que hacía que varias
 *      relaciones parecieran una sola.
 *
 * Forma editable por relación (`data.forma`: RECTA | L | CURVA, elegida en
 * RelacionEditorModal) y un punto de control arrastrable (visible con la
 * arista seleccionada) que desvía la línea; doble clic sobre el punto la
 * vuelve al centro. El desvío se confirma al soltar (moverPuntoRelacion en
 * useDiagrama.ts: guarda, sincroniza con Yjs y queda como un paso de Ctrl+Z).
 */
export function RelacionEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerStart,
  markerEnd,
  style,
  data,
  label,
  selected,
}: EdgeProps<EdgeData>) {
  const extremos = useStore(selectorExtremos(id, source, target), extremosIguales)
  const moverPunto = useContext(AccionesRelacionContext)
  const { screenToFlowPosition } = useReactFlow()
  // Durante el arrastre: diferencia entre donde se agarró el punto y su
  // posición real, para que no "salte" bajo el cursor al empezar.
  const agarreRef = useRef<Punto | null>(null)
  const ultimoDesvioRef = useRef<Punto | null>(null)

  // Si todavía no se midió alguno de los dos nodos (primer render), se usan
  // las props originales de React Flow como respaldo en vez de romper nada.
  const s = extremos ? { x: extremos.sx, y: extremos.sy } : { x: sourceX, y: sourceY }
  const t = extremos ? { x: extremos.tx, y: extremos.ty } : { x: targetX, y: targetY }
  const sLado = extremos?.sLado ?? (sourcePosition as Lado)
  const tLado = extremos?.tLado ?? (targetPosition as Lado)
  const desvio = { x: data?.desvio_x ?? 0, y: data?.desvio_y ?? 0 }
  const forma = data?.forma ?? 'RECTA'

  const trazado = trazar(forma, s, sLado, t, tLado, desvio)
  const etiqueta = label ?? data?.etiqueta

  const puntoMedio = { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 }

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    e.currentTarget.setPointerCapture(e.pointerId)
    const cursor = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    agarreRef.current = { x: trazado.control.x - cursor.x, y: trazado.control.y - cursor.y }
    ultimoDesvioRef.current = null
  }

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!agarreRef.current) return
    const cursor = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const nuevo = {
      x: Math.round(cursor.x + agarreRef.current.x - puntoMedio.x),
      y: Math.round(cursor.y + agarreRef.current.y - puntoMedio.y),
    }
    ultimoDesvioRef.current = nuevo
    moverPunto(id, nuevo, false)
  }

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!agarreRef.current) return
    e.currentTarget.releasePointerCapture(e.pointerId)
    agarreRef.current = null
    // Un clic sin mover no cuenta como cambio (no genera un guardado ni un
    // paso de Ctrl+Z vacío).
    if (ultimoDesvioRef.current) moverPunto(id, ultimoDesvioRef.current, true)
  }

  return (
    <>
      <BaseEdge id={id} path={trazado.path} markerStart={markerStart} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        {data?.multiplicidad_origen && (
          <div
            className="nodrag nopan edge-multiplicidad"
            style={{ transform: `translate(-50%, -50%) translate(${trazado.multOrigen.x}px, ${trazado.multOrigen.y}px)` }}
          >
            {data.multiplicidad_origen}
          </div>
        )}
        {data?.multiplicidad_destino && (
          <div
            className="nodrag nopan edge-multiplicidad"
            style={{
              transform: `translate(-50%, -50%) translate(${trazado.multDestino.x}px, ${trazado.multDestino.y}px)`,
            }}
          >
            {data.multiplicidad_destino}
          </div>
        )}
        {etiqueta && (
          <div
            className="nodrag nopan edge-etiqueta"
            style={{
              // Con la arista seleccionada, la etiqueta se corre un poco hacia
              // arriba para no tapar el punto de control.
              transform: `translate(-50%, ${selected ? '-150%' : '-50%'}) translate(${trazado.control.x}px, ${trazado.control.y}px)`,
            }}
          >
            {etiqueta}
          </div>
        )}
        {selected && (
          <div
            className="nodrag nopan edge-control"
            title="Arrastrá para mover la línea · doble clic para volverla al centro"
            style={{ transform: `translate(-50%, -50%) translate(${trazado.control.x}px, ${trazado.control.y}px)` }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onDoubleClick={(e) => {
              e.stopPropagation()
              moverPunto(id, null, true)
            }}
          />
        )}
      </EdgeLabelRenderer>
    </>
  )
}
