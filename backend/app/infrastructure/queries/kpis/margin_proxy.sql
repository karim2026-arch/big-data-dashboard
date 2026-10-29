-- KPI 28: revenue - fuel - allocated maintenance, averaged per trip.
-- revenue     = revenue_usd + fuel_surcharge_usd + accessorial_charges_usd (FCT_TRIPS)
-- fuel        = SUM(FCT_FUEL_PURCHASES.total_cost) of the trip, joined on TRIP_ID
-- maintenance = truck's SUM(FCT_MAINTENANCE.total_cost) x trip km / truck's total trip km (per-km allocation)
-- Trips without TRUCK_KEY are excluded (inner join to truck_distance) and counted.
-- *_all_* columns are the full table totals, to compare with what the KPI used.
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
