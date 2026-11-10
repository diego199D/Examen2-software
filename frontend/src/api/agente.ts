import { api } from './client'
import type { AgenteRespuesta, RolMensajeChat } from './types'

/**
 * CU13 — conversa con el agente integrado. `historial` va sin persistir
 * (vive en el estado de React del panel, ver `useAgente.ts`) y se manda
 * completo en cada turno para que el LLM tenga memoria de la conversación.
 */
export async function conversarConAgente(
  proyectoId: number,
  mensaje: string,
  historial: { rol: RolMensajeChat; texto: string }[],
): Promise<AgenteRespuesta> {
  const { data } = await api.post<AgenteRespuesta>(`/proyectos/${proyectoId}/agente`, { mensaje, historial })
  return data
}
