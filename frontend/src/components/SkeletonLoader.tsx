import type { FC, CSSProperties } from 'react'

interface SkeletonProps {
  width?: string
  height?: string
  borderRadius?: string
  style?: CSSProperties
}

export const Skeleton: FC<SkeletonProps> = ({
  width = '100%',
  height = '16px',
  borderRadius = 'var(--radius)',
  style,
}) => (
  <>
    <div className="skeleton" style={{ width, height, borderRadius, ...style }} />
    <style>{`
      .skeleton {
        background: linear-gradient(
          90deg,
          var(--color-card) 25%,
          var(--color-card-hover) 50%,
          var(--color-card) 75%
        );
        background-size: 200% 100%;
        animation: shimmer 1.6s infinite;
        flex-shrink: 0;
      }
      @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
    `}</style>
  </>
)

export const CardSkeleton: FC = () => (
  <div className="card-skeleton">
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
      <Skeleton width="80px" height="11px" />
      <Skeleton width="48px" height="18px" borderRadius="20px" />
    </div>
    <Skeleton height="16px" style={{ marginBottom: '6px' }} />
    <Skeleton width="70%" height="12px" style={{ marginBottom: '12px' }} />
    <Skeleton width="120px" height="11px" />
    <style>{`
      .card-skeleton {
        background: var(--color-card);
        border: 1px solid var(--color-border);
        border-radius: var(--radius);
        padding: 16px;
      }
    `}</style>
  </div>
)

export const ResultSkeleton: FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px' }}>
    <Skeleton height="14px" />
    <Skeleton height="14px" width="90%" />
    <Skeleton height="14px" width="95%" />
    <Skeleton height="14px" width="80%" />
    <Skeleton height="14px" width="88%" />
  </div>
)
