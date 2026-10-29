// The only import components use for data. Switch with VITE_DATA_SOURCE (mock | api).
// Both sources expose the same two functions (see contract.js):
//   getKpis(dashboardId)        -> Promise<DashboardResponse>
//   subscribe(eventType, onEvent) -> unsubscribe()
import { config } from '../config'
import { mockSource } from './mock/mockSource'
import { apiSource } from './api/apiSource'

const SOURCES = { mock: mockSource, api: apiSource }

export const dataSource = SOURCES[config.dataSource]

if (!dataSource) {
  throw new Error(`Unknown VITE_DATA_SOURCE "${config.dataSource}". Use one of: ${Object.keys(SOURCES).join(', ')}`)
}
