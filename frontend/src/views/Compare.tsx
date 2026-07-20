import { type FC, useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ResultSkeleton } from '../components/SkeletonLoader'
import { usePolyNexus } from '../hooks/usePolyNexus'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { postCompare, type CompareResult, ApiError, type Zone } from '../api/client'

const CompareSkeleton: FC = () => (
  <div className="compare__results-grid">
    {[0, 1].map(i => (
      <div key={i} className="compare-result-card">
        <ResultSkeleton />
      </div>
    ))}
    <style>{`
      .compare__results-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .compare-result-card { background: var(--color-card); border: 1px solid var(--color-border); border-radius: var(--radius); overflow: hidden; }
      @media (max-width: 640px) { .compare__results-grid { grid-template-columns: 1fr; } }
    `}</style>
  </div>
)

interface Props {
  polyNexus: ReturnType<typeof usePolyNexus>
}

export const Compare: FC<Props> = ({ polyNexus }) => {
  const { zones: rawZones, loading: zonesLoading } = polyNexus
  const [zoneA, setZoneA] = useState('')
  const [zoneB, setZoneB] = useState('')
  const [results, setResults] = useState<CompareResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const reduced = useReducedMotion()

  const zones: Zone[] = rawZones.map(z => ({
    zone_id: z.zone_id,
    name: z.name,
    lat: z.lat,
    lon: z.lon,
    status: 'active',
    description: ''
  }))

  useEffect(() => {
    if (zones.length >= 2 && !zoneA && !zoneB) {
      setZoneA(zones[0].zone_id)
      setZoneB(zones[1].zone_id)
    }
  }, [zones, zoneA, zoneB])

  useEffect(() => () => { abortRef.current?.abort() }, [])

  async function handleCompare() {
    if (!zoneA || !zoneB || loading) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setLoading(true)
    setError(null)
    setResults(null)

    try {
      const data = await postCompare(zoneA, zoneB, abortRef.current.signal)
      setResults(data)
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(err instanceof ApiError ? `Error ${err.status}: ${err.message}` : 'Comparison failed.')
      }
    } finally {
      setLoading(false)
    }
  }

  const resultForZone = (id: string) => results?.find(r => r.zone_id === id) ?? null
  const zoneNameFor = (id: string) => zones.find(z => z.zone_id === id)?.name ?? id

  return (
    <div className="compare">
      <motion.h1
        className="view-title"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        Compare
      </motion.h1>

      <motion.div
        className="compare__form"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, delay: 0.06 }}
      >
        <div className="compare__selectors">
          <div className="form-field">
            <label className="form-label" htmlFor="zone-a">Zone A</label>
            <select
              id="zone-a"
              className="form-select"
              value={zoneA}
              onChange={e => setZoneA(e.target.value)}
              disabled={zonesLoading}
            >
              <option value="">Select zone…</option>
              {zones.map(z => (
                <option key={z.zone_id} value={z.zone_id} disabled={z.zone_id === zoneB}>
                  {z.name}
                </option>
              ))}
            </select>
          </div>

          <div className="compare__vs">vs</div>

          <div className="form-field">
            <label className="form-label" htmlFor="zone-b">Zone B</label>
            <select
              id="zone-b"
              className="form-select"
              value={zoneB}
              onChange={e => setZoneB(e.target.value)}
              disabled={zonesLoading}
            >
              <option value="">Select zone…</option>
              {zones.map(z => (
                <option key={z.zone_id} value={z.zone_id} disabled={z.zone_id === zoneA}>
                  {z.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <button
          className="btn-primary"
          onClick={handleCompare}
          disabled={!zoneA || !zoneB || zoneA === zoneB || loading || zonesLoading}
        >
          {loading ? 'Comparing…' : 'Run Comparison'}
        </button>
      </motion.div>

      {loading && <CompareSkeleton />}

      <AnimatePresence>
        {results && (
          <motion.div
            className="compare__results-grid"
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.24 }}
          >
            {[zoneA, zoneB].map((id) => {
              const r = resultForZone(id)
              return (
                <div key={id} className={`compare-card${r?.error ? ' compare-card--error' : ''}`}>
                  <div className="compare-card__header">
                    <span className="compare-card__zone-name">{zoneNameFor(id)}</span>
                    <code className="compare-card__zone-id">{id}</code>
                  </div>
                  <div className="compare-card__body">
                    {r?.error ? (
                      <span className="compare-card__error">{r.error}</span>
                    ) : r?.summary ? (
                      <p>{r.summary}</p>
                    ) : (
                      <span className="compare-card__empty">No data returned</span>
                    )}
                    {r?.details && <pre className="compare-card__details">{r.details}</pre>}
                  </div>
                </div>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        .compare { display: flex; flex-direction: column; gap: 20px; }
        .compare__form {
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          border-radius: var(--radius);
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .compare__selectors {
          display: grid;
          grid-template-columns: 1fr auto 1fr;
          align-items: end;
          gap: 12px;
        }
        .compare__vs {
          font-size: 12px;
          font-weight: 700;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          padding-bottom: 10px;
          text-align: center;
        }
        .compare__results-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .compare-card {
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          border-radius: var(--radius);
          overflow: hidden;
        }
        .compare-card--error { border-color: rgba(255,107,107,0.3); }
        .compare-card__header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          border-bottom: 1px solid var(--color-border);
          background: rgba(255,255,255,0.02);
        }
        .compare-card__zone-name {
          font-size: 13px;
          font-weight: 600;
          color: var(--color-text);
        }
        .compare-card__zone-id {
          font-family: var(--font-mono);
          font-size: 10px;
          color: var(--color-accent);
        }
        .compare-card__body {
          padding: 16px;
          font-size: 13.5px;
          line-height: 1.7;
          color: var(--color-text);
        }
        .compare-card__error { color: var(--color-error); }
        .compare-card__empty { color: var(--color-text-muted); font-style: italic; }
        .compare-card__details {
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--color-text-muted);
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--color-border);
          white-space: pre-wrap;
          word-break: break-all;
          overflow-x: auto;
        }
        @media (max-width: 640px) {
          .compare__results-grid { grid-template-columns: 1fr; }
          .compare__selectors { grid-template-columns: 1fr; }
          .compare__vs { padding-bottom: 0; }
        }
      `}</style>
    </div>
  )
}
