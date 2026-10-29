import { DASHBOARDS_BY_ID } from '../dashboards'
import { useKpis } from '../hooks/useKpis'
import { KpiGrid } from './KpiCard'

// Common page frame: title, loading/error, KPI cards, then the page's charts.
// children can be a function (series) => charts (rendered once data is loaded) or plain elements (always rendered).
export default function DashboardShell({ dashboardId, children }) {
  const dashboard = DASHBOARDS_BY_ID[dashboardId]
  const { data, error, loading } = useKpis(dashboardId)

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{dashboard.title}</h1>
          <p className="text-xs text-slate-500">Audience: {dashboard.audience}</p>
        </div>
        {data && (
          <p className="text-xs text-slate-500">
            {data.period} · warehouse refreshed {new Date(data.as_of).toLocaleString()}
          </p>
        )}
      </header>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && (
        <p className="rounded-lg border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">Could not load data: {error.message}</p>
      )}
      {data && <KpiGrid kpiIds={dashboard.kpiIds} kpis={data.kpis} />}
      {typeof children === 'function' ? data && children(data.series) : children}
    </div>
  )
}
