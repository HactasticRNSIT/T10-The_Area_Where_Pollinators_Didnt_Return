import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type HealthStatus = 'loading' | 'online' | 'offline'

export function useHealth() {
  const [status, setStatus] = useState<HealthStatus>('loading')

  useEffect(() => {
    const controller = new AbortController()

    async function check() {
      try {
        await getHealth(controller.signal)
        setStatus('online')
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setStatus('offline')
        }
      }
    }

    check()
    const interval = setInterval(check, 30_000)

    return () => {
      controller.abort()
      clearInterval(interval)
    }
  }, [])

  return status
}
