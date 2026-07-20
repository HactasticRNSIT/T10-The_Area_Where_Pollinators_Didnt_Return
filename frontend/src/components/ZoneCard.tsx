import type { FC } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Zone } from '../api/client'
import { useReducedMotion } from '../hooks/useReducedMotion'

interface Props {
  zone: Zone
  isSelected: boolean
  onSelect: (id: string) => void
}

export const ZoneCard: FC<Props> = ({ zone, isSelected, onSelect }) => {
  const reduced = useReducedMotion()

  return (
    <motion.button
      layout
      className={`zone-card${isSelected ? ' zone-card--selected' : ''}`}
      onClick={() => onSelect(zone.zone_id)}
      aria-pressed={isSelected}
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
    >
      {/* Pulse ring — only on selected, only if motion is ok */}
      <AnimatePresence>
        {isSelected && !reduced && (
          <motion.span
            className="zone-card__pulse"
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{
              opacity: [0, 0.5, 0],
              scale: [0.88, 1.08, 0.88],
            }}
            exit={{ opacity: 0 }}
            transition={{
              duration: 2.4,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />
        )}
      </AnimatePresence>

      <div className="zone-card__header">
        <span className="zone-card__id">{zone.zone_id}</span>
        <span className={`zone-card__badge zone-card__badge--${zone.status}`}>
          {zone.status}
        </span>
      </div>

      <p className="zone-card__name">{zone.name}</p>

      {zone.description && (
        <p className="zone-card__desc">{zone.description}</p>
      )}

      <div className="zone-card__meta">
        <span>{zone.lat.toFixed(4)}°</span>
        <span className="zone-card__meta-sep">·</span>
        <span>{zone.lon.toFixed(4)}°</span>
      </div>

      <style>{`
        .zone-card {
          position: relative;
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          border-radius: var(--radius);
          padding: 16px;
          text-align: left;
          width: 100%;
          cursor: pointer;
          transition: border-color var(--transition-fast), background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
          overflow: hidden;
        }

        .zone-card:hover {
          background: var(--color-card-hover);
          border-color: rgba(255,255,255,0.18);
          transform: translateY(-1px);
          box-shadow: var(--shadow-card);
        }

        .zone-card--selected {
          border-color: var(--color-accent);
          background: var(--color-accent-dim);
        }

        .zone-card__pulse {
          position: absolute;
          inset: -1px;
          border-radius: var(--radius);
          border: 2px solid var(--color-accent);
          pointer-events: none;
        }

        .zone-card__header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 6px;
        }

        .zone-card__id {
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--color-text-muted);
          letter-spacing: 0.05em;
        }

        .zone-card__badge {
          font-size: 10px;
          font-weight: 600;
          padding: 2px 7px;
          border-radius: 20px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }

        .zone-card__badge--active {
          background: var(--color-highlight-dim);
          color: var(--color-highlight);
          border: 1px solid rgba(61,255,192,0.25);
        }

        .zone-card__badge--inactive {
          background: rgba(255,255,255,0.05);
          color: var(--color-text-muted);
          border: 1px solid var(--color-border-strong);
        }

        .zone-card__name {
          font-size: 14px;
          font-weight: 600;
          color: var(--color-text);
          margin-bottom: 4px;
        }

        .zone-card__desc {
          font-size: 12px;
          color: var(--color-text-muted);
          line-height: 1.5;
          margin-bottom: 10px;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .zone-card__meta {
          display: flex;
          align-items: center;
          gap: 4px;
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--color-text-muted);
          margin-top: 10px;
        }

        .zone-card__meta-sep {
          color: var(--color-border-strong);
        }
      `}</style>
    </motion.button>
  )
}
