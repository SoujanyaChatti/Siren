import { useId, useRef, type ReactNode } from 'react'

export interface TabDef { id: string; label: ReactNode; badge?: ReactNode; content: ReactNode }

/** Accessible tabs (arrow keys move between tabs). Only the active panel is rendered. */
export function Tabs({ tabs, active, onChange, label }: { tabs: TabDef[]; active: string; onChange: (id: string) => void; label: string }) {
  const uid = useId()
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  const idx = Math.max(0, tabs.findIndex((t) => t.id === active))
  const move = (d: number) => {
    const next = tabs[(idx + d + tabs.length) % tabs.length]
    onChange(next.id)
    refs.current[next.id]?.focus()
  }
  return (
    <div className="tabs">
      <div className="tab-list" role="tablist" aria-label={label}
        onKeyDown={(e) => { if (e.key === 'ArrowRight') move(1); if (e.key === 'ArrowLeft') move(-1) }}>
        {tabs.map((t) => (
          <button key={t.id} ref={(el) => { refs.current[t.id] = el }} role="tab" id={`${uid}-${t.id}`}
            aria-selected={t.id === tabs[idx].id} aria-controls={`${uid}-${t.id}-p`} tabIndex={t.id === tabs[idx].id ? 0 : -1}
            className={t.id === tabs[idx].id ? 'on' : ''} onClick={() => onChange(t.id)}>
            {t.label}{t.badge != null && <span className="tab-badge">{t.badge}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${uid}-${tabs[idx].id}-p`} aria-labelledby={`${uid}-${tabs[idx].id}`} className="tab-panel">
        {tabs[idx].content}
      </div>
    </div>
  )
}
