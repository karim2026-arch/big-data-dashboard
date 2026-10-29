// KPI catalog: ids, names, units and meanings copied from Notion_Data_Catalog.md (section 3-4).
// The backend sends only { kpi_id, value, previous }; everything a viewer reads comes from here.
// better: 'up' = higher is good, 'down' = lower is good, null = neutral.

export const KPIS = {
  // A. Delivery
  1: { name: 'On-Time Delivery Rate', unit: '%', better: 'up', meaning: 'Share of deliveries that started within the 15-min grace period.' },
  2: { name: 'On-Time Pickup Rate', unit: '%', better: 'up', meaning: 'Share of pickups that started within the 15-min grace period.' },
  3: { name: 'Average Delivery Delay', unit: 'min', better: 'down', meaning: 'Average positive delay of late deliveries (early ones excluded).' },
  4: { name: 'Late Delivery Rate', unit: '%', better: 'down', meaning: 'Share of deliveries later than the grace period.' },
  5: { name: 'Severe Delay Rate', unit: '%', better: 'down', meaning: 'Share of deliveries later than the severe threshold (assumption: 120 min).' },
  6: { name: 'Destination Queue Time', unit: 'min', better: 'down', meaning: 'Wait at destination before unloading starts.' },
  7: { name: 'Dock Time', unit: 'min', better: 'down', meaning: 'Average loading/unloading time (detention_minutes).' },
  8: { name: 'Trip Duration Variance', unit: '%', better: 'down', meaning: 'Actual vs planned trip hours. Compare lanes, not absolute value.' },
  9: { name: 'Distance Variance', unit: '%', better: 'down', meaning: 'Actual vs typical route miles.' },

  // B. Cold chain
  10: { name: 'Cold Chain Compliance (readings)', unit: '%', better: 'up', meaning: 'Share of valid reefer readings inside the allowed range.' },
  11: { name: 'Shipment Cold Chain Compliance', unit: '%', better: 'up', meaning: 'Share of refrigerated loads with no confirmed excursion.' },
  12: { name: 'Temperature Excursions', unit: 'count', better: 'down', meaning: 'Distinct events where cargo temperature left the allowed range.' },
  13: { name: 'Avg Excursion Duration', unit: 'min', better: 'down', meaning: 'Average minutes an excursion lasted.' },
  14: { name: 'Peak Excursion Severity', unit: '°F', better: 'down', meaning: 'Average peak degrees outside the allowed range.' },
  15: { name: 'Refrigeration Failure Rate', unit: '%', better: 'down', meaning: 'Share of reefer trips where the compressor stopped too long.' },
  16: { name: 'Door-Open Exposure', unit: 'min/trip', better: 'down', meaning: 'Minutes with door open per refrigerated trip.' },
  17: { name: 'Excursion Rate', unit: '%', better: 'down', meaning: 'Share of reefer trips with an excursion, by ambient temperature band.' },

  // C. Fuel & cost
  19: { name: 'Total Fuel Spend', unit: 'USD', better: null, meaning: 'Sum of fuel card purchases (bought, not burned).' },
  20: { name: 'Fuel Cost per Mile', unit: 'USD/mi', better: 'down', meaning: 'Fuel cost of completed trips divided by their miles.' },
  21: { name: 'Fuel Efficiency', unit: 'mpg', better: 'up', meaning: 'Miles per gallon. Expected range 5.8-7.8.' },
  22: { name: 'Fuel Price Variance', unit: '%', better: 'down', meaning: 'Price paid vs reference diesel price (same state).' },
  23: { name: 'Idle Fuel', unit: 'gal', better: 'down', meaning: 'Gallons burned with engine on and truck not moving.' },
  24: { name: 'Idle Time Share', unit: '%', better: 'down', meaning: 'Idle hours as a share of trip hours.' },
  26: { name: 'Revenue per Mile', unit: 'USD/mi', better: 'up', meaning: 'Load revenue + surcharge + accessorials per mile.' },
  27: { name: 'Fuel Cost % of Revenue', unit: '%', better: 'down', meaning: 'Trip fuel cost as a share of load revenue.' },
  28: { name: 'Margin Proxy per Trip', unit: 'USD', better: 'up', meaning: 'Revenue - fuel - maintenance. A proxy, not profit.' },

  // D. Utilization & safety
  29: { name: 'Truck Utilization', unit: '%', better: 'up', meaning: 'Productive time share. Low by design (60 h between loads): compare trucks.' },
  30: { name: 'Miles per Truck per Day', unit: 'mi', better: 'up', meaning: 'Trip miles / (trucks x days).' },
  33: { name: 'Speeding Events', unit: 'per 100 mi', better: 'down', meaning: 'Speed above 70 mph (assumption, no road limits in data).' },
  34: { name: 'Excessive Idling Events', unit: 'count', better: 'down', meaning: 'Engine on, speed ~0 for over 30 min (assumption).' },
  35: { name: 'Route Deviation Rate', unit: '%', better: 'down', meaning: 'Trips with at least one confirmed deviation (> 5 mi, assumption).' },
  36: { name: 'Incident Rate', unit: 'per 1M mi', better: 'down', meaning: 'Safety incidents per million miles. Expected ~1.4.' },
  38: { name: 'Claim Cost', unit: 'USD', better: 'down', meaning: 'Sum of safety_incidents.claim_amount.' },

  // E. Maintenance
  41: { name: 'Total Maintenance Cost', unit: 'USD', better: 'down', meaning: 'Labor + parts cost of all maintenance orders.' },
  42: { name: 'Maintenance Downtime', unit: 'h', better: 'down', meaning: 'Total hours trucks were out of service.' },
  43: { name: 'Orders per Truck', unit: 'orders', better: 'down', meaning: 'Maintenance orders per truck in the period (~8/year expected).' },
  44: { name: 'Maintenance Cost per Mile', unit: 'USD/mi', better: 'down', meaning: 'Maintenance cost / miles in the same period.' },
  46: { name: 'Truck Availability', unit: '%', better: 'up', meaning: 'Share of fleet time not in maintenance.' },

  // G. Anomaly detection quality (against gen_anomaly_labels)
  51: { name: 'Detection Precision', unit: '%', better: 'up', meaning: 'Correct detections / all flagged by our rules.' },
  52: { name: 'Detection Recall', unit: '%', better: 'up', meaning: 'Correct detections / all injected anomalies.' },
  53: { name: 'Time-to-Detect', unit: 'min', better: 'down', meaning: 'Our detection time - label start_ts.' },

  // Platform
  54: { name: 'Ingestion Throughput', unit: 'events/s', better: 'up', meaning: 'Stream events ingested per second.' },
  55: { name: 'End-to-End Latency', unit: 's', better: 'down', meaning: 'ingest_ts to available in Snowflake.' },
  56: { name: 'Data Completeness', unit: '%', better: 'up', meaning: 'Expected rows that arrived.' },
  57: { name: 'Duplicate Rate', unit: '%', better: 'down', meaning: 'Duplicate rows removed in staging (~0.3-0.4% injected).' },
  58: { name: 'Rejection Rate', unit: '%', better: 'down', meaning: 'Rows sent to quarantine (malformed).' },
  59: { name: 'S3 vs Snowflake Gap', unit: 'rows', better: 'down', meaning: 'Row-count difference between S3 and RAW.' },
  60: { name: 'Data Freshness', unit: 'min', better: 'down', meaning: 'Minutes since the last successful load.' },
  61: { name: 'Pipeline Success Rate', unit: '%', better: 'up', meaning: 'Successful orchestrated runs / all runs.' },
  62: { name: 'dbt Test Pass Rate', unit: '%', better: 'up', meaning: 'Passed dbt tests / all tests.' },
  63: { name: 'API Success Rate', unit: '%', better: 'up', meaning: 'Successful external API calls (EIA, Open-Meteo).' },
  64: { name: 'Warehouse Cost', unit: 'credits', better: 'down', meaning: 'Snowflake credits used this month.' },
}

// Anomaly families injected by the generator (gen_anomaly_labels.anomaly_type), with map colors.
export const ANOMALY_TYPES = {
  EXCESSIVE_IDLING: { label: 'Excessive idling', color: '#f59e0b' },
  ROUTE_DEVIATION: { label: 'Route deviation', color: '#a855f7' },
  REEFER_UNIT_FAILURE: { label: 'Reefer unit failure', color: '#06b6d4' },
  COLD_CHAIN_BREACH: { label: 'Cold chain breach', color: '#ef4444' },
}

export function formatValue(value, unit) {
  if (value == null) return '-'
  const digits = unit === 'USD/mi' ? 2 : Math.abs(value) >= 100 ? 0 : 1
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export const kpiLabel = (kpiId) => `${KPIS[kpiId].name} (${KPIS[kpiId].unit})`

// Series columns named kpi_<id> get their name + unit from KPIS; any other key is returned as is.
export function columnLabel(key) {
  const match = /^kpi_(\d+)$/.exec(key)
  return match ? kpiLabel(Number(match[1])) : key
}
