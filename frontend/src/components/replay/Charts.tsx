import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtLocal, useI18n } from '../../i18n'
import { SEV_COLOR } from '../../severity'
import type { AppState } from '../../types'

type Series = Record<string, { t: string; v: number }[]>

export default function Charts({ state, series }: { state: AppState; series: Series | null }) {
  const { t } = useI18n()
  const start = Date.parse(state.clock.start) - 30 * 60000
  const end = Date.parse(state.clock.end)
  const now = Date.parse(state.clock.now)
  const ticks: number[] = []
  for (let x = Date.parse(state.clock.start); x <= end; x += 3 * 3600000) ticks.push(x)
  const fmt = (x: number) => fmtLocal(new Date(x).toISOString())

  return (
    <div className="charts">
      {state.gauges.map((g) => {
        const data = (series?.[g.station_id] ?? []).map((p) => ({ x: Date.parse(p.t), v: p.v }))
        const fs = g.flood_stages_ft
        const vals = data.map((d) => d.v)
        const lo = Math.floor(Math.min(...vals, fs.action - 6) - 1)
        const hi = Math.ceil(Math.max(...vals, fs.moderate) + 1)
        const overOf = (v?: number) => v == null ? 'Unknown' : (v >= fs.moderate ? 'Emergency' : v >= fs.minor ? 'Warning' : v >= fs.action ? 'Watch' : 'Normal')
        const last = data[data.length - 1]
        const summary = last
          ? `${g.name}: ${last.v.toFixed(1)} ft at ${fmt(last.x)}. Action ${fs.action}, minor ${fs.minor}, moderate ${fs.moderate} ft. ${last.v >= fs.minor ? 'Above minor flood stage.' : last.v >= fs.action ? 'Above action stage.' : 'Below action stage.'}`
          : `${g.name}: no data yet.`
        return (
          <figure key={g.station_id} className="chart">
            <figcaption>
              <div className="cap-top">
                <span className="cap-name">{g.name}</span>
                <span className={`fresh ${g.freshness}`}>{t.fresh[g.freshness]}</span>
                <span className="cap-val num" style={{ color: SEV_COLOR[overOf(last?.v) as keyof typeof SEV_COLOR] }}>{last ? `${last.v.toFixed(1)} ft` : '—'}</span>
              </div>
              <div className="cap-legend">
                <span><i style={{ borderColor: SEV_COLOR.Watch }} />{t.action} {fs.action}</span>
                <span><i style={{ borderColor: SEV_COLOR.Warning }} />{t.minor} {fs.minor}</span>
                <span><i style={{ borderColor: SEV_COLOR.Emergency }} />{t.moderate} {fs.moderate}</span>
                {hi > fs.major && <span><i style={{ borderColor: '#b388ff' }} />Major {fs.major}</span>}
              </div>
            </figcaption>
            <p className="sr-only">{summary}</p>
            <div aria-hidden="true" style={{ height: 140 }}>
              <ResponsiveContainer>
                <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="#1f2a3d" vertical={false} />
                  <XAxis dataKey="x" type="number" domain={[start, end]} ticks={ticks} tickFormatter={fmt} stroke="#6b7a90" fontSize={11} />
                  <YAxis domain={[lo, hi]} stroke="#6b7a90" fontSize={11} width={44} />
                  <Tooltip labelFormatter={(x) => fmt(Number(x))} formatter={(v: number) => [`${v.toFixed(2)} ft`, t.stage]}
                    contentStyle={{ background: '#0f1726', border: '1px solid #2a3850', fontSize: 12 }} />
                  <ReferenceLine y={fs.action} stroke={SEV_COLOR.Watch} strokeDasharray="5 4" />
                  <ReferenceLine y={fs.minor} stroke={SEV_COLOR.Warning} strokeDasharray="5 4" />
                  <ReferenceLine y={fs.moderate} stroke={SEV_COLOR.Emergency} strokeDasharray="5 4" />
                  {hi > fs.major && <ReferenceLine y={fs.major} stroke="#b388ff" strokeDasharray="2 3" />}
                  <ReferenceLine x={now} stroke="#e2e8f0" strokeOpacity={0.7} />
                  <Line type="monotone" dataKey="v" stroke="#4da3ff" strokeWidth={2.2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </figure>
        )
      })}
      <figure className="chart">
        <figcaption>
          <div className="cap-top"><span className="cap-name">☔ {t.rain15}</span>
            <span className="cap-val num">{Math.max(...state.rain.map((r) => r.last_hour_in)).toFixed(2)} in/h</span></div>
          <div className="cap-legend">{state.rain.map((r, i) => <span key={r.station_id}><i className="bar" style={{ background: i ? '#7dd3fc' : '#38bdf8' }} />{r.station_id}: {r.last_hour_in.toFixed(2)} in last hour</span>)}</div>
        </figcaption>
        <p className="sr-only">{state.rain.map((r) => `${r.name}: ${r.last_hour_in.toFixed(2)} inches in the last hour.`).join(' ')}</p>
        <div aria-hidden="true" style={{ height: 140 }}>
          <ResponsiveContainer>
            <BarChart data={mergeRain(state, series)} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
              <CartesianGrid stroke="#1f2a3d" vertical={false} />
              <XAxis dataKey="x" type="number" domain={[start, end]} ticks={ticks} tickFormatter={fmt} stroke="#6b7a90" fontSize={11} />
              <YAxis stroke="#6b7a90" fontSize={11} width={44} domain={[0, (m: number) => Math.max(0.5, Math.ceil(m * 2) / 2)]} />
              <Tooltip labelFormatter={(x) => fmt(Number(x))} formatter={(v: number, n: string) => [`${v.toFixed(2)} in`, n]} contentStyle={{ background: '#0f1726', border: '1px solid #2a3850', fontSize: 12 }} />
              <ReferenceLine x={now} stroke="#e2e8f0" />
              {state.rain.map((r, i) => <Bar key={r.station_id} dataKey={r.station_id} fill={i ? '#7dd3fc' : '#38bdf8'} isAnimationActive={false} barSize={3} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </figure>
    </div>
  )
}

function mergeRain(state: AppState, series: Series | null) {
  const m = new Map<number, any>()
  for (const r of state.rain) for (const p of series?.[r.station_id] ?? []) {
    const x = Date.parse(p.t)
    m.set(x, { ...(m.get(x) ?? { x }), [r.station_id]: p.v })
  }
  return [...m.values()].sort((a, b) => a.x - b.x)
}
