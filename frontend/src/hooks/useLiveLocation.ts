import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

export interface Loc { lat: string; lon: string }
const KEY = 'siren-live-loc'

/** Where to check: URL (?lat&lon, shareable) > last place on this device > browser geolocation (asked on first visit). */
export function useLiveLocation() {
  const [params, setParams] = useSearchParams()
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lat = params.get('lat'), lon = params.get('lon')
  const loc: Loc | null = lat && lon ? { lat, lon } : null

  const set = useCallback((la: number, lo: number) => {
    const p = { lat: la.toFixed(4), lon: lo.toFixed(4) }
    try { localStorage.setItem(KEY, JSON.stringify(p)) } catch { /* storage unavailable */ }
    setParams(p, { replace: true })
  }, [setParams])

  const locate = useCallback(() => {
    setError(null)
    if (!navigator.geolocation) { setError('geo'); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => { setLocating(false); set(pos.coords.latitude, pos.coords.longitude) },
      () => { setLocating(false); setError('geo') },
      { timeout: 12000, maximumAge: 300000 })
  }, [set])

  const search = useCallback(async (q: string) => {
    if (!q.trim()) return
    setError(null); setLocating(true)
    try { const r = await api(`/api/geocode?q=${encodeURIComponent(q)}`); set(r.lat, r.lon) }
    catch (e) { setError((e as Error).message) } finally { setLocating(false) }
  }, [set])

  // First visit: restore the last place, otherwise ask for the browser location right away
  useEffect(() => {
    if (loc) return
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
      if (saved?.lat && saved?.lon) { setParams(saved, { replace: true }); return }
    } catch { /* ignore */ }
    locate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { loc, locating, error, locate, search, set }
}
