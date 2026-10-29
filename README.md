# 🚛 Fleet Data Platform

An end-to-end data engineering pipeline built on a simulated US trucking fleet (5,000 Class-8 trucks by default).
A Python generator produces realistic, intentionally dirty data. The platform ingests, cleans and models it, then serves it to dashboards.

**Team:** Mohamed Bedier, Omar Fathy, Karim Mohamed, Mohamad Farah
**Program:** Samsung Innovation Campus (SIC 8): Big Data graduation project

| Document | What it contains |
|---|---|
| [Notion_Data_Catalog.md](Notion_Data_Catalog.md) | All 16 tables and their columns, S3 layout, data quality notes, the 64 KPIs, dashboards, generator Q&A |
| [Notion_Documentation.md](Notion_Documentation.md) | Team setup log: EC2, Kafka, IAM, S3, plus the step templates for each tool |
| [Notion: Data Catalog](https://app.notion.com/p/Data-Catalog-404961599a4880f6898eea33b93d731d) / [Notion: Documentation](https://app.notion.com/p/Documentation-3ff961599a4880dc9232c35ae49c5409) | Live sources of the two files above |

---

## 1. Architecture

There are two paths, both fed by the same generator:

```
                         fleet_generator.py  (AWS EC2, 24/7)
              ┌────────────────────┴────────────────────┐
         batch CSV.gz                            Kafka (localhost:9092)
     (every 15 min) + JSON refs           fleet.telemetry.v1 / fleet.reefer.v1
              │                         ┌───────────────┴───────────────┐
              ▼                         ▼                               ▼
        Amazon S3  ◄──── Kafka Connect (bronze/telemetry.raw)   Spark Structured Streaming
        (Bronze)                                                        │ live state + alerts
              │                                                         ▼
              ▼                                              Store (DB/cache) → Backend API
        Airbyte Cloud                                                   │
              ▼                                                         ▼
        Snowflake RAW ──dbt──► STAGING ──► INTERMEDIATE ──► MARTS ──► Power BI
                                        (orchestrated by Airflow)
```

| Path | Purpose | Latency | Owner of the numbers |
|---|---|---|---|
| **Batch** (S3 → Airbyte → Snowflake → dbt → Power BI) | Historical analysis, the official KPIs | ~1 hour | ✅ The official source for KPIs |
| **Speed** (Kafka → Spark → Backend → Live dashboard) | Live truck positions, reefer and idling alerts | seconds | Operational status only |

> **Rule:** the same KPI is never computed on both paths. The live view shows status and alerts. Snowflake holds the official numbers.

### Tools
| Tool | Role |
|---|---|
| Python | Data generator (`fleet_generator.py`) |
| AWS EC2 | Runs the generator and Kafka 24/7 (Ubuntu 24.04, `c7i-flex.large`) |
| Apache Kafka 4.3.1 | Streaming broker (KRaft, `localhost:9092`) |
| Kafka Connect | Sinks Kafka topics to S3 |
| Spark Structured Streaming | Real-time processing and alerting |
| AWS S3 | Data lake (Bronze / raw layer) |
| Airbyte Cloud | Moves files from S3 to Snowflake |
| Snowflake | Data warehouse |
| dbt | Cleaning and modeling (Silver / Gold) |
| Airflow | Orchestration (Airbyte sync → dbt run → dbt test) |
| Power BI | Analytical dashboards |

---

## 2. Data in S3 (Bronze)

Partitions use `dt=YYYY-MM-DD` and `hr=HH` (UTC). Files are named `{entity}-{run_id}-{sequence}.csv.gz`.

| S3 path | Tables | Format |
|---|---|---|
| `fleet/bronze/registry/{trucks,trailers}/` | trucks, trailers (daily snapshots) | CSV.gz |
| `fleet/bronze/hr/drivers/` | drivers (daily snapshot) | CSV.gz |
| `fleet/bronze/tms/{customers,facilities,routes,loads,trips,delivery_events}/` | TMS exports | CSV.gz |
| `fleet/bronze/fuel_card/fuel_purchases/` | fuel_purchases | CSV.gz |
| `fleet/bronze/cmms/maintenance_records/` | maintenance_records | CSV.gz |
| `fleet/bronze/safety/safety_incidents/` | safety_incidents | CSV.gz |
| `fleet/bronze/prices/diesel_prices/` (+ `prices/eia/`) | diesel_prices (+ raw EIA) | CSV.gz / JSON.gz |
| `fleet/bronze/weather/open_meteo/` | raw Open-Meteo responses | JSON.gz |
| `fleet/bronze/stream_direct/{telemetry,reefer}/` | streams from direct-to-S3 trucks and backfill | JSONL.gz |
| `bronze/telemetry.raw/dt=/hour=/` | telemetry sunk by Kafka Connect | JSON (to confirm) |
| `bronze/reference/` | reference data | to confirm |
| `fleet/ground_truth/gen_anomaly_labels/` | injected anomaly labels (evaluation only) | JSONL.gz |

> ⚠️ The Kafka Connect folders sit at the bucket root (`bronze/…`), not under `fleet/`, and they use `hour=` instead of `hr=`.

Full column definitions: [Notion_Data_Catalog.md](Notion_Data_Catalog.md), section 3.

---

## 3. Snowflake design

| Object | Name | Notes |
|---|---|---|
| Database | `FLEET_DB` | |
| Schemas | `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `SEEDS` | Airbyte also creates `AIRBYTE_INTERNAL` |
| Warehouses | `AIRBYTE_WH`, `DBT_WH`, `BI_WH` | XSMALL, auto-suspend after 60 s |
| Roles | `AIRBYTE_ROLE` (writes RAW), `TRANSFORMER` (dbt), `REPORTER` (Power BI, reads MARTS) | |
| Users | `AIRBYTE_USER`, `DBT_USER` | `TYPE=SERVICE`, key-pair authentication |
| Cost guard | `FLEET_MONTHLY_RM` | Notifies at 75%, suspends at 90% / 100% |

Setup script: [snowflake/01_setup.sql](snowflake/01_setup.sql)

### Layer rules
- **RAW:** exactly what is in S3. Airbyte only copies, it never cleans. All CSV columns are loaded as strings.
- **STAGING (dbt):** one model per source:
  - de-duplicate on the primary key or `event_id`
  - trim and standardize case
  - turn empty strings into null
  - cast types
  - flag null foreign keys
  - quarantine malformed JSON
- **INTERMEDIATE (dbt):** match telemetry and reefer readings to trips, using `vehicle_id` plus the time window `dispatch_ts` to `arrival_ts`. Build excursion and idling events.
- **MARTS (dbt):** facts and dimensions for Power BI. Raw telemetry is never sent to Power BI; it is aggregated first.

---

## 4. Airbyte Cloud (S3 → Snowflake)

| Setting | Value |
|---|---|
| Source | Amazon S3, bucket `fleet-telematics-lakehouse-team11`, region `eu-north-1` |
| Source credentials | Dedicated IAM user `airbyte-s3-reader`, read-only ([aws/airbyte_s3_readonly_policy.json](aws/airbyte_s3_readonly_policy.json)) |
| Streams | One per table, matched by file pattern (for example `fleet/bronze/tms/trips/**/*.csv.gz`) |
| CSV parsing | Schema inference **off** (everything as string), so dirty values can't fail a sync |
| Sync mode | Incremental \| Append (new files only). De-duplication happens in dbt |
| Destination | Snowflake `FLEET_DB.RAW`, user `AIRBYTE_USER` (key pair), warehouse `AIRBYTE_WH` |
| Schedule | Hourly at first, triggered by Airflow later |

The stream list is finalized from a bucket survey: [tools/s3_survey.py](tools/s3_survey.py).

---

## 5. Repository layout

```
.
├── README.md
├── Notion_Data_Catalog.md         # data catalog + KPIs + Q&A (Notion export)
├── Notion_Documentation.md        # team documentation (Notion export)
├── aws/
│   └── airbyte_s3_readonly_policy.json
├── snowflake/
│   └── 01_setup.sql               # warehouses, DB, schemas, roles, users, monitor
├── tools/
│   ├── s3_survey.py               # lists S3 folders and samples file headers
│   └── validate_marts.py          # checks DBT_MARTS keys: orphans, duplicates, one current row (PASS/WARN/FAIL)
├── dashboard/                     # React web dashboard (mock data now, API later)
├── backend/                       # FastAPI in front of Snowflake (see backend/README.md)
└── dbt/                           # (coming in Step 6)
```

---

## 6. Progress

| # | Step | Status |
|---|---|---|
| 1 | EC2 + Python + Kafka on the generator server | ✅ Done (see Notion Documentation 2.1–2.3) |
| 2 | S3 bucket + EC2 IAM role | ✅ Done |
| 3 | Snowflake setup (`01_setup.sql`) | ✅ Done (2026-10-26) |
| 4 | AWS access for Airbyte + bucket survey | ✅ Done (2026-10-27, uses IAM user `Karim`) |
| 5 | Airbyte source (S3), destination (Snowflake), connection, first sync | ⬜ |
| 6 | Verify RAW: row counts S3 vs Snowflake | ⬜ |
| 7 | dbt project + connection | ⬜ |
| 8 | dbt staging models + tests | ⬜ |
| 9 | dbt intermediate + marts + seeds | ⬜ |
| 10 | Airflow DAG (Airbyte → dbt run → dbt test) | ⬜ |
| 11 | Spark Structured Streaming + backend + live dashboard | ⏳ Backend API: Snowflake connection, `/health`, `/api/tables` done (2026-10-28). KPI endpoint and stream open |
| 12 | Power BI dashboards | ⬜ |

---

## 7. Open questions

1. ✅ **Resolved (2026-10-26): bucket and region.** The live bucket is `fleet-telematics-lakehouse-team11` in `eu-north-1`. Snowflake is in the same region (`AWS_EU_NORTH_1`). Still to do: update the Notion page, which says `supply-chain-graduation-project` / `us-east-1`.
2. ✅ **Resolved (2026-10-27): `safety` and `fuel_card`.** Both are written to S3 (`safety_incidents`: 1 file, `fuel_purchases`: 89 files).
3. **Reefer stream in Kafka:** is there a Kafka Connect folder for `fleet.reefer.v1`, or only `telemetry.raw`?
4. **Topic and folder naming:** the topics are `fleet.telemetry.v1` but the S3 folder is `telemetry.raw`. Agree on one scheme.
5. **Kafka listens on `127.0.0.1` only,** so Spark must run on the same EC2 instance, or the listeners must change (with security group rules).
6. ✅ **Resolved (2026-10-27): `bronze/reference/`** does not exist in the bucket.
7. **`DIRECT_S3_PCT`:** trucks that write directly to S3 never reach Kafka, so they are missing from the live dashboard. Set it to 0, or document this.

---

## 8. Security rules

- Never commit or paste passwords, AWS keys, Snowflake private keys or tokens. Use `<YOUR_KEY>` in docs and blur screenshots.
- Each tool gets its own least-privilege identity: EC2 instance role (write), `airbyte-s3-reader` (read), `AIRBYTE_USER` / `DBT_USER` (key pair).
- Private keys live outside the repository (for example `~/.snowflake_keys/`).
- Add `*.pem`, `*.p8`, `.env` and `profiles.yml` to `.gitignore`.
- If a key is exposed, deactivate and replace it in IAM immediately.
# big-data-dashboard
