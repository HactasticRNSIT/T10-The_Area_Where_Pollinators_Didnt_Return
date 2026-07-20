/**
 * OfflineBanner.tsx
 *
 * Displays an unobtrusive banner when the browser goes offline, and shows
 * the "last updated" timestamp for cached zone data so farmers know when
 * the displayed data was last fetched from the server.
 *
 * Usage:
 *   <OfflineBanner lastUpdatedAt={result?.analysed_at} />
 *
 * The banner is purely informational — it never blocks interaction.
 */

import { useEffect, useState } from 'react';

interface OfflineBannerProps {
  /** ISO-8601 timestamp from the /analyse response `analysed_at` field. */
  lastUpdatedAt?: string;
}

function formatRelative(isoTs: string): string {
  const ms = Date.now() - new Date(isoTs).getTime();
  const minutes = Math.floor(ms / 60_000);
  const hours = Math.floor(ms / 3_600_000);
  const days = Math.floor(ms / 86_400_000);

  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

export function OfflineBanner({ lastUpdatedAt }: OfflineBannerProps) {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const online  = () => setIsOffline(false);
    const offline = () => setIsOffline(true);
    window.addEventListener('online',  online);
    window.addEventListener('offline', offline);

    // Refresh the "X minutes ago" label every 60 seconds while offline.
    const timer = setInterval(() => {
      if (!navigator.onLine) setTick(t => t + 1);
    }, 60_000);

    return () => {
      window.removeEventListener('online',  online);
      window.removeEventListener('offline', offline);
      clearInterval(timer);
    };
  }, []);

  // Only render when offline (or when we have stale-cache data to surface).
  if (!isOffline && !lastUpdatedAt) return null;

  const relativeTime = lastUpdatedAt ? formatRelative(lastUpdatedAt) : null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        bottom: '1rem',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.5rem 1rem',
        borderRadius: '0.5rem',
        fontSize: '0.8125rem',
        fontWeight: 500,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
        background: isOffline
          ? 'rgba(239, 68, 68, 0.85)'
          : 'rgba(30, 41, 59, 0.80)',
        color: '#f1f5f9',
        transition: 'background 0.3s ease',
        pointerEvents: 'none',      // never blocks clicks
        userSelect: 'none',
      }}
    >
      {/* Status dot */}
      <span
        style={{
          width: '0.5rem',
          height: '0.5rem',
          borderRadius: '50%',
          background: isOffline ? '#fca5a5' : '#86efac',
          flexShrink: 0,
        }}
      />

      {isOffline ? (
        <>
          <span>Offline</span>
          {relativeTime && (
            <span style={{ opacity: 0.8 }}>
              &nbsp;— showing data from {relativeTime}
            </span>
          )}
        </>
      ) : (
        relativeTime && (
          <span style={{ opacity: 0.8 }}>Last updated {relativeTime}</span>
        )
      )}

      {/* Suppress lint warning for tick dependency — used only to trigger re-render */}
      <span style={{ display: 'none' }} aria-hidden>{tick}</span>
    </div>
  );
}
