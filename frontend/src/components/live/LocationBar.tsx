import { useState } from 'react'
import { useI18n } from '../../i18n'

const EXAMPLES = ['Houston, TX', 'St. Louis, MO', 'Asheville, NC', 'Sacramento, CA', 'New Orleans, LA']

export default function LocationBar({ place, locating, onLocate, onSearch, compact }: {
  place?: string; locating: boolean; onLocate: () => void; onSearch: (q: string) => void; compact: boolean
}) {
  const { t } = useI18n()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(!compact)
  if (compact && !open) {
    return (
      <div className="locbar compact">
        <span className="loc-place">📍 {place}</span>
        <button className="ghost small" onClick={() => setOpen(true)}>{t.live.change}</button>
      </div>
    )
  }
  return (
    <div className="locbar">
      <button className="btn-primary" onClick={onLocate} disabled={locating}>📍 {t.live.useLoc}</button>
      <form className="loc-search" onSubmit={(e) => { e.preventDefault(); onSearch(q); setOpen(false) }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.live.search} aria-label={t.live.search} />
        <button type="submit" disabled={locating}>{t.live.go}</button>
      </form>
      <div className="loc-examples"><span className="muted">{t.live.try}:</span>
        {EXAMPLES.map((x) => <button key={x} className="chip-btn" onClick={() => { setQ(x); onSearch(x); setOpen(false) }}>{x}</button>)}
      </div>
    </div>
  )
}
