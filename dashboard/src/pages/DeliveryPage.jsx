import { useState } from 'react'
import { BarChartView } from '../components/charts'
import { scaleColor } from '../components/colorScale'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import { lane } from '../components/format'
import Heatmap from '../components/Heatmap'
import MapOverlay from '../components/MapOverlay'
import Panel from '../components/Panel'
import { formatValue } from '../kpis/definitions'
import MapCanvas from '../scene/MapCanvas'
import RouteArcs from '../scene/RouteArcs'

// Lane OTD color scale bounds (%): below 80 = full red, 100 = full green.
const OTD_MIN = 80
const OTD_MAX = 100
// Taller arc = worse lane, so problem lanes stand out.
const arcHeight = (row) => 0.5 + (100 - row.kpi_1) * 0.3
const arcColor = (row) => scaleColor(row.kpi_1, OTD_MIN, OTD_MAX)
// Legend bar sampled from the same scale as the arcs, so legend and arcs always match.
const OTD_LEGEND_STOPS = [80, 85, 90, 95, 100]
const OTD_GRADIENT = `linear-gradient(to right, ${OTD_LEGEND_STOPS.map((value) => scaleColor(value, OTD_MIN, OTD_MAX)).join(', ')})`

function LaneMap({ lanes }) {
  const [hovered, setHovered] = useState(null)
  return (
    <div className="relative h-[460px] overflow-hidden rounded-lg">
      <MapCanvas>
        <RouteArcs lanes={lanes} heightOf={arcHeight} colorOf={arcColor} onHover={setHovered} />
      </MapCanvas>
      <MapOverlay className="bottom-3 left-3">
        <div className="mb-1 font-semibold text-slate-900 dark:text-slate-100">Arc color = on-time delivery (%)</div>
        <div className="h-2 w-44 rounded-sm" style={{ background: OTD_GRADIENT }} />
        <div className="flex justify-between">
          <span>≤ {OTD_MIN}</span>
          <span>{(OTD_MIN + OTD_MAX) / 2}</span>
          <span>{OTD_MAX}</span>
        </div>
      </MapOverlay>
      <MapOverlay className="left-3 top-3">
        {hovered ? (
          <>
            <div className="font-semibold text-slate-900 dark:text-slate-100">{lane(hovered)}</div>
            <div>On-time delivery: {formatValue(hovered.kpi_1, '%')} %</div>
            <div>Deliveries: {hovered.deliveries.toLocaleString('en-US')}</div>
            <div>Typical distance: {formatValue(hovered.typical_distance_km, 'km')} km</div>
          </>
        ) : (
          'Hover a lane'
        )}
      </MapOverlay>
    </div>
  )
}

export default function DeliveryPage() {
  return (
    <DashboardShell dashboardId="delivery">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel
            className="lg:col-span-2"
            title="Lanes in 3D: on-time delivery by lane"
            subtitle="Arc height and color = how late the lane is (tall + red = worst on-time %). Each direction is its own lane."
          >
            <LaneMap lanes={series.lane_otd} />
          </Panel>
          <Panel className="lg:col-span-2" title="Lane heatmap: on-time delivery (%)" subtitle="Rows = origin_city, columns = destination_city">
            <Heatmap rows={series.lane_otd} rowKey="origin_city" colKey="destination_city" valueKey="kpi_1" min={OTD_MIN} max={OTD_MAX} unit="%" />
          </Panel>
          <Panel title="Customers with the lowest on-time rate">
            <DataTable
              columns={[{ key: 'customer_name', label: 'customer_name' }, { key: 'customer_type', label: 'customer_type' }, { key: 'deliveries', label: 'deliveries (count)' }, { key: 'kpi_1' }]}
              rows={series.worst_customers}
            />
          </Panel>
          <Panel title="Average delay by hour of day" subtitle="Scheduled delivery hour, minutes">
            <BarChartView data={series.delay_by_hour} xKey="hour" bars={[{ key: 'kpi_3' }]} />
          </Panel>
          <Panel className="lg:col-span-2" title="Facilities with the longest destination queue" subtitle="Minutes waiting before unloading starts">
            <BarChartView data={series.facility_queue} xKey="facility_name" bars={[{ key: 'kpi_6' }]} layout="vertical" height={320} />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
