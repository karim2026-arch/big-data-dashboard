import { Suspense, useState } from 'react'
import DashboardShell from '../components/DashboardShell'
import { yesNo } from '../components/format'
import Panel from '../components/Panel'
import { STATUS_STYLE, statusOf, useFleetState } from '../hooks/useFleetState'
import { ANOMALY_TYPES } from '../kpis/definitions'
import MapCanvas from '../scene/MapCanvas'
import TruckLayer from '../scene/TruckLayer'

// Fields shown for the selected truck: [column, unit]. Names = stream columns (catalog 3.14 / 3.15).
const TELEMETRY_FIELDS = [
  ['event_ts', ''], ['engine_on', ''], ['speed_mph', 'mph'], ['rpm', 'rpm'], ['engine_temp_f', '°F'],
  ['fuel_gph', 'gal/h'], ['fuel_level_gal', 'gal'], ['odometer_mi', 'mi'], ['lat', '°'], ['lon', '°'],
]
const REEFER_FIELDS = [
  ['trailer_id', ''], ['cargo_temp_f', '°F'], ['setpoint_f', '°F'], ['compressor_on', ''], ['door_open', ''], ['ambient_temp_f', '°F'],
]

function countByStatus(fleet) {
  const activeTypes = fleet.activeTypesByVehicle()
  const counts = Object.fromEntries(Object.keys(STATUS_STYLE).map((status) => [status, 0]))
  for (const [vehicleId, { telemetry }] of fleet.vehicles.current) {
    if (telemetry) counts[statusOf(telemetry, activeTypes.get(vehicleId))] += 1
  }
  return counts
}

// Missing values are shown as "missing", never as 0 (catalog A.6).
function FieldRows({ row, fields }) {
  return fields.map(([column, unit]) => {
    const value = row[column]
    const text = typeof value === 'boolean' ? yesNo(value) : value == null ? 'missing' : `${value}${unit ? ` ${unit}` : ''}`
    return (
      <div key={column} className="flex justify-between gap-2 border-b border-slate-100 py-1 dark:border-slate-800/60">
        <span className="text-slate-500">{column}</span>
        <span className="text-slate-800 dark:text-slate-200">{text}</span>
      </div>
    )
  })
}

export default function LiveMapPage() {
  const fleet = useFleetState()
  const [selectedId, setSelectedId] = useState(null)

  const counts = countByStatus(fleet)
  const selected = selectedId && fleet.vehicles.current.get(selectedId)
  const selectedAnomalies = selectedId ? [...(fleet.activeTypesByVehicle().get(selectedId) ?? [])] : []
  const streamTime = fleet.vehicles.current.values().next().value?.telemetry?.event_ts

  return (
    <DashboardShell dashboardId="live">
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Panel
          title="Live fleet"
          subtitle={`Drag to rotate · scroll to zoom · click a truck. Bigger trucks = active anomaly. Stream time: ${streamTime ?? 'waiting…'}`}
        >
          <div className="h-[60vh] min-h-[420px] overflow-hidden rounded-lg">
            <MapCanvas>
              <Suspense fallback={null}>
                <TruckLayer fleet={fleet} selectedId={selectedId} onSelect={setSelectedId} />
              </Suspense>
            </MapCanvas>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {Object.entries(STATUS_STYLE).map(([status, style]) => (
              <span key={status} className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: style.color }} />
                {style.label}: <span className="text-slate-800 dark:text-slate-200">{counts[status].toLocaleString('en-US')}</span> trucks
              </span>
            ))}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Selected truck" subtitle={selectedId ?? 'Click a truck or an alert'}>
            {selected?.telemetry ? (
              <div className="text-xs">
                {selectedAnomalies.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {selectedAnomalies.map((type) => (
                      <span key={type} className="rounded px-1.5 py-0.5 text-[10px] font-semibold text-slate-950" style={{ background: ANOMALY_TYPES[type].color }}>
                        {ANOMALY_TYPES[type].label}
                      </span>
                    ))}
                  </div>
                )}
                <FieldRows row={selected.telemetry} fields={TELEMETRY_FIELDS} />
                {selected.reefer && (
                  <>
                    <div className="mt-3 mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Reefer</div>
                    <FieldRows row={selected.reefer} fields={REEFER_FIELDS} />
                  </>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No truck selected.</p>
            )}
          </Panel>

          <Panel title="Alert feed" subtitle="Anomalies detected by the streaming job (newest first)">
            <ul className="max-h-[360px] space-y-1 overflow-y-auto text-xs">
              {fleet.alertFeed.length === 0 && <li className="text-slate-500">No alerts yet.</li>}
              {fleet.alertFeed.map((alert) => (
                <li key={alert.anomaly_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(alert.vehicle_id)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: ANOMALY_TYPES[alert.anomaly_type].color }} />
                    <span className="flex-1 text-slate-700 dark:text-slate-300">
                      {ANOMALY_TYPES[alert.anomaly_type].label} · {alert.vehicle_id}
                    </span>
                    <span className={alert.end_ts ? 'text-slate-500' : 'text-rose-600 dark:text-rose-300'}>
                      {alert.end_ts ? `ended ${alert.end_ts.slice(11, 16)} UTC` : `active since ${alert.start_ts.slice(11, 16)} UTC`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </DashboardShell>
  )
}
