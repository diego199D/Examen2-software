/**
 * Marcadores SVG para los extremos de las relaciones UML.
 * Se referencian desde las aristas por id: `markerEnd: 'url(#uml-generalization)'`.
 * Los colores son literales: los atributos de presentación SVG dentro de <marker>
 * no resuelven `var(--token)` de forma fiable entre navegadores.
 */
const STROKE = '#4a5261' // --edge-stroke
const FILL_HOLLOW = '#ffffff' // --node-body-bg
const FILL_SOLID = '#33383f' // --node-header-bg

export function UmlMarkers() {
  return (
    <svg className="uml-markers" aria-hidden="true">
      <defs>
        {/* Generalización: triángulo hueco en el extremo destino (markerEnd) */}
        <marker
          id="uml-generalization"
          markerWidth="18"
          markerHeight="14"
          refX="16"
          refY="7"
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path
            d="M1 1 L16 7 L1 13 Z"
            fill={FILL_HOLLOW}
            stroke={STROKE}
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </marker>

        {/* Agregación: rombo hueco en el extremo del todo (markerStart) */}
        <marker
          id="uml-aggregation"
          markerWidth="24"
          markerHeight="14"
          refX="1"
          refY="7"
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path
            d="M1 7 L11 1 L21 7 L11 13 Z"
            fill={FILL_HOLLOW}
            stroke={STROKE}
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </marker>

        {/* Composición: rombo relleno en el extremo del todo (markerStart) */}
        <marker
          id="uml-composition"
          markerWidth="24"
          markerHeight="14"
          refX="1"
          refY="7"
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path
            d="M1 7 L11 1 L21 7 L11 13 Z"
            fill={FILL_SOLID}
            stroke={FILL_SOLID}
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </marker>
      </defs>
    </svg>
  )
}
