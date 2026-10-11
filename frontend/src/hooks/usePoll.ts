import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

/** Poll a JSON endpoint. Keeps the last good value on errors so the UI never blanks. */
export function usePoll<T>(path: string | null, ms: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number>()
  const refresh = useCallback(async () => {
    if (!path) return
    try {
      setData(await api<T>(path))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [path])
  useEffect(() => {
    let alive = true
    const loop = async () => {
      if (!alive) return
      await refresh()
      if (alive) timer.current = window.setTimeout(loop, ms)
    }
    loop()
    return () => { alive = false; window.clearTimeout(timer.current) }
  }, [refresh, ms])
  return { data, error, refresh }
}
