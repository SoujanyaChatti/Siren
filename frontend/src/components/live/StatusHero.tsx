import { useState } from 'react'
import { speakOnDemand } from '../../hooks/useSpeech'
import { useI18n } from '../../i18n'
import { SEV_COLOR, SEV_TEXT_ON, SevIcon } from '../../severity'
import type { Severity } from '../../types'

export default function StatusHero({ st, onRefresh, busy }: { st: any; onRefresh: () => void; busy: boolean }) {
  const { t, lang } = useI18n()
  const [voice, setVoice] = useState<string | null>(null)
  const sev: Severity = st.severity
  const checked = new Date(st.checked_at).toLocaleTimeString(lang === 'es' ? 'es-US' : 'en-US',
    { timeZone: st.location.tz, hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
  return (
    <section className="hero" style={{ borderColor: SEV_COLOR[sev] }} aria-live="polite" aria-label={st.card.headline}>
      <div className="hero-band" style={{ background: SEV_COLOR[sev], color: SEV_TEXT_ON[sev] }}>
        <SevIcon s={sev} size={26} fill={SEV_TEXT_ON[sev]} inner={SEV_COLOR[sev]} />
        <span className="hero-sev">{st.card.severity_word}</span>
        <span className="hero-place">📍 {st.location.place || `${st.location.lat}, ${st.location.lon}`}</span>
      </div>
      <div className="hero-body">
        <h1 className="hero-headline">{st.card.headline}</h1>
        <dl className="hero-lines">
          <div><dt>{lang === 'es' ? 'Qué' : 'What'}</dt><dd>{st.card.what}</dd></div>
          <div><dt>{lang === 'es' ? 'Dónde' : 'Where'}</dt><dd>{st.card.where}</dd></div>
          <div><dt>{lang === 'es' ? 'Qué hacer' : 'Do'}</dt><dd><strong>{st.card.action}</strong></dd></div>
        </dl>
        {st.missing_data?.length > 0 && <p className="note warn">⚠ {st.missing_data.join(' · ')}</p>}
        <div className="hero-actions">
          <button className="btn-play" onClick={async () => setVoice(await speakOnDemand(st.text, lang))}>▶ {t.live.play}</button>
          {voice && <span className="muted small">{voice === 'elevenlabs' ? t.voiceBy : t.voiceBrowser}</span>}
        </div>
        <details className="transcript"><summary>{t.live.transcript}</summary><p>{st.text}</p></details>
        <div className="hero-meta muted small">
          {t.live.checked} {checked} · <button className="link" onClick={onRefresh} disabled={busy}>↻ {t.live.refresh}</button>
        </div>
      </div>
    </section>
  )
}
