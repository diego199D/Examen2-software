import { createContext } from 'react'

import type { Desvio } from './useDiagrama'

/** `moverPuntoRelacion` de useDiagrama, para que RelacionEdge (que React Flow
 * renderiza por su cuenta, sin props nuestras más allá de `data`) pueda
 * confirmar el arrastre del punto de control de una línea. */
export type MoverPuntoRelacion = (id: string, desvio: Desvio | null, confirmar: boolean) => void

export const AccionesRelacionContext = createContext<MoverPuntoRelacion>(() => {})
