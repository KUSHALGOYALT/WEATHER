import { useMemo, useState } from 'react'
import axios from 'axios'
import './App.css'

type Reading = {
  provider: string
  latitude: number
  longitude: number
  observed_at_unix: number | null
  temperature_c: number | null
  temperature_f: number | null
  humidity_pct: number | null
  pressure_hpa: number | null
  wind_speed_ms: number | null
  wind_direction_deg: number | null
  condition_code: string | null
  condition_text: string | null
}

const BACKEND_BASE = (import.meta as any).env.VITE_BACKEND_BASE || 'http://127.0.0.1:8010'

export default function App() {
  const [provider, setProvider] = useState('openmeteo')
  const [coordsText, setCoordsText] = useState('37.7749,-122.4194\n40.7128,-74.0060')
  const [readings, setReadings] = useState<Reading[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const coordsList = useMemo(() => {
    return coordsText
      .split(/\n|\r/)
      .map((s) => s.trim())
      .filter(Boolean)
  }, [coordsText])

  async function fetchWeather() {
    setLoading(true)
    setError(null)
    setReadings(null)
    try {
      const params = new URLSearchParams()
      params.set('provider', provider)
      for (const c of coordsList) params.append('coords', c)
      const url = `${BACKEND_BASE}/api/weather?${params.toString()}`
      const resp = await axios.get<Reading[]>(url)
      setReadings(resp.data)
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', padding: 16 }}>
      <h2>Weather Fetcher</h2>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr' }}>
        {/* Provider selection hidden as requested; defaulting to Open‑Meteo */}
        <label>
          Coordinates (one per line, lat,lon)
          <textarea
            value={coordsText}
            onChange={(e) => setCoordsText(e.target.value)}
            rows={6}
            style={{ width: '100%', fontFamily: 'monospace' }}
          />
        </label>
        <button onClick={fetchWeather} disabled={loading}>
          {loading ? 'Fetching…' : 'Fetch Weather'}
        </button>
      </div>

      {error && (
        <div style={{ color: 'red', marginTop: 12 }}>Error: {error}</div>
      )}

      {readings && (
        <div style={{ marginTop: 16, overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>T (°C)</th>
                <th>Hum (%)</th>
                <th>Press (hPa)</th>
                <th>Wind (m/s)</th>
                <th>Dir (°)</th>
                
              </tr>
            </thead>
            <tbody>
              {readings.map((r, idx) => (
                <tr key={idx}>
                  <td>{r.temperature_c ?? ''}</td>
                  <td>{r.humidity_pct ?? ''}</td>
                  <td>{r.pressure_hpa ?? ''}</td>
                  <td>{r.wind_speed_ms ?? ''}</td>
                  <td>{r.wind_direction_deg ?? ''}</td>
                  
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
