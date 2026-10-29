// Builds the mock DashboardResponse for each dashboard (see contract.js).
// The `series` keys returned here are the proposed shape of the future MARTS endpoints.
// Columns named kpi_<id> hold that KPI's value at a finer grain (per lane, per week, ...).
import { DASHBOARDS_BY_ID } from '../../dashboards'
import { MOCK_KPI_VALUES } from './kpiValues'
import { createRng, hashSeed } from './rng'
import {
  BATCH_TABLES, COMMODITIES, CUSTOMER_NAMES, CUSTOMER_TYPES, FACILITIES, FIRST_NAMES, INCIDENT_TYPES,
  LAST_NAMES, MAINTENANCE_TYPES, MAKES, ROUTES, padId,
} from './reference'

const PERIOD = 'Last 30 days vs previous 30 days'
const WEEKS = 12
const DAYS = 14
const DIESEL_REFERENCE_PRICE = 3.85 // USD/gal, national diesel_prices value

const round = (value, digits = 1) => Math.round(value * 10 ** digits) / 10 ** digits
const kpiValue = (kpiId) => MOCK_KPI_VALUES[kpiId][0]
const isoDate = (date) => date.toISOString().slice(0, 10)

// Last `count` dates going back `stepDays` each time, oldest first.
function pastDates(count, stepDays) {
  const today = new Date()
  today.setUTCHours(0, 0, 0, 0)
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(today)
    date.setUTCDate(date.getUTCDate() - stepDays * (count - 1 - index))
    return isoDate(date)
  })
}

// Random walk that ends at `end`, so trend charts finish at the value shown on the KPI card.
function walkTo(rng, end, count, step) {
  const values = [end]
  while (values.length < count) values.unshift(values[0] + rng.between(-step, step))
  return values
}

const ascending = (key) => (a, b) => a[key] - b[key]
const descending = (key) => (a, b) => b[key] - a[key]

const SERIES_BUILDERS = {
  live: () => ({}),

  executive(rng) {
    const weeks = pastDates(WEEKS, 7)
    const otd = walkTo(rng, kpiValue(1), WEEKS, 1.2)
    const compliance = walkTo(rng, kpiValue(11), WEEKS, 1)
    const fuelCostPerMile = walkTo(rng, kpiValue(20), WEEKS, 0.015)
    const revenuePerMile = walkTo(rng, kpiValue(26), WEEKS, 0.04)
    return {
      service_trend: weeks.map((week_start, i) => ({ week_start, kpi_1: round(otd[i]), kpi_11: round(compliance[i]) })),
      unit_economics_trend: weeks.map((week_start, i) => ({
        week_start, kpi_26: round(revenuePerMile[i], 2), kpi_20: round(fuelCostPerMile[i], 2),
      })),
    }
  },

  delivery(rng) {
    return {
      lane_otd: ROUTES.map((route) => ({
        ...route,
        deliveries: rng.int(40, 400),
        kpi_1: round(rng.between(76, 99.5)),
      })),
      worst_customers: CUSTOMER_NAMES.map((customer_name, index) => ({
        customer_id: padId('CUST', index + 1),
        customer_name,
        customer_type: rng.pick(CUSTOMER_TYPES),
        deliveries: rng.int(300, 2500),
        kpi_1: round(rng.between(82, 97)),
      })).sort(ascending('kpi_1')).slice(0, 8),
      delay_by_hour: Array.from({ length: 24 }, (_, hour) => ({
        hour: `${String(hour).padStart(2, '0')}:00`,
        kpi_3: round(30 + 18 * Math.sin(((hour - 10) * Math.PI) / 12) + rng.between(-4, 4)),
      })),
      facility_queue: FACILITIES.map(({ facility_id, facility_name, city }) => ({
        facility_id, facility_name, city, kpi_6: round(rng.between(12, 55)),
      })).sort(descending('kpi_6')).slice(0, 10),
    }
  },

  cold_chain(rng) {
    const range = COMMODITIES.find((row) => row.commodity === 'Chilled')
    const start = Date.now() - 10 * 3_600_000
    let cargo_temp_f = range.setpoint_f
    const readings = Array.from({ length: 120 }, (_, i) => {
      const minute = i * 5 // one reading every 5 min
      const failing = minute >= 200 && minute < 330 // reefer unit failure window
      cargo_temp_f += failing ? rng.between(0.3, 0.6) : (range.setpoint_f - cargo_temp_f) * 0.25 + rng.between(-0.3, 0.3)
      return {
        event_ts: new Date(start + minute * 60_000).toISOString().slice(11, 16),
        cargo_temp_f: rng.chance(0.03) ? null : round(cargo_temp_f), // null = dropped reading, shown as a gap
        setpoint_f: range.setpoint_f,
      }
    })
    return {
      trip_temperature: { trip_id: 'TRIP00184522', vehicle_id: 'TRK01377', trailer_id: 'TRL01377', ...range, readings },
      excursions_by_trailer: Array.from({ length: 10 }, () => ({
        trailer_id: padId('TRL', rng.int(1, 5000)), excursions: rng.int(2, 9),
      })).sort(descending('excursions')),
      excursion_rate_by_ambient: [
        ['< 50 °F', 2.1], ['50-70 °F', 3.4], ['70-90 °F', 6.8], ['> 90 °F', 12.5],
      ].map(([ambient_band, rate]) => ({ ambient_band, kpi_17: round(rate + rng.between(-0.4, 0.4)) })),
      high_risk_trips: Array.from({ length: 8 }, () => {
        const commodity = rng.pick(COMMODITIES)
        const truckNumber = rng.int(1, 5000)
        return {
          trip_id: padId('TRIP', rng.int(180000, 189999), 8),
          vehicle_id: padId('TRK', truckNumber),
          trailer_id: padId('TRL', truckNumber),
          commodity: commodity.commodity,
          peak_temp_f: round(commodity.max_temp_f + rng.between(1, 9)),
          duration_min: rng.int(20, 210),
        }
      }).sort(descending('duration_min')),
    }
  },

  fuel(rng) {
    const weeks = pastDates(WEEKS, 7)
    const weeklySpend = walkTo(rng, kpiValue(19) / 4.3, WEEKS, 150_000)
    const stateOffsets = [
      ['CA', 0.95], ['WA', 0.55], ['IL', 0.25], ['NJ', 0.2], ['AZ', 0.15], ['UT', 0.12], ['CO', 0.1], ['MN', 0.05],
      ['IN', 0.02], ['OH', 0], ['FL', -0.02], ['NC', -0.05], ['GA', -0.08], ['TN', -0.1], ['MO', -0.15], ['TX', -0.2],
    ]
    return {
      fuel_spend_trend: weeks.map((week_start, i) => ({ week_start, total_cost: Math.round(weeklySpend[i]) })),
      mpg_by_route: ROUTES.map(({ route_id, origin_city, destination_city }) => {
        const mpg = rng.between(5.8, 7.8)
        return { route_id, origin_city, destination_city, kpi_21: round(mpg, 2), kpi_20: round(DIESEL_REFERENCE_PRICE / mpg, 2) }
      }).sort(ascending('kpi_21')),
      mpg_by_truck: Array.from({ length: 10 }, () => ({
        truck_id: padId('TRK', rng.int(1, 5000)), make: rng.pick(MAKES), kpi_21: round(rng.between(5.8, 6.2), 2),
      })).sort(ascending('kpi_21')),
      price_by_state: stateOffsets.map(([location_state, offset]) => ({
        location_state,
        price_per_gallon: round(DIESEL_REFERENCE_PRICE + offset + rng.between(-0.05, 0.05), 2),
        reference_price_per_gallon: DIESEL_REFERENCE_PRICE,
      })),
      purchase_outliers: Array.from({ length: 8 }, () => {
        const gallons = round(rng.between(40, 260))
        const price_per_gallon = round(DIESEL_REFERENCE_PRICE * rng.between(1.12, 1.35), 2)
        return {
          fuel_purchase_id: padId('FUEL', rng.int(1, 999999), 9),
          truck_id: padId('TRK', rng.int(1, 5000)),
          location_state: rng.pick(stateOffsets)[0],
          gallons,
          price_per_gallon,
          total_cost: round(gallons * price_per_gallon, 2),
          kpi_22: round((price_per_gallon / DIESEL_REFERENCE_PRICE - 1) * 100),
        }
      }).sort(descending('kpi_22')),
    }
  },

  safety(rng) {
    return {
      time_in_state: [
        ['Driving', 28.0], ['Loading / unloading', 6.5], ['Idling', 3.4], ['Parked / waiting', 60.9], ['Maintenance', 1.2],
      ].map(([state, share_pct]) => ({ state, share_pct })),
      driver_scorecard: FIRST_NAMES.map((first_name, index) => ({
        driver_id: padId('DRV', rng.int(1, 6000)),
        first_name,
        last_name: LAST_NAMES[index],
        miles: rng.int(6000, 14000),
        kpi_33: round(rng.between(0.05, 1.4), 2),
        kpi_34: rng.int(0, 9),
        kpi_24: round(rng.between(4, 18)),
        incidents: rng.int(0, 2),
      })).sort(descending('kpi_33')),
      incidents_by_type: INCIDENT_TYPES.map((incident_type) => ({
        incident_type, incidents: rng.int(4, 40), claim_amount: rng.int(50_000, 1_400_000),
      })).sort(descending('claim_amount')),
    }
  },

  maintenance(rng) {
    const months = Array.from({ length: 12 }, (_, i) => {
      const date = new Date()
      date.setUTCDate(1)
      date.setUTCMonth(date.getUTCMonth() - (11 - i))
      return isoDate(date).slice(0, 7)
    })
    return {
      cost_trend: months.map((month) => ({
        month, labor_cost: rng.int(2_200_000, 2_700_000), parts_cost: rng.int(3_000_000, 3_600_000),
      })),
      maintenance_mix: MAINTENANCE_TYPES.map((maintenance_type) => ({
        maintenance_type, orders: rng.int(150, 900), total_cost: rng.int(300_000, 1_600_000),
      })).sort(descending('total_cost')),
      repeat_trucks: Array.from({ length: 10 }, () => ({
        truck_id: padId('TRK', rng.int(1, 5000)),
        make: rng.pick(MAKES),
        orders: rng.int(3, 7),
        total_cost: rng.int(8_000, 42_000),
        downtime_hours: round(rng.between(20, 160)),
      })).sort(descending('orders')),
      // Flat on purpose: the simulator assigns maintenance randomly, so there is no real age effect (catalog A.11).
      cost_by_model_year: Array.from({ length: 10 }, (_, i) => ({
        model_year: 2016 + i, kpi_44: round(kpiValue(44) + rng.between(-0.015, 0.015), 3),
      })),
    }
  },

  platform(rng) {
    const days = pastDates(DAYS, 1)
    return {
      pipeline_runs: days.map((run_date) => {
        const failed = rng.int(0, 2)
        return { run_date, succeeded: 96 - failed, failed } // one run every 15 min = 96 per day
      }),
      row_counts: BATCH_TABLES.map((table_name) => {
        const s3_rows = rng.int(5_000, 2_000_000)
        return { table_name, s3_rows, raw_rows: s3_rows, staging_rows: Math.round(s3_rows * (1 - 0.003)) }
      }),
      credits_trend: days.map((usage_date) => ({
        usage_date,
        AIRBYTE_WH: round(rng.between(0.2, 0.5), 2),
        DBT_WH: round(rng.between(0.4, 0.9), 2),
        BI_WH: round(rng.between(0.05, 0.25), 2),
      })),
    }
  },
}

export function buildDashboard(dashboardId) {
  const dashboard = DASHBOARDS_BY_ID[dashboardId]
  if (!dashboard) throw new Error(`Unknown dashboard "${dashboardId}"`)
  const rng = createRng(hashSeed(dashboardId))
  return {
    dashboard: dashboardId,
    period: PERIOD,
    as_of: new Date().toISOString(),
    kpis: dashboard.kpiIds.map((kpi_id) => {
      const [value, previous] = MOCK_KPI_VALUES[kpi_id]
      return { kpi_id, value, previous }
    }),
    series: SERIES_BUILDERS[dashboardId](rng),
  }
}
