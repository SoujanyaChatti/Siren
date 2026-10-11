import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import AlertsList from '../components/live/AlertsList'
import AskBox from '../components/live/AskBox'
import DecisionPanel from '../components/live/DecisionPanel'
import GaugeCard from '../components/live/GaugeCard'
import LiveMap from '../components/live/LiveMap'
import LocationBar from '../components/live/LocationBar'
import OutlookCard from '../components/live/OutlookCard'
import PhotoCheck from '../components/live/PhotoCheck'
import StatusHero from '../components/live/StatusHero'
import AppShell from '../components/shell/AppShell'
import { Panel } from '../components/ui/Panel'
import { useLiveLocation } from '../hooks/useLiveLocation'
import { useI18n } from '../i18n'

/** Home: live flood status where the person is, right now (and the official outlook). */
export default function LiveHome() {
  const { t, lang } = useI18n()
  const { loc, locating, error, locate, search } = useLiveLocation()
  const [st, setSt] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!loc) return
    setBusy(true); setErr(null)
    try { setSt(await api(`/api/live/status?lat=${loc.lat}&lon=${loc.lon}&lang=${lang}`)) }
    catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }, [loc?.lat, loc?.lon, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load() }, [load])
  useEffect(() => {  // re-check every 5 minutes (server caches upstream data)
    const id = window.setInterval(load, 5 * 60 * 1000)
    return () => window.clearInterval(id)
  }, [load])

  const showOnboarding = !loc && !locating
  return (
    <AppShell>
      <div className="live-head">
        <div>
          <h1 className="page-title">{t.live.title}</h1>
          <p className="muted">{t.live.sub}</p>
        </div>
        {(loc || st) && <LocationBar compact place={st?.location?.place ?? '…'} locating={locating} onLocate={locate} onSearch={search} />}
      </div>

      {showOnboarding && (
        <Panel className="onboard">
          <p className="onboard-lead">{error === 'geo' ? t.live.locErr : t.live.allow}</p>
          {error && error !== 'geo' && <p className="note warn">⚠ {error}</p>}
          <LocationBar compact={false} locating={locating} onLocate={locate} onSearch={search} />
        </Panel>
      )}
      {(locating || (busy && !st)) && <div className="loading-card" aria-live="polite"><span className="spinner" aria-hidden="true" />{t.live.checking}</div>}
      {err && <p className="note warn" role="alert">⚠ {err}</p>}

      {st && (
        <>
          <div className="live-grid">
            <div className="stack">
              <StatusHero st={st} onRefresh={load} busy={busy} />
              <OutlookCard st={st} />
            </div>
            <LiveMap st={st} />
          </div>

          <Panel title={t.live.gauges} icon="🌊"
            actions={st.rain && <span className="muted small">☔ {t.live.rain}: <strong>{st.rain.last_hour_in.toFixed(2)} in</strong> · {st.rain.name}</span>}>
            {st.gauges.length === 0 ? <p className="muted">{st.missing_data.join(' · ')}</p> : (
              <div className="gauge-grid">
                {st.gauges.map((g: any) => <GaugeCard key={g.station_id} g={g} primary={g.station_id === st.primary_gauge} />)}
              </div>
            )}
          </Panel>

          <div className="grid-3">
            <AlertsList alerts={st.alerts} />
            <AskBox endpoint="/api/live/ask" body={{ lat: Number(loc!.lat), lon: Number(loc!.lon) }} />
            <PhotoCheck lat={loc!.lat} lon={loc!.lon} />
          </div>

          <DecisionPanel st={st} />
        </>
      )}

      <Link to="/replay" className="replay-cta">
        <span className="replay-cta-icon" aria-hidden="true">⏪</span>
        <span><strong>{t.live.replayCta} →</strong><br /><span className="muted small">{t.live.replayCtaSub}</span></span>
      </Link>
    </AppShell>
  )
}
