import type { FC } from 'react'

interface Props {
  data: number[]
  labels?: string[]
  height?: number
  color?: string
  highlightColor?: string
}

export const SVGSparkline: FC<Props> = ({
  data,
  labels,
  height = 64,
  color = 'var(--color-accent)',
  highlightColor = 'var(--color-highlight)',
}) => {
  const width = 280
  const barGap = 6
  const barWidth = (width - barGap * (data.length - 1)) / data.length
  const max = Math.max(...data, 1)
  const maxIdx = data.indexOf(Math.max(...data))

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      aria-hidden="true"
      style={{ overflow: 'visible' }}
    >
      {data.map((val, i) => {
        const barH = Math.max((val / max) * (height - 4), 3)
        const x = i * (barWidth + barGap)
        const y = height - barH
        const isHighlight = i === maxIdx

        return (
          <g key={i}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barH}
              rx={2}
              fill={isHighlight ? highlightColor : color}
              opacity={isHighlight ? 1 : 0.5}
            />
            {labels?.[i] && (
              <text
                x={x + barWidth / 2}
                y={height + 14}
                textAnchor="middle"
                fontSize="10"
                fill="var(--color-text-muted)"
                fontFamily="var(--font-ui)"
              >
                {labels[i]}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
