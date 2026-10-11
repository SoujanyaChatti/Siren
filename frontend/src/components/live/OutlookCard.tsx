import { useI18n } from '../../i18n'
import { Panel } from '../ui/Panel'

const CAT_SEV: Record<string, string> = { below_action: 'Normal', action: 'Watch', minor: 'Warning', moderate: 'Emergency', major: 'Emergency' }

export default function OutlookCard({ st }: { st: any }) {
  const { t, lang } = useI18n()
  const o = st.outlook
  const fl = st.alerts.filter((a: any) => /Watch/.test(a.event) && a.flood_related)
  return (
    <Panel title={t.live.outlook} icon="📈" className="outlook">
      {o ? <p className={`outlook-line sev-text-${CAT_SEV[o.category]}`}>{o.text}</p> : <p className="muted">{t.live.noOutlook}</p>}
      {fl.map((a: any) => <p key={a.id} className="outlook-line">🏛 {a.event}: {a.headline}</p>)}
      <p className="muted small">{o ? `${o.source} · ${lang === 'es' ? 'emitido' : 'issued'} ${new Date(o.issued).toLocaleString(lang === 'es' ? 'es-US' : 'en-US', { timeZone: st.location.tz, weekday: 'short', hour: 'numeric', minute: '2-digit' })}` : 'NOAA National Water Prediction Service'}</p>
    </Panel>
  )
}
