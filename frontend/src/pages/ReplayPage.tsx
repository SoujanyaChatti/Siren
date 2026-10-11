import { useCallback, useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import AudiencePanel from '../components/replay/AudiencePanel'
import Charts from '../components/replay/Charts'
import DirectorPanel from '../components/replay/DirectorPanel'
import EvidenceDrawer from '../components/replay/EvidenceDrawer'
import MapView from '../components/replay/MapView'
import ResidentPhone from '../components/replay/ResidentPhone'
import Timeline from '../components/replay/Timeline'
import TimingCard from '../components/replay/TimingCard'
import AppShell from '../components/shell/AppShell'
import { Tabs } from '../components/ui/Tabs'
import { usePoll } from '../hooks/usePoll'
import { setTimeZone, useI18n } from '../i18n'
import { SEV_COLOR, SevBadge } from '../severity'
import type { AppState, User } from '../types'

interface AreaList { active: string; areas: { id: string; name: string; short_name: string; storm: string }[] }

/** Storm replay: a real past flood through the full SIREN pipeline, with alerts on judges' phones. */
export default function ReplayPage() {
  const { t, lang } = useI18n()
  const { data: state, error } = usePoll<AppState>('/api/state', 1000)
  const areaId = state?.area_info?.id ?? null
  const { data: series } = usePoll<Record<string, { t: string; v: number }[]>>('/api/series', 2000)
  const { data: timeline } = usePoll<any[]>('/api/timeline?limit=80', 1500)
  const { data: users, refresh: refreshUsers } = usePoll<User[]>(areaId ? `/api/users?a=${areaId}` : null, 10000)
  const [areas, setAreas] = useState<AreaList | null>(null)
  const [zonesGeo, setZonesGeo] = useState<any>(null)
  const [facilities, setFacilities] = useState<any[]>([])
  const [lead, setLead] = useState<any>(null)
  const [evidence, setEvidence] = useState<string | null>(null)
  const [director, setDirector] = useState(false)
  const [persona, setPersona] = useState<string | null>(null)
  const [tab, setTab] = useState('gauges')
  const [announce, setAnnounce] = useState('')
  const prevSev = useRef<Record<string, string>>({})

  if (state?.area_info?.tz) setTimeZone(state.area_info.tz)

  useEffect(() => {
    if (!areaId) return
    setZonesGeo(null); setLead(null); setEvidence(null); prevSev.current = {}
    api('/api/zones').then(setZonesGeo)
    api('/api/facilities').then(setFacilities)
    api('/api/lead-time').then(setLead)
    api<AreaList>('/api/areas').then(setAreas)
  }, [areaId])

  useEffect(() => {
    if (users?.length && !users.some((u) => u.id === persona)) setPersona(users[0].id)
  }, [users, persona])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(tag)) return
      if (e.key === 'D' && e.shiftKey) setDirector((d) => !d)
      if (e.key === ' ' && state) { e.preventDefault(); post('/api/replay', { action: state.clock.playing ? 'pause' : 'play' }) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state])

  useEffect(() => {
    if (!state) return
    const changes: string[] = []
    for (const z of state.zones) {
      if (prevSev.current[z.zone_id] && prevSev.current[z.zone_id] !== z.severity) changes.push(`${z.name} is now ${z.severity}`)
      prevSev.current[z.zone_id] = z.severity
    }
    if (changes.length) setAnnounce(changes.join('. '))
  }, [state])

  const onZone = useCallback((id: string) => {
    const z = state?.zones.find((x) => x.zone_id === id)
    if (z?.active_alert_id) setEvidence(z.active_alert_id)
  }, [state])

  if (!state) return <AppShell wide><div className="loading-card">{error ? `Cannot reach SIREN backend: ${error}` : 'Loading…'}</div></AppShell>

  const c = state.clock
  const user = users?.find((u) => u.id === persona)
  const pct = (100 * (Date.parse(c.now) - Date.parse(c.start))) / (Date.parse(c.end) - Date.parse(c.start))
  const tz = state.area_info.tz
  const tzAbbr = new Date(c.now).toLocaleTimeString('en-US', { timeZone: tz, timeZoneName: 'short' }).split(' ').pop()
  const shownTimeline = (timeline ?? []).filter((it) => it.kind !== 'delivery' || ['Delivered', 'Acknowledged'].includes(it.to))

  return (
    <AppShell wide>
      <div className="sr-only" aria-live="polite">{announce}</div>

      {/* 1. Which storm, and the replay controls */}
      <section className="replay-head" aria-label={t.replay}>
        <div className="replay-title">
          <span className="replay-badge">⏪ {lang === 'es' ? 'REPETICIÓN' : 'REPLAY'}</span>
          <label className="sr-only" htmlFor="area">Storm</label>
          <select id="area" className="area-select" value={areaId ?? ''} onChange={(e) => post('/api/area', { id: e.target.value })}>
            {(areas?.areas ?? []).map((a) => <option key={a.id} value={a.id}>{a.storm} · {a.short_name}</option>)}
          </select>
          {state.offline && <span className="badge offline" title="AI and voice read from cache; works with Wi-Fi off">✈ {t.offline}</span>}
          {state.force_gemini_failure && <span className="badge fallback">⚑ Gemini failure forced</span>}
        </div>
        <div className="replay-controls">
          <button className="play" onClick={() => post('/api/replay', { action: c.playing ? 'pause' : 'play' })} aria-label={c.playing ? t.pause : t.play}>{c.playing ? '❚❚' : '▶'}</button>
          <div className="clock-time num">{new Date(c.now).toLocaleString(lang === 'es' ? 'es-US' : 'en-US', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} <span className="muted">{tzAbbr}</span></div>
          <div className="seg" role="radiogroup" aria-label={t.speed}>
            {[1, 60, 300].map((s) => <button key={s} role="radio" aria-checked={c.speed === s} className={c.speed === s ? 'on' : ''} onClick={() => post('/api/replay', { action: 'speed', speed: s })}>{s}×</button>)}
          </div>
          <nav className="scenes" aria-label={t.scenes}>
            {state.scenes.map((s) => <button key={s.id} title={s.note} onClick={() => post('/api/replay', { action: 'scene', scene: s.id })}>{s.label}</button>)}
            <button className="ghost" title={t.reset} aria-label={t.reset} onClick={() => post('/api/replay', { action: 'reset' })}>⟲</button>
          </nav>
        </div>
        <div className="progress" aria-hidden="true"><div style={{ width: `${pct}%` }} /></div>
      </section>

      {/* 2. Zones + map | the resident's phone */}
      <div className="replay-grid">
        <div className="stack">
          <div className="zone-strip">
            {state.zones.map((z) => (
              <button key={z.zone_id} className="zone-card" style={{ borderLeftColor: SEV_COLOR[z.severity] }} onClick={() => onZone(z.zone_id)}
                aria-label={`${z.name}: ${z.severity}`}>
                <div className="zone-card-top"><SevBadge s={z.severity} label={t.severity[z.severity]} />{z.active_alert_id && <span className="zone-link">{t.evidence} →</span>}</div>
                <span className="zname">{lang === 'es' ? z.name_es : z.name}</span>
                <span className="zsub">
                  {z.exposure.label === 'verified_danger' && <span className="tag danger">◆ {t.verified}</span>}
                  {z.exposure.label === 'estimated_exposure' && <span className="tag est">◇ {t.estimated}</span>}
                  {z.missing.length > 0 && <span className="tag missing">⚠ data missing</span>}
                </span>
              </button>
            ))}
          </div>
          <div className="map-wrap">
            <MapView state={state} zonesGeo={zonesGeo} facilities={facilities} onZone={onZone} areaId={areaId} />
          </div>
        </div>

        <aside className="phone-col" aria-label={t.resident}>
          <div className="seg persona-switch" role="tablist" aria-label={t.persona}>
            {(users ?? []).map((u) => (
              <button key={u.id} role="tab" aria-selected={persona === u.id} className={persona === u.id ? 'on' : ''} onClick={() => setPersona(u.id)}>
                {u.name} <span className="muted small">{u.language.toUpperCase()}·{u.zone_id}</span>
              </button>
            ))}
          </div>
          {user && (
            <div className="phone-caption">
              <span>📱 {lang === 'es' ? `Teléfono de ${user.name}: recibe alertas en` : `${user.name}'s phone: gets alerts in`}</span>
              <div className="seg small" role="radiogroup" aria-label={lang === 'es' ? 'Idioma del residente' : "Resident's language"}>
                {(['en', 'es'] as const).map((l) => (
                  <button key={l} role="radio" aria-checked={user.language === l} className={user.language === l ? 'on' : ''}
                    onClick={async () => { await api(`/api/users/${user.id}`, { method: 'PATCH', json: { language: l } }); refreshUsers() }}>
                    {l === 'en' ? 'English' : 'Español'}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="phone-frame">
            {user && <ResidentPhone key={`${areaId}-${user.id}-${user.language}`} residentId={user.id} kind="persona" lang={user.language} feedPath={`/api/residents/${user.id}`} />}
          </div>
        </aside>
      </div>

      {/* 3. Details, one at a time */}
      <section className="panel">
        <Tabs label="Details" active={tab} onChange={setTab} tabs={[
          { id: 'gauges', label: lang === 'es' ? 'Medidores' : 'River gauges', content: <Charts state={state} series={series} /> },
          { id: 'timeline', label: t.timeline, badge: shownTimeline.length || undefined, content: <div className="timeline-box"><Timeline items={shownTimeline} onOpen={setEvidence} /></div> },
          { id: 'audience', label: t.audience, badge: state.audience.joined || undefined, content: <AudiencePanel summary={state.audience} runId={state.demo_run_id} /> },
          { id: 'timing', label: lang === 'es' ? 'Tiempos vs NWS' : 'Timing vs NWS', content: <TimingCard lt={lead} /> },
        ]} />
      </section>
      <p className="muted small center">Space: play/pause · Shift+D: director · {state.area_info.description}</p>

      {evidence && <EvidenceDrawer alertId={evidence} onClose={() => setEvidence(null)} />}
      {director && <DirectorPanel state={state} users={users ?? []} onClose={() => setDirector(false)} onPersona={setPersona} />}
    </AppShell>
  )
}
