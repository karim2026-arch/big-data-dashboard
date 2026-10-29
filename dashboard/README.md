# Fleet Dashboard (web)

React + Vite + Tailwind. Recharts for 2D KPI charts, Three.js (react-three-fiber) for the 3D map.
7 dashboards from `Notion_Data_Catalog.md` section 5, plus a Live Fleet Map.

## Run
```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173
npm run build      # production build in dist/
```

## Mock vs real data
Settings live in `.env.local` (copy from `.env.example`):

| Variable | Meaning |
|---|---|
| `VITE_DATA_SOURCE` | `mock` = in-browser fake data (default) · `api` = real backend |
| `VITE_API_BASE_URL` | Base URL for warehouse KPIs, e.g. `http://localhost:8000/api` |
| `VITE_STREAM_URL` | SSE endpoint for live data, e.g. `http://localhost:8000/stream` |

Switching to real data means: set `VITE_DATA_SOURCE=api` and build the two backend endpoints. No page changes.

## Flow
```
pages/*  ──>  hooks/useKpis, useStream, useFleetState  ──>  data/index.js (dataSource)
                                                             ├── data/mock/  (now)
                                                             └── data/api/   (later: fetch + EventSource)
```

## Backend contract (full detail: `src/data/contract.js`)
| What | Endpoint | Shape |
|---|---|---|
| Warehouse KPIs (already calculated in Snowflake MARTS) | `GET {VITE_API_BASE_URL}/kpis/{dashboard}` | `{ dashboard, period, as_of, kpis: [{ kpi_id, value, previous }], series: {...} }` |
| Live truck data | SSE event `telemetry` | array of `fleet.telemetry.v1` rows (one batch per tick) |
| Live reefer data | SSE event `reefer` | array of `fleet.reefer.v1` rows |
| Detected anomalies | SSE event `alert` | `{ anomaly_id, anomaly_type, vehicle_id, trip_id, start_ts, end_ts }`. Send active alerts first on connect |

Dashboard ids: `live, executive, delivery, cold_chain, fuel, safety, maintenance, platform` (`src/dashboards.js`).
The `series` keys each dashboard expects are in `src/data/mock/dashboards.js`.

## Where to change things
| Change | File |
|---|---|
| KPI name / unit / meaning | `src/kpis/definitions.js` (single source) |
| Which KPI cards a page shows | `src/dashboards.js` |
| Mock KPI numbers | `src/data/mock/kpiValues.js` |
| Mock fleet size, anomaly rates | `src/data/mock/fleetSimulator.js` (top constants) |
