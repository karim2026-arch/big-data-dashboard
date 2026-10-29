-- KPI 26 Revenue per km (USD/km): SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km).
-- Period date: TRIP_DATE.
SELECT
    IFF(trip_date >= %(current_start)s, 'value', 'previous')                                     AS period,
    SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km)    AS kpi_value
FROM fct_trips
WHERE trip_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
