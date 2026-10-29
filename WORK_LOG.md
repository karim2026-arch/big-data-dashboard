# 🧾 Work Log: S3 → Airbyte → Snowflake → dbt

**Author:** Karim Mohamed
**Scope:** the batch path, from S3 (Bronze) to Snowflake and dbt.
Step numbers follow the progress table in [README.md](README.md#6-progress).

**How I document each step (team rules from [Notion_Documentation.md](Notion_Documentation.md)):**
1. Write the step right after I finish it.
2. Each step = **what I did** (1–3 lines) + **screenshot** + **code** (if any).
3. Never show passwords, keys or tokens. Use `<YOUR_KEY>` and blur screenshots.

Screenshot naming: `tool-stepnumber-name.png` (for example `snowflake-3a-account.png`).

Status: ✅ done · ⏳ in progress · ⬜ not started

---

## Step 3: Snowflake setup ✅

### 3a. Create the Snowflake account ✅
**What I did:** Signed up at signup.snowflake.com with **Enterprise** edition on **AWS**, in the same region as the S3 bucket (avoids data transfer charges).

| Setting | Value |
|---|---|
| Edition | Enterprise |
| Cloud | AWS |
| Region | EU (Stockholm) `AWS_EU_NORTH_1`, same as the S3 bucket |
| Date | 2026-10-26 |

**Screenshot:** `snowflake-3a-account.png`

### 3b. Create the key pairs for the service users ✅
**What I did:** Created one RSA key pair per service user (`AIRBYTE_USER`, `DBT_USER`). The private key (`.p8`) stays on my PC. The public key (`.pub`) goes into Snowflake. Keys are stored outside the repo in `~/.snowflake_keys/`.

**Code (Git Bash):**
```bash
mkdir -p ~/.snowflake_keys && cd ~/.snowflake_keys

# Airbyte user
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out airbyte_rsa_key.p8 -nocrypt
openssl rsa -in airbyte_rsa_key.p8 -pubout -out airbyte_rsa_key.pub

# dbt user
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out dbt_rsa_key.p8 -nocrypt
openssl rsa -in dbt_rsa_key.p8 -pubout -out dbt_rsa_key.pub
```

**Result:** 4 files: `airbyte_rsa_key.p8`, `airbyte_rsa_key.pub`, `dbt_rsa_key.p8`, `dbt_rsa_key.pub`.

> ⚠️ Never commit or screenshot the `.p8` files. `.gitignore` blocks `*.p8` and `*.pub`.

### 3c. Run the setup script ✅
**What I did:** Ran [snowflake/01_setup.sql](snowflake/01_setup.sql) as `ACCOUNTADMIN` in a Snowflake worksheet. Placeholders were replaced **in the worksheet only**, not in the repo file.

| Placeholder | Replaced with |
|---|---|
| `<PASTE_AIRBYTE_PUBLIC_KEY_HERE>` | Body of `airbyte_rsa_key.pub` (no BEGIN/END lines, no line breaks) |
| `<PASTE_DBT_PUBLIC_KEY_HERE>` | Body of `dbt_rsa_key.pub` |

> The script grants the 3 roles to my own login automatically with `CURRENT_USER()`, so there is no username to replace.

**Code (print a public key on one line, ready to paste):**
```bash
grep -v "PUBLIC KEY" ~/.snowflake_keys/airbyte_rsa_key.pub | tr -d '\n'
grep -v "PUBLIC KEY" ~/.snowflake_keys/dbt_rsa_key.pub | tr -d '\n'
```

**What the script creates:**

| Object | Names |
|---|---|
| Warehouses (XSMALL, auto-suspend 60 s) | `AIRBYTE_WH`, `DBT_WH`, `BI_WH` |
| Database | `FLEET_DB` |
| Schemas | `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `SEEDS` |
| Roles | `AIRBYTE_ROLE`, `TRANSFORMER`, `REPORTER` |
| Service users (key pair) | `AIRBYTE_USER`, `DBT_USER` |
| Cost guard | `FLEET_MONTHLY_RM` (50 credits a month: notify at 75%, suspend at 90% and 100%) |

**Screenshot:** `snowflake-3c-setup-run.png`

### 3d. Verify ✅
**Code:**
```sql
SHOW SCHEMAS IN DATABASE FLEET_DB;
SHOW USERS LIKE '%_USER';
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier;
```

**Result:**
- Schemas found: `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `SEEDS`
- `RSA_PUBLIC_KEY_FP` set (starts with `SHA256:`) for `AIRBYTE_USER` and `DBT_USER`
- Account identifier (needed by Airbyte and dbt): `RSGNWLJ-PK32132` (Snowflake host: `RSGNWLJ-PK32132.snowflakecomputing.com`)

**Screenshot:** `snowflake-3d-verify.png`

---

## Step 4: AWS access for Airbyte + bucket survey ✅

### 4a. AWS identity for Airbyte ✅ (my IAM user `Karim`)
**Permission check (2026-10-26):** my IAM user can read the bucket in the S3 console ✅, but cannot create IAM users ❌ and cannot open CloudShell ❌. The account owner creates this user and its access key (4a + 4b) and sends me the key privately.
**Decision (2026-10-26): Airbyte uses my IAM user `Karim`.** My user cannot create its own access key (no IAM permissions: `iam:ListAccessKeys`, `iam:GetAccountSummary` and others are denied), so the account owner creates an access key **for user `Karim`** and sends it privately. Trade-off: Airbyte gets all of `Karim`'s permissions, and the pipeline depends on my user. Later option: switch to a dedicated `airbyte-s3-reader`.
**What the owner does:** In AWS IAM, creates the user `airbyte-s3-reader` (no console access) and attaches an inline policy that can only list and read the bucket `fleet-telematics-lakehouse-team11`.

**Code:** policy [aws/airbyte_s3_readonly_policy.json](aws/airbyte_s3_readonly_policy.json)
- `s3:ListBucket`, `s3:GetBucketLocation` on the bucket
- `s3:GetObject` on all objects in the bucket

**Screenshot:** `aws-4a-iam-user.png`

### 4b. Create an access key for Airbyte ✅
**Result (2026-10-27):** the owner created access key `…LKJI` for user `Karim`. Saved in `~/.aws/credentials`, and `.env` was rebuilt with `bash tools/build_env.sh`. Check: `who am I` = `user/Karim`, bucket region `eu-north-1`, list root OK (`bronze/`, `fleet/`), list `fleet/bronze/tms/trips/` OK.
**What I did:** IAM → `airbyte-s3-reader` → Security credentials → Create access key ("Application running outside AWS"). Saved the key ID and secret in a safe place (not in the repo).

**Screenshot:** `aws-4b-access-key.png` (blur the key)

### 4c. Run the bucket survey ✅
**What I did:** Ran [tools/s3_survey.py](tools/s3_survey.py) to list every folder in the bucket (file count, size, first and last file date) and print the first lines of one sample file per folder. This decides the Airbyte stream list.

**Code:**
```bash
# one-time: virtual env + dependencies (.venv is git-ignored)
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# credentials: C:\Users\dev\.aws\credentials (outside the repo, read by boto3)
.venv/Scripts/python tools/s3_survey.py fleet-telematics-lakehouse-team11 > tools/s3_survey.txt
```

**Result (2026-10-27):** 583 objects in 18 folder groups (sizes in MB, all small because the generator started on 2026-10-26).

| Folder | Files | Format | Airbyte stream? |
|---|---|---|---|
| `fleet/bronze/registry/trucks`, `registry/trailers`, `hr/drivers` | 3 each | CSV.gz (daily snapshot) | Yes |
| `fleet/bronze/tms/customers`, `facilities`, `routes` | 3 each | CSV.gz (daily snapshot) | Yes |
| `fleet/bronze/tms/loads`, `trips`, `delivery_events` | 103 each | CSV.gz (every 15 min) | Yes |
| `fleet/bronze/fuel_card/fuel_purchases` | 89 | CSV.gz | Yes |
| `fleet/bronze/cmms/maintenance_records` | 44 | CSV.gz | Yes |
| `fleet/bronze/safety/safety_incidents` | 1 | CSV.gz | Yes |
| `fleet/bronze/prices/diesel_prices` | 3 | CSV.gz | Yes |
| `bronze/telemetry.raw/dt=/hour=` | 4 | JSON lines (uncompressed), from Kafka Connect | To decide |
| `fleet/bronze/weather/open_meteo` | 6 | JSON.gz (one JSON array per file) | To decide |
| `fleet/ground_truth/gen_anomaly_labels` | 102 | JSONL.gz (evaluation only) | To decide |
| `fleet/silver/telemetry` | 7 | Parquet (written by Spark, 1 empty folder marker) | No (not Bronze) |

Not found in the bucket: `fleet/bronze/stream_direct/`, `fleet/bronze/prices/eia/`, `bronze/reference/`, and no Kafka Connect folder for reefer.

**Script fixes:** `tools/s3_survey.py` now skips empty (0-byte) objects when picking a sample (S3 returned `InvalidRange`) and writes UTF-8 output (Windows `cp1252` could not encode some characters).
(`tools/s3_survey.txt` is git-ignored.)

---

## Step 5: Airbyte source, destination, connection, first sync ⏳

### 5a. Source: Amazon S3 ✅ (S3 connector v4.16.1)
**What I did:** In Airbyte Cloud, created the source `fleet-s3-bronze` (Amazon S3, delivery method **Replicate Records**) with a first test stream. After the owner sent a working key (`…LKJI`, user `Karim`), the connection test passed and the source was saved (2026-10-27).

| Field | Value |
|---|---|
| Bucket | `fleet-telematics-lakehouse-team11` |
| Authentication | IAM user access key (user `Karim`) |
| Stream name | `trips` |
| Globs | `fleet/bronze/tms/trips/**/*.csv.gz` (default `**` removed) |
| Format | CSV, header from CSV, inference type **None** (all columns as text) |
| Validation policy | Emit record |

**Screenshot:** `airbyte-5a-source.png`

### 5b. Destination: Snowflake ✅
**What I did:** Created the destination `fleet-snowflake-raw` (Snowflake connector v5.2.0) with key-pair authentication.

| Field | Value |
|---|---|
| Host | `RSGNWLJ-PK32132.snowflakecomputing.com` |
| Role / Warehouse | `AIRBYTE_ROLE` / `AIRBYTE_WH` |
| Database / Default schema | `FLEET_DB` / `RAW` |
| Username | `AIRBYTE_USER` |
| Authorization | Key Pair: full `airbyte_rsa_key.p8`, including BEGIN/END lines, no passphrase |

**Code (copy the private key to the clipboard without showing it):**
```bash
cat ~/.snowflake_keys/airbyte_rsa_key.p8 | clip
```

**Test from my PC (same login as Airbyte):** login OK as `AIRBYTE_USER`, `AIRBYTE_ROLE`, `AIRBYTE_WH`, `FLEET_DB.RAW`, region `AWS_EU_NORTH_1`; create and drop a test table in `RAW` OK.

**Screenshot:** `airbyte-5b-destination.png`

### 5c. Connection + streams ✅
**What I did:** Added 12 more CSV streams to the source (13 in total, same settings as `trips`), then created the connection `fleet-s3-bronze → fleet-snowflake-raw` (2026-10-28).

| Setting | Value | Why |
|---|---|---|
| Streams | `trucks`, `trailers`, `drivers`, `customers`, `facilities`, `routes`, `loads`, `trips`, `delivery_events`, `fuel_purchases`, `maintenance_records`, `safety_incidents`, `diesel_prices` | Globs: `<S3 folder>**/*.csv.gz` (see the 4c survey table) |
| Sync mode | **Incremental \| Append** (all streams) | Reads only new files and keeps every row. No primary key needed. De-duplication happens in dbt (keeps snapshot history and dirty rows) |
| Destination namespace | Destination default (`RAW`) | Tables land in `FLEET_DB.RAW` |
| Stream prefix | none | Table names = stream names |
| Schema changes | Propagate field changes only | New columns are added automatically. All columns are text, so type changes cannot happen |
| Schedule | Every 1 hour | Airflow takes over later (Step 10) |

Not added yet: `telemetry_raw` (JSONL), weather (JSON array) and anomaly labels (evaluation only). Still to decide.

**Screenshot:** `airbyte-5c-connection.png`
### 5d. First sync ⬜

## Step 6: Verify RAW (row counts S3 vs Snowflake) ⬜

## Step 7: dbt project + connection ⬜

## Step 8: dbt staging models + tests ⬜

## Step 9: dbt intermediate + marts + seeds ⬜

## Step 10: Airflow DAG (Airbyte → dbt run → dbt test) ⬜

---

## Web dashboard (frontend) ⏳
> **Update 2026-10-29:** the mock data source (fake numbers + in-browser simulator) described in this entry was removed. The dashboard now reads only the backend. See "Mock data removed" below.

**What I did (2026-10-26):** Built [dashboard/](dashboard/): React + Vite + Tailwind, Recharts for KPI charts, Three.js (react-three-fiber) for the 3D map. All 7 dashboards from the catalog plus a Live Fleet Map. Data is mocked behind one switchable data source, so the real backend plugs in later without touching the pages. Details: [dashboard/README.md](dashboard/README.md).

**Logic:**
- Pages → hooks (`useKpis`, `useStream`) → `dataSource` → `mock` or `api` (chosen by `VITE_DATA_SOURCE`). Since 2026-10-29: `api` only, no switch.
- Warehouse KPIs come pre-calculated (`GET /kpis/{dashboard}`). The frontend does no KPI math.
- Live data comes over SSE (`telemetry` and `reefer` batches, `alert` rows) with the catalog column names.
- The mock simulator moves 5,000 trucks on 108 lanes and injects the 4 anomaly families.

**Tests done:** `vite build` passes. A headless check confirmed that all 8 dashboards return their KPIs and series, the simulator emits 5,000 telemetry plus about 2,500 reefer rows per tick, and all 4 anomaly types appear (about 50 active at once). The dev server serves all pages. Not yet checked: visual check in a browser.

**Still open:**
- Thresholds to confirm with the team (labelled as assumptions in the UI): speeding > 70 mph, excessive idling > 30 min, severe delay > 120 min, route deviation > 5 mi.
- Backend: implement `GET /kpis/{dashboard}` from MARTS and the SSE stream, both following [dashboard/src/data/contract.js](dashboard/src/data/contract.js).
- The `series` key names are proposals for the MARTS tables. Rename them together with dbt.

---

## Backend API (FastAPI → Snowflake) ⏳
**What I did (2026-10-28):** Built [backend/](backend/): FastAPI that logs in to Snowflake with username + password from `backend/.env` and answers `GET /health` (who am I in Snowflake) and `GET /api/tables` (tables and views the user can see, with row counts). Details and run steps: [backend/README.md](backend/README.md).
The Snowflake it will query is a **second account owned by a teammate** (not `RSGNWLJ-PK32132`). The owner sends account identifier, user, password, database (and optionally role, warehouse, schema); they go into `backend/.env` only.

**Decisions (2026-10-28):** password login only · first scope = connection + health + table listing · `backend/` next to `dashboard/`, API only (Vite dev server calls `http://localhost:8000/api`, CORS allows `http://localhost:5173`).

**Logic:** `main.py` routes → `snowflake_client.fetch_all(sql)` (one shared connection, reopened if Snowflake closes it) → `config.settings` (reads `backend/.env` once). Any Snowflake error becomes HTTP 503 with the Snowflake message.

**Files:** `backend/.env.example`, `backend/requirements.txt`, `backend/README.md`, `backend/app/{__init__,config,snowflake_client,main}.py`. Packages installed into the shared `.venv`: `fastapi`, `uvicorn`, `pydantic-settings` (`snowflake-connector-python` was already there).

**Tests done:** without `backend/.env` the app stops at startup listing the missing variables ✅ · server starts, `/docs` shows `/health` and `/api/tables` ✅ · with a fake account `/health` returns 503 `Snowflake error: 250001 (08001): Failed to login ...` ✅ · CORS preflight from `http://localhost:5173` returns 200 ✅.
**Real login (2026-10-29) ✅:** owner's account `QGAUKSF-CF11950`, user `AIRFLOW_USER` (role `AIRFLOW_ROLE`), database `SUPPLYCHAIN_DW`, schema `DBT_MARTS`. First `/api/tables` call failed with `000606: No active warehouse selected` because the user has no default warehouse. `SHOW GRANTS TO ROLE AIRFLOW_ROLE` shows `USAGE` on `AIRBYTE_WH` only, so `SNOWFLAKE_API_WAREHOUSE=AIRBYTE_WH` was set in `backend/.env`. After that `/health` and `/api/tables` return 200.

**Tables seen in `SUPPLYCHAIN_DW.DBT_MARTS` (row counts on 2026-10-29):** `DIM_CUSTOMER` 2,500 · `DIM_DATE` 1,034 · `DIM_DRIVER` 10,366 · `DIM_FACILITY` 50 · `DIM_LOCATION` 25 · `DIM_ROUTE` 116 · `DIM_TRAILER` 7,500 · `DIM_TRUCK` 5,000 · `FCT_DELIVERY_EVENTS` 1,909,128 · `FCT_FUEL_PURCHASES` 1,852,581 · `FCT_MAINTENANCE` 106,524 · `FCT_SAFETY_INCIDENTS` 2,422 · `FCT_SHIPMENTS` 953,716 · `FCT_TRIPS` 953,293. The role also reads `RAW_DATA` (13 tables, 1k to 7.7M rows). `FCT_MAINTENANCE` and `FCT_SAFETY_INCIDENTS` were not in the list the owner sent.

### KPI validation endpoint ✅ (2026-10-29)
**What I did:** Added `GET /api/kpis/validation`. It calculates two KPIs that need joins on `DBT_MARTS` over all rows, and returns each value with join checks (rows matched / unmatched, used vs full-table totals), to prove the model joins work.

**Decisions:** KPI 9 Distance Variance + KPI 28 Margin Proxy · units as stored (km, USD) · all data, no date filter · fuel = purchases by `TRIP_ID` · maintenance allocated per km of the truck · trips with no `TRUCK_KEY` excluded and counted · return KPI + totals.

**Logic:** `main.py` route → `kpi_validation.calculate_all()` runs one SQL per KPI (list `KPIS`) through `snowflake_client.fetch_all()` and adds `kpi_id, name, unit`. Decimals are cast to `FLOAT` in SQL so JSON has numbers, not strings.

**Files:** new `backend/app/kpi_validation.py` · `backend/app/main.py` (import + route) · `backend/README.md`.

**Result (2026-10-29, response time ~2 s):**

| Check | Value | Meaning |
|---|---|---|
| KPI 9 Distance Variance | 0.14 % | Trips are on average 0.14% longer than the route's typical km |
| `FCT_TRIPS` → `DIM_ROUTE` | 953,293 / 953,293 matched | Route join is clean |
| KPI 28 Margin Proxy | 3,046.04 USD per trip | Average revenue − fuel − maintenance, over 933,945 trips |
| Trips without `TRUCK_KEY` | 19,348 trips (2.0%) | ⚠️ Model gap: excluded from KPI 28 |
| Fuel purchases with unknown `TRIP_ID` | 4,353 rows, 2,352,817.84 USD | ⚠️ Orphan rows: fuel not linked to any trip |
| Used trips with no fuel purchase | 55,512 trips (5.9%) | To check with the owner: short trips or missing data |
| Fuel used vs all purchases | 1,055,137,876.93 / 1,079,341,007.04 USD | Gap 24,203,130.11 USD = orphans 2,352,817.84 + no-truck trips 21,850,312.27 (reconciles exactly) |
| Maintenance used vs all orders | 208,150,661.15 / 208,150,661.15 USD | Per-km allocation keeps 100% of the cost |

**Tests done:** both queries run in Snowflake ✅ · endpoint returns 200 on a test instance (port 8001) ✅ · margin recomputed by hand: (4,108,119,848.35 − 1,055,137,876.93 − 208,150,661.15) / 933,945 = 3,046.04 ✅ · fuel gap split checked with a separate query ✅. The server on port 8000 runs without `--reload`, so it needs a restart to serve the new route.

### Full model check script ✅ (2026-10-29)
**What I did:** Added [tools/validate_marts.py](tools/validate_marts.py). It runs 53 checks on `DBT_MARTS` and prints one PASS / WARN / FAIL line per check, then a total. Exit code 1 if any FAIL (ready for Airflow later).

**Decisions:** one-off script, not an API route · FAIL = orphan key, duplicate key, or a history ID without exactly one `IS_CURRENT` row · WARN = NULL keys.

**Logic:** three lists (`FOREIGN_KEYS` 33, `UNIQUE_KEYS` 18, `HISTORY_DIMS` 2) + three SQL templates, each returning `ROWS_TOTAL, NULL_KEYS, PROBLEM_KEYS`. It reuses the backend login (`backend/app/infrastructure/snowflake_client.py` since the 2026-10-29 restructure, `backend/.env`), so there is no second copy of the connection code.

**Code:**
```bash
.venv/Scripts/python tools/validate_marts.py
```

**Result (2026-10-29, ~21 s): 53 checks: 40 PASS, 9 WARN, 4 FAIL**

| Status | Check | Count (rows) | Cause found |
|---|---|---|---|
| FAIL | `FCT_DELIVERY_EVENTS.TRIP_ID` not in `FCT_TRIPS` | 5,236 events (2,618 trips) | 1,336 are from the last 10 days (trips not finished yet: `FCT_TRIPS` has only `Completed` trips). The rest go back to 2023-12-29 |
| FAIL | `FCT_DELIVERY_EVENTS.LOAD_ID` not in `FCT_SHIPMENTS` | 4,390 events | The same 4,390 rows have NULL `CUSTOMER_ID`, `ROUTE_ID`, `LOAD_DATE_KEY` (copied from the missing load) |
| FAIL | `FCT_FUEL_PURCHASES.TRIP_ID` not in `FCT_TRIPS` | 4,353 purchases | 3,546 (81%) from the last 10 days → mostly trips not finished yet |
| FAIL | `FCT_SAFETY_INCIDENTS.TRIP_ID` not in `FCT_TRIPS` | 6 incidents | All from 2026-10-25 to 10-28 → trips not finished yet |
| WARN | `FCT_MAINTENANCE.FACILITY_KEY` is NULL | 106,524 of 106,524 (100%) | ⚠️ Column is never filled: a dbt model bug |
| WARN | `FCT_TRIPS` NULL `TRUCK_KEY` / `TRAILER_KEY` / `DRIVER_KEY` | 19,348 / 19,099 / 18,967 (~2%) | Even across 2024–2026. `TRUCK_ID` is also NULL on all of them → missing in the source (dirty rows), not a failed dbt lookup |
| WARN | `FCT_FUEL_PURCHASES` NULL `TRUCK_KEY` / `DRIVER_KEY` | 36,987 / 37,312 (~2%) | Same: `TRUCK_ID` NULL in the source |
| WARN | `FCT_DELIVERY_EVENTS` NULL `CUSTOMER_ID`, `ROUTE_ID`, `LOAD_DATE_KEY` | 4,390 each | Same rows as the `LOAD_ID` FAIL above |
| PASS | All unique keys, all `DIM_*` → `DIM_LOCATION` keys, all `*_DATE_KEY` (except the 4,390), one current row per `CUSTOMER_ID` / `DRIVER_ID` | – | Model structure is sound |

**Tests done:** script ran end to end against Snowflake ✅ · exit code 1 because of the 4 FAILs ✅ · causes checked with extra queries (dates of orphans, NULL `TRUCK_ID` behind NULL `TRUCK_KEY`) ✅.

**Root causes found later (2026-10-29), reported to the owner in [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md):**
- Old orphans are not random: `RAW_DATA.LOADS` has `LOAD00000001`–`LOAD00001950` (`LOAD_DATE` 2023-12-29 to 12-31), but `FCT_SHIPMENTS` starts at 2024-01-01 and `RAW_DATA.TRIPS` starts at `TRIP00001951`. Their child rows (3,900 events, 807 fuel purchases) stay in the facts.
- All 846 events with a load but no trip are recent (unfinished trips).
- `RAW_DATA.MAINTENANCE_RECORDS` has only `FACILITY_LOCATION` (a city), with no facility ID, so `FACILITY_KEY` cannot be found.
- `RAW_DATA.TRIPS` already has an empty `TRUCK_ID` in 34,035 of 1,679,187 rows (2.0%).

### Backend restructure (clean architecture) ✅ (2026-10-29)
**What I did:** Split the flat `backend/app/` (4 files) into layers so the backend can grow to all 8 dashboards and the stream: `api/` → `services/` → `domain/` (contracts) ← `infrastructure/` (Snowflake), plus `core/` and `schemas/`. KPI SQL moved to `.sql` files. Response schemas added. Same URLs, same JSON. Details: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md).

**Decisions:** clean architecture (option C, chosen over layered / feature modules) · repositories have `Protocol` contracts · only KPI SQL in `.sql` files (health/tables SQL stays in the repository) · JSON keys kept exactly as before (upper-case Snowflake columns) · no tests folder for now · URLs not versioned (no `/api/v1`).

**Logic:** route gets its service from `api/dependencies.py` (`Depends`) → service runs the logic on a contract from `domain/repositories.py` → `infrastructure/repositories/snowflake_*.py` runs the SQL (`sql_loader.load_sql()` for `.sql` files) through `snowflake_client.fetch_all()` → route validates the result with its `schemas/` model.

**Files:** moved (`git mv`): `config.py` → `core/config.py` (`.env` path `parents[1]` → `parents[2]`), `snowflake_client.py` → `infrastructure/snowflake_client.py` (import path), `kpi_validation.py` → `services/kpi_validation_service.py` (SQL out, class `KpiValidationService`) · new: `core/errors.py`, `domain/repositories.py`, `infrastructure/sql_loader.py`, `infrastructure/queries/kpis/{distance_variance,margin_proxy}.sql`, `infrastructure/repositories/snowflake_{system,kpi}_repository.py`, `services/system_service.py`, `schemas/{system,kpi_validation}.py`, `api/{dependencies,router}.py`, `api/routes/{health,tables,kpis}.py`, `__init__.py` per folder, `backend/ARCHITECTURE.md` · changed: `main.py` (only builds the app), `backend/README.md` (flow), `tools/validate_marts.py` line 9 (`from app.infrastructure import snowflake_client`). No `.env` change, no new package.

**Tests done:** responses of `/health`, `/api/tables`, `/api/kpis/validation` saved before the change and compared after: byte-for-byte identical (149 / 2,827 / 597 bytes) ✅ · SQL in the `.sql` files equals the old Python strings ✅ · `/docs` lists the same 3 paths plus 4 schemas ✅ · CORS preflight 200 ✅ · no warnings at startup ✅ · service with a fake repository returns both KPI models ✅ · Snowflake error → 503 ✅ · `tools/validate_marts.py` import works ✅. The server on port 8000 still runs the old code until restarted.

**Still open:**
- Answers from the owner to the 4 questions in [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md#4-questions-for-the-model-owner).
- ~~`GET /api/kpis/{dashboard}` per [dashboard/src/data/contract.js](dashboard/src/data/contract.js)~~ done, see the next ticket.
- ~~SSE stream (`VITE_STREAM_URL`) belongs to the streaming team.~~ done, see "Live stream from Kafka over SSE".

### Warehouse KPIs on the dashboard + 30-min refresh ✅ (2026-10-29)
**What I did:** Added `GET /api/kpis/{dashboard_id}?kpi_ids=…`. It calculates every KPI card and chart that the warehouse can answer, for the last 30 days vs the previous 30 days, directly on `DBT_MARTS`. 23 KPIs + 17 charts. KPIs and charts that need the live stream or pipeline metadata return `null`. The dashboard calls it and re-fetches every 30 min. Units switched to metric everywhere (api and mock; the mock was removed on 2026-10-29).

**Decisions:**
- Scope: KPI cards and charts together. No cache (the KPI logic moves to dbt later; now the goal is correct logic).
- One SQL file per KPI (`queries/kpis/`), one per chart (`queries/series/`). The frontend sends the page's KPI ids (`dashboards.js` stays the only list).
- Not in the warehouse → `null` → card shows `-`, chart shows "No data" (no mock fill in api mode). Live map keeps the simulator in api mode (stream is instant, warehouse is refreshed every 30 min).
- Period: 30 days ending 3 days ago (trips land only when completed) vs the 30 days before. Row date = when it happened (`ACTUAL_DATE`, `TRIP_DATE` = dispatch, `PURCHASE_DATE`, `MAINTENANCE_DATE`, `INCIDENT_DATE`, snapshot date).
- Units: metric as in the marts (km, L, L/100km, USD/km, per 1M km).
- KPI rules: 1/2 = `on_time_flag`; 3 = average of late deliveries only (`delay_minutes > 0`: 170.4 min, vs 12.7 min if early deliveries count as 0); 5 = `delay_minutes > 120`; 8 = average per trip, planned = scheduled delivery − scheduled pickup; 20/27/28 fuel cost = consumption-based (`fuel_liters_used` × period price per liter); 21 = `AVERAGE_L_PER_100KM` as the data gives it; 22 = vs national price of the same day from `RAW_DATA.DIESEL_PRICES` (not in the marts); 30 = per fleet truck-day; 43 = per 30 days; 46 = `is_in_maintenance`.
- KPIs 4 and 9 skipped (removed from the dashboards). KPIs 23, 29 stay null (telemetry). Platform page all null (no Airflow/dbt/S3 tables; `SNOWFLAKE.ACCOUNT_USAGE` not authorized for `AIRFLOW_ROLE`).
- `GET /api/kpis/validation` removed (join checks stay in `tools/validate_marts.py`).

**Logic:** dashboard `useKpis` → `apiSource.getKpis(id)` → `GET /api/kpis/{id}?kpi_ids=…` → route checks the id → `KpiService.dashboard()` builds the period dates → for each KPI id in `KPI_QUERIES` runs `kpis/<name>.sql` (2 rows: `value`, `previous`), for each chart in `DASHBOARD_SERIES` runs `series/<name>.sql` (or null) → `SnowflakeKpiRepository.fetch_rows()` lower-cases keys and turns `Decimal` into `float` → `DashboardResponse`. Full flow: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md), formulas: [backend/README.md](backend/README.md).

**Result (period 2026-09-27 to 2026-10-26 vs 2026-08-28 to 2026-09-26):**

| KPI | Current | Previous | Meaning |
|---|---|---|---|
| 1 On-Time Delivery (%) | 93.27 | 93.39 | 93 of 100 deliveries start within the 15-min grace period |
| 2 On-Time Pickup (%) | 65.97 | 65.92 | Pickups are late far more often than deliveries |
| 3 Avg Delivery Delay (min) | 170.4 | 174.4 | A late delivery is ~2.8 h late on average |
| 5 Severe Delay (%) | 3.39 | 3.40 | 3.4% of deliveries are more than 2 h late |
| 6 Destination Queue (min) | 31.9 | 31.2 | ~32 min wait before unloading |
| 7 Dock Time (min) | 89.1 | 88.8 | ~1.5 h loading / unloading per stop |
| 8 Trip Duration Variance (%) | −15.6 | −15.7 | Trips take 16% less than planned (schedule slack) |
| 19 Total Fuel Spend (USD) | 29,023,609 | 29,688,871 | Fuel bought in 30 days |
| 20 Fuel Cost per km (USD/km) | 0.345 | 0.353 | |
| 21 Fuel Efficiency (L/100km) | 36.27 | 36.24 | = 6.5 mpg, inside the expected 5.8–7.8 mpg |
| 22 Fuel Price Variance (%) | 2.70 | 2.57 | Paid 2.7% above the national price (state offsets included) |
| 24 Idle Time Share (%) | 9.14 | 9.03 | |
| 26 Revenue per km (USD/km) | 1.451 | 1.452 | |
| 27 Fuel Cost % of Revenue (%) | 23.79 | 24.30 | = KPI 20 / KPI 26 (checked) |
| 28 Margin Proxy per Trip (USD) | 3,094.53 | 3,117.40 | Revenue − fuel − maintenance, not profit |
| 30 Km per Truck per Day (km) | 538.1 | 561.3 | ⚠️ see "Still open" (incomplete last days) |
| 36 Incident Rate (per 1M km) | 0.756 | 0.689 | = ~1.2 per 1M mi, near the expected 1.4 |
| 38 Claim Cost (USD) | 423,420 | 564,630 | |
| 41 Total Maintenance Cost (USD) | 6,175,651 | 6,157,836 | |
| 42 Maintenance Downtime (h) | 77,203 | 78,285 | |
| 43 Orders per Truck (orders) | 0.629 | 0.629 | = ~7.7 per year, expected ~8 |
| 44 Maintenance Cost per km (USD/km) | 0.077 | 0.073 | |
| 46 Truck Availability (%) | 97.90 | 97.91 | |

**Files:**
- Backend new: `services/kpi_service.py`, `schemas/dashboard.py`, `queries/kpis/` 22 new files + `margin_proxy.sql` rewritten (per period, consumption fuel), `queries/series/` 17 files.
- Backend changed: `domain/repositories.py` (`fetch_kpi` → `fetch_rows(query, params)`), `infrastructure/repositories/snowflake_kpi_repository.py`, `api/routes/kpis.py`, `api/dependencies.py`, `README.md`, `ARCHITECTURE.md`.
- Backend deleted: `services/kpi_validation_service.py`, `schemas/kpi_validation.py`, `queries/kpis/distance_variance.sql`.
- Dashboard new: `components/NoData.jsx`.
- Dashboard changed: `data/api/apiSource.js` (sends `kpi_ids`, simulator for the stream), `hooks/useKpis.js` (30-min refresh), `kpis/definitions.js` (metric units, formulas), `components/charts.jsx` + `DataTable.jsx` (No data, tooltip rounding), `pages/{Executive,Delivery,Fuel,Safety,Maintenance,ColdChain}Page.jsx`, `data/mock/{kpiValues,dashboards}.js` (metric), `data/contract.js`, `README.md`.
- No `.env` change, no new package, no database change (read-only).

**Tests done:** all 23 KPI SQL and 17 chart SQL run on Snowflake (4.5 s and 9.5 s for all) ✅ · endpoint on a test instance (port 8001) for all 8 dashboards, 1–4 s each ✅ · unknown id → 404 ✅ · JSON numbers are floats, dates `YYYY-MM-DD` ✅ · KPI 27 = KPI 20 / KPI 26 ✅ · found and fixed a Snowflake precision bug (KPI 36 gave exactly 1.0: a division keeps 6 decimals, so multiply by 1,000,000 first) ✅ · `npm run build` passes ✅. Not done: clicking through the pages in a browser in api mode.

**Still open:**
- ~~The 3-day lag is not enough~~ fixed, see "Follow-up" below.
- Repeated SQL to move into dbt later: the period fuel price (KPIs 20, 27, 28 + 2 charts) and the diesel reference (KPI 22 + 2 charts).
- `worst_customers` leaves out customers with fewer than 10 deliveries (assumption).
- ~~Server on port 8000 old + expired login; connection not reopened on expiry~~ fixed, see "Follow-up" below.
- `DIESEL_PRICES` into the marts (dbt owner), then KPI 22 reads the mart.

**Follow-up (2026-10-29): trips by finish day, window ends yesterday, reconnect on expired login, backend restarted**
- **Problem:** trips counted on their start day (`TRIP_DATE`). A trip lands only when completed (59 h on average, up to 5 days), so the last start days were incomplete (24 Oct 934 trips, 25 Oct 692, 26 Oct 371) and trip totals were ~3–4% low.
- **Fix:** trips count on the day they finished (`ARRIVAL_TS::DATE`). By finish day every day is complete (22–28 Oct: 857–951 trips). 15 SQL files changed (`trip_date` → `arrival_ts::DATE`): KPIs 8, 20, 21, 24, 26, 27, 28, 30, 36, 44 and charts `unit_economics_trend`, `fuel_efficiency_by_route`, `fuel_efficiency_by_truck`, `driver_scorecard`, `cost_by_model_year`. Window now ends yesterday (`DATA_LAG_DAYS = 1`).
- **Result:** KPI 30 = 559.79 vs 559.77 km (the fake drop 538 vs 561 is gone). Period now 2026-09-29 to 2026-10-28.
- **Connection fix:** `snowflake_client.fetch_all()` catches an expired login (`ReauthenticationRequest`, or codes 390111 / 390112 / 390114), opens a new connection and retries once. Tests: simulated expiry → 2 attempts, new session ✅ · real end of our session (`SYSTEM$ABORT_SESSION`, gave 390111) → next query works on a new session ✅ · a normal SQL error (2003, unknown table) is still raised, no retry ✅.
- **Backend restarted** on port 8000 with `--reload`, as a separate Windows process (survives the terminal). Logs: `backend/uvicorn.log`, `backend/uvicorn.err.log` (added to `.gitignore`), PID in `backend/uvicorn.pid`. `/health` 200, all dashboards 200 in 0.2–1.6 s ✅.
- **Files:** `backend/app/infrastructure/snowflake_client.py`, `backend/app/services/kpi_service.py`, the 15 SQL files above, `backend/README.md`, `backend/ARCHITECTURE.md`, `.gitignore`.
- ⚠️ **Still open:** yesterday is not fully loaded yet at midday (28 Oct at 12:30 EST: delivery events 690 of ~920, fuel purchases 1,281 of ~1,800, maintenance 50 of ~110). Sums of these tables (KPIs 19, 38, 41, 42, 43, and the incident count in 36) are ~1–2% low until the day completes. Pickup events have the same issue as trips had (saved only when the trip finishes): KPI 2 and 7 are rates/averages, so the effect is small.

### Live stream from Kafka over SSE ✅ (2026-10-29)
**What I did:** The backend reads the two Kafka silver topics, keeps the latest row of every truck in memory, makes alerts from the row flags, calculates the live KPIs, and pushes all of it to the dashboard over Server-Sent Events (`GET /api/stream`). The live map in api mode now uses this instead of the simulator, and shows a new "Live KPIs" panel. Details: [backend/README.md](backend/README.md#live-stream-get-apistream), [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md#live-stream-files-get-apistream).

**What the data is (measured 2026-10-29, read-only):**
| Topic | Partitions | Batch every | Rows per batch | Age of newest reading on arrival | Duplicates |
|---|---|---|---|---|---|
| `fleet.silver.telemetry.v1` | 3 | 5.0 min | ~2,150 (one per truck) | ~10 min | ~0.4% (same row again, without `updated_at`) |
| `fleet.silver.reefer.v1` | 3 | 5.0 min | ~1,180 (one per truck) | ~10 min | same |
- Proof that it is batches, not a continuous stream: Kafka's own timestamps put 9,000 telemetry messages of 20 min into only 6 seconds; a 400 s live watch saw messages in 2 seconds only.
- Kafka keeps ~11 h (oldest message 2026-10-28 23:24 UTC). The last hour = ~26k telemetry + ~14k reefer messages.
- `is_idling` = `motion_status = IDLING` (idle now, not "over 30 min"). `stream_latency_sec` is always null. No `ingest_ts` in silver rows.
- First connection was blocked (timeout from my PC, Colab and this machine); the owner opened port 9092, then it worked.

**Decisions:**
- aiokafka (async, same loop as FastAPI) · no consumer group, nothing committed · state in a Python dict in memory (no Redis) · FastAPI's built-in SSE (`fastapi.sse`, no new SSE package).
- `STREAM_HISTORY_MINUTES=60`, one key for both: read back 60 min from Kafka on start, drop rows whose `event_ts` is older than 60 min.
- Duplicates / late rows: keep a row only if its `event_ts` is newer than the truck's stored row.
- Send every 1 s, only when something changed. Every time rule uses `event_ts`, so a faster upstream batch (1 min, 2 s) needs no code change.
- Live KPIs: truck counts (+ per `motion_status`), counts of `is_speeding` / `is_engine_overheating` / `is_low_fuel` / `is_reefer_unit_failure`, cold-chain compliance (%) overall and per `commodity_type`, data age (min).
- Alerts option b: flag alerts (`SPEEDING`, `ENGINE_OVERHEATING`, `LOW_FUEL`, `COLD_CHAIN_BREACH`, `REEFER_UNIT_FAILURE`) + `EXCESSIVE_IDLING` after 30 min of `is_idling`. `IDLING` alone is only a map color. No `ROUTE_DEVIATION` live (no flag).
- New viewer gets a full snapshot: every truck's latest rows, active alerts, last 40 alert changes, KPIs.
- Endpoint `/api/stream` (the dashboard `.env` had `/stream`, changed).

**Logic:** `KafkaStreamSource.messages(since)` (one consumer on both topics, each partition moved to `since` with `offsets_for_times`) → `StreamService._read()` calls `FleetState.apply(kind, row, now)` for each message (retries every 10 s if Kafka fails) → every second `StreamService._send_changes()` calls `FleetState.take_changes(now)` (drops rows older than 60 min, ends their alerts, returns the new rows + alert changes + KPIs, or nothing) and puts the events in every viewer's queue → `GET /api/stream` yields the snapshot, then the queue, as SSE events `telemetry`, `reefer`, `alert`, `kpis` → dashboard `apiSource.subscribe()` (one shared `EventSource`) → `useFleetState()` → map, alert feed, Live KPIs panel.

**Files:**
- Backend new: `app/domain/stream_source.py`, `app/infrastructure/kafka_stream_source.py`, `app/services/fleet_state.py`, `app/services/stream_service.py`, `app/schemas/stream.py`, `app/api/routes/stream.py`.
- Backend changed: `app/core/config.py` (4 settings), `app/api/dependencies.py` (one shared `stream_service`), `app/api/router.py`, `app/main.py` (start/stop the stream), `requirements.txt` (`aiokafka>=0.12`, `fastapi>=0.141`), `.env.example`, `README.md`, `ARCHITECTURE.md`.
- Dashboard changed: `src/data/api/apiSource.js` (EventSource again instead of the simulator), `src/hooks/useFleetState.js` (`kpis` event, status from `motion_status`, new alert types), `src/pages/LiveMapPage.jsx` (Live KPIs panel, new columns), `src/kpis/definitions.js` (`SPEEDING`, `ENGINE_OVERHEATING`, `LOW_FUEL`), `src/data/mock/fleetSimulator.js` (silver columns + `kpis` event), `src/data/contract.js`, `.env.example`, `README.md`.
- **`.env` changes:** `backend/.env` + 4 lines (`KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TELEMETRY_TOPIC`, `KAFKA_REEFER_TOPIC`, `STREAM_HISTORY_MINUTES`); `dashboard/.env.local` `VITE_STREAM_URL` → `http://localhost:8000/api/stream`.
- Package installed in `.venv`: `aiokafka 0.15.0`. No database change.

**Tests done:**
- Logic with fake rows (7 checks, all pass ✅): duplicate / late / older-than-60-min rows dropped · flag alert starts and ends with the same `anomaly_id` · `EXCESSIVE_IDLING` not at 29 min, yes at 30 min with `start_ts` = first idle row · KPIs incl. compliance without null `cargo_temp_f` and per commodity · snapshot = one event per alert (latest version) · rows expire after 60 min and their alerts end · `StreamService`: snapshot first, then changes, viewer queue removed on disconnect.
- Real Kafka on a test instance (port 8001) ✅: snapshot 4.1 MB (telemetry 3.29 MB = 5,000 rows × 658 B, reefer 0.76 MB), first byte 0.66 s; KPIs: 5,000 trucks (3,543 parked / 1,215 driving / 242 idling), 46 speeding, 55 low fuel, 0 overheating, 1,205 reefers, compliance 100.0%, data age 13.0 min; 234 active alerts (133 `EXCESSIVE_IDLING`, 55 `LOW_FUEL`, 46 `SPEEDING`).
- Kafka down (first version had a bug: topic "not found") → the reader logged it and retried every 10 s, the API kept answering ✅. Bug fixed (topics passed to the consumer, aiokafka assigns all 6 partitions).
- `npm run build` passes ✅. Not done: clicking through the live map in a browser.

**Still open:**
- **Server on port 8000 restarted** (2026-10-29) as a separate process with `--reload --timeout-graceful-shutdown 3` (logs `backend/uvicorn.log`, `backend/uvicorn.err.log`, PID in `backend/uvicorn.pid`). Before the flag, an open dashboard tab (SSE) blocked every reload forever. With it, a reload finishes in 18–55 s ✅.
- ⚠️ **After a `--reload`, an open live-map tab freezes:** on Windows the old connection is not closed (tested: the SSE client stayed connected and got no more data), so `EventSource` does not reconnect. Refresh the page after a backend reload. Only in dev with `--reload`; a real stop/start closes the connection. Possible fix (not decided): the backend sends `kpis` every ~30 s even without changes, and the frontend reconnects when nothing arrived for ~90 s.
- Snapshot is ~4 MB per new viewer (all columns, 5,000 trucks). Fine on localhost; for remote viewers: send only the columns the dashboard uses, or gzip.
- An open tab keeps a truck on the map after the backend dropped it (no "removed" event); its alerts do end. A reload of the page is clean.
- After an `EventSource` reconnect the old alerts stay in the browser; ended alerts that are no longer in the last 40 can stay "active" until the page reloads.
- 133 `EXCESSIVE_IDLING` of 242 idling trucks looks high: compare with `gen_anomaly_labels` (KPIs 51–53) later.
- Ask the owner: `retention.ms` of the two topics (must be ≥ 60 min), and whether the 5-min batch can be faster.
- `Notion_Data_Catalog.md` still says "Kafka is not used" and lists the old topic names.

### Mock data removed ✅ (2026-10-29)
**What I did:** Deleted the dashboard's mock data source (fake KPI numbers, fake chart series, in-browser 5,000-truck simulator) and the `VITE_DATA_SOURCE` switch. The dashboard now always reads the backend: warehouse KPIs over REST, live stream over SSE.

**Decisions:**
- Remove the switch, not keep it with one option: one source means no dead code path.
- `data/index.js` stays as the only data import of the components, so no hook or page changed.
- `ROUTE_DEVIATION` kept (color, label, status priority) for a future stream flag; only its comments changed (the backend never sends it today).
- The dashboard is not deployed, so nothing public breaks.

**Logic:** pages → hooks (`useKpis`, `useStream`) → `data/index.js` (`export { apiSource as dataSource }`) → `apiSource` → backend `GET /api/kpis/{id}` and `GET /api/stream`. KPIs/charts not in the warehouse show `-` / "No data" (same as before in api mode).

**Files:**
- Deleted: `dashboard/src/data/mock/` (6 files: `mockSource.js`, `dashboards.js`, `fleetSimulator.js`, `kpiValues.js`, `reference.js`, `rng.js`, 746 lines).
- Changed: `dashboard/src/data/index.js`, `src/config.js` (no `dataSource`), `src/components/Layout.jsx` (commented-out data badge + unused `config` import removed), `src/data/contract.js`, `src/kpis/definitions.js`, `src/pages/ColdChainPage.jsx` (comments), `dashboard/.env.example`, docs (`dashboard/README.md` section 9 removed and sections renumbered, `RUN.md`, `README.md`, `backend/ARCHITECTURE.md`, this log, `worklog_dashboard.md`).
- **`.env` changes:** `dashboard/.env.example`: `VITE_DATA_SOURCE` removed. `dashboard/.env.local` not touched: its `VITE_DATA_SOURCE=api` line is now unused (safe to delete).

**Tests done:** `npm run build` passes ✅ · no `mock` / `VITE_DATA_SOURCE` reference left in `dashboard/src` ✅. Not done: clicking through the pages in a browser.

**Still open:** without the backend running, every page shows the error box and the live map stays "Waiting for the stream…" (no offline mode any more).

### Stream KPIs + moving trucks from Kafka ⏳ (step 1 of 3 ✅, 2026-10-29)
Plan and decisions: [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md). Step 1 = backend KPIs + charts ✅ · step 2 = pages show them ⬜ · step 3 = trucks replay by `event_ts` ⬜.

**What I did (step 1):** Every KPI and chart that needs telemetry / reefer data is now calculated **from Kafka** (not the warehouse, which has no stream table, so they were `null`). The backend keeps every Kafka row (only the columns the KPIs read), calculates KPIs 10, 11, 12, 13, 14, 15, 16, 23, 29, 33, 34 and the charts `trip_temperature`, `excursions_by_trailer`, `excursion_rate_by_ambient`, `high_risk_trips`, `time_in_state` once per Kafka batch, and sends them in a new SSE event `stream_kpis` on `GET /api/stream`. New filter `?events=stream_kpis` so pages without the map get ~1 KB instead of ~4 MB.

**Decisions:** window = last 60 min of `event_ts` (ending at the newest row) vs the 60 min before · no `trip_id` / `load_id` in Kafka → one trailer / truck in the window = one trip (assumption, KPIs 11, 15, 16) · KPI 29 = `DRIVING` time / all time · a row counts until the next row of its truck/trailer, max 15 min · only the needed columns kept (full rows = 223 MB for 120 min) · same shapes as `GET /api/kpis`, so the pages can use them as they are · KPIs 35, 51–53 stay `null` (not in Kafka).

**Found while testing on real data (and fixed):** KPI 34 was 49 now vs 153 before (edge effects): (1) an idle run is now counted when it **reaches** 30 min (same moment as the alert), not when it starts; (2) a run that begins with the first kept row is skipped (its real start is unknown); (3) 30 extra minutes are kept before the previous window so its runs have a known start. After: 71 vs 64.

**Logic:** `FleetState.apply()` → `StreamHistory.add()` (dedup `vehicle_id` + `event_ts`, `COLUMNS` only, drops rows older than `kept()` = 2 × 60 + 30 min before the newest) → `take_changes()` / `snapshot()` call `stream_kpis()` (calculates again only when rows were added, and is sent to every viewer even if a new viewer's snapshot calculated it first) → `stream_kpis.calculate()`: `_tracks` (rows per truck/trailer, sorted, minutes per row) → `_runs` (flag runs) → `_excursions` (≥ 2 `is_temp_breach` rows) → `_window_kpis()` for the window and the previous one + `_series()` → `StreamKpis` → SSE `stream_kpis`. `StreamService._read()` reads back `kept()` from Kafka on start.

**Files:**
- Backend new: `app/services/stream_history.py`, `app/services/stream_kpis.py`.
- Backend changed: `app/services/fleet_state.py` (history, `stream_kpis()`, `EXCESSIVE_IDLING_AFTER` moved to `stream_kpis.py`), `app/services/stream_service.py` (read back `kept()`), `app/schemas/stream.py` (`StreamKpis`, `EventName`), `app/api/routes/stream.py` (`?events=`), `app/services/kpi_service.py` (docstring), `.env.example` (comment), `README.md`, `ARCHITECTURE.md`.
- Dashboard changed: `src/data/contract.js` (docs only: `stream_kpis`, `StreamKpis`, `?events=`).
- **`.env` changes:** none (`backend/.env.example` comment only). No database change.

**Tests done:**
- Fake rows, values worked out by hand: **36 checks, all pass ✅** (minutes per row + 15-min cap · excursions: 1 row = none, null temp inside a run · KPIs 10–16, 23, 29, 33, 34 + previous window · window edges · all 5 charts · empty data → null · run at the first kept row skipped · history dedup / too old / expiry / columns · `stream_kpis` in snapshot and changes, still sent after a snapshot, not sent for a duplicate). Script: scratchpad `test_stream_kpis.py` (not in the repo).
- Real Kafka (2026-10-29 ~13:10 UTC, window to 13:00 UTC): 100,267 messages read, 99,827 rows kept = **42 MB**, `calculate()` **0.65–0.85 s**, event **0.9 KB**. Values (now vs previous): KPI 10 99.9 / 100.0 % · 11 100.0 / 99.9 % · 12 0 / 1 · 13 – / 85.0 min · 14 – / 6.2 °F · 15 0.1 / 0.1 % · 16 3.0 / 2.5 min per trailer · 23 1,209.7 / 1,232.8 L · 29 34.6 / 34.1 % · 33 0.08 / 0.08 per 100 km · 34 71 / 64.
- Running backend (port 8000, after reload) ✅: `?events=stream_kpis` → only `stream_kpis` (989 bytes); no filter → all 5 events (3.9 MB snapshot); `?events=nope` → 422.

**Still open:**
- Steps 2 (pages) and 3 (replay) of the plan.
- `calculate()` runs on the event loop (~0.8 s once per 5-min batch): sends to viewers wait that long. Fine now; move to a thread if the batch gets faster.
- `time_in_state` has only `DRIVING` / `IDLING` / `PARKED` (no loading/unloading or maintenance in Kafka).

### KPIs without a data source removed ✅ (2026-10-29)
**What I did:** With the mock gone, every KPI card, chart and chart column that neither the warehouse (`DBT_MARTS`) nor Kafka can fill was removed from the dashboard, with its definition (also gone from the KPI Guide).

| Removed | Page | Why no source |
|---|---|---|
| KPI 35 Route Deviation Rate | Safety | needs each trip's origin–destination line; Kafka has no `trip_id` / route |
| KPIs 51 Detection Precision, 52 Detection Recall, 53 Time-to-Detect | Live | need `gen_anomaly_labels` (only in S3, not connected) |
| KPIs 55 End-to-End Latency, 56 Data Completeness, 59 S3 vs Snowflake Gap, 61 Pipeline Success Rate, 62 dbt Test Pass Rate, 63 API Success Rate, 64 Warehouse Cost | Platform | no `ingest_ts` / stream in Snowflake, no "expected rows", no S3 access, Airflow not built, dbt results not stored, the APIs are the generator's, no `ACCOUNT_USAGE` access |
| Charts `pipeline_runs`, `credits_trend`, `row_counts` | Platform | same reasons (Airflow, `ACCOUNT_USAGE`, S3) |
| Column `kpi_11` (weekly) in `service_trend` | Executive | Kafka keeps ~13 h, not weeks |
| Columns `kpi_33`, `kpi_34` (per driver) in `driver_scorecard` | Safety | Kafka has no `driver_id` |

**Decisions:** KPIs 54, 57, 58, 60 have a source (Kafka / backend) → kept, to be built now · the live page has no KPI cards any more, so it does not call `GET /api/kpis/live` (stream only) and `live` was removed from the backend (`/api/kpis/live` → 404) · removed KPIs are also deleted from `definitions.js` (and so from the KPI Guide) · `QUESTIONS['Outcome 6']` and the KPI group "G. Anomaly Detection Quality" were only used by 51–53 → removed.

**Files:**
- Dashboard: `src/dashboards.js` (live `[]`, safety without 35, platform `[54, 57, 58, 60]`), `src/kpis/definitions.js` (11 KPIs, Outcome 6, group G removed → 39 KPIs), `src/hooks/useKpis.js` (no call when a page has no `kpiIds`), `src/pages/PlatformPage.jsx` (cards only), `src/pages/ExecutivePage.jsx` (`kpi_11` line), `src/pages/SafetyPage.jsx` (`kpi_33`/`kpi_34` columns), `src/data/contract.js`, `README.md`.
- Backend: `app/services/kpi_service.py` (`live` removed, `platform` no series, `SERIES_NOT_IN_WAREHOUSE` without the pipeline series), `queries/series/driver_scorecard.sql` (`NULL AS kpi_33/kpi_34` removed), `queries/series/service_trend.sql` (comment), `README.md`, [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md).
- **`.env` changes:** none. No database change.

**Tests done:** `npm run build` passes ✅ · every page's `kpiIds` exists in `KPIS` ✅ · no reference left to the removed KPIs / series / columns in `dashboard/src` ✅ · backend: `/api/kpis/live` → 404 ✅, `/api/kpis/platform` → 200 with `series: {}` ✅, `driver_scorecard` columns = `driver_id, first_name, last_name, distance_km, kpi_24, incidents` ✅, `service_trend` = `week_start, kpi_1` ✅.

**Still open:** build KPIs 54, 57, 58, 60 (design to agree first). `Notion_Data_Catalog.md` still lists all 64 catalog KPIs (it is the original catalog, not changed).

### Platform KPIs 54, 57, 58, 60 (stream) + 65 (warehouse) ✅ backend (2026-10-29)
**What I did:** Built the 4 platform KPIs that have a source, and a new KPI 65.
| KPI | Source | Rule | Unit |
|---|---|---|---|
| 54 Ingestion Throughput | Kafka messages | messages received / 3,600 s, last 60 min of Kafka time vs the 60 before | events/s |
| 57 Duplicate Rate | Kafka messages | rows with the same `vehicle_id` + `event_ts` as a kept row / received | % |
| 58 Rejection Rate | Kafka messages | not JSON, or no valid `vehicle_id` / `event_ts` / received | % |
| 60 Data Freshness | Kafka messages | now − Kafka time of the newest message (no previous) | min |
| 65 Warehouse Data Freshness (new, not in the catalog) | Snowflake `RAW_DATA` | now − newest `_AIRBYTE_EXTRACTED_AT` over the 13 tables (no previous) | min |

**Decisions:** the Kafka reader passes each message's partition + offset + Kafka time (`StreamMessage`), so (1) a message read again after a Kafka failure is skipped, never counted as a duplicate, and (2) a broken message (no `event_ts`) can still be placed in a window by its Kafka time · freshness on 2 cards: 60 = stream, 65 = warehouse (id and names chosen by the owner) · `stream_kpis` is also sent every minute, so KPI 60 grows between batches · one `pct()` helper shared by `stream_kpis.py` and `platform_stats.py`.

**Logic:** `KafkaStreamSource` → `StreamMessage(kind, row | None, partition, offset, timestamp)` → `StreamService._read()` → `FleetState.apply(message)`: `PlatformStats.is_new()` (skip a re-read) → `StreamHistory.add()` returns `added` / `duplicate` / `old` → `PlatformStats.count(duplicate, rejected)` per minute of Kafka time → `stream_kpis(now)` = row KPIs (cached, recalculated per batch) + `PlatformStats.kpis(now)` → SSE `stream_kpis`. A rejected message raises after being counted; `StreamService` logs it. KPI 65: `KPI_QUERIES[65]` → `queries/kpis/warehouse_data_freshness.sql` → `GET /api/kpis/platform`.

**Files:**
- Backend new: `app/services/platform_stats.py`, `app/infrastructure/queries/kpis/warehouse_data_freshness.sql`.
- Backend changed: `app/domain/stream_source.py` (`StreamMessage`), `app/infrastructure/kafka_stream_source.py` (yields `StreamMessage`, no own warning), `app/services/fleet_state.py` (`apply(message)`, `PlatformStats`, send rule, `STREAM_KPIS_EVERY`), `app/services/stream_history.py` (`add()` result), `app/services/stream_kpis.py` (`pct()` shared), `app/services/stream_service.py` (messages, one warning per rejected message), `app/services/kpi_service.py` (`65`), `README.md`, `ARCHITECTURE.md`.
- Dashboard: `src/kpis/definitions.js` (meanings of 54, 57, 58, 60; new 65; group to 65 → 40 KPIs), `src/dashboards.js` (platform `[54, 57, 58, 60, 65]`), `src/data/contract.js`, `README.md`.
- Package installed in `.venv`: `tzdata 2026.6` (already in `requirements.txt`, added by the Cairo-time change; without it `ZoneInfo("Africa/Cairo")` fails on Windows and the backend does not start).
- **`.env` changes:** none. No database change.

**Tests done:**
- Fake messages, values by hand: **51 checks, all pass ✅** (the 36 before, plus: re-read skipped · lower offset with newer Kafka time = new · duplicate → only `stream_kpis` · not JSON / no `vehicle_id` raise and are counted · refresh after 1 min, not after 30 s · KPI 54 = 10 / 60 s, 57 = 1 of 10, 58 = 2 of 10 and 1 of 4, 60 = 2 min).
- Running backend (2026-10-29 13:45 UTC): 54 = **11.17** events/s (prev 11.12) · 57 = **0.4 %** (prev 0.43) · 58 = **0.0 %** · 60 = **0.1 min** · 65 (REST) = **52.6 min** · `npm run build` ✅.

**Still open:** the Platform page (and the other pages) do not read `stream_kpis` yet, so 54, 57, 58, 60 show `-` on screen until step 2 of [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md). KPI 65 shows now.

## 📌 Open items (later)
- **Team access:** teammates need Snowflake, Airbyte and dbt access. Plan: a personal Snowflake user each (`snowflake/02_team_users.sql`), Airbyte workspace invites, and their own `profiles.yml`. Still to decide: access level (project roles + `SYSADMIN`, or `ACCOUNTADMIN`), usernames and emails.

---

## 🐞 Error log
| Date | Step | Error | Fix |
|---|---|---|---|
| 2026-10-26 | 3c | `New public key rejected by current policy. Reason: 'Invalid Public key'` on `CREATE USER AIRBYTE_USER` | The placeholder `<PASTE_AIRBYTE_PUBLIC_KEY_HERE>` was not replaced. Create the keys (3b), paste the real public key body, and re-run from section 7 |
| 2026-10-26 | 4a | CloudShell: `Unable to create the environment ... insufficient permissions` | My IAM user has no CloudShell or IAM permissions. Do the checks in the console instead. The AWS account owner creates `airbyte-s3-reader` |
| 2026-10-26 | 5a | Airbyte S3 source: `Error listing files`. Local check: `SignatureDoesNotMatch` on every call | The key from the generator `.env` (`…CTEG`) has a secret that does not match its key ID (my copy was checked and is identical to what I received). It was also shared in chat. Owner deletes it and creates `airbyte-s3-reader` with a fresh key. Also removed the default `**` glob from the stream |
| 2026-10-26 | 5b | Airbyte Snowflake destination: `HikariPool-1 - Connection is not available, request timed out after 30000ms` | The Snowflake login worked from my PC, so the form was wrong: the private key must be pasted in full (with the BEGIN/END lines, no quotes from `.env`) and the host without `https://`. Copied it with `cat ~/.snowflake_keys/airbyte_rsa_key.p8 \| clip` |
