import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, post } from '../api'
import { strings, type Lang } from '../i18n'

interface ZoneFeature { properties: { zone_id: string; name: string; name_es: string }; geometry: { coordinates: number[][][] } }

/** Two taps: language, then zone. No sign-up, no personal data; the session id lives only in the URL. */
export default function Join() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [lang, setLang] = useState<Lang | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [zones, setZones] = useState<ZoneFeature[]>([])
  const [area, setArea] = useState<any>(null)
  const t = strings(lang ?? 'en')

  useEffect(() => {
    api('/api/zones').then((g) => setZones(g.features)).catch((e) => setErr(e.message))
    api('/api/state').then((s) => setArea(s.area_info)).catch(() => {})
  }, [])

  // Project zone polygons into a small SVG so residents can tap their area
  const shapes = useMemo(() => {
    const pts = zones.flatMap((z) => z.geometry.coordinates[0])
    if (!pts.length) return []
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const kx = Math.cos(((y0 + y1) / 2) * Math.PI / 180)
    const w = (x1 - x0) * kx, h = y1 - y0
    const s = 300 / Math.max(w, h * 1.6)
    return zones.map((z) => {
      const ring = z.geometry.coordinates[0].map(([x, y]) => [10 + (x - x0) * kx * s, 10 + (y1 - y) * s])
      const cx = ring.reduce((a, p) => a + p[0], 0) / ring.length, cy = ring.reduce((a, p) => a + p[1], 0) / ring.length
      return { z, d: 'M' + ring.map((p) => p.map((v) => v.toFixed(1)).join(' ')).join(' L') + ' Z', cx, cy, vw: 20 + w * s, vh: 20 + h * s }
    })
  }, [zones])

  const join = async (zone: string) => {
    setBusy(true)
    try {
      const s = await post('/api/audience/join', { language: lang ?? 'en', zone_id: zone, run: params.get('run') })
      nav(`/r/${s.id}?lang=${s.language}`, { replace: true })
    } catch (e) { setErr((e as Error).message); setBusy(false) }
  }
  const def = area?.audience_default_zone

  return (
    <main className="join" lang={lang ?? 'en'}>
      <h1><span className="wordmark dark">SIREN</span></h1>
      <p className="join-sub">{area ? area.name : ''}</p>
      {area && <p className="join-storm">{lang === 'es' ? 'Repetición:' : 'Replaying:'} {area.storm}</p>}
      {!lang ? (
        <>
          <h2>Choose your language · Elija su idioma</h2>
          <div className="join-langs">
            <button onClick={() => setLang('en')}>English</button>
            <button onClick={() => setLang('es')}>Español</button>
          </div>
        </>
      ) : (
        <>
          <h2>{t.joinZone}</h2>
          {shapes.length > 0 && (
            <svg viewBox={`0 0 ${shapes[0].vw} ${shapes[0].vh}`} className="join-map" role="group" aria-label={t.joinZone}>
              {shapes.map(({ z, d, cx, cy }) => (
                <g key={z.properties.zone_id} role="button" tabIndex={0} className={`join-zone ${z.properties.zone_id === def ? 'def' : ''}`}
                  aria-label={lang === 'es' ? z.properties.name_es : z.properties.name}
                  onClick={() => !busy && join(z.properties.zone_id)}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && join(z.properties.zone_id)}>
                  <path d={d} />
                  <text x={cx} y={cy + 6} textAnchor="middle">{z.properties.zone_id}</text>
                </g>
              ))}
            </svg>
          )}
          <div className="join-list">
            {zones.map((z) => (
              <button key={z.properties.zone_id} className={z.properties.zone_id === def ? 'primary' : ''} disabled={busy}
                onClick={() => join(z.properties.zone_id)}>
                {lang === 'es' ? z.properties.name_es : z.properties.name}
              </button>
            ))}
          </div>
        </>
      )}
      {err && <p className="warn">⚠ {err}</p>}
      <p className="join-live"><a href={`/live${lang ? `?lang=${lang}` : ''}`}>{lang === 'es' ? '📍 Ver el estado real donde está ahora →' : '📍 Check live conditions where you are now →'}</a></p>
      <p className="phone-foot">{t.notOfficial}</p>
    </main>
  )
}
