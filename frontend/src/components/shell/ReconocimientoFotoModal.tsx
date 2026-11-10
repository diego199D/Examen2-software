import { useEffect, useState } from 'react'

import { confirmarReconocimientoFoto, reconocerDiagramaFoto } from '../../api/reconocimientoFoto'
import type { ReconocimientoFotoResultado } from '../../api/reconocimientoFoto'
import { getApiErrorMessage } from '../../api/errors'
import type { DiagramaData } from '../../api/types'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

type Props = {
  proyectoId: number
  archivo: File
  onClose: () => void
  onAplicado: (datos: DiagramaData) => void
}

const ETIQUETA_TIPO: Record<string, string> = {
  ASOCIACION: 'asociación',
  HERENCIA: 'herencia',
  AGREGACION: 'agregación',
  COMPOSICION: 'composición',
}

/**
 * CU12 — reconocimiento de diagrama por fotografía. Al montarse, sube la
 * imagen y muestra el resultado como VISTA PREVIA (nunca se toca el
 * diagrama real hasta que el usuario confirma) -- "Aplicar al diagrama"
 * llama a `/confirmar` y recién ahí `onAplicado` refresca el lienzo (mismo
 * patrón que ya usa CU09 con `diagrama.importarDiagrama` para XMI).
 */
export function ReconocimientoFotoModal({ proyectoId, archivo, onClose, onAplicado }: Props) {
  const [analizando, setAnalizando] = useState(true)
  const [resultado, setResultado] = useState<ReconocimientoFotoResultado | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aplicando, setAplicando] = useState(false)

  useEffect(() => {
    // El modal se monta una vez por archivo elegido (Toolbar lo desmonta al
    // cerrar) -- el estado inicial de `analizando`/`error` ya cubre el caso
    // normal, no hace falta resetearlos acá.
    let vivo = true
    reconocerDiagramaFoto(proyectoId, archivo)
      .then((datos) => {
        if (!vivo) return
        setResultado(datos)
      })
      .catch((err) => {
        if (!vivo) return
        setError(getApiErrorMessage(err, 'No se pudo interpretar la imagen'))
      })
      .finally(() => {
        if (vivo) setAnalizando(false)
      })
    return () => {
      vivo = false
    }
  }, [proyectoId, archivo])

  const handleAplicar = async () => {
    if (!resultado) return
    setAplicando(true)
    setError(null)
    try {
      const datos = await confirmarReconocimientoFoto(proyectoId, resultado)
      onAplicado(datos.diagrama)
      onClose()
    } catch (err) {
      setError(getApiErrorMessage(err, 'No se pudo aplicar el reconocimiento al diagrama'))
    } finally {
      setAplicando(false)
    }
  }

  return (
    <Modal
      title="Reconocer diagrama desde foto"
      onClose={onClose}
      footer={
        resultado ? (
          <>
            <Button onClick={onClose} disabled={aplicando}>
              Cancelar
            </Button>
            <Button variant="primary" loading={aplicando} onClick={handleAplicar}>
              Aplicar al diagrama
            </Button>
          </>
        ) : (
          <Button onClick={onClose} disabled={analizando}>
            Cerrar
          </Button>
        )
      }
    >
      {analizando && <p className="reconocimiento-preview__estado">Analizando imagen… puede tardar unos segundos.</p>}
      {error && <Banner>{error}</Banner>}

      {resultado && (
        <div className="reconocimiento-preview">
          <p className="reconocimiento-preview__resumen">{resultado.mensaje}</p>

          {resultado.advertencias && resultado.advertencias.length > 0 && (
            <ul className="reconocimiento-preview__advertencias">
              {resultado.advertencias.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          )}

          <div className="reconocimiento-preview__lista">
            {resultado.clases.map((clase, i) => (
              <div className="reconocimiento-preview__clase" key={i}>
                <strong>{clase.nombre}</strong>
                {clase.atributos.length > 0 && (
                  <ul>
                    {clase.atributos.map((a, j) => (
                      <li key={j}>
                        {a.nombre}
                        {a.tipo ? `: ${a.tipo}` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          {resultado.relaciones.length > 0 && (
            <div className="reconocimiento-preview__relaciones">
              <strong>Relaciones detectadas</strong>
              <ul>
                {resultado.relaciones.map((r, i) => (
                  <li key={i}>
                    {r.clase_origen} → {r.clase_destino}
                    {r.etiqueta ? ` "${r.etiqueta}"` : ''} ({ETIQUETA_TIPO[r.tipo] ?? r.tipo.toLowerCase()}
                    {r.multiplicidad_origen || r.multiplicidad_destino
                      ? `, ${r.multiplicidad_origen ?? '?'} - ${r.multiplicidad_destino ?? '?'}`
                      : ''}
                    )
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
