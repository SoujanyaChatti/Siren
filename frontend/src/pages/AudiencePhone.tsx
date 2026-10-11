import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import ResidentPhone from '../components/replay/ResidentPhone'
import type { Lang } from '../i18n'

export default function AudiencePhone() {
  const { sid = '' } = useParams()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const lang = (params.get('lang') === 'es' ? 'es' : 'en') as Lang
  return (
    <main className="audience-phone">
      <ResidentPhone residentId={sid} kind="audience" lang={lang} feedPath={`/api/audience/${sid}/feed`}
        header={<div className="aud-head"><span className="wordmark dark">SIREN</span></div>}
        onSessionLost={() => nav('/join', { replace: true })} />
    </main>
  )
}
