-- KPI 9: (actual_distance_km - typical_distance_km) / typical_distance_km x 100, averaged over trips.
-- Join check: FCT_TRIPS -> DIM_ROUTE on ROUTE_KEY.
SELECT
    COUNT(*)                     AS trips_total,
    COUNT(r.route_key)           AS trips_matched_route,
    COUNT(*) - COUNT(r.route_key) AS trips_unmatched_route,
    ROUND(AVG((t.actual_distance_km - r.typical_distance_km) / NULLIF(r.typical_distance_km, 0) * 100), 2)::FLOAT
                                 AS distance_variance_pct
FROM fct_trips t
LEFT JOIN dim_route r ON t.route_key = r.route_key
