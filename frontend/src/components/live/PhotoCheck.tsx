import { useState } from 'react'
import { apiUrl } from '../../api'
import { useI18n } from '../../i18n'
import { Panel } from '../ui/Panel'

/** Photo -> depth estimate at your location, with the same do-not-drive rule as the replay. */
export default function PhotoCheck({ lat, lon }: { lat: string; lon: string }) {
  const { t, lang } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const pick = (f: File | null) => { setFile(f); setRes(null); setPreview(f ? URL.createObjectURL(f) : null) }
  const send = async () => {
    if (!file) return
    setBusy(true); setErr(null)
    try {
      const fd = new FormData()
      fd.append('image', file); fd.append('lat', lat); fd.append('lon', lon); fd.append('lang', lang)
      const r = await fetch(apiUrl('/api/live/photo'), { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json()).detail ?? r.status)
      setRes(await r.json())
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const a = res?.analysis
  return (
    <Panel title={t.live.photo} icon="📷">
      <p className="muted small">{t.live.photoHelp}</p>
      <div className="photo-row">
        <label className="file-btn">
          <input type="file" accept="image/*" capture="environment" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          {file ? file.name : (lang === 'es' ? 'Elegir foto' : 'Choose photo')}
        </label>
        <button onClick={send} disabled={!file || busy}>{busy ? '…' : t.live.photoSend}</button>
      </div>
      {err && <p className="note warn">⚠ {err}</p>}
      {preview && (
        <div className="photo-wrap">
          <img src={preview} alt="" />
          {a?.waterline_y != null && <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="1" y1={a.waterline_y} y2={a.waterline_y} stroke="#4dd2ff" strokeWidth="0.005" strokeDasharray="0.02 0.01" /></svg>}
        </div>
      )}
      {res && (
        <div className={`photo-verdict ${res.do_not_drive ? 'danger' : ''}`}>
          <strong>{res.do_not_drive ? (lang === 'es' ? '⛔ No maneje aquí' : '⛔ Do not drive here') : (lang === 'es' ? 'Resultado' : 'Result')}</strong>
          <p>{res.message}</p>
          <div className="chips">
            <span className="chip">{res.checks.status}</span>
            {a?.confidence != null && <span className="chip ghost">conf {Number(a.confidence).toFixed(2)}</span>}
            {res.checks.flags.map((f: string) => <span key={f} className="chip ghost">{f}</span>)}
            <span className="chip ghost">{res.ai.path} · {res.ai.model}</span>
          </div>
          {res.checks.reasons.map((r: string) => <p key={r} className="small muted">{r}</p>)}
        </div>
      )}
    </Panel>
  )
}
