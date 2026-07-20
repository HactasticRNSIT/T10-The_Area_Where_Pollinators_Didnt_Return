import type { FC } from 'react'

type Status = 'loading' | 'online' | 'offline'

interface Props {
  status: Status
}

const labels: Record<Status, string> = {
  loading: 'Connecting',
  online: 'Connected',
  offline: 'Offline',
}

export const StatusPill: FC<Props> = ({ status }) => {
  return (
    <div className={`status-pill status-pill--${status}`}>
      <span className="status-pill__dot" />
      <span className="status-pill__label">{labels[status]}</span>
      <style>{`
        .status-pill {
          display: flex;
          align-items: center;
          gap: 7px;
          padding: 6px 10px;
          border-radius: 20px;
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          width: fit-content;
        }
        .status-pill__dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .status-pill__label {
          font-size: 12px;
          font-weight: 500;
          color: var(--color-text-muted);
          letter-spacing: 0.02em;
        }
        .status-pill--online .status-pill__dot {
          background: var(--color-highlight);
          box-shadow: 0 0 6px var(--color-highlight);
        }
        .status-pill--offline .status-pill__dot {
          background: var(--color-error);
        }
        .status-pill--loading .status-pill__dot {
          background: var(--color-text-muted);
          animation: pulse-dot 1.2s ease-in-out infinite;
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
