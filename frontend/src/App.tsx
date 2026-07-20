import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Search } from 'lucide-react'
import { Sidebar, type ViewId } from './components/Sidebar'
import { Overview } from './views/Overview'
import { Zones } from './views/Zones'
import { Analyse } from './views/Analyse'
import { Compare } from './views/Compare'
import { Chat } from './views/Chat'
import { OfflineBanner } from './components/OfflineBanner'
import { useReducedMotion } from './hooks/useReducedMotion'
import { usePolyNexus } from './hooks/usePolyNexus'
import './styles/globals.css'
import './App.css'

function getStateCode(stateName: string = ''): string {
  const normalized = stateName.toLowerCase().trim();
  if (normalized.includes('karnataka')) return 'KA';
  if (normalized.includes('maharashtra')) return 'MH';
  if (normalized.includes('tamil nadu')) return 'TN';
  if (normalized.includes('uttar pradesh')) return 'UP';
  if (normalized.includes('gujarat')) return 'GJ';
  if (normalized.includes('west bengal')) return 'WB';
  if (normalized.includes('kerala')) return 'KL';
  if (normalized.includes('himachal')) return 'HP';
  if (normalized.includes('madhya')) return 'MP';
  if (normalized.includes('bihar')) return 'BR';
  if (normalized.includes('punjab')) return 'PB';
  if (normalized.includes('assam')) return 'AS';
  if (normalized.includes('telangana')) return 'TG';
  if (normalized.includes('jammu') || normalized.includes('kashmir')) return 'JK';
  if (normalized.includes('rajasthan')) return 'RJ';
  if (normalized.includes('delhi')) return 'DL';
  if (normalized.includes('haryana')) return 'HR';
  if (normalized.includes('andhra')) return 'AP';
  if (normalized.includes('odisha')) return 'OR';
  return 'IN';
}

interface ViewRendererProps {
  view: ViewId
  polyNexus: ReturnType<typeof usePolyNexus>
  setView: (view: ViewId) => void
}

function ViewRenderer({ view, polyNexus, setView }: ViewRendererProps) {
  switch (view) {
    case 'overview': 
      return <Overview polyNexus={polyNexus} />
    case 'zones':    
      return <Zones polyNexus={polyNexus} setView={setView} />
    case 'analyse':  
      return <Analyse polyNexus={polyNexus} />
    case 'compare':  
      return <Compare polyNexus={polyNexus} />
    case 'chat':     
      return <Chat />
  }
}

export default function App() {
  const [view, setView] = useState<ViewId>('overview')
  const reduced = useReducedMotion()
  const polyNexus = usePolyNexus()
  const [searchQuery, setSearchQuery] = useState('')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [showDropdown, setShowDropdown] = useState(false)

  // Debounced search for Nominatim geocoding
  useEffect(() => {
    if (searchQuery.trim().length < 4) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(
            searchQuery
          )}&countrycodes=in&limit=5&addressdetails=1`,
          {
            headers: {
              'User-Agent': 'PolyNexus-Dashboard/1.0'
            }
          }
        );
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
        }
      } catch (err) {
        console.error('Search failed', err);
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSelectSuggestion = (item: any) => {
    const stateName = item.address?.state || '';
    const stateCode = getStateCode(stateName);
    const zoneId = `${stateCode}_${Date.now()}`;
    const name = item.display_name.split(',')[0] || item.display_name;
    const lat = parseFloat(item.lat);
    const lon = parseFloat(item.lon);

    const newZone = {
      zone_id: zoneId,
      name,
      lat,
      lon
    };

    polyNexus.addCustomZone(newZone);
    setSearchQuery('');
    setSuggestions([]);
    setShowDropdown(false);
    setView('overview');
  };

  return (
    <div className="app-layout">
      {/* Top Header Navbar */}
      <header className="navbar">
        <div className="nav-left">
          <div className="brand" onClick={() => setView('overview')} style={{ cursor: 'pointer' }}>
            <div className="brand-icon">PX</div>
            <div className="brand-text">
              <h1>PolyNexus</h1>
              <p>Pollinator intelligence</p>
            </div>
          </div>
        </div>

        {/* Global location search */}
        <div className="search-container">
          <Search size={16} className="search-icon" strokeWidth={1.8} />
          <input
            type="text"
            placeholder="Search Indian state, city, or farm region..."
            className="search-input"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 200)} // short delay for clicks
          />
          
          {showDropdown && suggestions.length > 0 && (
            <div className="search-suggestions-dropdown">
              {suggestions.map((item, index) => (
                <div
                  key={index}
                  className="suggestion-item"
                  onMouseDown={() => handleSelectSuggestion(item)}
                >
                  <span className="suggestion-title">
                    {item.display_name.split(',')[0]}
                  </span>
                  <span className="suggestion-subtitle">
                    {item.display_name.split(',').slice(1).join(',')}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="nav-right">
          <div className="api-status">
            <span className={`status-dot ${polyNexus.apiHealth ? 'online' : 'offline'}`} />
            {polyNexus.apiHealth ? 'API Online' : 'API Offline'}
          </div>
        </div>
      </header>

      <div className="app">
        <Sidebar active={view} onChange={setView} />

        <main className="app__main">
          <div className="app__scroll">
            <AnimatePresence mode="wait">
              <motion.div
                key={view}
                className="app__view"
                initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, y: -16, scale: 0.98 }}
                transition={{ type: 'spring', stiffness: 300, damping: 25, mass: 0.8 }}
              >
                <ViewRenderer view={view} polyNexus={polyNexus} setView={setView} />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      {/* Offline / stale-data indicator — non-blocking fixed banner */}
      <OfflineBanner lastUpdatedAt={polyNexus.analysis?.analysed_at} />

      <style>{`
        .app-layout {
          display: flex;
          flex-direction: column;
          height: 100vh;
          overflow: hidden;
        }

        .app {
          display: flex;
          flex: 1;
          overflow: hidden;
        }

        .app__main {
          flex: 1;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .app__scroll {
          flex: 1;
          overflow-y: auto;
          padding: 28px 32px;
        }

        .app__view {
          max-width: 1200px;
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
        }

        /* Shared view styles */
        :global(.view-title) {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.025em;
          color: var(--color-text);
          margin-bottom: 20px;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        :global(.view-title__count) {
          font-size: 13px;
          font-weight: 500;
          color: var(--color-text-muted);
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          padding: 2px 8px;
          border-radius: 20px;
        }

        :global(.error-banner) {
          padding: 10px 14px;
          background: rgba(255,107,107,0.08);
          border: 1px solid rgba(255,107,107,0.25);
          border-radius: var(--radius);
          color: var(--color-error);
          font-size: 13px;
        }

        :global(.form-field) { display: flex; flex-direction: column; gap: 6px; }

        :global(.form-label) {
          font-size: 12px;
          font-weight: 600;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        :global(.form-select) {
          padding: 9px 12px;
          width: 100%;
          cursor: pointer;
          appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238888AA' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 10px center;
          padding-right: 30px;
        }

        :global(.form-hint) {
          font-size: 11px;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }

        :global(.btn-primary) {
          padding: 10px 20px;
          background: var(--color-accent);
          color: #fff;
          border-radius: var(--radius);
          font-size: 13.5px;
          font-weight: 600;
          transition: opacity var(--transition-fast), transform var(--transition-fast);
          align-self: flex-start;
        }

        :global(.btn-primary:hover:not(:disabled)) {
          opacity: 0.88;
          transform: translateY(-1px);
        }

        :global(.btn-primary:disabled) {
          opacity: 0.4;
          cursor: not-allowed;
        }

        @media (max-width: 768px) {
          .app__scroll {
            padding: 20px 16px 80px;
          }
        }
      `}</style>
    </div>
  )
}
