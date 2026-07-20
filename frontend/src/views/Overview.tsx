import type { FC } from 'react'
import { motion } from 'framer-motion'
import { usePolyNexus, FACTOR_META } from '../hooks/usePolyNexus'
import { 
  ScoreDisplay, 
  StressInsights, 
  CropRiskCards, 
  WindStressIndicator, 
  PhenologyCalendar, 
  InterventionPlan, 
  HivePlacementCard 
} from '../components/RoadmapWidgets'

interface Props {
  polyNexus: ReturnType<typeof usePolyNexus>
}

export const Overview: FC<Props> = ({ polyNexus }) => {
  const { analysis, loading, zones } = polyNexus

  if (loading) {
    const activeZone = zones.find(z => z.zone_id === polyNexus.activeZoneId)
    return (
      <div className="overview-loading-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="loading-panel glass-panel" style={{ width: '100%', maxWidth: '480px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', padding: '40px', background: 'var(--color-card)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', textAlign: 'center' }}>
          <div className="orbital-loader" style={{ position: 'relative', width: '90px', height: '90px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="orbital-ring ring-1" style={{ position: 'absolute', width: '100%', height: '100%', borderRadius: '50%', border: '2px solid transparent', borderTopColor: 'var(--color-accent)', animation: 'spin-cw 2s linear infinite' }} />
            <div className="orbital-ring ring-2" style={{ position: 'absolute', width: '80%', height: '80%', borderRadius: '50%', border: '2px solid transparent', borderTopColor: 'var(--color-highlight)', animation: 'spin-ccw 1.5s linear infinite' }} />
            <div className="orbital-core" style={{ fontSize: '24px' }}>🐝</div>
          </div>
          <div className="loader-text" style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text)' }}>Analysing ecosystem data...</div>
          <div className="loader-subtext" style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
            Fetching live satellite and climate signals for {activeZone?.name || 'zone'}...
          </div>
        </div>
        <style>{`
          @keyframes spin-cw {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
          @keyframes spin-ccw {
            from { transform: rotate(0deg); }
            to { transform: rotate(-360deg); }
          }
        `}</style>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="overview-empty-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="empty-state glass-panel" style={{ padding: '40px', textAlign: 'center', background: 'var(--color-card)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', color: 'var(--color-text-muted)', maxWidth: '400px' }}>
          <p style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 500 }}>No zone selected for analysis</p>
          <p style={{ margin: 0, fontSize: '13px', lineHeight: 1.5 }}>
            Please select a preset zone from the <strong>Zones</strong> page or search for an Indian region at the top of the screen.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="overview">
      <motion.div
        className="dashboard-bento-layout"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        {/* 1. Hero KPI Card */}
        <div className="hero-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '24px 32px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(15, 23, 42, 0.8))', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)', position: 'relative', overflow: 'hidden' }}>
          <div className="hero-info" style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
            <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Selected Zone</span>
            <h2 style={{ fontSize: '24px', fontWeight: 800, margin: '6px 0', letterSpacing: '-0.5px', color: 'var(--color-text)' }}>
              {analysis.displayName || analysis.zone_id}
            </h2>
            <p className="hero-meta" style={{ fontSize: '12px', color: 'var(--color-text-muted)', margin: '0 0 16px 0', fontFamily: 'var(--font-mono)' }}>
              {analysis.latitude.toFixed(4)}°N, {analysis.longitude.toFixed(4)}°E
            </p>
            
            <div className="hero-kpis" style={{ display: 'flex', flexWrap: 'wrap', gap: '20px' }}>
              <div className="kpi-item" style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '110px' }}>
                <span className="kpi-label" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>Stress Index</span>
                <strong className="kpi-value" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--color-highlight)', textShadow: '0 0 15px rgba(20, 184, 166, 0.25)' }}>
                  {Math.round((analysis._meta?.overall_stress || 0) * 100)}%
                </strong>
                <span className="kpi-sublabel" style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>overall stress</span>
              </div>
              <div className="kpi-item" style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '110px' }}>
                <span className="kpi-label" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>Habitat</span>
                <strong className="kpi-value" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--color-accent)' }}>
                  {analysis.habitat_suitability_score || 0}%
                </strong>
                <span className="kpi-sublabel" style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>suitability</span>
              </div>
              <div className="kpi-item" style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '110px' }}>
                <span className="kpi-label" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>Simulator Range</span>
                <strong className="kpi-value" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--color-text)' }}>
                  {analysis.activity_score_range ? `${analysis.activity_score_range[0]} - ${analysis.activity_score_range[1]}` : '--'}
                </strong>
                <span className="kpi-sublabel" style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>activity score margin</span>
              </div>
            </div>
          </div>

          <div className="hero-ring-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="ring-svg-wrapper" style={{ position: 'relative', width: '130px', height: '130px' }}>
              <svg className="metric-ring" viewBox="0 0 160 160" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
                <circle className="ring-track" cx="80" cy="80" r="64" fill="none" stroke="rgba(255, 255, 255, 0.04)" strokeWidth="10" />
                <circle 
                  className="ring-progress" 
                  cx="80" 
                  cy="80" 
                  r="64" 
                  fill="none" 
                  stroke="var(--color-accent)"
                  strokeWidth="10"
                  strokeDasharray={`${2 * Math.PI * 64}`}
                  strokeDashoffset={`${2 * Math.PI * 64 * (1 - (analysis.activity_score || 0) / 100)}`}
                  strokeLinecap="round"
                  style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4, 0, 0.2, 1)' }}
                />
              </svg>
              <div className="ring-value-content" style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <ScoreDisplay analysis={analysis} />
              </div>
            </div>
          </div>
        </div>

        {/* Bento Grid */}
        <div className="bento-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px', marginTop: '20px' }}>
          
          {/* Factor Stress Breakdown */}
          <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)' }}>
            <div className="bento-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
              <div>
                <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Drivers</span>
                <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Factor Stress Breakdown</h3>
              </div>
              <WindStressIndicator analysis={analysis} />
            </div>
            <div className="factor-stress-bars" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {Object.entries(analysis.contribution_scores || {}).map(([key, score]) => {
                const meta = FACTOR_META[key] || { label: key, color: 'var(--color-accent)' };
                return (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12.5px' }}>
                      <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>{meta.label}</span>
                      <span style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>{score}%</span>
                    </div>
                    <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                      <motion.div 
                        style={{ height: '100%', background: meta.color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${score}%` }}
                        transition={{ duration: 0.8, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Compound Stress Insights */}
          <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)' }}>
            <div className="bento-header" style={{ marginBottom: '16px' }}>
              <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Stress Analysis</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Compound Stress Insights</h3>
            </div>
            <StressInsights analysis={analysis} />
          </div>

          {/* Crop Risk Cards */}
          <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)', gridColumn: 'span 1' }}>
            <div className="bento-header" style={{ marginBottom: '16px' }}>
              <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Risk Assessment</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Crop Risk Assessment</h3>
            </div>
            <CropRiskCards analysis={analysis} />
          </div>

          {/* Managed Hive Placement */}
          <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)' }}>
            <div className="bento-header" style={{ marginBottom: '16px' }}>
              <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Colony Placement</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Managed Hive Calculator</h3>
            </div>
            <HivePlacementCard advice={analysis.decision_brief?.hive_placement} />
          </div>

        </div>

        {/* Flowering Calendar section */}
        <div style={{ marginTop: '20px' }}>
          <PhenologyCalendar zoneId={analysis.zone_id} anomalies={analysis.anomalies || []} />
        </div>

        {/* Advisory Checklist */}
        <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid var(--color-border-strong)', borderRadius: 'var(--radius)', marginTop: '20px' }}>
          <div className="bento-header" style={{ marginBottom: '16px' }}>
            <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Advisory</span>
            <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Ecosystem Advisory Checklist</h3>
          </div>
          <InterventionPlan analysis={analysis} />
        </div>

        {/* Anomaly alert Feed */}
        {analysis.anomalies && analysis.anomalies.length > 0 && (
          <div className="bento-card glass-panel" style={{ padding: '20px', background: 'var(--color-card)', border: '1px solid rgba(255,107,107,0.15)', borderRadius: 'var(--radius)', marginTop: '20px' }}>
            <div className="bento-header" style={{ marginBottom: '16px' }}>
              <span className="eyebrow" style={{ fontSize: '10px', fontWeight: 700, color: 'var(--color-error)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>Alert Feed</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 0 0', color: 'var(--color-text)' }}>Anomaly Alerts</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {analysis.anomalies.map((anomaly, idx) => (
                <div 
                  key={idx} 
                  style={{ 
                    padding: '12px 16px', 
                    background: 'rgba(255,107,107,0.03)', 
                    border: '1px solid rgba(255,107,107,0.12)', 
                    borderRadius: 'var(--radius)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ color: 'var(--color-error)', fontSize: '12px', textTransform: 'uppercase' }}>{anomaly.severity}</strong>
                    <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>{anomaly.factor}</span>
                  </div>
                  <p style={{ margin: '4px 0', fontSize: '13px', color: 'var(--color-text)', lineHeight: 1.5 }}>{anomaly.description}</p>
                  {anomaly.recommended_action && (
                    <div style={{ marginTop: '4px', fontSize: '12.5px', color: 'var(--color-highlight)' }}>
                      <strong>Advice:</strong> {anomaly.recommended_action}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </motion.div>
    </div>
  )
}
