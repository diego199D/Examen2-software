import { useCallback, useEffect, useRef, useState } from 'react'

import { interpretarComandoVoz } from '../../api/comandosVoz'
import { getApiErrorMessage } from '../../api/errors'
import { aplicarAccionVoz } from './aplicarAccionVoz'
import type { useDiagrama } from './useDiagrama'

/**
 * CU11 — tipos mínimos de la Web Speech API (no vienen en el lib.dom.d.ts de
 * TypeScript). Solo se declara lo que se usa acá.
 */
interface SpeechRecognitionResultado {
  transcript: string
}
interface SpeechRecognitionListaAlternativas {
  isFinal: boolean
  [index: number]: SpeechRecognitionResultado
}
interface SpeechRecognitionEvento extends Event {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionListaAlternativas }
}
interface SpeechRecognitionErrorEvento extends Event {
  error: string
}
interface SpeechRecognitionInstancia extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((ev: SpeechRecognitionEvento) => void) | null
  onerror: ((ev: SpeechRecognitionErrorEvento) => void) | null
  onend: (() => void) | null
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionInstancia

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

const MENSAJES_ERROR_RECONOCIMIENTO: Record<string, string> = {
  'not-allowed': 'Se necesita permiso de micrófono para usar comandos de voz.',
  'service-not-allowed': 'Se necesita permiso de micrófono para usar comandos de voz.',
  'no-speech': 'No se detectó voz. Intenta de nuevo.',
  'audio-capture': 'No se encontró un micrófono disponible.',
  network: 'Se perdió la conexión con el servicio de reconocimiento de voz.',
}

/** Errores que el auto-reinicio ya cubre: el navegador corta la sesión tras
 * un silencio largo aun en modo continuo, pero la escucha tiene que seguir
 * hasta que la usuaria presione stop. */
const ERRORES_RECUPERABLES = new Set(['no-speech', 'aborted'])

function unirTexto(...partes: string[]): string {
  return partes.map((p) => p.trim()).filter(Boolean).join(' ')
}

function obtenerConstructorReconocimiento(): SpeechRecognitionConstructor | undefined {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition
}

/** Frase corta hablada, best-effort: nunca debe romper el flujo si el
 * navegador no soporta síntesis de voz o no tiene voces instaladas. */
function hablar(mensaje: string): void {
  try {
    if (!window.speechSynthesis) return
    const utterance = new SpeechSynthesisUtterance(mensaje)
    utterance.lang = 'es-419'
    window.speechSynthesis.speak(utterance)
  } catch {
    // best-effort, sin fallback
  }
}

type Diagrama = ReturnType<typeof useDiagrama>

export function useComandoVoz(proyectoId: number, diagrama: Diagrama) {
  const [escuchando, setEscuchando] = useState(false)
  const [procesando, setProcesando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mensajeConfirmacion, setMensajeConfirmacion] = useState<string | null>(null)
  // Espejo siempre-actualizado de `diagrama`, para que `aplicarAccion` (que
  // se dispara desde el callback async de la API) lea el estado más
  // reciente -- mismo patrón que nodesRef/edgesRef en useDiagrama.ts.
  const diagramaRef = useRef(diagrama)
  useEffect(() => {
    diagramaRef.current = diagrama
  }, [diagrama])

  const soportado = obtenerConstructorReconocimiento() !== undefined

  // Las advertencias (lo que se descartó o ajustó) solo se muestran; en voz
  // alta se dice el resumen.
  const confirmarAccion = useCallback((mensaje: string, advertencias: string[] = []) => {
    setMensajeConfirmacion([mensaje, ...advertencias].join(' '))
    hablar(mensaje)
  }, [])

  const aplicarAccion = useCallback((texto: string) => {
    setProcesando(true)
    setError(null)
    interpretarComandoVoz(proyectoId, texto)
      .then((resultado) => {
        aplicarAccionVoz(resultado, diagramaRef.current)
        confirmarAccion(resultado.resumen, resultado.accion === 'modificar_diagrama' ? resultado.advertencias : [])
      })
      .catch((err) => {
        setError(getApiErrorMessage(err, 'No se pudo interpretar el comando de voz'))
      })
      .finally(() => setProcesando(false))
  }, [proyectoId, confirmarAccion])

  // La escucha es continua hasta que la usuaria presiona stop: el navegador
  // puede terminar una sesión por su cuenta (silencio largo, red), así que
  // cada sesión que termina sola se reinicia sobre una instancia nueva y lo
  // ya confirmado se guarda en `textoAcumuladoRef` para no perderlo.
  const reconocimientoRef = useRef<SpeechRecognitionInstancia | null>(null)
  const detenidoPorUsuarioRef = useRef(false)
  const textoAcumuladoRef = useRef('')
  const [transcripcionParcial, setTranscripcionParcial] = useState('')

  const iniciarSesion = useCallback(
    function iniciarSesion(Constructor: SpeechRecognitionConstructor) {
      const reconocimiento = new Constructor()
      reconocimiento.lang = 'es-419'
      reconocimiento.continuous = true
      reconocimiento.interimResults = true
      reconocimiento.maxAlternatives = 1

      // Finales confirmados dentro de ESTA sesión del navegador (sus
      // `results` arrancan de cero en cada reinicio).
      let finalesSesion = ''
      let errorFatal = false

      reconocimiento.onresult = (ev) => {
        let finales = ''
        let parciales = ''
        for (let i = 0; i < ev.results.length; i++) {
          const resultado = ev.results[i]
          const texto = resultado[0]?.transcript ?? ''
          if (resultado.isFinal) finales = unirTexto(finales, texto)
          else parciales = unirTexto(parciales, texto)
        }
        finalesSesion = finales
        setTranscripcionParcial(unirTexto(textoAcumuladoRef.current, finales, parciales))
      }
      reconocimiento.onerror = (ev) => {
        if (ERRORES_RECUPERABLES.has(ev.error)) return
        errorFatal = true
        setError(MENSAJES_ERROR_RECONOCIMIENTO[ev.error] ?? 'No se pudo escuchar, intenta de nuevo.')
      }
      reconocimiento.onend = () => {
        if (reconocimientoRef.current !== reconocimiento) return
        textoAcumuladoRef.current = unirTexto(textoAcumuladoRef.current, finalesSesion)

        if (!detenidoPorUsuarioRef.current && !errorFatal) {
          iniciarSesion(Constructor)
          return
        }

        reconocimientoRef.current = null
        setEscuchando(false)
        setTranscripcionParcial('')
        if (errorFatal) return
        const texto = textoAcumuladoRef.current
        if (texto) aplicarAccion(texto)
        else setError(MENSAJES_ERROR_RECONOCIMIENTO['no-speech'])
      }

      reconocimientoRef.current = reconocimiento
      try {
        reconocimiento.start()
      } catch {
        reconocimientoRef.current = null
        setEscuchando(false)
        setError('No se pudo iniciar el micrófono, intenta de nuevo.')
      }
    },
    [aplicarAccion],
  )

  const iniciarEscucha = useCallback(() => {
    const Constructor = obtenerConstructorReconocimiento()
    if (!Constructor) {
      setError('Tu navegador no soporta reconocimiento de voz.')
      return
    }
    setError(null)
    setMensajeConfirmacion(null)
    detenidoPorUsuarioRef.current = false
    textoAcumuladoRef.current = ''
    setTranscripcionParcial('')
    setEscuchando(true)
    iniciarSesion(Constructor)
  }, [iniciarSesion])

  /** `stop()` y no `abort()`: así el navegador entrega el último resultado
   * pendiente antes del `onend` que arma y envía el comando completo. */
  const detenerEscucha = useCallback(() => {
    detenidoPorUsuarioRef.current = true
    reconocimientoRef.current?.stop()
  }, [])

  const alternarEscucha = useCallback(() => {
    if (reconocimientoRef.current) detenerEscucha()
    else iniciarEscucha()
  }, [detenerEscucha, iniciarEscucha])

  // Al salir del editor se corta la escucha sin enviar nada.
  useEffect(() => {
    return () => {
      const reconocimiento = reconocimientoRef.current
      reconocimientoRef.current = null
      reconocimiento?.abort()
    }
  }, [])

  return {
    soportado,
    escuchando,
    procesando,
    error,
    mensajeConfirmacion,
    transcripcionParcial,
    iniciarEscucha,
    detenerEscucha,
    alternarEscucha,
    cerrarError: () => setError(null),
    cerrarConfirmacion: () => setMensajeConfirmacion(null),
  }
}
