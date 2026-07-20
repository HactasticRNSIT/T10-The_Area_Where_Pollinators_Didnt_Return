import { useEffect, useState, useCallback } from 'react'
import { getZones, type Zone } from '../api/client'

const STORAGE_KEY = 'selectedZone'

export function useZones() {
  const [zones, setZones] = useState<Zone[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function fetch() {
      setLoading(true)
      setError(null)
      try {
        const data = await getZones(controller.signal)
        setZones(data)

        const storedId = localStorage.getItem(STORAGE_KEY)
        const isValid = data.some(z => z.zone_id === storedId)
        setSelectedId(isValid ? storedId : (data[0]?.zone_id ?? null))
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError('Failed to load zones')
        }
      } finally {
        setLoading(false)
      }
    }

    fetch()
    return () => controller.abort()
  }, [])

  const selectZone = useCallback((id: string) => {
    setSelectedId(id)
    localStorage.setItem(STORAGE_KEY, id)
  }, [])

  const selectedZone = zones.find(z => z.zone_id === selectedId) ?? null

  return { zones, selectedId, selectedZone, selectZone, loading, error }
}
