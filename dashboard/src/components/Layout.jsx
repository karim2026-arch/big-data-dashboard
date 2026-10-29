import { NavLink, Outlet } from 'react-router-dom'
import { config } from '../config'
import { DASHBOARDS } from '../dashboards'

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-200 md:flex-row">
      <aside className="w-full shrink-0 border-b border-slate-800 bg-slate-900/40 p-4 md:w-60 md:border-b-0 md:border-r">
        <div className="mb-5">
          <div className="text-sm font-semibold text-slate-100">Fleet Data Platform</div>
          <span
            className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              config.dataSource === 'mock' ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300'
            }`}
          >
            data: {config.dataSource}
          </span>
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {DASHBOARDS.map((dashboard) => (
            <NavLink
              key={dashboard.id}
              to={dashboard.path}
              end
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-2 text-sm ${
                  isActive ? 'bg-sky-500/15 text-sky-300' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`
              }
            >
              {dashboard.title}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
