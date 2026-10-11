import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { SEV_COLOR } from '../../severity'
import type { AppState } from '../../types'

const FAC_ICON: Record<string, string> = {
  hospital: '✚', clinic: '⚕', school: '🎓', nursing_home: '♿', fire_station: '🚒', shelter: '⛺',
}

interface Props { state: AppState; zonesGeo: any; facilities: any[]; onZone?: (id: string) => void; areaId: string | null }

export default function MapView({ state, zonesGeo, facilities, onZone, areaId }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map>()
  const layers = useRef<{ zones?: L.GeoJSON; dyn?: L.LayerGroup; fac?: L.LayerGroup }>({})

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, keyboard: true, scrollWheelZoom: false }).setView([39, -96], 4)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, className: 'dark-tiles',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    layers.current.dyn = L.layerGroup().addTo(m)
    layers.current.fac = L.layerGroup().addTo(m)
    map.current = m
    // Keep tiles and bounds correct when the layout changes size
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = undefined }
  }, [])

  // Fit the map to the active area's zones (on load and on area switch)
  const fitted = useRef<string | null>(null)
  useEffect(() => {
    const m = map.current
    if (!m || !zonesGeo || fitted.current === areaId) return
    m.invalidateSize()
    m.fitBounds(L.geoJSON(zonesGeo).getBounds(), { padding: [24, 24] })
    fitted.current = areaId
  }, [zonesGeo, areaId])

  // Zones (re-styled on severity change)
  useEffect(() => {
    const m = map.current
    if (!m || !zonesGeo) return
    layers.current.zones?.remove()
    const sev = Object.fromEntries(state.zones.map((z) => [z.zone_id, z]))
    layers.current.zones = L.geoJSON(zonesGeo, {
      style: (f) => {
        const z = sev[f!.properties.zone_id]
        const c = SEV_COLOR[z?.severity ?? 'Unknown']
        const verified = z?.exposure.label === 'verified_danger'
        return { color: c, weight: verified ? 3 : 2, dashArray: verified ? undefined : '6 5', fillColor: c, fillOpacity: z?.severity === 'Normal' ? 0.12 : 0.32 }
      },
      onEachFeature: (f, layer) => {
        const z = sev[f.properties.zone_id]
        layer.bindTooltip(`<strong>${f.properties.name}</strong><br/>${z?.severity ?? ''}${z?.exposure.label === 'verified_danger' ? ' · Verified danger' : z?.exposure.label === 'estimated_exposure' ? ' · Estimated exposure' : ''}`, { sticky: true })
        layer.on('click', () => onZone?.(f.properties.zone_id))
      },
    }).addTo(m)
    layers.current.zones.bringToBack()
  }, [zonesGeo, state.zones, onZone])

  // Facilities: only those inside affected zones are emphasised
  const affectedKey = state.zones.filter((z) => z.severity !== 'Normal' && z.severity !== 'Unknown').map((z) => z.zone_id).join(',')
  useEffect(() => {
    const g = layers.current.fac
    if (!g) return
    g.clearLayers()
    const affected = new Set(affectedKey.split(','))
    for (const f of facilities) {
      const on = affected.has(f.zone_id)
      if (!on && f.kind === 'school') continue
      const icon = L.divIcon({ className: `fac-icon ${on ? 'on' : ''}`, html: `<span title="${f.name}">${FAC_ICON[f.kind] ?? '•'}</span>`, iconSize: [18, 18] })
      L.marker([f.lat, f.lon], { icon, keyboard: false, alt: f.name }).bindTooltip(`${f.name} (${f.kind.replace('_', ' ')})`).addTo(g)
    }
  }, [facilities, affectedKey])

  // Gauges, photos, route
  useEffect(() => {
    const g = layers.current.dyn
    if (!g) return
    g.clearLayers()
    const r = state.route
    if (r) {
      const usual = r.usual.geometry.coordinates.map(([x, y]) => [y, x]) as [number, number][]
      const safer = r.safer.geometry.coordinates.map(([x, y]) => [y, x]) as [number, number][]
      if (r.recommended === 'safer') {
        L.polyline(usual, { color: '#ff4d6d', weight: 3, dashArray: '4 6', opacity: 0.8 }).bindTooltip('Usual commute — blocked').addTo(g)
        L.polyline(safer, { color: '#2ee6a6', weight: 5, opacity: 0.95 }).bindTooltip('Safer route').addTo(g)
      } else {
        L.polyline(usual, { color: '#9fb3c8', weight: 3, opacity: 0.55, dashArray: '2 5' }).bindTooltip('Resident commute').addTo(g)
      }
    }
    for (const gauge of state.gauges) {
      const st = gauge.latest?.value
      const fs = gauge.flood_stages_ft
      const c = st == null ? SEV_COLOR.Unknown : st >= fs.moderate ? SEV_COLOR.Emergency : st >= fs.minor ? SEV_COLOR.Warning : st >= fs.action ? SEV_COLOR.Watch : SEV_COLOR.Normal
      const icon = L.divIcon({
        className: 'gauge-icon',
        html: `<div class="gauge-pin ${gauge.freshness}" style="border-color:${c}"><span style="color:${c}">▲</span>${st != null ? st.toFixed(1) : '—'} ft${gauge.freshness === 'missing' ? ' ⚠' : ''}</div>`,
        iconSize: [80, 24], iconAnchor: [10, 12],
      })
      L.marker([gauge.lat, gauge.lon], { icon, alt: gauge.name }).bindTooltip(`${gauge.name}<br/>USGS ${gauge.usgs_id} · action ${fs.action} / minor ${fs.minor} / moderate ${fs.moderate} ft`).addTo(g)
    }
    for (const p of state.photos) {
      const icon = L.divIcon({ className: 'photo-icon', html: `<div class="cam-pin ${p.status}">📷</div>`, iconSize: [26, 26] })
      L.marker([p.lat, p.lon], { icon, alt: 'Photo report' })
        .bindTooltip(p.analysis?.depth_in != null ? `Photo: ≈${Math.round(p.analysis.depth_in)} in (${p.status})` : `Photo (${p.status})`)
        .addTo(g)
    }
  }, [state.route, state.gauges, state.photos])

  return <div ref={el} className="map" role="application" aria-label="Map of Brays Bayou watch zones, gauges, facilities and photo reports" />
}
