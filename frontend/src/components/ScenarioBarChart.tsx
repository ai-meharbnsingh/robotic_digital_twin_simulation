interface BarValue {
  name: string
  value: number
  color: string
}

interface ScenarioBarChartProps {
  label: string
  values: BarValue[]
  unit?: string
}

/**
 * Pure SVG horizontal bar chart — no external charting libraries.
 * Dark-theme compatible with transparent background.
 */
export function ScenarioBarChart({ label, values, unit }: ScenarioBarChartProps) {
  const maxVal = Math.max(...values.map((v) => v.value), 1)
  const barHeight = 18
  const labelWidth = 100
  const valueWidth = 70
  const chartWidth = 220
  const totalWidth = labelWidth + chartWidth + valueWidth
  const totalHeight = values.length * (barHeight + 6) + 24

  return (
    <div>
      <div className="text-[10px] text-muted font-semibold mb-1">{label}</div>
      <svg
        width="100%"
        height={totalHeight}
        viewBox={`0 0 ${totalWidth} ${totalHeight}`}
        className="overflow-visible"
      >
        {values.map((v, i) => {
          const y = i * (barHeight + 6)
          const barW = Math.max((v.value / maxVal) * chartWidth, 2)
          return (
            <g key={v.name}>
              <text
                x={labelWidth - 6}
                y={y + barHeight / 2 + 1}
                textAnchor="end"
                dominantBaseline="middle"
                fill="#a6adc8"
                fontSize={10}
              >
                {v.name.length > 14 ? v.name.slice(0, 13) + '\u2026' : v.name}
              </text>
              <rect
                x={labelWidth}
                y={y}
                width={barW}
                height={barHeight}
                rx={3}
                fill={v.color}
                opacity={0.85}
              />
              <text
                x={labelWidth + barW + 6}
                y={y + barHeight / 2 + 1}
                dominantBaseline="middle"
                fill="#cdd6f4"
                fontSize={10}
                fontFamily="monospace"
              >
                {v.value.toFixed(1)}{unit ? ` ${unit}` : ''}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
