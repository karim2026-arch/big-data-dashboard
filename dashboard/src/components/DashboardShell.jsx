import { DASHBOARDS_BY_ID } from '../dashboards'
import { useKpis } from '../hooks/useKpis'
import { dateTime } from './format'
import InfoTip from './InfoTip'
import { KpiGrid } from './KpiCard'
import ThemeToggle from './ThemeToggle'

// Period label with an info icon that explains, on hover or keyboard focus, what the card numbers and arrows compare.
function PeriodInfo({ period }) {
  return (
    <div className="flex items-center gap-1 text-xs text-slate-500">
      {period}
      <InfoTip label="What does the period mean?">
        The big number on each card is for the <b>current period</b>.
        <br />
        The ▲▼ arrow shows the change vs the <b>previous period</b> (pp = percentage points, for % KPIs).
      </InfoTip>
    </div>
  )
}

// Common page frame: title, loading/error, KPI cards, then the page's charts.
// children can be a function (series) => charts (rendered once data is loaded) or plain elements (always rendered).
export default function DashboardShell({ dashboardId, children }) {
  const dashboard = DASHBOARDS_BY_ID[dashboardId]
  const { data, error, loading } = useKpis(dashboardId)

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{dashboard.title}</h1>
          <p className="text-xs text-slate-500">Audience: {dashboard.audience}</p>
        </div>
        <div className="flex items-center gap-4">
          {data && (
            <>
              <PeriodInfo period={data.period} />
              <div className="text-right">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Last updated</div>
                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">{dateTime(data.as_of)}</div>
              </div>
            </>
          )}
          <ThemeToggle />
        </div>
      </header>

      {loading && <p className="text-sm text-slate-600 dark:text-slate-400">Loading…</p>}
      {error && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300">
          Could not load data: {error.message}
        </p>
      )}
      {data && <KpiGrid kpiIds={dashboard.kpiIds} kpis={data.kpis} />}
      {typeof children === 'function' ? data && children(data.series) : children}
    </div>
  )
}
