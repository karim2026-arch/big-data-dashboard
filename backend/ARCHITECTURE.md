# Backend architecture

How `backend/app/` is organised, why, and how to add a new endpoint.
Run steps, config and the endpoint list are in [README.md](README.md).

## 1. Why layers
The backend will serve 8 dashboards (about 60 KPIs) and a live stream ([../dashboard/src/data/contract.js](../dashboard/src/data/contract.js)).
If routes, logic and SQL all live in one file, that file becomes very large, and every change touches it.
So the code is split by **job**, and each job has one folder:

| Folder | Job | Knows about |
|---|---|---|
| `api/` | HTTP: URL, which service to call, response schema | services, schemas |
| `services/` | Logic: what to compute and how results are combined | `domain/` contracts only |
| `domain/` | Contracts: which data functions exist (Python `Protocol`) | nothing |
| `infrastructure/` | Real data access: Snowflake connection, SQL files, repositories | Snowflake, `core/config` |
| `schemas/` | Exact JSON shape of each response (Pydantic) | nothing |
| `core/` | Shared setup: settings from `.env`, error handler | `.env` |

**The one rule:** services never import Snowflake. They only see the contracts in `domain/repositories.py`.
`api/dependencies.py` is the single place that says "use the Snowflake version".

```
            api/routes  ──calls──>  services  ──uses contract──>  domain/repositories.py
                │                                                        ▲
         api/dependencies.py ──builds service with──>  infrastructure/repositories  (implements it)
                                                              │
                                              sql_loader + snowflake_client ──> Snowflake
```

## 2. One request, step by step: `GET /api/kpis/validation`
1. `main.py` has included `api/router.py`, which mounts `api/routes/kpis.py` under `/api`.
2. FastAPI sees `Depends(get_kpi_validation_service)` in the route and calls `api/dependencies.py`.
   It builds `KpiValidationService(SnowflakeKpiRepository())`.
3. The route calls `service.calculate_all()`.
4. The service loops over `KPIS` (`(9, "Distance Variance", "%", "distance_variance")`, …) and for each
   calls `repository.fetch_kpi("distance_variance")`.
5. `SnowflakeKpiRepository.fetch_kpi()` gets the SQL with `load_sql("kpis/distance_variance")`
   (reads `infrastructure/queries/kpis/distance_variance.sql` once, then from memory) and runs it with `snowflake_client.fetch_all()`.
6. The service adds `kpi_id, name, unit` to each row and returns a list of dicts.
7. FastAPI checks the list against `response_model=list[KpiValidation]` and sends the JSON.
8. If Snowflake fails at any step, `core/errors.py` turns it into HTTP 503 with the Snowflake message.

## 3. Every file
```
backend/app/
  main.py
  core/        config.py, errors.py
  domain/      repositories.py
  infrastructure/
               snowflake_client.py, sql_loader.py
               queries/kpis/distance_variance.sql, margin_proxy.sql
               repositories/snowflake_system_repository.py, snowflake_kpi_repository.py
  services/    system_service.py, kpi_validation_service.py
  schemas/     system.py, kpi_validation.py
  api/         dependencies.py, router.py
               routes/health.py, tables.py, kpis.py
```
Each folder has an empty `__init__.py` so Python treats it as a package (needed for `from ..core.config import settings`).

### `main.py` (builds the app, nothing else)
| Line | What it does |
|---|---|
| `lifespan` | Code after `yield` runs on shutdown: closes the shared Snowflake connection |
| `app.add_middleware(CORSMiddleware, ...)` | Lets the dashboard (`http://localhost:5173`) call the API from the browser |
| `app.add_exception_handler(SnowflakeError, snowflake_error_handler)` | Any Snowflake error → 503 (was a decorator in `main.py` before) |
| `app.include_router(api_router)` | Adds all routes from `api/router.py` |

### `core/`
- **`config.py`**: unchanged except `parents[1]` → `parents[2]`. `Path(__file__).parents[0]` is `core/`, `[1]` is `app/`, `[2]` is `backend/`, where `.env` lives.
- **`errors.py`**: `snowflake_error_handler`, moved out of `main.py` with the same code.

### `domain/repositories.py` (the contracts)
```python
class KpiRepository(Protocol):
    def fetch_kpi(self, query: str) -> dict: ...
```
A `Protocol` lists the methods a class must have. It has no code (`...`).
Any class with a matching `fetch_kpi` method counts as a `KpiRepository`, with no inheritance needed.
The service is typed against this contract, so a test can pass a fake class instead of Snowflake.

`fetch_kpi(query)` takes the query name instead of one method per KPI, so 60 KPIs don't need 60 methods.

### `infrastructure/`
- **`snowflake_client.py`**: unchanged except the import path (`..core.config`). Still the only file that opens a connection.
- **`sql_loader.py`**: `load_sql("kpis/margin_proxy")` returns the text of `queries/kpis/margin_proxy.sql`.
  `@cache` stores the result, so each file is read from disk only once.
  The name always comes from code (`KPIS`), never from a URL, so a user cannot make it read another file.
- **`queries/kpis/*.sql`**: the same SQL as the old Python strings (checked character by character), with the comments as `--` lines.
  You can paste them straight into a Snowflake worksheet.
- **`repositories/snowflake_kpi_repository.py`**: `fetch_kpi(query)` = `fetch_all(load_sql(f"kpis/{query}"))[0]` (the first and only row).
- **`repositories/snowflake_system_repository.py`**: `current_session()` and `list_tables()`. Their short SQL stays here as strings (decision: only KPI SQL in `.sql` files).

### `services/`
- **`kpi_validation_service.py`**: was `kpi_validation.py`. `KPIS` now holds the query name instead of the SQL text.
  `calculate_all()` has the same logic as before, but calls `self._repository.fetch_kpi(query)`.
  `__init__(self, repository: KpiRepository)` receives the repository from outside (dependency injection). The service never creates it.
- **`system_service.py`**: `health()` is the old `/health` logic (`status: "ok"` + lower-cased keys). `tables()` passes the table list through.

### `schemas/`
The exact JSON fields. They appear in `/docs`, and FastAPI checks every response against them.
- **`system.py`**: `HealthResponse`, `TableRow`. `schema` is already a name inside Pydantic's `BaseModel`, so the field is
  `schema_: str | None = Field(alias="schema")`. FastAPI writes the alias, so the JSON key is still `schema`.
- **`kpi_validation.py`**: `KpiValidationBase` holds the shared `kpi_id, name, unit` (written once, not repeated).
  `DistanceVarianceValidation` (`kpi_id: Literal[9]`) and `MarginProxyValidation` (`kpi_id: Literal[28]`) add each query's columns.
  `KpiValidation = Annotated[A | B, Field(discriminator="kpi_id")]` tells Pydantic to choose the model by `kpi_id`.
  Field names stay upper case because Snowflake returns them that way, so the JSON is identical to before.

### `api/`
- **`dependencies.py`**: one function per service, e.g. `get_kpi_validation_service()` returns `KpiValidationService(SnowflakeKpiRepository())`.
  This is the only file that imports both services and Snowflake repositories.
- **`routes/*.py`**: each file has `router = APIRouter(...)` and one function per URL. Example:
  ```python
  @router.get("/validation", response_model=list[KpiValidation])
  def kpis_validation(service: Annotated[KpiValidationService, Depends(get_kpi_validation_service)]) -> list[dict]:
      return service.calculate_all()
  ```
  `Depends(...)` makes FastAPI call `get_kpi_validation_service()` and pass the result in as `service`.
  `tags=[...]` only groups the routes in `/docs`.
- **`router.py`**: joins the route files. `/health` stays at the root; `tables` and `kpis` get `prefix="/api"`.

## 4. How to add a new endpoint (example: `GET /api/kpis/{dashboard}`)
Each layer gets one small addition, and nothing existing changes except `router.py` and `dependencies.py`:

| Step | File | Add |
|---|---|---|
| 1 | `infrastructure/queries/dashboards/<id>.sql` | The SQL for that dashboard |
| 2 | `domain/repositories.py` | `class DashboardRepository(Protocol)` with the method the service needs |
| 3 | `infrastructure/repositories/snowflake_dashboard_repository.py` | The Snowflake version, using `load_sql()` + `fetch_all()` |
| 4 | `services/dashboard_service.py` | `DashboardService(repository)` with the logic (e.g. current vs previous period) |
| 5 | `schemas/dashboard.py` | `DashboardResponse` and `KpiValue`, as in `contract.js` |
| 6 | `api/dependencies.py` | `get_dashboard_service()` |
| 7 | `api/routes/dashboards.py` | The route, which must check `dashboard` against the list of known ids before using it in a file name |
| 8 | `api/router.py` | `api_router.include_router(dashboards.router, prefix="/api")` |

The live stream (SSE) follows the same pattern: `routes/stream.py` → `services/stream_service.py` → a stream contract in `domain/` → a Kafka (or other) implementation in `infrastructure/`.

## 5. What did not change
- URLs: `/health`, `/api/tables`, `/api/kpis/validation`.
- JSON: byte-for-byte identical to before (checked on 2026-10-29).
- `.env`, `requirements.txt`, the start command (`uvicorn app.main:app`).
