import { useI18n } from '../../i18n'

export default function DecisionPanel({ st }: { st: any }) {
  const { t } = useI18n()
  return (
    <details className="panel decision">
      <summary><strong>{t.live.decided}</strong> <span className="muted small">· {st.rules.filter((r: any) => r.fired).length} rules fired</span></summary>
      <table className="rules-table">
        <tbody>{st.rules.map((r: any) => (
          <tr key={r.rule_id} className={r.fired ? 'fired' : ''}>
            <td><code>{r.rule_id}</code> <span className="muted small">v{r.version}</span></td>
            <td>{r.fired ? '● fired' : '○'}{r.held ? ' (held)' : ''}</td>
            <td className="small">{r.description}</td>
            <td className="small muted mono">{r.inputs_hash ? `#${r.inputs_hash}` : ''}</td>
          </tr>
        ))}</tbody>
      </table>
      <p className="small muted">{st.caveat}</p>
      <p className="small muted">{st.sources.join(' · ')}</p>
    </details>
  )
}
