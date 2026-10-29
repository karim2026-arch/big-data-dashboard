# Fleet Dashboard API (backend)

FastAPI in front of Snowflake. The React dashboard ([../dashboard](../dashboard)) calls it at `http://localhost:8000/api`.
Login is username + password, read from `backend/.env`. No Snowflake value is written in code.

## Run
```bash
# from the project root, once: install into the shared .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt

# config: copy and fill with the values from the Snowflake owner
cp backend/.env.example backend/.env

# start (from backend/)
cd backend
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs to try the endpoints.

## Config (`backend/.env`, git-ignored)
| Variable | Required | Meaning |
|---|---|---|
| `SNOWFLAKE_API_ACCOUNT` | yes | Account identifier `ORGNAME-ACCOUNTNAME` |
| `SNOWFLAKE_API_USER` / `SNOWFLAKE_API_PASSWORD` | yes | Login |
| `SNOWFLAKE_API_DATABASE` | yes | Database to query |
| `SNOWFLAKE_API_ROLE` / `_WAREHOUSE` / `_SCHEMA` | no | Empty = the user's defaults in Snowflake |
| `API_CORS_ORIGINS` | no | Browser origins allowed, comma-separated (default `http://localhost:5173`) |

## Endpoints
| Endpoint | Returns |
|---|---|
| `GET /health` | `{status, login_user, role, warehouse, database, schema}` as Snowflake sees the session |
| `GET /api/tables` | One row per table or view the user can see: `TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ROW_COUNT` |
| `GET /api/kpis/validation` | KPI 9 and KPI 28 over all `DBT_MARTS` rows, each with join checks (see below) |

Any Snowflake failure (login, SQL, timeout) returns HTTP 503 with the Snowflake message in `detail`.

## Flow
```
browser  ──>  app/main.py (routes, CORS, error handler)
                 ├──>  app/kpi_validation.py  calculate_all()  (KPI SQL)
                 └──>  app/snowflake_client.py  fetch_all(sql)  ──>  Snowflake
                            └── app/config.py  settings (backend/.env)
```
- `config.py`: reads `.env` once; fails at startup with the list of missing variables.
- `snowflake_client.py`: one shared connection, opened on first query and reopened if Snowflake closed it. `fetch_all()` returns rows as dicts.
- `kpi_validation.py`: one SQL query per KPI in `KPIS`; `calculate_all()` runs each and adds `kpi_id, name, unit`.
- `main.py`: endpoints only call `fetch_all()` or `calculate_all()`. Column names come back upper case, as Snowflake returns them.

## KPI validation (`GET /api/kpis/validation`)
Checks that the mart joins work by calculating two KPIs that need joins, over **all rows** (no date filter).
Units are as the marts store them: **km** and **USD** (not the catalog's miles). Table names are not schema-qualified, so `SNOWFLAKE_API_SCHEMA` must be `DBT_MARTS`.

| KPI | Formula | Join checked |
|---|---|---|
| 9 Distance Variance (%) | AVG over trips of `(actual_distance_km − typical_distance_km) / typical_distance_km × 100` | `FCT_TRIPS` → `DIM_ROUTE` on `ROUTE_KEY` |
| 28 Margin Proxy per Trip (USD) | AVG over trips of revenue − fuel − maintenance | `FCT_TRIPS` → `FCT_FUEL_PURCHASES` on `TRIP_ID`, → `FCT_MAINTENANCE` on `TRUCK_KEY` |

KPI 28 rules: revenue = `REVENUE_USD + FUEL_SURCHARGE_USD + ACCESSORIAL_CHARGES_USD`; fuel = sum of the trip's `FCT_FUEL_PURCHASES.TOTAL_COST`; maintenance = truck's total `FCT_MAINTENANCE.TOTAL_COST` × trip km / truck's total trip km. Trips with no `TRUCK_KEY` are excluded and counted.
The `*_ALL_*` columns are full-table totals: compare them with the used totals to see how much cost the joins dropped.

## Next
`GET /api/kpis/{dashboard}` per [../dashboard/src/data/contract.js](../dashboard/src/data/contract.js), once the table names in the owner's Snowflake are known (use `/api/tables` to list them).
