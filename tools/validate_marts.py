"""Checks the DBT_MARTS model: foreign keys (orphans), unique keys (duplicates), one current row per history ID.
Status: FAIL = orphan / duplicate / not exactly one current row, WARN = NULL keys, PASS = clean.
Uses the backend's Snowflake login (backend/.env, schema DBT_MARTS). Exit code 1 if any check fails.
Run from the project root: .venv/Scripts/python tools/validate_marts.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.infrastructure import snowflake_client  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

# (table, column, referenced table, referenced column)
FOREIGN_KEYS = [
    ("FCT_TRIPS", "CUSTOMER_KEY", "DIM_CUSTOMER", "CUSTOMER_KEY"),
    ("FCT_TRIPS", "ROUTE_KEY", "DIM_ROUTE", "ROUTE_KEY"),
    ("FCT_TRIPS", "TRUCK_KEY", "DIM_TRUCK", "TRUCK_KEY"),
    ("FCT_TRIPS", "TRAILER_KEY", "DIM_TRAILER", "TRAILER_KEY"),
    ("FCT_TRIPS", "DRIVER_KEY", "DIM_DRIVER", "DRIVER_KEY"),
    ("FCT_TRIPS", "DISPATCH_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("FCT_TRIPS", "LOAD_ID", "FCT_SHIPMENTS", "LOAD_ID"),
    ("FCT_SHIPMENTS", "CUSTOMER_ID", "DIM_CUSTOMER", "CUSTOMER_ID"),
    ("FCT_SHIPMENTS", "ROUTE_ID", "DIM_ROUTE", "ROUTE_ID"),
    ("FCT_SHIPMENTS", "LOAD_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("FCT_DELIVERY_EVENTS", "LOAD_ID", "FCT_SHIPMENTS", "LOAD_ID"),
    ("FCT_DELIVERY_EVENTS", "TRIP_ID", "FCT_TRIPS", "TRIP_ID"),
    ("FCT_DELIVERY_EVENTS", "CUSTOMER_ID", "DIM_CUSTOMER", "CUSTOMER_ID"),
    ("FCT_DELIVERY_EVENTS", "ROUTE_ID", "DIM_ROUTE", "ROUTE_ID"),
    ("FCT_DELIVERY_EVENTS", "FACILITY_ID", "DIM_FACILITY", "FACILITY_ID"),
    ("FCT_DELIVERY_EVENTS", "LOAD_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("FCT_FUEL_PURCHASES", "TRIP_ID", "FCT_TRIPS", "TRIP_ID"),
    ("FCT_FUEL_PURCHASES", "TRUCK_KEY", "DIM_TRUCK", "TRUCK_KEY"),
    ("FCT_FUEL_PURCHASES", "DRIVER_KEY", "DIM_DRIVER", "DRIVER_KEY"),
    ("FCT_FUEL_PURCHASES", "PURCHASE_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("FCT_MAINTENANCE", "TRUCK_KEY", "DIM_TRUCK", "TRUCK_KEY"),
    ("FCT_MAINTENANCE", "FACILITY_KEY", "DIM_FACILITY", "FACILITY_KEY"),
    ("FCT_MAINTENANCE", "LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
    ("FCT_MAINTENANCE", "MAINTENANCE_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("FCT_SAFETY_INCIDENTS", "TRIP_ID", "FCT_TRIPS", "TRIP_ID"),
    ("FCT_SAFETY_INCIDENTS", "TRUCK_KEY", "DIM_TRUCK", "TRUCK_KEY"),
    ("FCT_SAFETY_INCIDENTS", "DRIVER_KEY", "DIM_DRIVER", "DRIVER_KEY"),
    ("FCT_SAFETY_INCIDENTS", "INCIDENT_DATE_KEY", "DIM_DATE", "DATE_KEY"),
    ("DIM_ROUTE", "ORIGIN_LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
    ("DIM_ROUTE", "DESTINATION_LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
    ("DIM_FACILITY", "LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
    ("DIM_DRIVER", "HOME_TERMINAL_LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
    ("DIM_TRUCK", "HOME_TERMINAL_LOCATION_KEY", "DIM_LOCATION", "LOCATION_KEY"),
]

# (table, column) that must be unique. *_ID of dims without history is unique too, because facts join on it.
UNIQUE_KEYS = [
    ("FCT_TRIPS", "TRIP_ID"),
    ("FCT_SHIPMENTS", "LOAD_ID"),
    ("FCT_DELIVERY_EVENTS", "EVENT_ID"),
    ("FCT_FUEL_PURCHASES", "FUEL_PURCHASE_ID"),
    ("FCT_MAINTENANCE", "MAINTENANCE_ID"),
    ("FCT_SAFETY_INCIDENTS", "INCIDENT_ID"),
    ("DIM_CUSTOMER", "CUSTOMER_KEY"),
    ("DIM_DATE", "DATE_KEY"),
    ("DIM_DRIVER", "DRIVER_KEY"),
    ("DIM_FACILITY", "FACILITY_KEY"),
    ("DIM_FACILITY", "FACILITY_ID"),
    ("DIM_LOCATION", "LOCATION_KEY"),
    ("DIM_ROUTE", "ROUTE_KEY"),
    ("DIM_ROUTE", "ROUTE_ID"),
    ("DIM_TRAILER", "TRAILER_KEY"),
    ("DIM_TRAILER", "TRAILER_ID"),
    ("DIM_TRUCK", "TRUCK_KEY"),
    ("DIM_TRUCK", "TRUCK_ID"),
]

# (table, ID column) of dims with history (VALID_FROM / VALID_TO / IS_CURRENT)
HISTORY_DIMS = [
    ("DIM_CUSTOMER", "CUSTOMER_ID"),
    ("DIM_DRIVER", "DRIVER_ID"),
]

# Every query returns ROWS_TOTAL, NULL_KEYS, PROBLEM_KEYS
FOREIGN_KEY_SQL = """
SELECT COUNT(*) AS rows_total,
       COUNT_IF(f.{column} IS NULL) AS null_keys,
       COUNT_IF(f.{column} IS NOT NULL AND r.ref_key IS NULL) AS problem_keys
FROM {table} f
LEFT JOIN (SELECT DISTINCT {ref_column} AS ref_key FROM {ref_table}) r ON f.{column} = r.ref_key
"""
UNIQUE_KEY_SQL = """
SELECT COUNT(*) AS rows_total,
       COUNT_IF({column} IS NULL) AS null_keys,
       COUNT({column}) - COUNT(DISTINCT {column}) AS problem_keys
FROM {table}
"""
# PROBLEM_KEYS = IDs that do not have exactly one IS_CURRENT row
HISTORY_SQL = """
SELECT COUNT(*) AS rows_total,
       COUNT_IF(id IS NULL) AS null_keys,
       COUNT_IF(current_rows <> 1) AS problem_keys
FROM (SELECT {column} AS id, COUNT_IF(is_current) AS current_rows FROM {table} GROUP BY {column})
"""


def checks() -> list[tuple[str, str, str]]:
    """(check type, target label, SQL) for every check."""
    return (
        [("foreign key", f"{t}.{c} -> {rt}.{rc}", FOREIGN_KEY_SQL.format(table=t, column=c, ref_table=rt, ref_column=rc))
         for t, c, rt, rc in FOREIGN_KEYS]
        + [("unique", f"{t}.{c}", UNIQUE_KEY_SQL.format(table=t, column=c)) for t, c in UNIQUE_KEYS]
        + [("one current row", f"{t}.{c}", HISTORY_SQL.format(table=t, column=c)) for t, c in HISTORY_DIMS]
    )


def status(row: dict) -> str:
    if row["PROBLEM_KEYS"]:
        return "FAIL"
    return "WARN" if row["NULL_KEYS"] else "PASS"


def main() -> int:
    results = []
    for check, target, sql in checks():
        row = snowflake_client.fetch_all(sql)[0]
        results.append((status(row), check, target, row))
        print(f"{status(row):<5} {check:<16} {target:<66} rows={row['ROWS_TOTAL']:>9,} "
              f"nulls={row['NULL_KEYS']:>7,} problems={row['PROBLEM_KEYS']:>7,}")
    snowflake_client.close_connection()

    totals = {s: sum(1 for r in results if r[0] == s) for s in ("PASS", "WARN", "FAIL")}
    print(f"\n{len(results)} checks: {totals['PASS']} PASS, {totals['WARN']} WARN, {totals['FAIL']} FAIL")
    return 1 if totals["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
