# Fleet Dashboard (web)

React 19 + Vite + Tailwind 4. Recharts draws the 2D charts. Three.js (through react-three-fiber) draws the 3D maps.
There are 8 pages: 7 dashboards from `Notion_Data_Catalog.md` section 5, plus the Live Fleet Map. A KPI Guide page explains every KPI.

This file explains how the dashboard works, part by part. Each part has its own architecture view.

**Contents**
1. [Run it](#1-run-it)
2. [Big picture](#2-big-picture)
3. [Folder map (every file)](#3-folder-map-every-file)
4. [Startup: from `index.html` to a page on screen](#4-startup-from-indexhtml-to-a-page-on-screen)
5. [The page registry (`dashboards.js`)](#5-the-page-registry-dashboardsjs)
6. [Data layer (mock or api)](#6-data-layer-mock-or-api)
7. [Flow 1: warehouse KPIs and charts (REST)](#7-flow-1-warehouse-kpis-and-charts-rest)
8. [Flow 2: live stream (SSE)](#8-flow-2-live-stream-sse)
9. [Mock data source (no backend)](#9-mock-data-source-no-backend)
10. [Hooks](#10-hooks)
11. [KPI catalog (`kpis/definitions.js`)](#11-kpi-catalog-kpisdefinitionsjs)
12. [Shared components](#12-shared-components)
13. [3D map (`scene/`)](#13-3d-map-scene)
14. [Each page in detail](#14-each-page-in-detail)
15. [Theme (light / dark)](#15-theme-light--dark)
16. [Units](#16-units)
17. [Deploy](#17-deploy)
18. [How to change or add things](#18-how-to-change-or-add-things)

---

## 1. Run it
```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173
npm run build      # production build in dist/
npm run preview    # serve the dist/ build locally
```

### Settings (`.env.local`, copy from `.env.example`)
| Variable | Meaning | Default |
|---|---|---|
| `VITE_DATA_SOURCE` | `mock` = fake data made in the browser · `api` = real backend | `mock` |
| `VITE_API_BASE_URL` | Base URL of the backend REST API, e.g. `http://localhost:8000/api` | empty |
| `VITE_STREAM_URL` | SSE endpoint of the live stream, e.g. `http://localhost:8000/api/stream` | empty |

- Only `VITE_*` values reach the browser. **Never put secrets here**: anyone can read them in the built JavaScript.
- Vite copies these values into the code when it starts (`dev`) or builds (`build`). After you edit `.env.local`, restart `npm run dev` or build again.
- `src/config.js` is the only file that reads them.

---

## 2. Big picture
The dashboard only **shows** data. It does not calculate KPIs. The backend calculates them in Snowflake (warehouse KPIs) or from Kafka (live KPIs).
The one exception is the mock mode, where the browser makes all the fake data itself.

```
┌────────────────────────────────────────── Browser ──────────────────────────────────────────┐
│                                                                                              │
│  main.jsx ─> App.jsx (ThemeProvider + Router) ─> Layout (sidebar + <Outlet/>)                │
│                                                    │                                         │
│                                                    ▼                                         │
│   PAGES          pages/*Page.jsx          (what to show: panels, charts, tables, 3D map)     │
│                     │            │                                                           │
│   UI PARTS          │      components/*  +  scene/*   (reusable: cards, charts, 3D layers)   │
│                     │            │                                                           │
│   KPI TEXT          │      kpis/definitions.js        (names, units, meanings, formulas)     │
│                     ▼                                                                        │
│   HOOKS          hooks/useKpis   hooks/useStream ─> hooks/useFleetState                      │
│                     │                 │                                                      │
│                     ▼                 ▼                                                      │
│   DATA LAYER     data/index.js  ->  dataSource = mockSource | apiSource  (picked by .env)    │
│                     │                                   │                                    │
└─────────────────────┼───────────────────────────────────┼────────────────────────────────────┘
                      │ mock                               │ api
                      ▼                                    ▼
        data/mock/* (fake numbers +            Backend (FastAPI)
        5,000-truck simulator)                  ├─ GET /api/kpis/{dashboard}?kpi_ids=..  -> Snowflake DBT_MARTS
                                                └─ GET /api/stream  (SSE)                -> Kafka silver topics
```

**Two kinds of data, two flows**
| Flow | Used by | Transport | How often | Section |
|---|---|---|---|---|
| Warehouse KPIs + chart series | Every dashboard page (KPI cards and charts) | REST `fetch` | On page open, then every 30 min | [7](#7-flow-1-warehouse-kpis-and-charts-rest) |
| Live stream (trucks, reefers, alerts, live KPIs) | Live Fleet Map only | SSE `EventSource` | Pushed by the server as data arrives | [8](#8-flow-2-live-stream-sse) |

**Main design rules**
| Rule | Why |
|---|---|
| Components import data only from `data/index.js` | Switching mock ↔ api is one `.env` line. No page code changes. |
| Both sources have the same two functions (`getKpis`, `subscribe`) | The pages do not know which source is active. |
| The backend sends only numbers (`kpi_id`, `value`, `previous`) | Every text a viewer reads (name, unit, meaning) lives in one file: `kpis/definitions.js`. |
| `dashboards.js` is the one list of pages and KPI ids | The sidebar, the routes, the KPI cards and the API query all read it. Nothing is repeated. |
| Column names are the catalog/data names (`vehicle_id`, `cargo_temp_f`, `kpi_21`...) | The same name is used in Snowflake, the backend, and the screen. |

---

## 3. Folder map (every file)
```
dashboard/
  index.html               HTML shell: <div id="root"> + loads src/main.jsx
  vite.config.js           Vite plugins: React + Tailwind
  vercel.json              Sends every URL to index.html (deep links work on refresh)
  .env.example             Template for .env.local
  public/models/truck_toyota_corsa_b.glb   3D truck model used on the live map
  src/
    main.jsx               Mounts <App/> into #root (React StrictMode)
    App.jsx                Theme provider + router; builds one route per dashboard
    config.js              Reads VITE_* values (the only place)
    dashboards.js          Page registry: id, path, title, audience, KPI ids
    index.css              Tailwind import + dark-mode rule + base font

    data/
      index.js             Picks the data source (mock | api) -> exports `dataSource`
      contract.js          JSDoc of every data shape (no runtime code)
      api/apiSource.js     Real backend: fetch for KPIs, one shared EventSource for the stream
      mock/mockSource.js   Fake backend with the same interface
      mock/dashboards.js   Builds the fake DashboardResponse (KPI values + chart series) per page
      mock/kpiValues.js    Fake KPI numbers: kpi_id -> [value, previous]
      mock/fleetSimulator.js  In-browser 5,000-truck simulator that emits the 4 stream events
      mock/reference.js    Fake reference data: facilities, routes, commodities, names
      mock/rng.js          Seeded random generator (same fake data on every run)

    hooks/
      useKpis.js           Loads one dashboard's KPIs + series, refreshes every 30 min
      useStream.js         Subscribes to one stream event while the component is on screen
      useFleetState.js     Builds the live fleet picture from the 4 stream events
      useTheme.jsx         Light/dark theme state (saved in localStorage)

    kpis/
      definitions.js       KPI catalog (name, unit, meaning, formula...), anomaly types, formatters

    components/
      Layout.jsx           Sidebar navigation + page area
      DashboardShell.jsx   Common page frame: title, period, last updated, KPI cards, charts
      KpiCard.jsx          One KPI card + the grid of cards + the trend arrow
      Panel.jsx            White box with a title and subtitle around a chart/table
      charts.jsx           LineChartView, BarChartView (Recharts wrappers)
      DataTable.jsx        Simple table with KPI-aware column labels
      Heatmap.jsx          Color grid (origin city × destination city)
      MapOverlay.jsx       Box drawn on top of a 3D map (legend, hover info)
      InfoTip.jsx          Info icon with a tooltip
      NoData.jsx           "No data" text when a series is null or empty
      ThemeToggle.jsx      Light/dark button
      colorScale.js        Value -> red..green color
      format.js            Small formatters: usd, usdCents, yesNo, dateTime, lane

    scene/                 3D map parts
      projection.js        lat/lon -> 3D scene position
      MapCanvas.jsx        3D canvas: camera, lights, US borders, mouse controls
      UsOutline.jsx        US state borders (from the bundled us-atlas file)
      RouteArcs.jsx        One 3D arc per lane (delivery page)
      TruckLayer.jsx       All trucks as one instanced mesh, with smooth movement (live page)

    pages/                 One file per page (see section 14)
      LiveMapPage, ExecutivePage, DeliveryPage, ColdChainPage, FuelPage,
      SafetyPage, MaintenancePage, PlatformPage, KpiGuidePage
```

---

## 4. Startup: from `index.html` to a page on screen
```
index.html
  └─ <script src="/src/main.jsx">
       └─ createRoot(#root).render(<StrictMode><App/></StrictMode>)
            └─ App
                 └─ ThemeProvider            (theme state, adds/removes the "dark" class on <html>)
                      └─ BrowserRouter       (reads the URL)
                           └─ Routes
                                └─ <Route element={<Layout/>}>     (sidebar is always shown)
                                     ├─ one <Route path={dashboard.path} element={<Page/>}/> per item in DASHBOARDS
                                     ├─ <Route path="/kpi-guide" element={<KpiGuidePage/>}/>
                                     └─ <Route path="*" -> Navigate to "/">               (unknown URL -> live map)
```
- `App.jsx` has a `PAGES` object: dashboard id → page component (`live → LiveMapPage`, `fuel → FuelPage`...).
  It loops over `DASHBOARDS` and makes one route per entry. To add a page you add it to `DASHBOARDS` and to `PAGES`.
- `Layout` draws the sidebar and puts the current page in `<Outlet/>`.
- `StrictMode` (development only) mounts every component twice to find bugs. That is why the data code counts subscribers (section 8).

---

## 5. The page registry (`dashboards.js`)
One array drives four things:

```
DASHBOARDS = [{ id, path, title, audience, kpiIds }, ...]
     │
     ├─> App.jsx           one route per entry (path -> page)
     ├─> Layout.jsx        one sidebar link per entry (title)
     ├─> DashboardShell    page title, audience, and which KPI cards to show (kpiIds, in this order)
     └─> apiSource.js      sends kpiIds to the backend as ?kpi_ids=1&kpi_ids=2...
```

| id | path | title | audience | KPI cards (ids) |
|---|---|---|---|---|
| `live` | `/` | Live Fleet Map | Operations (live stream) | 51, 52, 53 |
| `executive` | `/executive` | Executive Overview | Management | 1, 20, 26, 11, 46, 41, 36 |
| `delivery` | `/delivery` | Delivery & Route Performance | Dispatch and customer service | 1, 2, 3, 5, 6, 7, 8 |
| `cold_chain` | `/cold-chain` | Cold Chain Monitoring | Cold-chain operations and quality | 11, 10, 12, 13, 14, 15, 16 |
| `fuel` | `/fuel` | Fuel & Cost | Fleet finance and operations | 19, 20, 21, 22, 23, 24, 27, 28 |
| `safety` | `/safety` | Fleet Utilization & Driver Safety | Fleet safety and operations | 29, 30, 33, 34, 35, 36, 38 |
| `maintenance` | `/maintenance` | Maintenance & Reliability | Maintenance managers | 41, 42, 43, 44, 46 |
| `platform` | `/platform` | Data Platform Health | Data engineers | 54 – 64 |

`KPI_GUIDE = { path: '/kpi-guide', title: 'KPI Guide' }` is kept outside `DASHBOARDS` on purpose: it is text only, so it has no backend endpoint.
`DASHBOARDS_BY_ID` is the same list as an object (`id → dashboard`) for quick lookup.

---

## 6. Data layer (mock or api)
```
                         config.dataSource  ('mock' | 'api', from VITE_DATA_SOURCE)
                                 │
data/index.js:   SOURCES = { mock: mockSource, api: apiSource }
                 export const dataSource = SOURCES[config.dataSource]   (unknown value -> throws an error at startup)
                                 │
          ┌──────────────────────┴───────────────────────┐
          ▼                                              ▼
  mockSource (data/mock/)                        apiSource (data/api/)
  getKpis(id)      -> buildDashboard(id)         getKpis(id)      -> fetch GET {API}/kpis/{id}?kpi_ids=..
                      after 300 ms fake delay
  subscribe(e, fn) -> fleetSimulator             subscribe(e, fn) -> shared EventSource(STREAM_URL)
```

**The interface (both sources)**
| Function | Input | Output |
|---|---|---|
| `getKpis(dashboardId)` | a dashboard id from `dashboards.js` | `Promise<DashboardResponse>` |
| `subscribe(eventType, onEvent)` | `'telemetry' \| 'reefer' \| 'alert' \| 'kpis'` and a callback | an `unsubscribe()` function |

**`contract.js`** writes down every shape in JSDoc (no runtime code). It is the agreement between frontend and backend:

| Shape | Fields (short) |
|---|---|
| `DashboardResponse` | `dashboard`, `period` (text), `as_of` (ISO UTC), `kpis: KpiValue[]`, `series: { name: rows }` |
| `KpiValue` | `kpi_id`, `value` (current period), `previous` (previous period). `null` = not in the warehouse |
| `TelemetryRow` | Kafka `fleet.silver.telemetry.v1`: `vehicle_id`, `event_ts`, `lat`, `lon`, `speed_mph`, `heading_deg`, `rpm`, `engine_temp_f`, `fuel_gph`, `fuel_level_gal`, `odometer_mi`, `engine_on`, `motion_status`, flags `is_speeding`, `is_engine_overheating`, `is_low_fuel`, `is_idling` |
| `ReeferRow` | Kafka `fleet.silver.reefer.v1`: `vehicle_id`, `trailer_id`, `cargo_temp_f`, `setpoint_f`, `compressor_on`, `door_open`, `ambient_temp_f`, `commodity_type`, `allowed_temp_min_f/max_f`, flags `is_temp_breach`, `is_reefer_unit_failure` |
| `AlertRow` | `anomaly_id`, `anomaly_type`, `vehicle_id`, `trip_id`, `start_ts`, `end_ts` (`null` while active) |
| `LiveKpis` | truck counts, `motion_status` counts, flag counts, `cold_chain_compliance_pct` (+ by commodity), `data_age_min` |

---

## 7. Flow 1: warehouse KPIs and charts (REST)
Used by every page that is wrapped in `DashboardShell`.

```
FuelPage
  └─ <DashboardShell dashboardId="fuel">{(series) => charts}</DashboardShell>
        │
        ├─ useKpis("fuel")
        │     ├─ first load: state = { data: null, loading: true }
        │     ├─ dataSource.getKpis("fuel")
        │     │     api : GET {VITE_API_BASE_URL}/kpis/fuel?kpi_ids=19&kpi_ids=20&...&kpi_ids=28
        │     │           backend runs one SQL per KPI + one SQL per series on Snowflake (DBT_MARTS)
        │     │     mock: buildDashboard("fuel") after 300 ms
        │     ├─ success: state = { data, error: null, loading: false }
        │     └─ every 30 min: load again (old data stays on screen while it loads)
        │
        ├─ header: title, "Audience: ...", period (with info tip), "Last updated" = data.as_of
        ├─ <KpiGrid kpiIds={dashboard.kpiIds} kpis={data.kpis}/>   -> one KpiCard per id, in registry order
        └─ children(data.series)                                    -> the page's charts and tables
```

**Step by step**
1. The page renders `DashboardShell` with its dashboard id.
2. `DashboardShell` reads the page info from `DASHBOARDS_BY_ID` and calls `useKpis(dashboardId)`.
3. `useKpis` calls `dataSource.getKpis()`. In api mode this is one HTTP call per page.
4. While loading: "Loading…". On error: a red box "Could not load data: ...". If a 30-min refresh fails, the old data stays and the error box shows too.
5. With data: the header shows `period` and `as_of`. The KPI grid shows one card per id in `kpiIds`.
   A card finds its number by `kpi_id`. A missing or `null` value shows `-`.
6. `children` can be:
   - **a function** `(series) => ...`: called only after data arrived (all dashboards except live).
   - **plain elements**: always shown (the live page, because its content comes from the stream, not from `series`).
7. Each chart reads one key from `series` (e.g. `series.fuel_spend_trend`). A `null` or empty series shows "No data".

**What is `null` in api mode today** (the backend has no table for it yet):
| Not in the warehouse | Effect on screen |
|---|---|
| KPIs 10–17, 23, 29, 33, 34, 35, 51–64 | Card shows `-` and "no change vs previous" |
| Series `trip_temperature`, `excursions_by_trailer`, `excursion_rate_by_ambient`, `high_risk_trips` (reefer stream) | Cold Chain charts show "No data" |
| Series `time_in_state` (telemetry stream) | Safety "Where truck time goes" shows "No data" |
| Series `pipeline_runs`, `row_counts`, `credits_trend` (pipeline metadata) | Platform charts show "No data" |

The full list of KPI queries and series per dashboard is in `backend/app/services/kpi_service.py` (`KPI_QUERIES`, `DASHBOARD_SERIES`).

**The `kpi_<id>` naming rule for series columns**
A series column named `kpi_<id>` holds that KPI at a finer level (per lane, per week, per truck...).
Example: `fuel_efficiency_by_route` rows have `kpi_21` = Fuel Efficiency (L/100km) of that route.
Charts and tables turn `kpi_21` into the label "Fuel Efficiency (L/100km)" through `columnLabel()` (section 11). So the page does not repeat KPI names.

---

## 8. Flow 2: live stream (SSE)
Used only by the Live Fleet Map.

```
Backend  GET /api/stream  (Server-Sent Events, reads Kafka silver topics)
   │  event: telemetry  data: TelemetryRow[]   (only rows that changed, one batch per tick)
   │  event: reefer     data: ReeferRow[]
   │  event: alert      data: AlertRow         (when an alert starts, and again with end_ts when it ends)
   │  event: kpis       data: LiveKpis         (on every change)
   │  On connect: a snapshot first (latest row of every truck, active alerts, last 40 alert changes, KPIs)
   ▼
apiSource: ONE EventSource shared by all subscribers (opened by the 1st, closed by the last)
   ▼
useStream(eventType, handler)  x4   (subscribe on mount, unsubscribe on unmount)
   ▼
useFleetState()
   ├─ vehicles      (ref)   Map vehicle_id -> { telemetry, reefer }         ← telemetry + reefer events
   ├─ activeAlerts  (ref)   Map anomaly_id -> AlertRow (active only)        ← alert events
   ├─ dirty         (ref)   true = 3D scene must redraw
   ├─ tick          (state) +1 per telemetry batch -> side panels re-render
   ├─ alertFeed     (state) last 40 alerts, newest first                    ← alert events
   └─ liveKpis      (state) last LiveKpis                                   ← kpis events
   ▼
LiveMapPage
   ├─ LiveKpiPanel  (liveKpis)
   ├─ TruckLayer    (reads vehicles + dirty every animation frame, no React re-render)
   ├─ legend counts (countByStatus)
   ├─ Selected truck panel
   └─ Alert feed
```

**Why some data lives in refs and some in state**
- 5,000 trucks change every batch. If that map were React state, React would re-render the whole page on every batch.
  So `vehicles` and `activeAlerts` are **refs** (React does not watch them). The 3D layer reads them directly on each frame.
- `tick` is a small **state** number. It goes up once per telemetry batch, so the panels (counts, selected truck) re-render once per batch, not once per truck.
- `dirty` tells the 3D layer "something changed, rebuild colors and targets on the next frame".

**Shared EventSource (`apiSource.js`)**
- The live page subscribes to 4 events. Opening 4 HTTP connections would be wasteful, so all 4 share one `EventSource`.
- `subscriberCount` counts users. The first `subscribe` opens the connection, the last `unsubscribe` closes it.
  This also makes StrictMode's double mount safe (count goes 4 → 0 → 4, never a second connection).
- `EventSource` reconnects by itself when the connection drops. The backend sends a full snapshot on every connect, so the page never stays empty.

**`useStream` and `handlerRef`**
The handler function is a new function on every render. `useStream` keeps the latest one in a ref and subscribes **once** per event type.
Without the ref, it would unsubscribe and subscribe again on every render.

**Rules inside `useFleetState`**
| Rule | Code |
|---|---|
| GPS lost (`lat` is `null`) → keep the last known position, do not jump to 0,0 | telemetry handler |
| Alert with `end_ts` → remove from active alerts; else add it | alert handler |
| Alert feed has one row per `anomaly_id`: the "ended" update replaces the "started" row and moves to the top. Max 40 rows (`FEED_SIZE`) | alert handler |
| A truck's display status = its highest-priority active anomaly, else its `motion_status` | `statusOf()` |

**Status priority** (when a truck has several active anomalies, the first one wins):
`COLD_CHAIN_BREACH` > `REEFER_UNIT_FAILURE` > `ENGINE_OVERHEATING` > `ROUTE_DEVIATION` > `SPEEDING` > `LOW_FUEL` > `EXCESSIVE_IDLING` > `motion_status` (`DRIVING` / `IDLING` / `PARKED`).

The frontend does **no anomaly detection**. The backend makes alerts from the row flags (e.g. `is_speeding` → `SPEEDING`). See `AlertRow` in `contract.js`.

---

## 9. Mock data source (no backend)
`VITE_DATA_SOURCE=mock` (default). Everything is made in the browser. It follows the same contract, so pages cannot tell the difference.

### 9.1 Warehouse part (`mock/dashboards.js`)
```
getKpis(id) ──300 ms──> buildDashboard(id)
                          ├─ rng = createRng(hashSeed(id))       same seed per page -> same numbers on every load
                          ├─ kpis   = dashboard.kpiIds -> MOCK_KPI_VALUES[id] = [value, previous]
                          ├─ series = SERIES_BUILDERS[id](rng)    one builder per page
                          ├─ period = "Last 30 days vs previous 30 days"
                          └─ as_of  = now
```
- `kpiValues.js`: one table `kpi_id → [value, previous]` for all pages, so the same KPI shows the same number everywhere.
  The numbers are inside the catalog baselines (A.10), e.g. fuel efficiency 34.6 L/100km.
- `walkTo()` makes a random line that **ends at the KPI card value**, so trend charts finish at the number on the card.
- `reference.js`: 18 facilities with real city coordinates, routes between them (each facility to the ones 1, 4 and 7 places ahead, both directions = 108 lanes),
  route distance = straight line × 1.18 (road factor), cold-chain ranges per commodity, and name lists.
- `rng.js`: `mulberry32` seeded generator. Same seed → same "random" data on every run (reproducible).

### 9.2 Live part (`mock/fleetSimulator.js`)
A stand-in for Kafka → Spark → backend SSE. It emits the same 4 events.

| Setting | Value | Meaning |
|---|---|---|
| `TRUCK_COUNT` | 5,000 trucks | fleet size |
| `TICK_MS` / `TICK_MINUTES` | 1,000 ms / 1 min | 1 second of real time = 1 simulated minute |
| `WARMUP_TICKS` | 240 ticks (= 4 simulated hours) | played before the first event, so anomalies already exist |
| `REEFER_SHARE` | 0.5 | ~50% of trucks pull a reefer trailer |
| `REFUEL_LEVEL` | 0.18 | refuel when tank < 18% |
| `SPEEDING_MPH` / `LOW_FUEL_SHARE` / `OVERHEATING_F` | 70 mph / 25% of tank / 230 °F | thresholds of the mock flags |
| `GPS_DROP_CHANCE` / `SENSOR_DROP_CHANCE` | 0.1% / 0.2% per row | dirty data: `null` lat/lon, `null` cargo_temp_f |
| Anomaly start chance per truck per tick | idling 0.004%, route deviation 0.003%, reefer failure 0.006% | how often anomalies start |

**One tick**
```
for each truck:
  advanceTruck   end/start anomaly -> parked? (wait 60-600 min, then new trip from the destination city)
                 idling anomaly? (engine on, speed 0) : drive at cruise speed ± 4 mph along the lane
                 fuel burn (speed / 6.8 mpg, or 0.8 gal/h idle), refuel under 18%
  advanceReefer  failing unit -> cargo warms; else pulled back to setpoint
                 out of allowed range -> open COLD_CHAIN_BREACH alert; back in range -> close it
  positionOf     point on the straight lane; route deviation drifts sideways and back (sine shape)
  build TelemetryRow (+ ReeferRow)
emit 'telemetry' (all 5,000 rows), emit 'reefer', emit 'kpis' (LiveKpis from this tick's rows)
```
- Alerts are emitted when they open and again (with `end_ts`) when they close.
- A new subscriber gets the active alerts and the last `kpis` right away (same as the real backend snapshot).
- The timer starts with the first subscriber and stops when nobody listens. The simulated fleet stays in memory, so going back to the live page continues the same fleet.
- `ROUTE_DEVIATION` exists only in the mock. The real stream has no flag for it.

**Mock vs real stream**
| | Mock | Real backend |
|---|---|---|
| Rows per `telemetry` event | all 5,000 trucks | only rows that changed |
| How often | every 1 s | batches, ~every 5 min today |
| Extra columns | `ingest_ts` | `event_timestamp`, `speed_kmh`, `stream_latency_sec`, `dt`, `hr`, `updated_at` (not used by the dashboard) |

---

## 10. Hooks
| Hook | Input | Output | What it does |
|---|---|---|---|
| `useKpis(dashboardId)` | dashboard id | `{ data, error, loading }` | Loads once, then every 30 min (`REFRESH_MS`). `loading` is true only on the first load. `cancelled` flag ignores answers that come after the page closed. |
| `useStream(eventType, onEvent)` | event name + handler | nothing | Subscribes on mount, unsubscribes on unmount. Always calls the latest handler (`handlerRef`). |
| `useFleetState()` | none | `{ vehicles, dirty, tick, alertFeed, liveKpis, activeTypesByVehicle }` | Builds the live fleet picture (section 8). `activeTypesByVehicle()` returns `vehicle_id → Set of active anomaly types`. |
| `useTheme()` | none | `{ theme, toggleTheme }` | Theme for JS colors (charts, 3D) that cannot use Tailwind `dark:` classes (section 15). |

`useFleetState.js` also exports:
- `STATUS_STYLE`: label + color for every status (the 7 anomaly types + `DRIVING` green, `IDLING` lime, `PARKED` grey).
- `statusOf(telemetry, anomalyTypes)`: the display status of one truck.

---

## 11. KPI catalog (`kpis/definitions.js`)
The backend sends only numbers. Everything a viewer reads about a KPI comes from this file (copied from `Notion_Data_Catalog.md` sections 1–4).

```
KPIS[21] = {
  name:     'Fuel Efficiency',
  unit:     'L/100km',
  better:   'down',          'up' = higher is good, 'down' = lower is good, null = neutral
  meaning:  '...',           shown on the card
  question: 'Q9',            key in QUESTIONS (why we track it)
  formula:  '...',           shown in the KPI Guide tooltip
  action:   '...',           business action (optional; else the group's decisions are used)
}
```

| Export | What it is | Used by |
|---|---|---|
| `KPIS` | 50 KPIs (ids 1–64, some ids removed) | KpiCard, KpiGuidePage, labels |
| `QUESTIONS` | Business questions Q1–Q15 + Outcome 6, 7 | KpiGuidePage ("Why we track it") |
| `KPI_GROUPS` | Catalog sections A–G + Data Platform, with id ranges and "decisions" text | KpiGuidePage sections |
| `ANOMALY_TYPES` | 7 alert types with label + map color | live map, legend, alert feed, TruckLayer |
| `formatValue(value, unit)` | `null` → `-`; `USD/km` → 3 decimals; value ≥ 100 → 0 decimals; else 1 decimal | KPI cards, map hover |
| `kpiLabel(id)` | `"Fuel Efficiency (L/100km)"` | `columnLabel` |
| `columnLabel(key)` | `kpi_21` → `"Fuel Efficiency (L/100km)"`; any other key unchanged | charts, tables |

---

## 12. Shared components
### Page frame
```
Layout
├─ <aside> sidebar                          (on phones: a top bar that scrolls sideways)
│    ├─ "Fleet Data Platform"
│    ├─ one NavLink per DASHBOARDS item     (active link is highlighted)
│    └─ KPI Guide link                      (opens in a new tab, so the viewer keeps the dashboard)
└─ <main> <Outlet/>                         (current page)
      └─ DashboardShell
           ├─ header: title · audience · PeriodInfo (InfoTip) · Last updated · ThemeToggle
           ├─ Loading… / error box
           ├─ KpiGrid -> KpiCard × n
           └─ page content: Panel(title, subtitle) -> chart / table / map
```

| Component | Input (props) | What it shows / does |
|---|---|---|
| `Layout` | none | Sidebar + page area. Below the `md` width the sidebar becomes a top bar. |
| `DashboardShell` | `dashboardId`, `children` (function or elements) | Common frame of every dashboard page (section 7). |
| `KpiGrid` | `kpiIds`, `kpis` | 1 / 2 / 4 cards per row (phone / tablet / wide screen). Order = `kpiIds`. |
| `KpiCard` | `kpiId`, `value`, `previous` | Name + `#id`, big number + unit, trend line, meaning. |
| `Trend` (inside KpiCard) | `value`, `previous`, `unit`, `better` | `▲`/`▼` + change. % KPIs: difference in **pp** (percentage points). Other KPIs: relative change in **%**. Green = good direction, red = bad, grey = neutral KPI. No number if `previous` is 0. |
| `Panel` | `title`, `subtitle`, `className` | White rounded box around one chart or table. |
| `LineChartView` | `data`, `xKey`, `lines[]`, `band?`, `height` | Line chart. `band = {min, max, label}` draws a green "allowed range" area (cold chain). |
| `BarChartView` | `data`, `xKey`, `bars[]`, `layout`, `stacked`, `height` | Bar chart. `layout="vertical"` = horizontal bars (rankings with long names). `stacked` stacks the bars. |
| `DataTable` | `columns[{key, label?, format?}]`, `rows` | Table. Numbers in `en-US` format, `null` → `-`. Missing `label` → `columnLabel(key)`. |
| `Heatmap` | `rows`, `rowKey`, `colKey`, `valueKey`, `min`, `max`, `unit` | Grid colored red→green. Hover a cell for the exact value. |
| `MapOverlay` | `className` (corner) | Box on top of a 3D map. Mouse passes through it to the map. |
| `InfoTip` | `label`, `children` | Info icon; tooltip on hover or keyboard focus. |
| `NoData` | none | "No data" text. |
| `ThemeToggle` | none | Light / dark button. |

**Chart details (`charts.jsx`)**
- Series colors: `#38bdf8, #a78bfa, #34d399, #fbbf24, #f87171` (used in order unless a line/bar gives its own `color`).
- `CHROME` holds grid, tooltip and band-label colors per theme. Series colors are the same in both themes.
- Tooltip shows at most 2 decimals (warehouse values are not rounded, e.g. 93.3726).
- Animations are off, so charts do not move on every refresh.
- An empty or `null` `data` shows `NoData`.

**Helpers**
| File | Function | Result |
|---|---|---|
| `colorScale.js` | `scaleColor(value, min, max, higherIsBetter)` | HSL color: hue 0 (red, bad) → 120 (green, good). Values outside min..max are clamped. |
| `format.js` | `usd(v)` | `$1,240` (no cents) |
| | `usdCents(v)` | `$0.35` (2 decimals) |
| | `yesNo(v)` | `yes` / `no` / `missing` |
| | `dateTime(iso)` | `29 Oct 2026, 11:54` in the viewer's local time |
| | `lane(row)` | `Chicago → Atlanta` from `origin_city`, `destination_city` |

---

## 13. 3D map (`scene/`)
```
MapCanvas  (react-three-fiber <Canvas>)
├─ camera at [0, 30, 24], field of view 45°
├─ background color per theme, ambient + directional light
├─ UsOutline           state borders of the lower 48 states (line segments)
├─ children            the layer of the page:
│    ├─ RouteArcs      (Delivery page)  one arc per lane
│    └─ TruckLayer     (Live page)      all trucks
└─ OrbitControls       drag = rotate, scroll = zoom (distance 6..70 units, cannot go under the map)
```

### `projection.js`
`project(lat, lon)` → `[x, y, z]`. Flat projection centered on lat 38, lon −96.
**1 scene unit = 1 degree of latitude ≈ 69 mi (≈ 111 km).** Longitude is scaled by `cos(38°)` so the map is not stretched.
Good enough for a picture of the country; not for distance math.

### `UsOutline.jsx`
Reads `us-atlas/states-10m.json` (bundled with the app, no map service, no API key), turns borders into line segments with `topojson-client`,
and drops points outside the lower-48 box (Alaska, Hawaii). Built once (`useMemo`).

### `RouteArcs.jsx` (Delivery page)
```
for each lane:
  start   = project(origin lat/lon)
  end     = project(destination lat/lon)
  control = middle point, raised to heightOf(lane)
  arc     = quadratic Bézier curve, 32 segments, color = colorOf(lane)
+ one small sphere per origin city
```
The page decides what height and color mean (`heightOf`, `colorOf`). Hovering an arc calls `onHover(lane)`.

### `TruckLayer.jsx` (Live page)
Draws **all trucks as one instanced mesh**: one 3D model, drawn up to 10,000 times in **one draw call**. This is what keeps 5,000 trucks smooth.

```
every animation frame (useFrame):
  if fleet.dirty:                      (new stream batch or new selection)
     refresh():
       for each truck with a position:
         new telemetry row?  -> new segment from "where it is drawn now" to the new position
                                (jump instead of glide if the move is > 1 unit ≈ 69 mi = a new trip)
         color  = STATUS_STYLE[statusOf(...)]
         scale  = 4.5 selected · 2.6 active anomaly · 1 normal
       measure the gap between batches (max 5 s) = glide duration
  if not settled:
     progress = time since batch / batch gap   (0..1)
     move every truck to progress along its segment, update its matrix
```

| Constant | Value | Meaning |
|---|---|---|
| `CAPACITY` | 10,000 trucks | max trucks drawn |
| `TRUCK_LENGTH` | 0.25 units (≈ 17 mi) | model size, big enough to see the shape when zoomed in |
| `SCALE` | 1 / 2.6 / 4.5 × | normal / anomaly / selected |
| `SNAP_DISTANCE` | 1 unit (≈ 69 mi) | bigger move = jump, not glide |
| `MAX_INTERVAL_MS` | 5,000 ms | longest glide, so a paused browser tab does not make the next glide crawl |
| `MODEL_URL` | `/models/truck_toyota_corsa_b.glb` | 3D model in `public/models/` |

- Heading: `heading_deg` 0 = north. The model is rotated to match, and turns take the short way round.
- Trucks are drawn about **one batch behind** the data, because each batch starts a glide to the new position.
- Click: the mesh reports `instanceId` → `instanceIds[instanceId]` → `vehicle_id` → `onSelect`.
- The model loads in the background (`useGLTF.preload`). `LiveMapPage` wraps the layer in `<Suspense fallback={null}>`, so the map shows without trucks until the model is ready.

---

## 14. Each page in detail
All tables below list: the panel, the `series` key it reads, the chart type, and its unit.
"api" column: ✅ = filled by the backend from Snowflake today, ❌ = `null` today (shows "No data").

### 14.1 Live Fleet Map (`/`, `LiveMapPage.jsx`)
Data: KPI cards from `getKpis('live')` + everything else from the live stream (section 8).
```
DashboardShell("live")      KPI cards 51 Detection Precision (%), 52 Detection Recall (%), 53 Time-to-Detect (min)   api ❌
├─ LiveKpiPanel             11 tiles from LiveKpis
└─ grid
   ├─ "Live fleet" panel    MapCanvas + TruckLayer + legend (truck count per status)
   └─ side column
        ├─ "Selected truck"  telemetry fields (+ reefer fields if the truck has a reefer)
        └─ "Alert feed"      last 40 alerts; click one -> selects that truck
```
| Live KPI tile | Unit | Source field |
|---|---|---|
| Trucks reporting | trucks | `trucks_reporting` |
| Driving / Idling / Parked | trucks | `motion_status[...]` |
| Speeding, Engine overheating, Low fuel | trucks | `is_speeding`, `is_engine_overheating`, `is_low_fuel` (trucks with the flag now) |
| Reefers reporting, Reefer unit failure | reefers | `reefers_reporting`, `is_reefer_unit_failure` |
| Cold-chain compliance | % (+ per commodity) | `cold_chain_compliance_pct` |
| Data age | min | `data_age_min` = backend time − newest `event_ts` |

- Selected truck fields use stream units: `speed_mph` mph, `engine_temp_f` °F, `fuel_gph` gal/h, `fuel_level_gal` gal, `odometer_mi` mi, `lat`/`lon` degrees.
- A missing value shows `missing`, never `0` (catalog A.6). Booleans show `yes` / `no`.
- Alert times are `HH:MM UTC`. Active alerts are red "active since …", ended ones grey "ended …".

### 14.2 Executive Overview (`/executive`)
KPI cards: 1, 20, 26, 11, 46, 41, 36 (11 is ❌ in api mode).
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Service quality trend | `service_trend` (`week_start`, `kpi_1`, `kpi_11`) | line, weekly | % | ✅ |
| Unit economics trend | `unit_economics_trend` (`week_start`, `kpi_26`, `kpi_20`) | line, weekly | USD/km | ✅ |

Meaning: the gap between revenue per km and fuel cost per km is what is left for driver pay, maintenance and profit.

### 14.3 Delivery & Route Performance (`/delivery`)
KPI cards: 1, 2, 3, 5, 6, 7, 8.
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Lanes in 3D | `lane_otd` | 3D arcs (`RouteArcs`) | % on-time | ✅ |
| Lane heatmap | `lane_otd` | `Heatmap` origin × destination | % on-time | ✅ |
| Customers with the lowest on-time rate | `worst_customers` | table | deliveries (count), % | ✅ |
| Average delay by hour of day | `delay_by_hour` (`hour`, `kpi_3`) | bar | min, hour in UTC | ✅ |
| Facilities with the longest destination queue | `facility_queue` (`facility_name`, `kpi_6`) | horizontal bar | min | ✅ |

3D lane map encoding:
- Color: `scaleColor(kpi_1, 80, 100)` → 80% or less = red, 100% = green. The legend bar is sampled from the same scale, so legend and arcs always match.
- Height: `0.5 + (100 − kpi_1) × 0.3` scene units → the later the lane, the taller the arc. Problem lanes stand out.
- Each direction is its own lane (Chicago → Atlanta and Atlanta → Chicago are two arcs).
- Hover shows: lane, on-time %, deliveries (count), typical distance (km).

### 14.4 Cold Chain Monitoring (`/cold-chain`)
KPI cards: 11, 10, 12, 13, 14, 15, 16 (all ❌ in api mode: they need the reefer stream in the warehouse).
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Cargo temperature of one trip | `trip_temperature` (`readings[]`, `min_temp_f`, `max_temp_f`...) | line + green allowed band; gaps = missing readings | °F, time UTC | ❌ |
| Excursion rate by ambient temperature | `excursion_rate_by_ambient` (`ambient_band`, `kpi_17`) | bar | % | ❌ |
| Trailers with the most excursions | `excursions_by_trailer` | horizontal bar | count | ❌ |
| High-risk trips | `high_risk_trips` | table | `peak_temp_f` °F, `duration_min` min | ❌ |

### 14.5 Fuel & Cost (`/fuel`)
KPI cards: 19, 20, 21, 22, 23, 24, 27, 28 (23 is ❌ in api mode).
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Weekly fuel spend | `fuel_spend_trend` (`week_start`, `total_cost`) | line | USD (purchased, not burned) | ✅ |
| Diesel price by state vs national reference | `price_by_state` | bar (2 bars per state) | USD/L | ✅ |
| Least fuel-efficient routes (worst 12) | `fuel_efficiency_by_route` first 12 rows | horizontal bar | L/100km (higher = worse) | ✅ |
| Least fuel-efficient trucks | `fuel_efficiency_by_truck` | table | L/100km | ✅ |
| Fuel efficiency and cost per route (all lanes) | `fuel_efficiency_by_route` | scrollable table | L/100km, USD/km | ✅ |
| Fuel purchase outliers | `purchase_outliers` | table | L, USD/L, USD, % above reference | ✅ |

`fuel_efficiency_by_route` must come sorted worst first (the backend query and the mock both do this); the page takes the first 12 rows.

### 14.6 Fleet Utilization & Driver Safety (`/safety`)
KPI cards: 29, 30, 33, 34, 35, 36, 38 (29, 33, 34, 35 are ❌ in api mode).
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Driver safety & idling scorecard | `driver_scorecard` | table | km, per 100 km, count, %, count | ✅ |
| Where truck time goes | `time_in_state` (`state`, `share_pct`) | horizontal bar | % of fleet hours | ❌ |
| Incidents by type | `incidents_by_type` | table | count, USD | ✅ |

### 14.7 Maintenance & Reliability (`/maintenance`)
KPI cards: 41, 42, 43, 44, 46.
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Monthly maintenance cost | `cost_trend` (`month`, `labor_cost`, `parts_cost`) | stacked bar | USD | ✅ |
| Maintenance mix | `maintenance_mix` | horizontal bar | USD | ✅ |
| Trucks with repeated orders | `repeat_trucks` | table | orders (count), USD, h | ✅ |
| Maintenance cost per km by model year | `cost_by_model_year` (`model_year`, `kpi_44`) | line | USD/km | ✅ |

The model-year line is flat on purpose: the data generator gives maintenance at random, so there is no real age effect.

### 14.8 Data Platform Health (`/platform`)
KPI cards: 54–64 (all ❌ in api mode: pipeline metadata is not in a table the backend can read).
| Panel | Series | Chart | Unit | api |
|---|---|---|---|---|
| Pipeline runs per day | `pipeline_runs` (`succeeded`, `failed`) | stacked bar | runs (96 per day = one every 15 min) | ❌ |
| Snowflake credits per warehouse | `credits_trend` (`AIRBYTE_WH`, `DBT_WH`, `BI_WH`) | stacked bar | credits per day | ❌ |
| Row count reconciliation by layer | `row_counts` | table; gap = `s3_rows − raw_rows` computed on screen | rows | ❌ |

Reading the reconciliation table: S3 and RAW must match (Airbyte lost nothing). STAGING is lower by the removed duplicates.

### 14.9 KPI Guide (`/kpi-guide`, `KpiGuidePage.jsx`)
No data call. Built only from `KPIS`, `QUESTIONS`, `KPI_GROUPS` and `DASHBOARDS`.
```
for each group in KPI_GROUPS:              (A. Delivery ... Data Platform)
  section title
  for each KPI with id in group.from..to:
    GuideCard
      name #id · unit · "Higher/Lower is better" or "Neutral"
      meaning
      Why we track it   = QUESTIONS[kpi.question]
      Business action   = kpi.action, or the group's decisions
      Reference         = Notion_Data_Catalog.md › KPI id
      Shown on          = links to every dashboard whose kpiIds include this id
      Formula           = in the info tooltip
```
It opens in a new tab from the sidebar.

---

## 15. Theme (light / dark)
```
ThemeProvider (useTheme.jsx)
  ├─ start value: localStorage "theme" ('dark' or else 'light')
  ├─ on change: <html class="dark"> on/off + save to localStorage
  │
  ├─> CSS:  index.css  @custom-variant dark (&:where(.dark, .dark *))
  │         -> every Tailwind "dark:..." class works when <html> has "dark"
  │
  └─> JS:   useTheme().theme for colors set in code
            charts.jsx CHROME[theme], MapCanvas BACKGROUND[theme],
            UsOutline BORDER_COLOR[theme], RouteArcs CITY_COLOR[theme]
```
Two ways because Tailwind classes cannot reach colors that Recharts and Three.js set in JavaScript.

---

## 16. Units
| Where | Unit system | Examples |
|---|---|---|
| Warehouse KPIs and series (Snowflake) | Metric + USD | km, L, L/100km, USD/km, USD/L |
| Live stream rows (Kafka silver) | US units, as in the source data | mph, gal, gal/h, mi, °F |
| Cold chain (both) | °F | `cargo_temp_f`, `setpoint_f` |
| Times | UTC in data; "Last updated" is shown in the viewer's local time | `event_ts`, `as_of` |
| Trend on KPI cards | pp for % KPIs, % relative change for all others | `▲ 1.2 pp`, `▼ 4.3%` |
| 3D scene | 1 unit ≈ 1° latitude ≈ 69 mi ≈ 111 km | |

Each KPI's own unit is in `KPIS[id].unit`.

---

## 17. Deploy
- `npm run build` → static files in `dist/`. No server code.
- `vercel.json` sends every path to `index.html`. Without it, refreshing `/fuel` would give a 404, because only `index.html` exists on the server; React Router then reads the URL.
- Set `VITE_DATA_SOURCE`, `VITE_API_BASE_URL`, `VITE_STREAM_URL` in the hosting settings **before** the build (they are copied into the code at build time).
- In api mode the backend must allow the dashboard's origin in CORS (`backend/app/main.py`).

---

## 18. How to change or add things
| Change | File(s) |
|---|---|
| KPI name / unit / meaning / formula / action | `src/kpis/definitions.js` (`KPIS`) |
| KPI Guide sections or business questions | `KPI_GROUPS`, `QUESTIONS` in `src/kpis/definitions.js` |
| Which KPI cards a page shows, and their order | `kpiIds` in `src/dashboards.js` |
| Mock KPI numbers | `src/data/mock/kpiValues.js` |
| Mock chart data | `SERIES_BUILDERS` in `src/data/mock/dashboards.js` |
| Mock fleet size, speed, anomaly rates, thresholds | constants at the top of `src/data/mock/fleetSimulator.js` |
| Truck colors per status | `ANOMALY_TYPES` (`definitions.js`) and `STATUS_STYLE` (`useFleetState.js`) |
| Light / dark colors | `dark:` classes in components; `CHROME` in `charts.jsx`; constants in `src/scene/*` |
| Data shape agreement | `src/data/contract.js` (update together with the backend) |

**Add a KPI card to an existing page**
1. Add the KPI to `KPIS` in `definitions.js` (if it is new).
2. Add its id to the page's `kpiIds` in `dashboards.js`.
3. Mock: add `id: [value, previous]` to `kpiValues.js`.
4. Api: the backend needs a query for it (`backend/app/services/kpi_service.py` → `KPI_QUERIES` + a SQL file). Until then the card shows `-`.

**Add a chart to an existing page**
1. Pick a series name, e.g. `fuel_by_make`. Use `kpi_<id>` for columns that are a KPI.
2. Mock: return it from that page's builder in `mock/dashboards.js`.
3. Api: add it to `DASHBOARD_SERIES` in the backend + a SQL file in `queries/series/`.
4. Page: `<Panel title=... subtitle=...><BarChartView data={series.fuel_by_make} .../></Panel>`.

**Add a new dashboard page**
1. `dashboards.js`: add `{ id, path, title, audience, kpiIds }`.
2. `pages/NewPage.jsx`: `<DashboardShell dashboardId="new_id">{(series) => ...}</DashboardShell>`.
3. `App.jsx`: add `new_id: NewPage` to `PAGES`.
4. Mock: add `new_id(rng) { return {...} }` to `SERIES_BUILDERS`.
5. Backend: add `new_id` to `DASHBOARD_SERIES` (else the API returns 404 for it).
