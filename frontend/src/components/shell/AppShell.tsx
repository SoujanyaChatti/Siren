import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useI18n } from '../../i18n'
import Footer from './Footer'

/** Top navigation shared by the Live, Replay and How-it-works pages. */
export default function AppShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { t, lang, setLang } = useI18n()
  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <header className="nav">
        <NavLink to="/" className="nav-brand" aria-label="SIREN home"><span className="wordmark">SIREN</span></NavLink>
        <nav className="nav-links" aria-label="Main">
          <NavLink to="/" end><span className="live-dot" aria-hidden="true" />{t.nav.live}</NavLink>
          <NavLink to="/replay">{t.nav.replay}</NavLink>
          <NavLink to="/how">{t.nav.how}</NavLink>
        </nav>
        <button className="lang" onClick={() => setLang(lang === 'en' ? 'es' : 'en')} aria-label={t.language}>
          {lang === 'en' ? 'Español' : 'English'}
        </button>
      </header>
      <main id="main" className={`page ${wide ? 'wide' : ''}`}>{children}</main>
      <Footer />
    </div>
  )
}
