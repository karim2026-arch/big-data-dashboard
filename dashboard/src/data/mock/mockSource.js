// Mock data source: same interface as apiSource, no backend needed.
import { buildDashboard } from './dashboards'
import { subscribeSimulator } from './fleetSimulator'

const LATENCY_MS = 300 // fake network delay so loading states are visible

export const mockSource = {
  getKpis(dashboardId) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        try {
          resolve(buildDashboard(dashboardId))
        } catch (error) {
          reject(error)
        }
      }, LATENCY_MS)
    })
  },

  subscribe: subscribeSimulator,
}
