import { fmtLocal, useI18n } from '../../i18n'

/** Timing vs official NWS warnings, broken into what SIREN actually does well and where it is slower. */
export default function TimingCard({ lt }: { lt: any }) {
  const { lang } = useI18n()
  if (!lt) return <p className="muted">…</p>
  const zones = lt.zones as any[]
  const bestWatch = Math.max(...zones.map((z) => z.watch_lead_minutes ?? -1e9))
  const relay = Math.max(...zones.map((z) => z.relay_minutes ?? 0))
  const worst = Math.min(...zones.map((z) => z.lead_minutes ?? 0))
  const m = (v: number) => `${Math.abs(Math.round(v))} min`
  return (
    <div className="timing">
      <div className="kpis">
        <div className="kpi"><span className="kpi-label">{lang === 'es' ? 'Primera señal de SIREN' : "SIREN's first signal (Watch)"}</span>
          <span className={`kpi-val ${bestWatch > 0 ? 'pos' : 'neg'}`}>{bestWatch > 0 ? `${m(bestWatch)} earlier` : `${m(bestWatch)} later`}</span>
          <span className="kpi-sub">{lang === 'es' ? 'vs alerta oficial (mejor zona)' : 'than the official warning (best zone)'}</span></div>
        <div className="kpi"><span className="kpi-label">{lang === 'es' ? 'Advertencia propia de SIREN' : "SIREN's own gauge Warning"}</span>
          <span className={`kpi-val ${worst > 0 ? 'pos' : 'neg'}`}>{worst > 0 ? `${m(worst)} earlier` : `${m(worst)} later`}</span>
          <span className="kpi-sub">{lang === 'es' ? 'los ríos responden después de la lluvia' : 'rivers rise after the rain the NWS sees on radar'}</span></div>
        <div className="kpi"><span className="kpi-label">{lang === 'es' ? 'Retransmite la alerta oficial' : 'Relays the official warning'}</span>
          <span className="kpi-val pos">≤ {m(relay)}</span>
          <span className="kpi-sub">{lang === 'es' ? 'en el idioma y voz del residente' : "in the resident's language and voice"}</span></div>
      </div>
      <table className="lead-table">
        <thead><tr><th>Zone</th><th>SIREN Watch</th><th>SIREN Warning</th><th>Official</th><th className="r">Warning lead</th><th className="r">Relay</th></tr></thead>
        <tbody>{zones.map((z) => (
          <tr key={z.zone_id}>
            <td><strong>{z.zone_id}</strong></td>
            <td title={z.siren_first_watch_rules.join(' + ')}>{fmtLocal(z.siren_first_watch_at, lang, true)}</td>
            <td title={z.siren_rules.join(' + ')}>{fmtLocal(z.siren_first_alert_at, lang, true)}</td>
            <td><a href={z.official_source_url} target="_blank" rel="noreferrer" title={z.official_event}>{fmtLocal(z.official_issued_at, lang, true)}</a></td>
            <td className={`r num ${z.lead_minutes > 0 ? 'pos' : 'neg'}`}>{z.lead_minutes == null ? '—' : `${z.lead_minutes > 0 ? '+' : ''}${Math.round(z.lead_minutes)} min`}</td>
            <td className="r num">{z.relay_minutes == null ? '—' : `${Math.round(z.relay_minutes)} min`}</td>
          </tr>
        ))}</tbody>
      </table>
      <details className="small muted"><summary>{lang === 'es' ? 'Por qué la anticipación es negativa' : 'Why is the Warning lead negative?'}</summary>
        <p>{lang === 'es'
          ? 'Las Advertencias de Inundación Repentina del NWS se basan en radar y en el juicio de pronosticadores: ven la lluvia antes de que los ríos suban. Las reglas de SIREN en la repetición usan medidores de río, que reaccionan después. Los umbrales se fijaron antes de comparar y no se ajustaron para ganar.'
          : "NWS Flash Flood Warnings are issued from radar rainfall estimates and forecaster judgment, so they see the rain before rivers respond. SIREN's replay rules use river gauges, which react later. Thresholds were fixed before the comparison and were not tuned to win it. SIREN's job is to add street-level depth, language access, voice and delivery tracking on top of official warnings, and in live mode it also shows the official NWS river forecast."}</p>
        <p>{lt.method}</p><p>{lt.caveat}</p>
      </details>
    </div>
  )
}
