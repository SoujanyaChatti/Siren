import { useState } from 'react'
import { post } from '../../api'
import type { AppState, User } from '../../types'

/** Hidden presenter controls (Shift+D). */
export default function DirectorPanel({ state, users, onClose, onPersona }: { state: AppState; users: User[]; onClose: () => void; onPersona: (id: string) => void }) {
  const [msg, setMsg] = useState('')
  const run = async (label: string, fn: () => Promise<any>) => {
    setMsg(`${label}…`)
    try { await fn(); setMsg(`${label} ✓`) } catch (e) { setMsg(`${label} failed: ${(e as Error).message}`) }
  }
  return (
    <div className="director" role="dialog" aria-label="Director panel">
      <header><strong>🎬 Director</strong> <button onClick={onClose} aria-label="Close director">✕</button></header>
      <div className="dgrid">
        <button onClick={() => run('Photo report', () => post('/api/director', { action: 'photo' }))}>📷 Trigger demo photo report</button>
        <button onClick={() => run('Fallback', () => post('/api/director', { action: 'force_fallback', value: !state.force_gemini_failure }))}>
          ⚑ {state.force_gemini_failure ? 'Restore Gemini' : 'Force Gemini failure'}</button>
        <button onClick={() => run('Surge', () => post('/api/simulate', { rise_to: 'moderate' }))}>🌊 Simulate surge (backup)</button>
        {users.map((u) => <button key={u.id} onClick={() => onPersona(u.id)}>👤 {u.name}</button>)}
        <button onClick={() => run('Reset', () => post('/api/director', { action: 'reset_all' }))}>⟲ Reset everything</button>
      </div>
      <div className="muted small">{msg} · Gemini fallback forced: {String(state.force_gemini_failure)}</div>
    </div>
  )
}
