import { useRef, useState } from 'react'
import { ANOMALY_TYPES } from '../kpis/definitions'
import { useStream } from './useStream'

const FEED_SIZE = 40

// Display status of a truck. Anomalies come from backend alerts (no detection in the frontend).
// When a truck has several active anomalies, the first in this order wins.
const ANOMALY_PRIORITY = [
  'COLD_CHAIN_BREACH', 'REEFER_UNIT_FAILURE', 'ENGINE_OVERHEATING', 'ROUTE_DEVIATION', 'SPEEDING', 'LOW_FUEL', 'EXCESSIVE_IDLING',
]

// Without an anomaly, the status is the row's motion_status (silver stream column).
export const STATUS_STYLE = {
  ...ANOMALY_TYPES,
  DRIVING: { label: 'Driving', color: '#22c55e' },
  IDLING: { label: 'Idling', color: '#a3e635' },
  PARKED: { label: 'Parked', color: '#475569' },
}

export function statusOf(telemetry, anomalyTypes) {
  const anomaly = anomalyTypes && ANOMALY_PRIORITY.find((type) => anomalyTypes.has(type))
  return anomaly ?? telemetry.motion_status
}

// Live fleet picture built from the four stream events.
// Big data (5,000 trucks) lives in refs so the 3D scene can read it every frame without React re-renders;
// `tick` changes once per telemetry batch so side panels can refresh.
export function useFleetState() {
  const vehicles = useRef(new Map()) // vehicle_id -> { telemetry, reefer }
  const activeAlerts = useRef(new Map()) // anomaly_id -> AlertRow
  const dirty = useRef(false) // true when the 3D scene must redraw
  const [tick, setTick] = useState(0)
  const [alertFeed, setAlertFeed] = useState([])
  const [liveKpis, setLiveKpis] = useState(null) // LiveKpis, calculated by the backend

  useStream('telemetry', (rows) => {
    for (const row of rows) {
      const vehicle = vehicles.current.get(row.vehicle_id) ?? { telemetry: null, reefer: null }
      // Null GPS = signal lost: keep the last known position instead of jumping to 0,0.
      const telemetry = row.lat == null && vehicle.telemetry ? { ...row, lat: vehicle.telemetry.lat, lon: vehicle.telemetry.lon } : row
      vehicles.current.set(row.vehicle_id, { ...vehicle, telemetry })
    }
    dirty.current = true
    setTick((value) => value + 1)
  })

  useStream('reefer', (rows) => {
    for (const row of rows) {
      const vehicle = vehicles.current.get(row.vehicle_id) ?? { telemetry: null, reefer: null }
      vehicles.current.set(row.vehicle_id, { ...vehicle, reefer: row })
    }
  })

  useStream('alert', (alert) => {
    if (alert.end_ts) activeAlerts.current.delete(alert.anomaly_id)
    else activeAlerts.current.set(alert.anomaly_id, alert)
    dirty.current = true
    // One row per anomaly: an "ended" update replaces its "started" row and moves to the top.
    setAlertFeed((feed) => [alert, ...feed.filter((row) => row.anomaly_id !== alert.anomaly_id)].slice(0, FEED_SIZE))
  })

  useStream('kpis', setLiveKpis)

  // vehicle_id -> Set of active anomaly types
  function activeTypesByVehicle() {
    const result = new Map()
    for (const alert of activeAlerts.current.values()) {
      if (!result.has(alert.vehicle_id)) result.set(alert.vehicle_id, new Set())
      result.get(alert.vehicle_id).add(alert.anomaly_type)
    }
    return result
  }

  return { vehicles, dirty, tick, alertFeed, liveKpis, activeTypesByVehicle }
}
