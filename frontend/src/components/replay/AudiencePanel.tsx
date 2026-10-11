import { QRCodeSVG } from 'qrcode.react'
import { post } from '../../api'
import { useI18n } from '../../i18n'
import type { AudienceSummary } from '../../types'

export default function AudiencePanel({ summary, runId }: { summary: AudienceSummary; runId: string }) {
  const { t } = useI18n()
  const base = (import.meta.env.VITE_PUBLIC_URL as string | undefined) || window.location.origin
  const url = `${base.replace(/\/$/, '')}/join?run=${runId}`
  return (
    <div className="audience" aria-label={t.audience}>
      <div className="aud-grid">
        <a href={url} target="_blank" rel="noreferrer" className="qr" aria-label={`Join link ${url}`}>
          <QRCodeSVG value={url} size={116} bgColor="#ffffff" fgColor="#0b1220" includeMargin />
        </a>
        <div className="aud-info">
          <div className="muted small">{t.scanToJoin}</div>
          <div className="join-url" title={url}>{url.replace(/^https?:\/\//, '')}</div>
          <dl className="counts" aria-live="polite">
            <div><dt>{t.joined}</dt><dd>{summary.joined}</dd></div>
            <div><dt>{t.delivered}</dt><dd>{summary.delivered}</dd></div>
            <div><dt>{t.acked}</dt><dd>{summary.acknowledged}</dd></div>
          </dl>
          <div className="muted small">EN {summary.by_language.en ?? 0} · ES {summary.by_language.es ?? 0}
            {summary.median_seconds_to_ack != null && <> · {t.medianAck} <strong>{summary.median_seconds_to_ack}s</strong></>}
            {' · '}<button className="link small" onClick={() => post('/api/audience/reset')}>Reset</button></div>
        </div>
      </div>
    </div>
  )
}
