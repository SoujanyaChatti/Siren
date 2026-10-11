import { useState } from 'react'
import { post } from '../../api'
import { speak, useSpeech } from '../../hooks/useSpeech'
import { useI18n } from '../../i18n'
import { Panel } from '../ui/Panel'

/** Grounded Q&A: voice or text in, cited answer out (text + voice). */
export default function AskBox({ endpoint, body }: { endpoint: string; body: Record<string, unknown> }) {
  const { t, lang } = useI18n()
  const [q, setQ] = useState('')
  const [a, setA] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const ask = async (question: string) => {
    if (!question.trim() || busy) return
    setBusy(true)
    try {
      const r = await post(endpoint, { ...body, question, language: lang })
      setA(r); speak(r.answer, lang, r.audio_url)
    } catch (e) { setA({ answer: `⚠ ${(e as Error).message}`, citation_details: [] }) } finally { setBusy(false) }
  }
  const sp = useSpeech(lang, (text) => { setQ(text); ask(text) })
  return (
    <Panel title={t.live.ask} icon="💬">
      <form className="ask-row" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <button type="button" className={`mic ${sp.listening ? 'on' : ''}`} onClick={sp.listening ? sp.stop : sp.start} aria-label="Microphone">🎤</button>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.live.askPh} aria-label={t.live.ask} />
        <button type="submit" disabled={busy}>{busy ? '…' : t.send}</button>
      </form>
      {sp.err && <p className="small muted">⚠ {sp.err}</p>}
      {a && (
        <div className="answer">
          <p>{a.answer}</p>
          <div className="chips">{(a.citation_details ?? []).map((c: any) => (
            <a key={c.id} className="chip" title={c.text} href={c.source?.startsWith('http') ? c.source : undefined} target="_blank" rel="noreferrer">{c.id}</a>
          ))}</div>
        </div>
      )}
    </Panel>
  )
}
