export type Severity = 'Normal' | 'Watch' | 'Warning' | 'Emergency' | 'Unknown'

export interface Reading { time: string; value: number; station_id: string; metric: string; quality?: string; source?: string; source_url?: string }
export interface Clock { now: string; start: string; end: string; speed: number; playing: boolean }
export interface ZoneState {
  zone_id: string; name: string; name_es: string; severity: Severity; changed_at: string | null; fired: string[]
  missing: string[]; gauge: string; rain: string; incident_id: string | null; active_alert_id: string | null
  exposure: { label: 'verified_danger' | 'estimated_exposure' | 'none'; verified_by: string[]; facility_count: number }
}
export interface Gauge {
  station_id: string; usgs_id: string; name: string; lat: number; lon: number
  flood_stages_ft: { action: number; minor: number; moderate: number; major: number }; flood_stages_source: string
  latest: Reading | null; age_minutes: number | null; freshness: 'live' | 'delayed' | 'missing'
}
export interface AlertSummary {
  id: string; incident_id: string; zone_id: string; severity: Severity; rule_ids: string[]; created_at: string
  state: string; text_en: string; headline: string; ai_path: string | null; deliveries: number
}
export interface Photo {
  id: string; time: string; lat: number; lon: number; status: string; zone_id: string | null
  road: { road_id: string; name: string } | null; analysis: any; checks: { status: string; flags: string[]; reasons: string[] }
  image_url: string; ai_path: string | null; model: string | null; reporter: string
}
export interface RouteInfo {
  recommended: 'usual' | 'safer'; blocked_by: string[]; source: string
  usual: { geometry: { coordinates: [number, number][] }; distance_m: number; duration_s: number }
  safer: { geometry: { coordinates: [number, number][] }; distance_m: number; duration_s: number }
}
export interface AudienceSummary {
  demo_run_id: string; joined: number; by_language: Record<string, number>; by_zone: Record<string, number>
  deliveries: number; delivered: number; acknowledged: number; median_seconds_to_ack: number | null
}
export interface Scene { id: string; label: string; time: string; note: string }
export interface AppState {
  clock: Clock; offline: boolean; mode: string; force_gemini_failure: boolean; demo_run_id: string; area: string; storm: string
  zones: ZoneState[]; gauges: Gauge[]; rain: { station_id: string; name: string; last_hour_in: number; lat: number; lon: number }[]
  alerts: AlertSummary[]; photos: Photo[]; route: RouteInfo | null; last_ai_path: string | null; audience: AudienceSummary
  scenes: Scene[]; pending_generation: number
  area_info: { id: string; name: string; short_name: string; storm: string; tz: string; description: string; audience_default_zone: string; rain_source: string }
}
export interface Delivery {
  id: string; alert_id: string; user_id: string; kind: string; language: 'en' | 'es'; state: string; text: string | null
  card: { headline: string; what: string; where: string; action: string; updated: string; source: string; severity_word: string } | null
  audio_url: string | null; voice: { provider: string; error: string | null } | null
  translation: { path: string; model: string } | null; reviewed: { template_phrases_reviewed: boolean } | null
  alert_severity?: Severity; alert_created_at?: string; alert_state?: string
}
export interface ResidentView {
  zone: { zone_id: string; name: string; name_es: string; severity: Severity; changed_at: string | null; missing: string[] }
  clock: Clock; delivery: Delivery | null; history: Delivery[]; route?: RouteInfo | null; session?: any
  demo_location?: { lat: number; lon: number; name: string; zone_id: string } | null
}
export interface User { id: string; name: string; language: 'en' | 'es'; zone_id: string; vehicle: string | null; needs: Record<string, any> }
