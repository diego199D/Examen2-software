import { useCallback, useEffect, useRef, useState } from 'react'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'

import { API_BASE_URL } from '../api/client'
import type { DiagramaData } from '../api/types'
import { getToken } from '../auth/tokenStorage'
import { leerDiagramaDeYjs, ORIGEN_LOCAL, sincronizarLocalAYjs } from './yjsDiagrama'

export type EstadoConexion = 'conectando' | 'conectado' | 'desconectado'

export type ColaboradorPresencia = {
  clientId: number
  nombre: string
  color: string
}

export type CursorRemoto = ColaboradorPresencia & {
  x: number
  y: number
}

type UsuarioActual = { id: number; nombre_completo: string } | null

type AwarenessUser = { nombre: string; color: string }
type AwarenessState = { user?: AwarenessUser; cursor?: { x: number; y: number } | null }

// Paleta fija (no depende de --accent de tokens.css a propósito: varios
// colaboradores conectados a la vez necesitan colores distintos entre sí,
// no coordinados con el acento de la UI).
const COLORES = ['#2b4c7e', '#b03a3a', '#3c7a5c', '#a3671f', '#6a3f91', '#1f7a8c', '#a13d78']

const ESTADO_DESDE_YWEBSOCKET: Record<'connected' | 'connecting' | 'disconnected', EstadoConexion> = {
  connected: 'conectado',
  connecting: 'conectando',
  disconnected: 'desconectado',
}

function colorPara(clientId: number): string {
  return COLORES[clientId % COLORES.length]
}

function wsBaseUrl(): string {
  const url = new URL(API_BASE_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString().replace(/\/+$/, '')
}

/**
 * CU10 — conecta el documento Yjs compartido del proyecto (uno por
 * `/ws/proyectos/{id}/diagrama`) y expone presencia/cursores en vivo vía el
 * protocolo de awareness de Yjs. El contenido del diagrama (clases/
 * relaciones) se sincroniza aparte, mediante `publicarCambioLocal` /
 * `onCambioRemoto` — ver useDiagrama.ts, que es quien de verdad entiende el
 * modelo del diagrama; este hook solo mueve bytes.
 */
export function useColaboracion(
  proyectoId: number,
  usuario: UsuarioActual,
  onCambioRemoto: (datos: DiagramaData) => void,
) {
  const [estadoConexion, setEstadoConexion] = useState<EstadoConexion>('conectando')
  const [colaboradores, setColaboradores] = useState<ColaboradorPresencia[]>([])
  const [cursores, setCursores] = useState<CursorRemoto[]>([])
  const providerRef = useRef<WebsocketProvider | null>(null)
  const undoManagerRef = useRef<Y.UndoManager | null>(null)

  const onCambioRemotoRef = useRef(onCambioRemoto)
  useEffect(() => {
    onCambioRemotoRef.current = onCambioRemoto
  }, [onCambioRemoto])

  useEffect(() => {
    const token = getToken()
    if (!token || !usuario) return

    const doc = new Y.Doc()
    // El "roomname" de y-websocket se concatena tal cual tras el serverUrl:
    // wsBaseUrl + '/ws/proyectos' + '/' + '{id}/diagrama' reproduce
    // exactamente la ruta del endpoint del backend.
    const provider = new WebsocketProvider(`${wsBaseUrl()}/ws/proyectos`, `${proyectoId}/diagrama`, doc, {
      params: { token },
    })
    providerRef.current = provider

    provider.awareness.setLocalStateField('user', {
      nombre: usuario.nombre_completo,
      color: colorPara(doc.clientID),
    } satisfies AwarenessUser)

    setEstadoConexion('conectando')
    setColaboradores([])
    setCursores([])

    const onStatus = ({ status }: { status: 'connected' | 'connecting' | 'disconnected' }) =>
      setEstadoConexion(ESTADO_DESDE_YWEBSOCKET[status])
    provider.on('status', onStatus)

    // y-websocket solo limpia la awareness al desconectar cuando ALGO llama
    // a provider.disconnect() (nuestro cleanup de abajo, en un desmontaje
    // normal de React) — pero si el usuario cierra la pestaña o navega fuera
    // de la SPA, React nunca llega a desmontar nada, así que sin esto los
    // demás colaboradores recién se enteran cuando expira el
    // outdated_timeout de 30s del lado del servidor. `pagehide` (más
    // confiable que `beforeunload`, funciona con bfcache) dispara el mismo
    // aviso explícito de desconexión al instante.
    const handlePageHide = () => provider.disconnect()
    window.addEventListener('pagehide', handlePageHide)

    const onSync = (sincronizado: boolean) => {
      if (sincronizado) onCambioRemotoRef.current(leerDiagramaDeYjs(doc))
    }
    provider.on('sync', onSync)

    const clasesMap = doc.getMap('clases')
    const relacionesMap = doc.getMap('relaciones')

    // Undo/redo (solo atajos de teclado, sin control visible en la UI):
    // `trackedOrigins` limitado a ORIGEN_LOCAL es lo que hace que el Ctrl+Z
    // de este usuario nunca deshaga cambios de otro colaborador -- las
    // transacciones que llegan por la red (aplicadas por el provider al
    // recibir un update) tienen un origin distinto y el UndoManager las
    // ignora por completo, tanto para capturarlas como para no reescribirlas
    // al hacer undo/redo de las propias. `sincronizarLocalAYjs` ya agrupa
    // todo un diff local (ej. borrar una clase + sus atributos + sus
    // relaciones) en una sola `doc.transact(...)`, así que ya sale como un
    // único paso de undo sin configuración extra; el `captureTimeout` por
    // default (500ms) además funde ediciones muy seguidas (ej. tipear un
    // nombre) en un solo paso, como se espera de un undo tipo editor de
    // texto.
    const undoManager = new Y.UndoManager([clasesMap, relacionesMap], {
      trackedOrigins: new Set([ORIGEN_LOCAL]),
    })
    undoManagerRef.current = undoManager

    const onCambioProfundo = (_events: unknown, transaccion: Y.Transaction) => {
      // Los cambios que acabamos de escribir nosotros mismos (ver
      // publicarCambioLocal) ya están reflejados en el estado local — no
      // hace falta (ni conviene, por el drag en curso) volver a aplicarlos.
      if (transaccion.origin === ORIGEN_LOCAL) return
      onCambioRemotoRef.current(leerDiagramaDeYjs(doc))
    }
    clasesMap.observeDeep(onCambioProfundo)
    relacionesMap.observeDeep(onCambioProfundo)

    const actualizarPresencia = () => {
      const propio = doc.clientID
      const nuevosColaboradores: ColaboradorPresencia[] = []
      const nuevosCursores: CursorRemoto[] = []
      provider.awareness.getStates().forEach((estado, clientId) => {
        if (clientId === propio) return
        const { user, cursor } = estado as AwarenessState
        if (!user) return
        nuevosColaboradores.push({ clientId, nombre: user.nombre, color: user.color })
        if (cursor) nuevosCursores.push({ clientId, nombre: user.nombre, color: user.color, ...cursor })
      })
      setColaboradores(nuevosColaboradores)
      setCursores(nuevosCursores)
    }
    provider.awareness.on('change', actualizarPresencia)
    actualizarPresencia()

    return () => {
      window.removeEventListener('pagehide', handlePageHide)
      provider.off('status', onStatus)
      provider.off('sync', onSync)
      provider.awareness.off('change', actualizarPresencia)
      clasesMap.unobserveDeep(onCambioProfundo)
      relacionesMap.unobserveDeep(onCambioProfundo)
      undoManager.destroy()
      undoManagerRef.current = null
      // disconnect() manda el aviso de desconexión de awareness antes de
      // cerrar el socket -- así los demás colaboradores pierden nuestro
      // cursor/chip de inmediato en vez de esperar el timeout de 30s.
      provider.disconnect()
      provider.destroy()
      doc.destroy()
      providerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proyectoId, usuario?.id, usuario?.nombre_completo])

  const publicarCursor = useCallback((posicion: { x: number; y: number } | null) => {
    providerRef.current?.awareness.setLocalStateField('cursor', posicion)
  }, [])

  const publicarCambioLocal = useCallback((datos: DiagramaData) => {
    const provider = providerRef.current
    if (!provider) return
    sincronizarLocalAYjs(provider.doc, datos)
  }, [])

  const deshacer = useCallback(() => {
    undoManagerRef.current?.undo()
  }, [])

  const rehacer = useCallback(() => {
    undoManagerRef.current?.redo()
  }, [])

  return {
    estadoConexion,
    colaboradores,
    cursores,
    publicarCursor,
    publicarCambioLocal,
    deshacer,
    rehacer,
  }
}
