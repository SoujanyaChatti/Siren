import { useI18n } from '../../i18n'
import { Panel } from '../ui/Panel'

export default function AlertsList({ alerts }: { alerts: any[] }) {
  const { t } = useI18n()
  return (
    <Panel title={t.live.alerts} icon="🏛" actions={<span className="count">{alerts.length}</span>}>
      {alerts.length === 0 ? <p className="muted">{t.live.noAlerts}</p> : (
        <ul className="nws-list">
          {alerts.map((a) => (
            <li key={a.id} className={a.flood_related ? 'flood' : ''}>
              <details>
                <summary><strong>{a.event}</strong> <span className="muted small">· {a.severity}</span></summary>
                <p className="small">{a.headline}</p>
                {a.instruction && <p className="small muted">{a.instruction}</p>}
                <a className="small" href={a.url} target="_blank" rel="noreferrer">NWS ↗</a>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
