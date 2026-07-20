import type { FC } from 'react'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Map,
  BarChart2,
  GitCompare,
  MessageSquare,
} from 'lucide-react'
import { StatusPill } from './StatusPill'
import { useHealth } from '../hooks/useHealth'

export type ViewId = 'overview' | 'zones' | 'analyse' | 'compare' | 'chat'

interface NavItem {
  id: ViewId
  label: string
  icon: FC<{ size?: number; strokeWidth?: number; className?: string }>
}

const NAV: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'zones', label: 'Zones', icon: Map },
  { id: 'analyse', label: 'Analyse', icon: BarChart2 },
  { id: 'compare', label: 'Compare', icon: GitCompare },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
]

interface Props {
  active: ViewId
  onChange: (id: ViewId) => void
}

export const Sidebar: FC<Props> = ({ active, onChange }) => {
  const health = useHealth()

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar__wordmark">
          <span className="sidebar__wordmark-z">Z</span>onelytics
        </div>

        <nav className="sidebar__nav" aria-label="Main navigation">
          {NAV.map(({ id, label, icon: Icon }) => (
            <motion.button
              key={id}
              className={`sidebar__nav-item${active === id ? ' sidebar__nav-item--active' : ''}`}
              onClick={() => onChange(id)}
              aria-current={active === id ? 'page' : undefined}
              whileHover={{ scale: 1.02, backgroundColor: 'var(--color-card)' }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            >
              {active === id && (
                <motion.div
                  layoutId="sidebarActiveIndicator"
                  className="sidebar__active-indicator"
                  initial={false}
                  transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                />
              )}
              <Icon size={16} strokeWidth={1.8} className="sidebar__icon" />
              <span className="sidebar__label">{label}</span>
            </motion.button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <StatusPill status={health} />
        </div>
      </aside>

      {/* Mobile bottom tab bar */}
      <nav className="tab-bar" aria-label="Main navigation">
        {NAV.map(({ id, icon: Icon }) => (
          <button
            key={id}
            className={`tab-bar__item${active === id ? ' tab-bar__item--active' : ''}`}
            onClick={() => onChange(id)}
            aria-current={active === id ? 'page' : undefined}
            aria-label={id}
          >
            <Icon size={20} strokeWidth={1.8} />
          </button>
        ))}
      </nav>

      <style>{`
        .sidebar {
          width: var(--sidebar-width);
          min-width: var(--sidebar-width);
          height: 100%;
          background: var(--color-surface);
          border-right: 1px solid var(--color-border);
          display: flex;
          flex-direction: column;
          padding: 20px 0;
          flex-shrink: 0;
        }

        .sidebar__wordmark {
          font-size: 16px;
          font-weight: 700;
          letter-spacing: -0.02em;
          color: var(--color-text);
          padding: 0 20px 24px;
          border-bottom: 1px solid var(--color-border);
          margin-bottom: 12px;
        }

        .sidebar__wordmark-z {
          color: var(--color-accent);
        }

        .sidebar__nav {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 0 12px;
        }

        .sidebar__nav-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 12px;
          border-radius: var(--radius);
          font-size: 13.5px;
          font-weight: 500;
          color: var(--color-text-muted);
          position: relative;
          text-align: left;
          width: 100%;
          border: none;
          background: transparent;
        }

        .sidebar__nav-item:hover {
          color: var(--color-text);
        }

        .sidebar__nav-item--active {
          color: var(--color-text);
          background: var(--color-accent-dim) !important;
        }

        .sidebar__active-indicator {
          position: absolute;
          left: 0;
          top: 15%;
          height: 70%;
          width: 3px;
          background: var(--color-accent);
          border-radius: 0 3px 3px 0;
        }

        .sidebar__icon, .sidebar__label {
          position: relative;
          z-index: 1;
        }

        .sidebar__footer {
          padding: 16px 20px 4px;
          border-top: 1px solid var(--color-border);
        }

        /* Mobile tab bar */
        .tab-bar {
          display: none;
        }

        @media (max-width: 768px) {
          .sidebar {
            display: none;
          }

          .tab-bar {
            display: flex;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--color-surface);
            border-top: 1px solid var(--color-border);
            z-index: 100;
            padding-bottom: env(safe-area-inset-bottom, 0);
          }

          .tab-bar__item {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 14px 0;
            color: var(--color-text-muted);
            transition: color var(--transition-fast);
          }

          .tab-bar__item--active {
            color: var(--color-accent);
          }
        }
      `}</style>
    </>
  )
}
