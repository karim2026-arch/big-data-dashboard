import { useEffect, useState } from 'react'
import { dataSource } from '../data'

// Loads one dashboard's warehouse KPIs + chart series.
export function useKpis(dashboardId) {
  const [state, setState] = useState({ data: null, error: null, loading: true })

  useEffect(() => {
    let cancelled = false
    setState({ data: null, error: null, loading: true })
    dataSource
      .getKpis(dashboardId)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }))
    return () => {
      cancelled = true
    }
  }, [dashboardId])

  return state
}
