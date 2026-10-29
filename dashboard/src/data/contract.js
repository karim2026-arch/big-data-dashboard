// The contract every data source (mock or api) must follow. Documentation only (JSDoc), no runtime code.
//
// 1) Warehouse KPIs: GET {VITE_API_BASE_URL}/kpis/{dashboardId}
//    dashboardId is one of the ids in src/dashboards.js. Values are already calculated in Snowflake MARTS;
//    the frontend only displays them.
//
// 2) Live stream: Server-Sent Events at {VITE_STREAM_URL}, three named events:
//    event: telemetry  data: TelemetryRow[]  (one batch per tick, not one message per truck)
//    event: reefer     data: ReeferRow[]
//    event: alert      data: AlertRow        (sent when an anomaly starts, and again with end_ts when it ends)
//    On connect the backend must first send every currently active alert, so a new viewer sees them.

/**
 * @typedef {Object} DashboardResponse
 * @property {string} dashboard            dashboard id
 * @property {string} period               human label, e.g. "Last 30 days vs previous 30 days"
 * @property {string} as_of                ISO timestamp (UTC) of the last warehouse refresh
 * @property {KpiValue[]} kpis
 * @property {Object<string, any>} series  chart data; keys per dashboard are listed in src/data/mock/dashboards.js
 */

/**
 * @typedef {Object} KpiValue
 * @property {number} kpi_id    catalog KPI number (see src/kpis/definitions.js)
 * @property {number|null} value     current period
 * @property {number|null} previous  previous period (for the trend arrow)
 */

/**
 * Same columns as Kafka topic fleet.telemetry.v1 (Notion_Data_Catalog.md 3.14).
 * @typedef {Object} TelemetryRow
 * @property {string} vehicle_id
 * @property {string} device_id
 * @property {string} event_id
 * @property {string} event_ts
 * @property {number} source_sequence
 * @property {number|null} lat
 * @property {number|null} lon
 * @property {number|null} speed_mph
 * @property {number} heading_deg
 * @property {number} rpm
 * @property {number} engine_temp_f
 * @property {number} fuel_gph
 * @property {number} fuel_level_gal
 * @property {number} odometer_mi
 * @property {boolean} engine_on
 * @property {string} ingest_ts
 */

/**
 * Same columns as Kafka topic fleet.reefer.v1 (Notion_Data_Catalog.md 3.15).
 * @typedef {Object} ReeferRow
 * @property {string} vehicle_id
 * @property {string} trailer_id
 * @property {string} sensor_id
 * @property {string} event_id
 * @property {string} event_ts
 * @property {number|null} cargo_temp_f
 * @property {number} setpoint_f
 * @property {boolean} compressor_on
 * @property {boolean} door_open
 * @property {number} ambient_temp_f
 * @property {number} reefer_fuel_gph
 * @property {string} unit_mode
 * @property {string} ingest_ts
 */

/**
 * An anomaly detected by the streaming job. Same names as gen_anomaly_labels (3.16).
 * @typedef {Object} AlertRow
 * @property {string} anomaly_id
 * @property {'EXCESSIVE_IDLING'|'ROUTE_DEVIATION'|'REEFER_UNIT_FAILURE'|'COLD_CHAIN_BREACH'} anomaly_type
 * @property {string} vehicle_id
 * @property {string} trip_id
 * @property {string} start_ts
 * @property {string|null} end_ts   null while the anomaly is still active
 */

export {}
