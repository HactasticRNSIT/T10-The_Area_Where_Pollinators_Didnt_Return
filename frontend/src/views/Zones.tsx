import { useState, type FC } from 'react'
import { motion } from 'framer-motion'
import { Search } from 'lucide-react'
import { ZoneCard } from '../components/ZoneCard'
import { CardSkeleton } from '../components/SkeletonLoader'
import { usePolyNexus } from '../hooks/usePolyNexus'
import { useReducedMotion } from '../hooks/useReducedMotion'
import type { Zone } from '../api/client'

const ZonesSkeleton: FC = () => (
  <div className="zones__grid">
    {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
    <style>{`
      .zones__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
    `}</style>
  </div>
)

interface Props {
  polyNexus: ReturnType<typeof usePolyNexus>
  setView: (view: any) => void
}

export const Zones: FC<Props> = ({ polyNexus, setView }) => {
  const { zones: rawZones, activeZoneId, runAnalysis, loading } = polyNexus
  const reduced = useReducedMotion()
  const [searchQuery, setSearchQuery] = useState('')

  // Map ZoneSummary to the frontend client's Zone type
  const zones: Zone[] = rawZones.map(z => ({
    zone_id: z.zone_id,
    name: z.name,
    lat: z.lat,
    lon: z.lon,
    status: 'active', // default status
    description: z.zone_id.includes('_SEARCH_') ? 'Custom geocoded search location' : 'Preset agricultural region'
  }))

  const filteredZones = zones.filter(z => 
    z.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    z.zone_id.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleSelectZone = (id: string) => {
    const matched = zones.find(z => z.zone_id === id)
    if (matched) {
      runAnalysis(matched.zone_id, matched.lat, matched.lon, matched.name)
      setView('overview')
    }
  }

  return (
    <div className="zones">
      <motion.h1
        className="view-title"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        Zones
        {!loading && <span className="view-title__count">{zones.length}</span>}
      </motion.h1>

      <div className="search-container">
        <Search size={16} className="search-icon" strokeWidth={1.8} />
        <input 
          type="text" 
          placeholder="Filter zones..." 
          className="search-input"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
        />
      </div>

      {loading ? (
        <ZonesSkeleton />
      ) : zones.length === 0 ? (
        <div className="empty-state">
          <p>No zones returned from the API.</p>
        </div>
      ) : (
        <motion.div
          className="zones__grid"
          initial="hidden"
          animate="visible"
          variants={{
            visible: { transition: { staggerChildren: 0.06 } },
            hidden: {},
          }}
        >
          {filteredZones.length === 0 ? (
            <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
              <p>No zones match your filter.</p>
            </div>
          ) : (
            filteredZones.map(zone => (
              <motion.div
                key={zone.zone_id}
                variants={reduced ? {} : {
                  hidden: { opacity: 0, y: 20 },
                  visible: { opacity: 1, y: 0, transition: { duration: 0.22 } },
                }}
              >
                <ZoneCard
                  zone={zone}
                  isSelected={zone.zone_id === activeZoneId}
                  onSelect={handleSelectZone}
                />
              </motion.div>
            ))
          )}
        </motion.div>
      )}

      <style>{`
        .zones { display: flex; flex-direction: column; gap: 20px; }
        .search-container {
          position: relative;
          display: flex;
          align-items: center;
          margin-bottom: 4px;
        }
        .search-icon {
          position: absolute;
          left: 12px;
          color: var(--color-text-muted);
        }
        .search-input {
          width: 100%;
          max-width: 320px;
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: var(--radius);
          padding: 10px 12px 10px 36px;
          font-family: 'Inter', sans-serif;
          font-size: 14px;
          color: var(--color-text);
          transition: border-color var(--transition-fast);
          outline: none;
        }
        .search-input:focus {
          border-color: var(--color-accent);
        }
        .zones__grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 12px;
        }
        .empty-state {
          padding: 40px;
          text-align: center;
          color: var(--color-text-muted);
          background: var(--color-card);
          border-radius: var(--radius);
          border: 1px solid var(--color-border);
        }
      `}</style>
    </div>
  )
}
