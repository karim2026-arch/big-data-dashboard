-- KPI 44 Maintenance Cost per km (USD/km): SUM(maintenance total_cost) / SUM(trips' actual_distance_km) in the same period.
-- Period date: MAINTENANCE_DATE for maintenance, TRIP_DATE for trips.
WITH maintenance AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
        SUM(total_cost)                                                   AS maintenance_cost
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_km AS (
    SELECT
        IFF(trip_date >= %(current_start)s, 'value', 'previous')          AS period,
        SUM(actual_distance_km)                                           AS distance_km
    FROM fct_trips
    WHERE trip_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    k.period,
    COALESCE(m.maintenance_cost, 0) / k.distance_km                       AS kpi_value
FROM trip_km k
LEFT JOIN maintenance m ON m.period = k.period
