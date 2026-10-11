import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { I18nProvider } from './i18n'
import AudiencePhone from './pages/AudiencePhone'
import HowItWorks from './pages/HowItWorks'
import Join from './pages/Join'
import LiveHome from './pages/LiveHome'
import ReplayPage from './pages/ReplayPage'

export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LiveHome />} />
          <Route path="/live" element={<LiveHome />} />
          <Route path="/replay" element={<ReplayPage />} />
          <Route path="/how" element={<HowItWorks />} />
          <Route path="/join" element={<Join />} />
          <Route path="/r/:sid" element={<AudiencePhone />} />
          <Route path="*" element={<LiveHome />} />
        </Routes>
      </BrowserRouter>
    </I18nProvider>
  )
}
