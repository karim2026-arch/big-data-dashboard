-- KPI 21 Fuel Efficiency (L/100km): average of FCT_TRIPS.average_l_per_100km, as the data gives it. Lower is better.
-- Period date: TRIP_DATE.
SELECT
    IFF(trip_date >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(average_l_per_100km)                                   AS kpi_value
FROM fct_trips
WHERE trip_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
