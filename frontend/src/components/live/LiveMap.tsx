import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { useI18n } from '../../i18n'
import { SEV_COLOR } from '../../severity'
import type { Severity } from '../../types'

/** Your location, nearby gauges coloured by SIREN severity, and official NWS alert areas. */
export default function LiveMap({ st }: { st: any }) {
  const { t } = useI18n()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map>()
  const layer = useRef<L.LayerGroup>()

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { scrollWheelZoom: false }).setView([39, -96], 4)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, className: 'dark-tiles', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = undefined }
  }, [])

  useEffect(() => {
    const m = map.current, g = layer.current
    if (!m || !g || !st) return
    g.clearLayers()
    const pts: L.LatLngExpression[] = [[st.location.lat, st.location.lon]]
    L.circleMarker([st.location.lat, st.location.lon], { radius: 9, color: '#fff', weight: 3, fillColor: '#4da3ff', fillOpacity: 1 })
      .bindTooltip(t.live.you, { permanent: true, direction: 'top', offset: [0, -8], className: 'you-tip' }).addTo(g)
    for (const gg of st.gauges) {
      const c = gg.severity ? SEV_COLOR[gg.severity as Severity] : SEV_COLOR.Unknown
      const icon = L.divIcon({ className: 'gauge-icon', iconSize: [90, 24], iconAnchor: [10, 12],
        html: `<div class="gauge-pin" style="border-color:${c}"><span style="color:${c}">▲</span>${gg.latest ? gg.latest.value.toFixed(1) : '—'} ft</div>` })
      L.marker([gg.lat, gg.lon], { icon, alt: gg.name }).bindTooltip(`${gg.name}<br/>${gg.distance_km} km`).addTo(g)
      pts.push([gg.lat, gg.lon])
    }
    m.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 13 })
  }, [st, t])

  return <div ref={el} className="map live-map" role="img" aria-label={`${t.live.map}: ${st?.location?.place ?? ''}`} />
}
