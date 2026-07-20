import type { FC } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { AnalyseResponse } from '../api/client'
import { useReducedMotion } from '../hooks/useReducedMotion'

interface Props {
  result: AnalyseResponse | null
}

export const AnalysisResult: FC<Props> = ({ result }) => {
  const reduced = useReducedMotion()

  return (
    <AnimatePresence>
      {result && (
        <motion.div
          className="analysis-result"
          layout
          initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
        >
          <div className="analysis-result__inner">
            <div className="analysis-result__header">
              <span className="analysis-result__tag">Analysis Result</span>
              {result.timestamp && (
                <span className="analysis-result__timestamp">{result.timestamp}</span>
              )}
            </div>

            <div className="analysis-result__zone">
              Zone: <code>{result.zone_id}</code>
            </div>

            <div className="analysis-result__body">
              {result.summary}
            </div>

            {result.details && (
              <pre className="analysis-result__details">{result.details}</pre>
            )}
          </div>

          <style>{`
            .analysis-result {
              overflow: hidden;
            }

            .analysis-result__inner {
              background: var(--color-card);
              border: 1px solid var(--color-border-strong);
              border-radius: var(--radius);
              overflow: hidden;
              margin-top: 16px;
            }

            .analysis-result__header {
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 12px 16px;
              border-bottom: 1px solid var(--color-border);
              background: rgba(108,111,209,0.06);
            }

            .analysis-result__tag {
              font-size: 11px;
              font-weight: 600;
              text-transform: uppercase;
              letter-spacing: 0.08em;
              color: var(--color-accent);
            }

            .analysis-result__timestamp {
              font-family: var(--font-mono);
              font-size: 11px;
              color: var(--color-text-muted);
            }

            .analysis-result__zone {
              padding: 10px 16px;
              font-size: 12px;
              color: var(--color-text-muted);
              border-bottom: 1px solid var(--color-border);
            }

            .analysis-result__zone code {
              font-family: var(--font-mono);
              color: var(--color-highlight);
              font-size: 11px;
            }

            .analysis-result__body {
              padding: 16px;
              font-size: 13.5px;
              line-height: 1.7;
              color: var(--color-text);
              white-space: pre-wrap;
            }

            .analysis-result__details {
              font-family: var(--font-mono);
              font-size: 12px;
              line-height: 1.6;
              color: var(--color-text-muted);
              padding: 16px;
              border-top: 1px solid var(--color-border);
              overflow-x: auto;
              white-space: pre-wrap;
              word-break: break-all;
            }
          `}</style>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
