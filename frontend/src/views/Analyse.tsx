import { type FC, useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { AnalysisResult } from '../components/AnalysisResult'
import { ResultSkeleton } from '../components/SkeletonLoader'
import { usePolyNexus } from '../hooks/usePolyNexus'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { postAnalyse, type AnalyseResponse, ApiError, type Zone } from '../api/client'

const AnalyseSkeleton: FC = () => (
  <div style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', overflow: 'hidden', marginTop: '16px' }}>
    <ResultSkeleton />
  </div>
)

interface Props {
  polyNexus: ReturnType<typeof usePolyNexus>
}

export const Analyse: FC<Props> = ({ polyNexus }) => {
  const { zones: rawZones, activeZoneId: selectedId, runAnalysis, loading: zonesLoading } = polyNexus
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<AnalyseResponse | null>(null)
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

  const selectedZone = zones.find(z => z.zone_id === selectedId) ?? null

  const selectZone = (id: string) => {
    const matched = zones.find(z => z.zone_id === id)
    if (matched) {
      runAnalysis(matched.zone_id, matched.lat, matched.lon, matched.name)
    }
  }

  useEffect(() => () => { abortRef.current?.abort() }, [])

  async function handleSubmit() {
    if (!selectedId || !prompt.trim() || loading) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const data = await postAnalyse(
        selectedId,
        prompt.trim(),
        selectedZone?.lat,
        selectedZone?.lon,
        abortRef.current.signal
      )
      setResult(data)
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(err instanceof ApiError ? `Error ${err.status}: ${err.message}` : 'Analysis failed. Check backend connection.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="analyse">
      <motion.h1
        className="view-title"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        Analyse
      </motion.h1>

      <motion.div
        className="analyse__form"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, delay: 0.06 }}
      >
        <div className="form-field">
          <label className="form-label" htmlFor="analyse-zone">Zone</label>
          {zonesLoading ? (
            <div style={{ height: '38px', background: 'var(--color-card)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }} />
          ) : (
            <select
              id="analyse-zone"
              className="form-select"
              value={selectedId ?? ''}
              onChange={e => selectZone(e.target.value)}
              disabled={zones.length === 0}
            >
              {zones.length === 0 && <option value="">No zones available</option>}
              {zones.map(z => (
                <option key={z.zone_id} value={z.zone_id}>
                  {z.name} ({z.zone_id})
                </option>
              ))}
            </select>
          )}
          {selectedZone && (
            <div className="form-hint">
              {selectedZone.lat.toFixed(4)}°, {selectedZone.lon.toFixed(4)}°
            </div>
          )}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="analyse-prompt">Prompt</label>
          <textarea
            id="analyse-prompt"
            className="form-textarea"
            rows={4}
            placeholder="Describe what you want to analyse about this zone…"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
            }}
          />
          <div className="form-hint">⌘ + Enter to submit</div>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <button
          className="btn-primary"
          onClick={handleSubmit}
          disabled={!selectedId || !prompt.trim() || loading || zonesLoading}
        >
          {loading ? 'Analysing…' : 'Run Analysis'}
        </button>
      </motion.div>

      {loading && <AnalyseSkeleton />}
      <AnalysisResult result={result} />

      <style>{`
        .analyse { display: flex; flex-direction: column; gap: 8px; }
        .analyse__form {
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          border-radius: var(--radius);
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .form-field { display: flex; flex-direction: column; gap: 6px; }
        .form-label {
          font-size: 12px;
          font-weight: 600;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .form-select, .form-textarea {
          padding: 9px 12px;
          width: 100%;
          resize: vertical;
        }
        .form-hint {
          font-size: 11px;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .btn-primary {
          padding: 10px 20px;
          background: var(--color-accent);
          color: #fff;
          border-radius: var(--radius);
          font-size: 13.5px;
          font-weight: 600;
          transition: opacity var(--transition-fast), transform var(--transition-fast);
          align-self: flex-start;
        }
        .btn-primary:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
        .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
      `}</style>
    </div>
  )
}
