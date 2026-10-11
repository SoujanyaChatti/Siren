import { useI18n } from '../../i18n'

export default function Footer({ rainSource }: { rainSource?: string }) {
  const { t } = useI18n()
  return (
    <footer className="footer">
      <strong>{t.notOfficial}</strong>
      <span>Data: NOAA/NWS National Water Prediction Service (gauges, flood categories, forecasts) · USGS Water Data · NWS alerts and observations ·
        {rainSource ? ` ${rainSource} ·` : ''} NWS warning archive via Iowa Environmental Mesonet · Map data © OpenStreetMap contributors ·
        Voice by ElevenLabs · AI: Google Gemini with Groq fallback.</span>
    </footer>
  )
}
