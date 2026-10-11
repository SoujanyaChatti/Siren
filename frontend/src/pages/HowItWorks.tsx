import { useEffect, useState } from 'react'
import { api, apiUrl } from '../api'
import AppShell from '../components/shell/AppShell'
import { Panel } from '../components/ui/Panel'
import { useI18n } from '../i18n'

/** Methods for judges: rules, depth validation, timing vs official warnings, sources and limits. */
export default function HowItWorks() {
  const { lang } = useI18n()
  const es = lang === 'es'
  const [rules, setRules] = useState<any>(null)
  const [val, setVal] = useState<any>(null)
  const [timing, setTiming] = useState<any[] | null>(null)
  useEffect(() => {
    api('/api/rules').then(setRules)
    api('/api/validation').then(setVal)
    api('/api/lead-time/all').then(setTiming)
  }, [])
  const sum = val?.results?.summary
  const rows: any[] = val?.results?.rows ?? []

  return (
    <AppShell>
      <h1 className="page-title">{es ? 'Cómo funciona SIREN' : 'How SIREN works'}</h1>
      <p className="lead-p">{es
        ? 'Las reglas deciden, la IA explica. Cada alerta se puede rastrear hasta las lecturas, una regla versionada y su ciclo de vida.'
        : 'Rules decide, AI explains. Every alert traces back to source readings, a versioned rule and a timestamped lifecycle.'}</p>

      <div className="how-steps">
        {[
          ['📡', es ? 'Datos' : 'Data', es ? 'Medidores NOAA/USGS, alertas y pronósticos del NWS, lluvia, fotos de residentes.' : 'NOAA/USGS river gauges, NWS alerts and forecasts, rain, residents’ photos.'],
          ['⚖️', es ? 'Reglas' : 'Rules', es ? 'Umbrales oficiales, histéresis, datos faltantes nunca son "seguro".' : 'Official thresholds, hysteresis; missing data is never "safe".'],
          ['🗣', es ? 'Comunicar' : 'Communicate', es ? 'Texto fijo, traducción validada, voz, preguntas con citas.' : 'Fixed template, validated translation, voice, cited answers.'],
          ['🧾', es ? 'Verificar' : 'Verify', es ? 'Evidencia, hash de entradas y estados de entrega por residente.' : 'Evidence, inputs hash and per-resident delivery states.'],
        ].map(([i, h, d]) => <div key={h} className="how-step"><span className="how-icon">{i}</span><strong>{h}</strong><span className="muted small">{d}</span></div>)}
      </div>

      <Panel title={es ? 'Validación de profundidad por foto' : 'Photo depth validation'} icon="📷" id="validation">
        {sum ? (
          <>
            <div className="kpis">
              <div className="kpi"><span className="kpi-label">{es ? 'Fotos evaluadas' : 'Photos scored'}</span><span className="kpi-val">{sum.n_scored}/{sum.n_photos}</span></div>
              <div className="kpi"><span className="kpi-label">{es ? 'Error absoluto medio' : 'Mean absolute error'}</span><span className="kpi-val">{sum.mae_in} in</span></div>
              <div className="kpi"><span className="kpi-label">{es ? 'Profundidad real dentro del rango' : 'Judged depth inside range'}</span><span className="kpi-val">{Math.round(sum.range_coverage * 100)}%</span></div>
              <div className="kpi"><span className="kpi-label">{es ? 'Verificadas (pueden alertar)' : 'Verified (can fire alerts)'}</span><span className="kpi-val">{Math.round(sum.verified_share * 100)}%</span></div>
            </div>
            <p className="muted small">{es ? 'Muestra pequeña. La profundidad "real" es una estimación humana a partir de objetos de referencia.' : 'Small sample. "True" depth is itself a human judgement from reference objects.'} {sum.note} {val.results.model ? `Model: ${val.results.model}.` : ''}</p>
            <div className="val-grid">
              {rows.map((r) => (
                <figure key={r.file} className="val-card">
                  <img src={apiUrl(`/api/validation/image/${r.file}`)} alt="" loading="lazy" />
                  <figcaption>
                    <span>{es ? 'Juzgado' : 'Judged'} <strong>{r.truth_range[0]}–{r.truth_range[1]} in</strong></span>
                    <span>SIREN <strong>{r.estimate_in ?? '—'}{r.estimate_in != null ? ` (${r.range[0]}–${r.range[1]}) in` : ''}</strong></span>
                    <span className={`chip ${r.truth_in_range ? 'verified' : r.estimate_in == null ? 'unverified' : 'rejected'}`}>{r.estimate_in == null ? r.status : r.truth_in_range ? '✓ in range' : `off by ${r.abs_error_in} in`}</span>
                  </figcaption>
                </figure>
              ))}
            </div>
          </>
        ) : (
          <p className="muted">{es ? `Conjunto de ${val?.manifest?.length ?? 0} fotos listo; la validación aún no se ha ejecutado.` : `${val?.manifest?.length ?? 0} judged photos ready; the validation run hasn't happened yet (needs a Gemini key: scripts/validate_depth.py).`}</p>
        )}
      </Panel>

      <Panel title={es ? 'Tiempos frente a alertas oficiales (5 tormentas)' : 'Timing vs official warnings (5 storms)'} icon="⏱">
        <p className="small muted">{es
          ? 'Las alertas del NWS usan radar y pronosticadores; las reglas de SIREN en repetición usan medidores de río, que reaccionan después. Lo reportamos tal cual.'
          : 'NWS warnings use radar and forecasters; SIREN’s replay rules use river gauges, which respond later. Reported as-is; thresholds were fixed before comparing.'}</p>
        <table className="lead-table">
          <thead><tr><th>{es ? 'Tormenta' : 'Storm'}</th><th className="r">{es ? 'Primera Vigilancia' : 'First Watch'}</th><th className="r">{es ? 'Advertencia propia' : 'Own Warning'}</th><th className="r">{es ? 'Retransmisión' : 'Relay'}</th></tr></thead>
          <tbody>{(timing ?? []).map((a) => {
            const best = (k: string) => Math.max(...a.zones.map((z: any) => z[k] ?? -1e9))
            const fmt = (v: number) => v <= -1e8 ? '—' : `${v > 0 ? '+' : ''}${Math.round(v)} min`
            const relay = Math.max(...a.zones.map((z: any) => z.relay_minutes ?? 0))
            return (
              <tr key={a.area.id}>
                <td>{a.area.storm}<br /><span className="muted small">{a.area.name}</span></td>
                <td className={`r num ${best('watch_lead_minutes') > 0 ? 'pos' : 'neg'}`}>{fmt(best('watch_lead_minutes'))}</td>
                <td className={`r num ${best('lead_minutes') > 0 ? 'pos' : 'neg'}`}>{fmt(best('lead_minutes'))}</td>
                <td className="r num">≤ {Math.round(relay)} min</td>
              </tr>
            )
          })}</tbody>
        </table>
        <p className="small muted">{es ? '+ = SIREN antes que la alerta oficial (mejor zona). Retransmisión = tiempo hasta que SIREN entrega la alerta oficial en el idioma del residente.' : '+ = SIREN earlier than the official warning (best zone). Relay = time for SIREN to deliver the official warning in the resident’s language.'}</p>
      </Panel>

      <Panel title={es ? 'Reglas (versionadas)' : 'Rules (versioned)'} icon="⚖️">
        <table className="rules-table">
          <tbody>{(rules?.rules ?? []).map((r: any) => (
            <tr key={r.id}><td><code>{r.id}</code> <span className="muted small">v{r.version}</span></td><td className="small">{es ? r.description_es : r.description}</td><td className="small">{r.severity ?? (r.effect ? `+${r.effect.raise_levels} (max ${r.effect.max})` : '—')}</td></tr>
          ))}</tbody>
        </table>
        <p className="small muted">{es ? 'Histéresis: sube de inmediato; baja solo tras 2 evaluaciones falsas y 0.3 pies bajo el umbral.' : 'Hysteresis: escalate immediately; de-escalate only after 2 false evaluations and 0.3 ft below the threshold.'} ruleset {rules?.ruleset_version}</p>
      </Panel>

      <Panel title={es ? 'Límites' : 'Limits'} icon="⚠️">
        <ul className="small">
          <li>{es ? 'No es un sistema oficial de alertas; enlaza a las alertas oficiales.' : 'Not an official warning system; it links to official warnings.'}</li>
          <li>{es ? 'En vivo: solo EE. UU.; datos provisionales con 30–60 min de retraso.' : 'Live: US only; provisional data, 30–60 min behind.'}</li>
          <li>{es ? 'Un medidor mide el río en un punto; la inundación de calles puede ocurrir lejos de los ríos.' : 'A gauge measures the river at one point; street flooding can happen away from rivers.'}</li>
          <li>{es ? 'Las zonas de las repeticiones están dibujadas a mano para la demo.' : 'Replay zones are hand-drawn for the demo.'}</li>
        </ul>
      </Panel>
    </AppShell>
  )
}
