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

## Web dashboard (frontend, mock data) ⏳
**What I did (2026-10-26):** Built [dashboard/](dashboard/): React + Vite + Tailwind, Recharts for KPI charts, Three.js (react-three-fiber) for the 3D map. All 7 dashboards from the catalog plus a Live Fleet Map. Data is mocked behind one switchable data source, so the real backend plugs in later without touching the pages. Details: [dashboard/README.md](dashboard/README.md).

**Logic:**
- Pages → hooks (`useKpis`, `useStream`) → `dataSource` → `mock` (now) or `api` (later, chosen by `VITE_DATA_SOURCE`).
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

**Logic:** three lists (`FOREIGN_KEYS` 33, `UNIQUE_KEYS` 18, `HISTORY_DIMS` 2) + three SQL templates, each returning `ROWS_TOTAL, NULL_KEYS, PROBLEM_KEYS`. It reuses the backend login (`backend/app/snowflake_client.py`, `backend/.env`), so there is no second copy of the connection code.

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

**Still open:**
- Answers from the owner to the 4 questions in [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md#4-questions-for-the-model-owner).
- `GET /api/kpis/{dashboard}` per [dashboard/src/data/contract.js](dashboard/src/data/contract.js), after the table names are known.
- SSE stream (`VITE_STREAM_URL`) belongs to the streaming team.

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
