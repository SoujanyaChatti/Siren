import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useI18n } from '../../i18n'
import { SEV_COLOR, SevIcon } from '../../severity'
import type { Severity } from '../../types'

export default function GaugeCard({ g, primary }: { g: any; primary: boolean }) {
  const { t } = useI18n()
  const s: Severity = g.severity ?? 'Unknown'
  const ch = g.change_60m_ft
  const trend = ch == null ? '' : ch > 0.05 ? `↑ ${t.live.rising} ${ch.toFixed(2)} ft/h` : ch < -0.05 ? `↓ ${t.live.falling} ${Math.abs(ch).toFixed(2)} ft/h` : `→ ${t.live.steady}`
  const fs = g.flood_stages_ft
  const obs = g.series.map((p: any) => ({ x: Date.parse(p.t), v: p.v }))
  const fc = (g.forecast?.series ?? []).map((p: any) => ({ x: Date.parse(p.t), f: p.v }))
  const data = [...obs, ...fc].sort((a, b) => a.x - b.x)
  const vals = data.map((d: any) => d.v ?? d.f)
  const lo = Math.min(...vals), hi = Math.max(...vals, fs.action ?? -Infinity)
  return (
    <article className={`gauge-card ${primary ? 'primary' : ''}`}>
      <header className="gc-top">
        {g.severity ? <SevIcon s={s} size={16} /> : <span className="muted">—</span>}
        <span className="gc-name" title={g.name}>{g.name}</span>
        <span className="muted small">{g.distance_km} {t.live.km}</span>
      </header>
      <div className="gc-row">
        <span className="gc-val num" style={{ color: g.severity ? SEV_COLOR[s] : undefined }}>{g.latest ? `${g.latest.value.toFixed(1)} ft` : '—'}</span>
        <span className="small muted">{trend}<br />{g.age_minutes} {t.live.minAgo}</span>
      </div>
      {data.length > 2 && (
        <div className="gc-chart" aria-hidden="true">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} hide />
              <YAxis hide domain={[Math.floor(lo - 0.5), Math.ceil(hi + 0.5)]} />
              <Tooltip labelFormatter={(x) => new Date(Number(x)).toLocaleString()} formatter={(v: number) => `${v.toFixed(2)} ft`}
                contentStyle={{ background: '#0f1726', border: '1px solid #2a3850', fontSize: 11 }} />
              {fs.action != null && fs.action <= hi + 0.5 && <ReferenceLine y={fs.action} stroke={SEV_COLOR.Watch} strokeDasharray="4 3" />}
              {fs.minor != null && fs.minor <= hi + 0.5 && <ReferenceLine y={fs.minor} stroke={SEV_COLOR.Warning} strokeDasharray="4 3" />}
              <ReferenceLine x={Date.now()} stroke="#94a3b8" strokeOpacity={0.5} />
              <Line dataKey="v" stroke="#4da3ff" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls />
              <Line dataKey="f" stroke="#c084fc" dot={false} strokeWidth={2} strokeDasharray="5 4" isAnimationActive={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <footer className="gc-foot small">
        {g.has_categories ? <span className="muted">Action {fs.action ?? '—'} · Minor {fs.minor ?? '—'} · Mod {fs.moderate ?? '—'} ft</span>
          : <span className="muted">{t.live.noCats}</span>}
        {g.forecast && <span className="fc-tag">{t.live.forecastPeak} {g.forecast.peak_ft} ft</span>}
        <a href={g.source_url} target="_blank" rel="noreferrer">NOAA ↗</a>
      </footer>
    </article>
  )
}
