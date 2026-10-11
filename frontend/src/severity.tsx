import type { Severity } from './types'

export const SEV_COLOR: Record<Severity, string> = {
  Normal: '#3b82f6',     // blue
  Watch: '#f2b705',      // amber
  Warning: '#f0642e',    // orange-red
  Emergency: '#d6338a',  // magenta
  Unknown: '#8b93a1',    // grey
}
export const SEV_TEXT_ON: Record<Severity, string> = {
  Normal: '#ffffff', Watch: '#1a1300', Warning: '#1a0700', Emergency: '#ffffff', Unknown: '#0b0f16',
}
export const SEV_ORDER: Severity[] = ['Normal', 'Watch', 'Warning', 'Emergency']

/** Distinct shape per level so severity never relies on colour alone. */
export function SevIcon({ s, size = 16, title, fill, inner }: { s: Severity; size?: number; title?: string; fill?: string; inner?: string }) {
  const c = fill ?? SEV_COLOR[s]
  const k = inner ?? SEV_TEXT_ON[s]
  const common = { width: size, height: size, viewBox: '0 0 24 24', role: 'img' as const, 'aria-label': title ?? s }
  switch (s) {
    case 'Normal':
      return (<svg {...common}><circle cx="12" cy="12" r="10" fill={c} /><path d="M7 12.5l3.2 3.2L17 9" stroke={k} strokeWidth="2.4" fill="none" strokeLinecap="round" /></svg>)
    case 'Watch':
      return (<svg {...common}><rect x="3" y="3" width="18" height="18" rx="3" transform="rotate(45 12 12)" fill={c} /><rect x="11" y="6.5" width="2" height="7" fill={k} /><rect x="11" y="15.5" width="2" height="2" fill={k} /></svg>)
    case 'Warning':
      return (<svg {...common}><path d="M12 2L23 21H1z" fill={c} /><rect x="11" y="8" width="2" height="7" fill={k} /><rect x="11" y="16.5" width="2" height="2" fill={k} /></svg>)
    case 'Emergency':
      return (<svg {...common}><path d="M8 2h8l6 6v8l-6 6H8l-6-6V8z" fill={c} /><rect x="6" y="10.5" width="12" height="3" fill={k} /></svg>)
    default:
      return (<svg {...common}><rect x="2" y="2" width="20" height="20" rx="4" fill={c} /><text x="12" y="17" textAnchor="middle" fontSize="14" fontWeight="700" fill={k}>?</text></svg>)
  }
}

export function SevBadge({ s, label, large }: { s: Severity; label?: string; large?: boolean }) {
  return (
    <span className={`sev-badge ${large ? 'lg' : ''}`} style={{ background: SEV_COLOR[s], color: SEV_TEXT_ON[s] }}>
      <SevIcon s={s} size={large ? 22 : 15} title="" fill={SEV_TEXT_ON[s]} inner={SEV_COLOR[s]} />
      <span>{label ?? s}</span>
    </span>
  )
}
