import { useEffect, useState } from 'react'
import { api, apiUrl, post } from '../../api'
import { fmtLocal } from '../../i18n'
import { SevBadge } from '../../severity'
import { PhotoWithOverlay } from './ResidentPhone'

const STATES = ['Drafted', 'Generated', 'Delivered', 'Acknowledged']

export default function EvidenceDrawer({ alertId, onClose }: { alertId: string; onClose: () => void }) {
  const [ev, setEv] = useState<any>(null)
  const [rerun, setRerun] = useState<any>(null)
  useEffect(() => {
    let alive = true
    const load = () => api(`/api/alerts/${alertId}/evidence`).then((d) => alive && setEv(d)).catch(() => {})
    load()
    const id = window.setInterval(load, 2000)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => { alive = false; window.clearInterval(id); window.removeEventListener('keydown', onKey) }
  }, [alertId, onClose])
  useEffect(() => setRerun(null), [alertId])

  return (
    <aside className="drawer" role="dialog" aria-modal="false" aria-label={`Evidence for alert ${alertId}`}>
      <header className="drawer-head">
        <h2>Evidence · {alertId}</h2>
        <button onClick={onClose} aria-label="Close evidence">✕</button>
      </header>
      {!ev ? <p className="muted">Loading…</p> : (
        <div className="drawer-body">
          <section>
            <div className="row"><SevBadge s={ev.alert.severity} large /> <span className="chip">{ev.alert.state}</span>
              <span className="muted">Zone {ev.alert.zone_id} · decided {fmtLocal(ev.alert.created_at)} · ruleset {ev.ruleset_version}</span></div>
            <p className="quote">“{ev.message_en.text}”</p>
          </section>

          <section>
            <h3>Rules that fired</h3>
            {ev.rules.filter((r: any) => r.fired).map((r: any) => <RuleBlock key={r.rule_id} r={r} />)}
            <details><summary>Rules evaluated but not fired ({ev.rules.filter((r: any) => !r.fired).length})</summary>
              {ev.rules.filter((r: any) => !r.fired).map((r: any) => <RuleBlock key={r.rule_id} r={r} />)}
            </details>
            <div className="row">
              <button onClick={async () => setRerun(await post(`/api/alerts/${alertId}/rerun`))}>↻ Re-run rule from stored inputs</button>
              {rerun && <span className={`chip ${rerun.all_match ? 'verified' : 'rejected'}`}>{rerun.all_match ? '✓ Same result, same inputs_hash' : '✗ Mismatch'}</span>}
            </div>
          </section>

          <section>
            <h3>Data freshness</h3>
            {ev.missing_data.length ? <p className="warn">⚠ {ev.missing_data.join('; ')}</p> : <p className="muted">All inputs fresh (gauge readings ≤ 30 min old).</p>}
          </section>

          {ev.photos.length > 0 && (
            <section>
              <h3>Photo evidence</h3>
              {ev.photos.map((p: any) => (
                <div key={p.id}>
                  <PhotoWithOverlay src={apiUrl(p.image_url)} analysis={p.analysis} />
                  <p>≈ {Math.round(p.analysis.depth_in)} in ({Math.round(p.analysis.depth_low_in)}–{Math.round(p.analysis.depth_high_in)} in), confidence {p.analysis.confidence} ·
                    status <strong>{p.status}</strong> · path <span className={`chip ${p.ai_path === 'gemini' ? '' : 'fallback'}`}>{p.ai_path} · {p.model}</span></p>
                  <p className="muted">{p.analysis.notes}</p>
                </div>
              ))}
            </section>
          )}

          <section>
            <h3>AI explanation</h3>
            {ev.explanation ? (
              <>
                <div className="row"><AIPath ai={ev.ai} /></div>
                <p><strong>{ev.explanation.headline}</strong></p>
                <p>{ev.explanation.what_is_happening}</p>
                <p className="muted">{ev.explanation.who_may_be_affected}</p>
                <ul>{ev.explanation.why.map((w: any, i: number) => <li key={i}><code>{w.rule_id}</code> {w.evidence}</li>)}</ul>
                <p className="muted small">{ev.explanation.confidence_note}</p>
                {ev.ai?.fallback_reasons?.length > 0 && <details><summary>Fallback reasons</summary><ul>{ev.ai.fallback_reasons.map((r: string, i: number) => <li key={i} className="small">{r}</li>)}</ul></details>}
              </>
            ) : <p className="muted">Generating… (the decision was already made by rules)</p>}
          </section>

          <section>
            <h3>Exposure</h3>
            <p><span className={`chip ${ev.exposure.label === 'verified_danger' ? 'verified-danger' : 'estimated'}`}>
              {ev.exposure.label === 'verified_danger' ? '◆ Verified danger' : '◇ Estimated exposure'}</span>
              {ev.exposure.verified_by.length > 0 && <span className="muted"> by {ev.exposure.verified_by.join(', ')}</span>}</p>
            <ul className="fac-list">{ev.exposure.facilities.slice(0, 8).map((f: any) => <li key={f.id}>{f.name} <span className="muted">({f.kind.replace('_', ' ')}, {(f.distance_m / 1000).toFixed(1)} km)</span></li>)}</ul>
          </section>

          <section>
            <h3>Deliveries ({ev.deliveries.length})</h3>
            {ev.deliveries.map((d: any) => (
              <div key={d.id} className="delivery">
                <div className="row"><strong>{d.label}</strong> <span className="chip">{d.language.toUpperCase()}</span>
                  <span className={`chip ${d.translation && d.translation.path !== 'gemini' && d.translation.path !== 'groq' ? 'fallback' : ''}`}>
                    text: {d.translation ? d.translation.path : 'template (EN)'}</span>
                  <span className="chip">voice: {d.voice?.provider === 'elevenlabs' ? 'ElevenLabs' : 'browser fallback'}</span>
                  {d.language === 'es' && <span className={`chip ${d.reviewed?.template_phrases_reviewed ? 'verified' : 'fallback'}`}>{d.reviewed?.template_phrases_reviewed ? 'ES reviewed' : 'ES review pending'}</span>}
                </div>
                <Lifecycle events={d.events} />
                <details><summary>Transcript</summary><p>{d.text}</p>{d.source_text_en && <p className="muted small">EN source: {d.source_text_en}</p>}</details>
              </div>
            ))}
          </section>

          <section>
            <h3>Alert lifecycle</h3>
            <ol className="events">{ev.lifecycle.map((e: any, i: number) => <li key={i}><time>{fmtLocal(e.time)}</time> {e.from_state ?? '∅'} → <strong>{e.to_state}</strong> <span className="muted">· {e.actor} · {e.note}</span></li>)}</ol>
          </section>
        </div>
      )}
    </aside>
  )
}

function RuleBlock({ r }: { r: any }) {
  return (
    <div className={`rule ${r.fired ? 'fired' : ''}`}>
      <div className="row"><code>{r.rule_id}</code> <span className="muted">v{r.version}</span>
        {r.official && <span className="chip">official</span>}
        {r.held_by_hysteresis && <span className="chip fallback">held by hysteresis</span>}
        {r.raw === null && <span className="chip fallback">inputs missing</span>}
        <span className="hash" title="inputs_hash">#{r.inputs_hash}</span></div>
      <div className="small">{r.description}{r.threshold_ft != null && <> · threshold <strong>{r.threshold_ft} ft</strong> (<a href={r.threshold_source} target="_blank" rel="noreferrer">NOAA</a>)</>}{r.sum_in != null && <> · sum <strong>{r.sum_in} in</strong></>}</div>
      {r.readings.length > 0 && (
        <table className="readings">
          <thead><tr><th>role</th><th>time</th><th>station</th><th>value</th><th>quality</th><th>source</th></tr></thead>
          <tbody>{r.readings.slice(0, 6).map((x: any, i: number) => (
            <tr key={i}><td>{x.role}</td><td>{fmtLocal(x.time)}</td><td>{x.station_id}</td><td className="num">{x.value} {x.metric === 'stage_ft' ? 'ft' : 'in'}</td><td>{x.quality}</td>
              <td>{x.source_url?.startsWith('http') ? <a href={x.source_url} target="_blank" rel="noreferrer">{x.source}</a> : x.source}</td></tr>
          ))}</tbody>
        </table>
      )}
      {r.active_warnings?.length > 0 && <div className="small">Active: {r.active_warnings.map((w: any) => <a key={w.id} href={w.source_url} target="_blank" rel="noreferrer">{w.id}</a>)}</div>}
    </div>
  )
}

function AIPath({ ai }: { ai: any }) {
  if (!ai) return null
  const fallback = ai.path !== 'gemini'
  return (
    <>
      <span className={`chip ${fallback ? 'fallback' : ''}`}>{fallback ? '⚑ fallback: ' : ''}{ai.path}</span>
      <span className="chip ghost">{ai.model}</span>
      {ai.cache_hit && <span className="chip ghost">cache hit</span>}
      <span className="chip ghost">{ai.latency_ms} ms</span>
    </>
  )
}

function Lifecycle({ events }: { events: any[] }) {
  const reached = new Map(events.map((e) => [e.to_state, e]))
  const terminal = events.find((e) => ['Superseded', 'Expired', 'Cancelled'].includes(e.to_state))
  return (
    <ol className="lifecycle">
      {STATES.map((s) => (
        <li key={s} className={reached.has(s) ? 'on' : ''} title={reached.get(s) ? `${reached.get(s).actor} @ ${fmtLocal(reached.get(s).time)}` : ''}>{s}</li>
      ))}
      {terminal && <li className="on term">{terminal.to_state}</li>}
    </ol>
  )
}
