import { fmtLocal, useI18n } from '../../i18n'
import { SevBadge } from '../../severity'
import type { Severity } from '../../types'

export default function Timeline({ items, onOpen }: { items: any[]; onOpen: (alertId: string) => void }) {
  const { lang } = useI18n()
  if (!items.length) {
    return (
      <div className="tl-empty">
        <p>{lang === 'es' ? 'Todo tranquilo por ahora.' : 'All quiet so far.'}</p>
        <p className="muted small">{lang === 'es' ? 'Presione ▶ o elija una escena. Cada cambio de nivel, alerta oficial y entrega aparecerá aquí.' : 'Press ▶ or pick a scene. Every severity change, official warning and alert delivery appears here.'}</p>
      </div>
    )
  }
  // Resident deliveries only show the moments that matter: delivered and acknowledged
  const shown = items.filter((it) => it.kind !== 'delivery' || ['Delivered', 'Acknowledged'].includes(it.to))
  return (
    <ol className="timeline">
      {shown.map((it, i) => {
        const time = fmtLocal(it.time, lang, true)
        if (it.kind === 'severity') {
          return (
            <li key={i} className="tl sev" style={{ borderLeftColor: `var(--sev-${it.to})` }}>
              <time>{time}</time>
              <div className="tl-main">
                <div className="tl-line"><strong>Zone {it.zone_id}</strong> <SevBadge s={it.from as Severity} /> <span className="arrow">→</span> <SevBadge s={it.to as Severity} /></div>
                <div className="tl-sub">{it.rules.length ? it.rules.join(' + ') : 'no rules firing'}{it.missing?.length ? ` · ⚠ ${it.missing.join('; ')}` : ''}</div>
              </div>
            </li>
          )
        }
        if (it.kind === 'official') {
          return (
            <li key={i} className="tl official">
              <time>{time}</time>
              <div className="tl-main">
                <div className="tl-line"><strong>🏛 NWS</strong> {it.event}</div>
                <div className="tl-sub"><a href={it.source_url} target="_blank" rel="noreferrer">{it.warning_id}</a></div>
              </div>
            </li>
          )
        }
        const label = it.kind === 'alert' ? `Alert ${it.alert_id}` : `${it.user_id} (${it.language})`
        return (
          <li key={i} className={`tl ${it.kind}`}>
            <time>{time}</time>
            <button className="tl-btn" onClick={() => onOpen(it.alert_id)}>
              <span className="tl-line">{it.kind === 'alert' ? '🔔' : '📱'} {label} <span className="state-pill">{it.to}</span></span>
              <span className="tl-sub">{it.actor}{it.note ? ` · ${it.note}` : ''}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
