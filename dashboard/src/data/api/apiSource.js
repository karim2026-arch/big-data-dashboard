// Real backend: warehouse KPIs over REST, live data over one shared SSE connection.
import { config } from '../../config'

let eventSource = null
let subscriberCount = 0

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
  async getKpis(dashboardId) {
    const response = await fetch(`${config.apiBaseUrl}/kpis/${dashboardId}`)
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
