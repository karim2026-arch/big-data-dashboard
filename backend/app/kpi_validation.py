"""KPIs calculated on the DBT_MARTS tables over all rows, to validate the model's joins.
Each KPI returns its value together with join checks (rows matched / unmatched), because a broken join
can still give a plausible-looking value. Units are as the marts store them (km, USD)."""
from . import snowflake_client

# KPI 9: (actual_distance_km - typical_distance_km) / typical_distance_km x 100, averaged over trips.
# Join check: FCT_TRIPS -> DIM_ROUTE on ROUTE_KEY.
DISTANCE_VARIANCE_SQL = """
SELECT
    COUNT(*)                     AS trips_total,
    COUNT(r.route_key)           AS trips_matched_route,
    COUNT(*) - COUNT(r.route_key) AS trips_unmatched_route,
    ROUND(AVG((t.actual_distance_km - r.typical_distance_km) / NULLIF(r.typical_distance_km, 0) * 100), 2)::FLOAT
                                 AS distance_variance_pct
FROM fct_trips t
LEFT JOIN dim_route r ON t.route_key = r.route_key
"""

# KPI 28: revenue - fuel - allocated maintenance, averaged per trip.
# revenue     = revenue_usd + fuel_surcharge_usd + accessorial_charges_usd (FCT_TRIPS)
# fuel        = SUM(FCT_FUEL_PURCHASES.total_cost) of the trip, joined on TRIP_ID
# maintenance = truck's SUM(FCT_MAINTENANCE.total_cost) x trip km / truck's total trip km (per-km allocation)
# Trips without TRUCK_KEY are excluded (inner join to truck_distance) and counted.
# *_all_* columns are the full table totals, to compare with what the KPI used.
MARGIN_PROXY_SQL = """
WITH trip_fuel AS (
    SELECT trip_id, SUM(total_cost) AS fuel_cost
    FROM fct_fuel_purchases
    GROUP BY trip_id
),
truck_maintenance AS (
    SELECT truck_key, SUM(total_cost) AS maintenance_cost
    FROM fct_maintenance
    GROUP BY truck_key
),
truck_distance AS (
    SELECT truck_key, SUM(actual_distance_km) AS truck_distance_km
    FROM fct_trips
    WHERE truck_key IS NOT NULL
    GROUP BY truck_key
),
trip_margin AS (
    SELECT
        t.revenue_usd + t.fuel_surcharge_usd + t.accessorial_charges_usd                AS revenue,
        COALESCE(f.fuel_cost, 0)                                                         AS fuel_cost,
        COALESCE(m.maintenance_cost, 0) * t.actual_distance_km / d.truck_distance_km    AS maintenance_cost,
        f.trip_id IS NULL                                                                AS no_fuel_purchase
    FROM fct_trips t
    JOIN truck_distance d         ON t.truck_key = d.truck_key
    LEFT JOIN trip_fuel f         ON t.trip_id   = f.trip_id
    LEFT JOIN truck_maintenance m ON t.truck_key = m.truck_key
)
SELECT
    (SELECT COUNT(*) FROM fct_trips)                                AS trips_total,
    COUNT(*)                                                        AS trips_used,
    (SELECT COUNT(*) FROM fct_trips WHERE truck_key IS NULL)        AS trips_without_truck_key,
    COUNT_IF(no_fuel_purchase)                                      AS trips_used_without_fuel_purchase,
    (SELECT COUNT(*) FROM fct_fuel_purchases
      WHERE trip_id NOT IN (SELECT trip_id FROM fct_trips))         AS fuel_purchases_unmatched_trip,
    ROUND(SUM(revenue), 2)::FLOAT                                   AS revenue_usd,
    ROUND(SUM(fuel_cost), 2)::FLOAT                                 AS fuel_cost_usd,
    ROUND(SUM(maintenance_cost), 2)::FLOAT                          AS maintenance_cost_usd,
    (SELECT ROUND(SUM(total_cost), 2)::FLOAT FROM fct_fuel_purchases) AS fuel_cost_all_purchases_usd,
    (SELECT ROUND(SUM(total_cost), 2)::FLOAT FROM fct_maintenance)  AS maintenance_cost_all_orders_usd,
    ROUND(AVG(revenue - fuel_cost - maintenance_cost), 2)::FLOAT    AS margin_proxy_per_trip_usd
FROM trip_margin
"""

KPIS = (
    (9, "Distance Variance", "%", DISTANCE_VARIANCE_SQL),
    (28, "Margin Proxy per Trip", "USD", MARGIN_PROXY_SQL),
)


def calculate_all() -> list[dict]:
    """One dict per KPI: kpi_id, name, unit, then the query's columns (value + join checks)."""
    return [
        {"kpi_id": kpi_id, "name": name, "unit": unit, **snowflake_client.fetch_all(sql)[0]}
        for kpi_id, name, unit, sql in KPIS
    ]
