import { useCallback, useEffect, useRef, useState } from 'react'

import { conversarConAgente } from '../../api/agente'
import { getApiErrorMessage } from '../../api/errors'
import type { MensajeChat } from '../../api/types'
import { aplicarAccionVoz } from './aplicarAccionVoz'
import type { useDiagrama } from './useDiagrama'

type Diagrama = ReturnType<typeof useDiagrama>

// Cuántos turnos previos se mandan a la API en cada mensaje nuevo -- el
// panel sigue mostrando el historial completo, esto solo acota lo que viaja
// por red/tokens en cada turno.
const MAX_HISTORIAL_ENVIADO = 12

function nuevoId(): string {
  return crypto.randomUUID()
}

export function useAgente(proyectoId: number, diagrama: Diagrama) {
  const [mensajes, setMensajes] = useState<MensajeChat[]>([])
  const [enviando, setEnviando] = useState(false)
  const [abierto, setAbierto] = useState(false)

  // Mismo patrón que useComandoVoz.ts: espejo siempre-actualizado para que
  // el callback async de la API lea el estado más reciente sin necesidad de
  // recrear `enviarMensaje` en cada render.
  const diagramaRef = useRef(diagrama)
  useEffect(() => {
    diagramaRef.current = diagrama
  }, [diagrama])
  const mensajesRef = useRef(mensajes)
  useEffect(() => {
    mensajesRef.current = mensajes
  }, [mensajes])

  const enviarMensaje = useCallback(
    (texto: string) => {
      const textoLimpio = texto.trim()
      if (!textoLimpio || enviando) return

      const mensajeUsuario: MensajeChat = { id: nuevoId(), rol: 'usuario', texto: textoLimpio }
      const historialParaEnviar = mensajesRef.current
        .slice(-MAX_HISTORIAL_ENVIADO)
        .map((m) => ({ rol: m.rol, texto: m.texto }))

      setMensajes((actuales) => [...actuales, mensajeUsuario])
      setEnviando(true)

      conversarConAgente(proyectoId, textoLimpio, historialParaEnviar)
        .then((respuesta) => {
          if (respuesta.accion) aplicarAccionVoz(respuesta.accion, diagramaRef.current)
          setMensajes((actuales) => [
            ...actuales,
            { id: nuevoId(), rol: 'agente', texto: respuesta.texto, accion: respuesta.accion },
          ])
        })
        .catch((err) => {
          setMensajes((actuales) => [
            ...actuales,
            {
              id: nuevoId(),
              rol: 'agente',
              texto: getApiErrorMessage(err, 'El agente no está disponible en este momento.'),
              esError: true,
            },
          ])
        })
        .finally(() => setEnviando(false))
    },
    [proyectoId, enviando],
  )

  return {
    mensajes,
    enviando,
    abierto,
    toggleAbierto: () => setAbierto((v) => !v),
    enviarMensaje,
  }
}
