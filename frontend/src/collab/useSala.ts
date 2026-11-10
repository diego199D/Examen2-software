import { useCallback, useEffect, useRef, useState } from 'react'

import type { DiagramaData } from '../api/types'
import { getToken } from '../auth/tokenStorage'
import { wsBaseUrl } from './useColaboracion'

/**
 * Segundo parcial — sala en tiempo real del GRUPO (un único chat público
 * para todos los proyectos del grupo, presencia y Desarrollador Senior) sobre
 * `/ws/proyectos/{id}/sala`: se entra desde un proyecto, que es el contexto
 * del Senior para lo que se pregunta desde esta pestaña.
 * Protocolo JSON `{type, payload}`: ver backend/app/services/sala.py y
 * docs/documentacion-tecnica.md. Se reconecta solo (backoff exponencial,
 * hasta 15 s) y al reconectar el servidor reenvía historial y snapshot.
 *
 * El diagrama en sí sigue viajando por Yjs (useColaboracion.ts): cuando el
 * Senior aplica un cambio, el servidor lo escribe en el documento Yjs y llega
 * a todos como un cambio remoto más. `onDiagramaIA` solo se usa como respaldo
 * si este cliente no tiene Yjs conectado.
 */

export type ModoIA = 'consultivo' | 'con_confirmacion' | 'automatico'

export type PropuestaIA = {
  acciones: unknown[]
  resumen: string[]
  estado: 'pendiente' | 'aplicada' | 'rechazada' | 'fallida'
  decidida_por?: string
}

export type MensajeSala = {
  id: number
  autor: { id: number | null; nombre: string }
  tipo: 'humano' | 'senior_ai' | 'sistema'
  texto: string
  fecha: string
  /** Proyecto desde el que se escribió (el chat es único por grupo). */
  proyecto: { id: number; nombre: string | null }
  dirigido_a: { id: number; nombre: string } | null
  propuesta: PropuestaIA | null
}

export type UsuarioSala = { id: number; nombre: string; proyecto?: { id: number; nombre: string } }

export type EstadoSala = 'conectando' | 'conectado' | 'desconectado'

type Evento = { type: string; payload: Record<string, unknown> }

export function useSala(proyectoId: number, onDiagramaIA?: (diagrama: DiagramaData) => void) {
  const [estado, setEstado] = useState<EstadoSala>('conectando')
  const [mensajes, setMensajes] = useState<MensajeSala[]>([])
  const [presentes, setPresentes] = useState<UsuarioSala[]>([])
  const [modo, setModo] = useState<ModoIA>('automatico')
  const [grupo, setGrupo] = useState<string | null>(null)
  const [seniorEscribiendo, setSeniorEscribiendo] = useState<{ para?: string; enCola: number } | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const onDiagramaRef = useRef(onDiagramaIA)
  useEffect(() => {
    onDiagramaRef.current = onDiagramaIA
  }, [onDiagramaIA])

  useEffect(() => {
    let cerrado = false
    let intento = 0
    let temporizador: ReturnType<typeof setTimeout> | undefined
    let ping: ReturnType<typeof setInterval> | undefined

    const manejar = (ev: Evento) => {
      const p = ev.payload
      switch (ev.type) {
        case 'WELCOME':
          setGrupo((p.grupo as string | null) ?? null)
          setModo((p.modo_ia as ModoIA) ?? 'automatico')
          break
        case 'CHAT_HISTORY':
          setMensajes(p.mensajes as MensajeSala[])
          break
        case 'CHAT_MESSAGE': {
          const m = p.mensaje as MensajeSala
          setMensajes((ms) => (ms.some((x) => x.id === m.id) ? ms : [...ms, m]))
          // La respuesta ya llegó: el indicador se apaga en el acto (si hay
          // más preguntas en cola, el próximo AI_TYPING lo vuelve a encender).
          if (m.tipo === 'senior_ai') setSeniorEscribiendo(null)
          break
        }
        case 'CHAT_MESSAGE_UPDATED': {
          const m = p.mensaje as MensajeSala
          setMensajes((ms) => ms.map((x) => (x.id === m.id ? m : x)))
          break
        }
        case 'PRESENCE_LIST':
          setPresentes(p.usuarios as UsuarioSala[])
          break
        case 'AI_TYPING':
          setSeniorEscribiendo(
            p.activo ? { para: p.para as string | undefined, enCola: Number(p.en_cola ?? 0) } : null,
          )
          break
        case 'AI_MODE_CHANGED':
          setModo(p.modo as ModoIA)
          setAviso(`${p.por as string} cambió el modo del Senior a "${etiquetaModo(p.modo as ModoIA)}".`)
          break
        case 'AI_DIAGRAM_ACTION_EXECUTED':
          // El chat es del grupo: solo interesa si el cambio fue en ESTE proyecto.
          if (p.proyecto_id === proyectoId) onDiagramaRef.current?.(p.diagrama as DiagramaData)
          break
        case 'ERROR':
          setAviso(p.mensaje as string)
          break
      }
    }

    const conectar = () => {
      if (cerrado) return
      setEstado('conectando')
      const token = getToken() ?? ''
      const ws = new WebSocket(`${wsBaseUrl()}/ws/proyectos/${proyectoId}/sala?token=${encodeURIComponent(token)}`)
      wsRef.current = ws
      ws.onopen = () => {
        intento = 0
        setEstado('conectado')
        ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: 'PING', payload: {} })), 25000)
      }
      ws.onmessage = (e) => {
        try {
          manejar(JSON.parse(e.data as string) as Evento)
        } catch {
          /* evento malformado: se ignora */
        }
      }
      ws.onclose = (e) => {
        clearInterval(ping)
        if (cerrado) return
        setEstado('desconectado')
        setSeniorEscribiendo(null)
        // 4401/4403/4404: sin permiso -- no tiene sentido reintentar.
        if (e.code >= 4400 && e.code < 4500) {
          setAviso('No tenés acceso a la sala de este proyecto.')
          return
        }
        intento += 1
        temporizador = setTimeout(conectar, Math.min(15000, 500 * 2 ** intento))
      }
    }

    conectar()
    return () => {
      cerrado = true
      clearTimeout(temporizador)
      clearInterval(ping)
      wsRef.current?.close()
    }
  }, [proyectoId])

  const enviarEvento = useCallback((type: string, payload: Record<string, unknown>) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setAviso('Sin conexión con la sala: reintentando…')
      return false
    }
    ws.send(JSON.stringify({ type, payload }))
    return true
  }, [])

  return {
    estado,
    mensajes,
    presentes,
    modo,
    grupo,
    seniorEscribiendo,
    aviso,
    descartarAviso: () => setAviso(null),
    enviarMensaje: (texto: string, preguntarSenior: boolean) =>
      enviarEvento('CHAT_MESSAGE', { texto, preguntar_senior: preguntarSenior }),
    decidirPropuesta: (mensajeId: number, aprobar: boolean) =>
      enviarEvento('AI_ACTION_DECISION', { mensaje_id: mensajeId, aprobar }),
    cambiarModo: (nuevo: ModoIA) => enviarEvento('SET_AI_MODE', { modo: nuevo }),
  }
}

export function etiquetaModo(modo: ModoIA): string {
  return { consultivo: 'Consultivo', con_confirmacion: 'Con confirmación', automatico: 'Automático' }[modo]
}
