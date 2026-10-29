// Real backend: warehouse KPIs + chart series over REST, live data over one shared SSE connection.
import { config } from '../../config'
import { DASHBOARDS_BY_ID } from '../../dashboards'

let eventSource = null
let subscriberCount = 0

// One EventSource for all subscribers. It reconnects by itself, and each (re)connect starts with a full snapshot.
function openStream() {
  if (!eventSource) eventSource = new EventSource(config.streamUrl)
  subscriberCount += 1
  return eventSource
}

function closeStream() {
  subscriberCount -= 1
  if (subscriberCount === 0) {
    eventSource.close()
    eventSource = null
  }
}

export const apiSource = {
  // dashboards.js is the only list of KPI ids per page: they are sent as ?kpi_ids=1&kpi_ids=2...
  async getKpis(dashboardId) {
    const query = new URLSearchParams(DASHBOARDS_BY_ID[dashboardId].kpiIds.map((kpiId) => ['kpi_ids', kpiId]))
    const response = await fetch(`${config.apiBaseUrl}/kpis/${dashboardId}?${query}`)
    if (!response.ok) throw new Error(`GET /kpis/${dashboardId} failed with status ${response.status}`)
    return response.json()
  },

  subscribe(eventType, onEvent) {
    const source = openStream()
    const listener = (message) => onEvent(JSON.parse(message.data))
    source.addEventListener(eventType, listener)
    return () => {
      source.removeEventListener(eventType, listener)
      closeStream()
    }
  },
}
