// Registry of pages: drives the sidebar, the routes, and which KPI cards each page shows (in order).
// Dashboards 1-7 follow Notion_Data_Catalog.md section 5; "live" is the streaming map.
export const DASHBOARDS = [
  { id: 'live', path: '/', title: 'Live Fleet Map', audience: 'Operations (live stream)', kpiIds: [51, 52, 53] },
  { id: 'executive', path: '/executive', title: 'Executive Overview', audience: 'Management', kpiIds: [1, 4, 20, 26, 11, 46, 41, 36] },
  { id: 'delivery', path: '/delivery', title: 'Delivery & Route Performance', audience: 'Dispatch and customer service', kpiIds: [1, 2, 3, 5, 6, 7, 8, 9] },
  { id: 'cold_chain', path: '/cold-chain', title: 'Cold Chain Monitoring', audience: 'Cold-chain operations and quality', kpiIds: [11, 10, 12, 13, 14, 15, 16] },
  { id: 'fuel', path: '/fuel', title: 'Fuel & Cost', audience: 'Fleet finance and operations', kpiIds: [19, 20, 21, 22, 23, 24, 27, 28] },
  { id: 'safety', path: '/safety', title: 'Fleet Utilization & Driver Safety', audience: 'Fleet safety and operations', kpiIds: [29, 30, 33, 34, 35, 36, 38] },
  { id: 'maintenance', path: '/maintenance', title: 'Maintenance & Reliability', audience: 'Maintenance managers', kpiIds: [41, 42, 43, 44, 46] },
  { id: 'platform', path: '/platform', title: 'Data Platform Health', audience: 'Data engineers', kpiIds: [54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64] },
]

export const DASHBOARDS_BY_ID = Object.fromEntries(DASHBOARDS.map((dashboard) => [dashboard.id, dashboard]))
