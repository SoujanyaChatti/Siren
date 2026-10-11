import { useEffect, useRef, useState } from 'react'
import { apiUrl, post } from '../../api'
import { usePoll } from '../../hooks/usePoll'
import { speak, useSpeech } from '../../hooks/useSpeech'
import { fmtLocal, strings, type Lang } from '../../i18n'
import { SEV_COLOR, SevBadge, SevIcon } from '../../severity'
import type { Delivery, ResidentView } from '../../types'

interface Props {
  residentId: string
  kind: 'persona' | 'audience'
  lang: Lang
  feedPath: string
  header?: React.ReactNode
  onSessionLost?: () => void
}

/** What one resident sees and hears. Used for the on-screen personas and for judges' phones. */
export default function ResidentPhone({ residentId, kind, lang: alertLang, feedPath, header, onSessionLost }: Props) {
  // Everything in the phone (interface, alert, answers) is in the resident's own language
  const lang: Lang = alertLang
  const t = strings(lang)
  const { data, error } = usePoll<ResidentView>(feedPath, kind === 'audience' ? 2000 : 1500)
  const [large, setLarge] = useState(false)
  const [contrast, setContrast] = useState(false)
  const [announce, setAnnounce] = useState('')
  const seen = useRef<Set<string>>(new Set())
  const lastSev = useRef<string | null>(null)

  useEffect(() => {
    if (error && error.includes('session not found')) onSessionLost?.()
  }, [error, onSessionLost])

  // Confirm render: "Delivered" means this device actually fetched and displayed the alert.
  const d = data?.delivery
  useEffect(() => {
    if (d && d.state === 'Generated' && !seen.current.has(d.id)) {
      seen.current.add(d.id)
      post(`/api/deliveries/${d.id}/rendered?actor=${kind}:${residentId.slice(0, 6)}`).catch(() => {})
      if ('vibrate' in navigator) navigator.vibrate?.([200, 100, 200])
    }
  }, [d, kind, residentId])

  useEffect(() => {
    const s = data?.zone.severity
    if (s && s !== lastSev.current) {
      if (lastSev.current) setAnnounce(`${t.severity[s]}: ${lang === 'es' ? data!.zone.name_es : data!.zone.name}`)
      lastSev.current = s
    }
  }, [data, lang, t])

  if (!data) return <div className="phone-body"><p className="muted">{error ? `⚠ ${error}` : '…'}</p></div>

  const zoneName = lang === 'es' ? data.zone.name_es : data.zone.name
  const sev = data.zone.severity
  return (
    <div className={`phone-body ${large ? 'large' : ''} ${contrast ? 'contrast' : ''}`} lang={lang}>
      <div className="sr-only" aria-live="assertive">{announce}</div>
      {header}
      <div className="phone-prefs" role="group" aria-label="Display options">
        <button aria-pressed={large} onClick={() => setLarge(!large)}>A+ {t.largeText}</button>
        <button aria-pressed={contrast} onClick={() => setContrast(!contrast)}>◐ {t.highContrast}</button>
      </div>
      {d && d.state !== 'Superseded' && d.state !== 'Cancelled' && sev !== 'Normal'
        ? <AlertCard d={d} lang={d.language} residentId={residentId} kind={kind} />
        : (
          <section className="calm-card" aria-label={t.monitoring}>
            <SevIcon s={sev === 'Unknown' ? 'Unknown' : sev} size={34} />
            <div>
              <div className="calm-title">{t.monitoring} {zoneName.split(' — ')[0]}</div>
              <div className="calm-sub">{sev === 'Normal' ? t.allCalm : t.severity[sev]}</div>
              {data.zone.missing.length > 0 && <div className="calm-sub warn">⚠ {data.zone.missing.join('; ')}</div>}
            </div>
          </section>
        )}
      {data.route && <RouteCard r={data.route} lang={lang} />}
      <AskSiren lang={alertLang} residentId={residentId} kind={kind} />
      <PhotoReport lang={lang} residentId={residentId} kind={kind} demo={data.demo_location ?? null} />
      <p className="phone-foot">{t.notOfficial}</p>
    </div>
  )
}

function AlertCard({ d, lang, residentId, kind }: { d: Delivery; lang: Lang; residentId: string; kind: string }) {
  const t = strings(lang)
  const [busy, setBusy] = useState(false)
  const sev = d.alert_severity ?? 'Warning'
  const acked = d.state === 'Acknowledged'
  const ack = async () => {
    setBusy(true)
    try {
      if (kind === 'audience') await post(`/api/audience/${residentId}/ack`, { delivery_id: d.id })
      else await post(`/api/deliveries/${d.id}/ack?actor=persona:${residentId}`)
    } finally { setBusy(false) }
  }
  const c = d.card
  return (
    <section className="alert-card pulse-once" style={{ borderColor: SEV_COLOR[sev] }} aria-labelledby={`h-${d.id}`}>
      <div className="alert-top" style={{ background: SEV_COLOR[sev] }}>
        <SevBadge s={sev} label={c?.severity_word ?? sev} large />
      </div>
      <h2 id={`h-${d.id}`} className="alert-headline">{c?.headline}</h2>
      <ul className="alert-lines">
        <li><strong>{lang === 'es' ? 'Qué' : 'What'}:</strong> {c?.what}</li>
        <li><strong>{lang === 'es' ? 'Dónde' : 'Where'}:</strong> {c?.where}</li>
        <li><strong>{lang === 'es' ? 'Qué hacer' : 'What to do'}:</strong> {c?.action}</li>
      </ul>
      <div className="alert-meta">{c?.updated.replace(/\.$/, '')} · {t.source}: USGS, NWS, SIREN</div>
      <button className="btn-play" onClick={() => speak(d.text ?? '', lang, d.audio_url)} aria-label={t.play_alert}>
        ▶ {t.play_alert}
      </button>
      <div className="voice-credit">{d.audio_url ? t.voiceBy : t.voiceBrowser}</div>
      <details className="transcript" open>
        <summary>{t.transcript}</summary>
        <p>{d.text}</p>
      </details>
      <button className={`btn-ack ${acked ? 'done' : ''}`} onClick={ack} disabled={acked || busy}>
        {acked ? `✓ ${t.acknowledged}` : t.understand}
      </button>
    </section>
  )
}

function RouteCard({ r, lang }: { r: NonNullable<ResidentView['route']>; lang: Lang }) {
  const t = strings(lang)
  const safer = r.recommended === 'safer'
  return (
    <section className={`route-card ${safer ? 'blocked' : ''}`} aria-label={t.route}>
      <div className="route-title">🚗 {t.route}</div>
      {safer ? (
        <div><strong>{t.routeSafer}</strong> · {t.blockedAt}: {r.blocked_by.join(', ')} ({(r.safer.distance_m / 1609).toFixed(1)} mi)</div>
      ) : <div>{t.routeUsual}</div>}
    </section>
  )
}

function AskSiren({ lang, residentId, kind }: { lang: Lang; residentId: string; kind: string }) {
  const t = strings(lang)
  const [q, setQ] = useState('')
  const [ans, setAns] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ask = async (question: string) => {
    if (!question.trim()) return
    setBusy(true); setErr(null)
    try {
      const body = kind === 'audience' ? { question, session_id: residentId, language: lang } : { question, user_id: residentId, language: lang }
      const a = await post('/api/ask', body)
      setAns(a)
      speak(a.answer, lang, a.audio_url)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const sp = useSpeech(lang, (text) => { setQ(text); ask(text) })
  return (
    <section className="ask" aria-label={t.ask}>
      <div className="ask-title">💬 {t.ask}</div>
      <form className="ask-row" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <button type="button" className={`mic ${sp.listening ? 'on' : ''}`} onClick={sp.listening ? sp.stop : sp.start}
          aria-label={sp.listening ? t.listening : 'Microphone'}>🎤</button>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.askPlaceholder} aria-label={t.ask} />
        <button type="submit" disabled={busy}>{busy ? '…' : t.send}</button>
      </form>
      {sp.listening && <div className="muted">{t.listening}</div>}
      {(sp.err || err) && <div className="muted warn">⚠ {sp.err || err}</div>}
      {ans && (
        <div className="answer">
          <p>{ans.answer}</p>
          <div className="chips">
            {(ans.citation_details ?? []).map((c: any) => (
              <a key={c.id} className="chip" href={c.source.startsWith('http') ? c.source : undefined} target="_blank" rel="noreferrer" title={c.text}>{c.id}</a>
            ))}
            <span className="chip ghost">{ans.ai?.path === 'template' ? 'guidance match' : ans.ai?.path}</span>
          </div>
          <button className="link" onClick={() => speak(ans.answer, lang, ans.audio_url)}>▶ {t.play_alert}</button>
        </div>
      )}
    </section>
  )
}

function PhotoReport({ lang, residentId, kind, demo }: { lang: Lang; residentId: string; kind: string; demo: ResidentView['demo_location'] }) {
  const t = strings(lang)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [loc, setLoc] = useState<'demo' | 'mine'>('demo')
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const submit = async () => {
    if (!file) return
    setBusy(true); setErr(null)
    try {
      let lat = demo?.lat ?? 0, lon = demo?.lon ?? 0
      if (loc === 'mine' || !demo) {
        const p = await new Promise<GeolocationPosition>((ok, no) => navigator.geolocation.getCurrentPosition(ok, no, { timeout: 8000 }))
        lat = p.coords.latitude; lon = p.coords.longitude
      }
      const fd = new FormData()
      fd.append('image', file); fd.append('lat', String(lat)); fd.append('lon', String(lon))
      fd.append('reporter', `${kind}:${residentId.slice(0, 6)}`)
      if (kind === 'audience') fd.append('session_id', residentId)
      const r = await fetch(apiUrl('/api/photos'), { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json()).detail ?? r.status)
      setRes(await r.json())
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  if (!open) return <button className="btn-report" onClick={() => setOpen(true)}>📷 {t.report}</button>
  return (
    <section className="report" aria-label={t.report}>
      <div className="ask-title">📷 {t.report}</div>
      <p className="muted">{t.reportHelp}</p>
      <input type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label={t.report} />
      <fieldset className="loc">
        <legend>{t.location}</legend>
        {demo && <label><input type="radio" checked={loc === 'demo'} onChange={() => setLoc('demo')} /> {t.useDemoLoc}: {demo.name}</label>}
        <label><input type="radio" checked={loc === 'mine'} onChange={() => setLoc('mine')} /> {t.useMyLoc}</label>
      </fieldset>
      <button onClick={submit} disabled={!file || busy}>{busy ? '…' : t.submit}</button>
      {err && <div className="muted warn">⚠ {err}</div>}
      {res && <PhotoResult p={res} lang={lang} />}
    </section>
  )
}

export function PhotoResult({ p, lang }: { p: any; lang: Lang }) {
  const a = p.analysis ?? {}
  const statusLabel: Record<string, string> = lang === 'es'
    ? { verified: 'Verificado', unverified: 'Reporte no verificado', rejected: 'Rechazado' }
    : { verified: 'Verified', unverified: 'Unverified report', rejected: 'Rejected' }
  return (
    <div className="photo-result">
      <PhotoWithOverlay src={apiUrl(p.image_url)} analysis={a} />
      {a.depth_in != null ? (
        <div className="depth-line">≈ {Math.round(a.depth_in)} in ({Math.round(a.depth_low_in)}–{Math.round(a.depth_high_in)} in) ·
          {lang === 'es' ? ' La mayoría de los carros pueden flotar con 12 pulg.' : ' Most cars can float at 12 in.'}</div>
      ) : <div className="depth-line">{a.notes}</div>}
      <div className="chips">
        <span className={`chip ${p.status}`}>{statusLabel[p.status] ?? p.status}</span>
        {a.confidence != null && <span className="chip ghost">conf {Number(a.confidence).toFixed(2)}</span>}
        {(p.checks?.flags ?? []).map((f: string) => <span key={f} className="chip ghost">{f}</span>)}
        <span className="chip ghost">{p.ai_path}{p.model ? ` · ${p.model}` : ''}</span>
      </div>
      {(p.checks?.reasons ?? []).map((r: string) => <div key={r} className="muted">{r}</div>)}
    </div>
  )
}

export function PhotoWithOverlay({ src, analysis }: { src: string; analysis: any }) {
  const refs = analysis?.reference_objects ?? []
  return (
    <div className="photo-wrap">
      <img src={src} alt="Flood photo report" />
      <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
        {refs.filter((r: any) => r.box && r.box.length === 4 && r.box[2] > r.box[0]).map((r: any, i: number) => (
          <g key={i}>
            <rect x={r.box[0]} y={r.box[1]} width={r.box[2] - r.box[0]} height={r.box[3] - r.box[1]} fill="none" stroke="#ffd60a" strokeWidth="0.004" />
          </g>
        ))}
        {analysis?.waterline_y != null && (
          <line x1="0" x2="1" y1={analysis.waterline_y} y2={analysis.waterline_y} stroke="#4dd2ff" strokeWidth="0.004" strokeDasharray="0.02 0.01" />
        )}
      </svg>
      {refs[0] && <span className="photo-tag">{refs[0].type.replace('_', ' ')} · {Math.round(refs[0].waterline_fraction * 100)}% under water</span>}
    </div>
  )
}

export { fmtLocal }
