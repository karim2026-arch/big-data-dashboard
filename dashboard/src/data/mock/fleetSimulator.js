// In-browser stand-in for Kafka -> Spark -> backend SSE.
// Emits the same three events as the real stream (see contract.js) with the catalog column names.
// 1 tick = 1 simulated minute (the generator's telemetry interval), played every TICK_MS of wall time.
import { COMMODITIES, ROUTES, padId } from './reference'
import { createRng } from './rng'

const TRUCK_COUNT = 5000
const TICK_MS = 1000
const TICK_MINUTES = 1
const WARMUP_TICKS = 240 // play 4 simulated hours before the first emit, so anomalies already exist
const REEFER_SHARE = 0.5 // ~50% refrigerated loads (catalog A.10)
const REFUEL_LEVEL = 0.18 // refuel at ~18% of tank (catalog A.10)
const MPG = 6.8
const IDLE_GPH = 0.8
const MILES_PER_DEGREE = 69
const GPS_DROP_CHANCE = 0.001 // null lat/lon (dirty data, catalog A.6)
const SENSOR_DROP_CHANCE = 0.002 // null cargo_temp_f

// Chance per truck per tick that an anomaly starts, and its duration in minutes (catalog A.5).
// COLD_CHAIN_BREACH is not started directly: it follows when a reefer failure pushes cargo out of range.
const ANOMALIES = {
  EXCESSIVE_IDLING: { chance: 0.00004, minutes: [45, 150] },
  ROUTE_DEVIATION: { chance: 0.00003, minutes: [30, 90], offsetMiles: [6, 25] },
  REEFER_UNIT_FAILURE: { chance: 0.00006, minutes: [45, 240] },
}

const rng = createRng(42)
const listeners = { telemetry: new Set(), reefer: new Set(), alert: new Set() }
const activeAlerts = new Map() // anomaly_id -> AlertRow

const routesByOrigin = new Map()
for (const route of ROUTES) {
  if (!routesByOrigin.has(route.origin_city)) routesByOrigin.set(route.origin_city, [])
  routesByOrigin.get(route.origin_city).push(route)
}

let trucks = null
let simTime = 0
let tripCounter = 0
let anomalyCounter = 0
let timer = null

const iso = (ms) => new Date(ms).toISOString()
const round = (value, digits) => Math.round(value * 10 ** digits) / 10 ** digits

function emit(eventType, payload) {
  listeners[eventType].forEach((listener) => listener(payload))
}

function startTrip(truck, route) {
  tripCounter += 1
  truck.route = route
  truck.trip_id = padId('TRIP', tripCounter, 8)
  truck.progress = 0
}

function createTruck(index) {
  const tank = rng.pick([150, 200, 250])
  const truck = {
    vehicle_id: padId('TRK', index + 1),
    device_id: padId('TU-', index + 1),
    tank,
    cruise_mph: rng.between(55, 68),
    speed_mph: 0,
    engine_on: false,
    fuel_gph: 0,
    fuel_level_gal: tank * rng.between(0.3, 1),
    odometer_mi: rng.int(50_000, 600_000),
    source_sequence: 0,
    parkedMinutes: 0,
    anomaly: null,
    reefer: null,
  }
  startTrip(truck, rng.pick(ROUTES))
  truck.progress = rng.next() // spread trucks along their lanes
  if (rng.chance(REEFER_SHARE)) {
    const trailer_id = padId('TRL', index + 1)
    const range = rng.pick(COMMODITIES)
    truck.reefer = { trailer_id, sensor_id: `RF-${trailer_id}-S1`, range, cargo_temp_f: range.setpoint_f, source_sequence: 0, breach: null }
  }
  return truck
}

function openAlert(truck, anomaly_type) {
  anomalyCounter += 1
  const alert = {
    anomaly_id: padId('A', anomalyCounter, 8),
    anomaly_type,
    vehicle_id: truck.vehicle_id,
    trip_id: truck.trip_id,
    start_ts: iso(simTime),
    end_ts: null,
  }
  activeAlerts.set(alert.anomaly_id, alert)
  emit('alert', alert)
  return alert
}

function closeAlert(alert) {
  activeAlerts.delete(alert.anomaly_id)
  emit('alert', { ...alert, end_ts: iso(simTime) })
}

function maybeStartAnomaly(truck) {
  for (const [type, spec] of Object.entries(ANOMALIES)) {
    if (type === 'REEFER_UNIT_FAILURE' && !truck.reefer) continue
    if (!rng.chance(spec.chance)) continue
    const totalMinutes = rng.int(...spec.minutes)
    truck.anomaly = {
      type,
      totalMinutes,
      minutesLeft: totalMinutes,
      offsetMiles: spec.offsetMiles ? rng.between(...spec.offsetMiles) : 0,
      alert: openAlert(truck, type),
    }
    return
  }
}

// Moves one truck forward by one tick: trip progress, parking, anomalies, fuel.
function advanceTruck(truck) {
  if (truck.anomaly) {
    truck.anomaly.minutesLeft -= TICK_MINUTES
    if (truck.anomaly.minutesLeft <= 0) {
      closeAlert(truck.anomaly.alert)
      truck.anomaly = null
    }
  } else if (truck.parkedMinutes === 0) {
    maybeStartAnomaly(truck)
  }

  if (truck.parkedMinutes > 0) {
    truck.parkedMinutes -= TICK_MINUTES
    truck.speed_mph = 0
    truck.engine_on = false
    if (truck.parkedMinutes <= 0) {
      truck.parkedMinutes = 0
      startTrip(truck, rng.pick(routesByOrigin.get(truck.route.destination_city)))
    }
  } else if (truck.anomaly?.type === 'EXCESSIVE_IDLING') {
    truck.speed_mph = 0
    truck.engine_on = true
  } else {
    truck.engine_on = true
    truck.speed_mph = truck.cruise_mph + rng.between(-4, 4)
    const miles = (truck.speed_mph * TICK_MINUTES) / 60
    truck.progress += miles / truck.route.typical_distance_miles
    truck.odometer_mi += miles
    if (truck.progress >= 1) {
      truck.progress = 1
      truck.parkedMinutes = rng.int(60, 600)
    }
  }

  truck.fuel_gph = !truck.engine_on ? 0 : truck.speed_mph > 0 ? truck.speed_mph / MPG : IDLE_GPH
  truck.fuel_level_gal -= (truck.fuel_gph * TICK_MINUTES) / 60
  if (truck.fuel_level_gal < truck.tank * REFUEL_LEVEL) truck.fuel_level_gal = truck.tank
}

// Cargo warms while the unit is failed and is pulled back to setpoint while it works.
// Leaving the allowed range opens a COLD_CHAIN_BREACH alert; returning closes it.
function advanceReefer(truck) {
  const { reefer } = truck
  const failing = truck.anomaly?.type === 'REEFER_UNIT_FAILURE'
  reefer.compressor_on = !failing
  reefer.cargo_temp_f += failing
    ? rng.between(0.05, 0.12)
    : (reefer.range.setpoint_f - reefer.cargo_temp_f) * 0.08 + rng.between(-0.2, 0.2)

  const outOfRange = reefer.cargo_temp_f > reefer.range.max_temp_f || reefer.cargo_temp_f < reefer.range.min_temp_f
  if (outOfRange && !reefer.breach) reefer.breach = openAlert(truck, 'COLD_CHAIN_BREACH')
  if (!outOfRange && reefer.breach) {
    closeAlert(reefer.breach)
    reefer.breach = null
  }
}

// Position on the straight lane between the two facilities; a route deviation drifts out and back.
function positionOf(truck) {
  const route = truck.route
  const dLat = route.destination_latitude - route.origin_latitude
  const dLon = route.destination_longitude - route.origin_longitude
  let lat = route.origin_latitude + dLat * truck.progress
  let lon = route.origin_longitude + dLon * truck.progress
  if (truck.anomaly?.type === 'ROUTE_DEVIATION') {
    const { minutesLeft, totalMinutes, offsetMiles } = truck.anomaly
    const shape = Math.sin(Math.PI * (1 - minutesLeft / totalMinutes))
    const offsetDegrees = (offsetMiles * shape) / MILES_PER_DEGREE
    const length = Math.hypot(dLat, dLon)
    lat += (-dLon / length) * offsetDegrees
    lon += (dLat / length) * offsetDegrees
  }
  const heading_deg = Math.round(((Math.atan2(dLon * Math.cos((lat * Math.PI) / 180), dLat) * 180) / Math.PI + 360) % 360)
  return { lat, lon, heading_deg }
}

function telemetryRow(truck, position) {
  truck.source_sequence += 1
  const gpsLost = rng.chance(GPS_DROP_CHANCE)
  const moving = truck.speed_mph > 0
  return {
    schema_version: 1,
    event_id: `T${truck.vehicle_id.slice(3)}${Math.floor(simTime / 1000)}`,
    vehicle_id: truck.vehicle_id,
    device_id: truck.device_id,
    event_ts: iso(simTime),
    source_sequence: truck.source_sequence,
    lat: gpsLost ? null : round(position.lat, 5),
    lon: gpsLost ? null : round(position.lon, 5),
    speed_mph: round(truck.speed_mph, 1),
    heading_deg: position.heading_deg,
    rpm: !truck.engine_on ? 0 : moving ? rng.int(1200, 1600) : rng.int(600, 750),
    engine_temp_f: round(truck.engine_on ? rng.between(190, 210) : rng.between(70, 100), 1),
    fuel_gph: round(truck.fuel_gph, 2),
    fuel_level_gal: round(truck.fuel_level_gal, 1),
    odometer_mi: round(truck.odometer_mi, 1),
    engine_on: truck.engine_on,
    ingest_ts: iso(simTime + rng.int(1, 5) * 1000),
  }
}

function reeferRow(truck, position) {
  const { reefer } = truck
  reefer.source_sequence += 1
  return {
    schema_version: 1,
    event_id: `R${truck.vehicle_id.slice(3)}${Math.floor(simTime / 1000)}`,
    vehicle_id: truck.vehicle_id,
    trailer_id: reefer.trailer_id,
    sensor_id: reefer.sensor_id,
    event_ts: iso(simTime),
    source_sequence: reefer.source_sequence,
    cargo_temp_f: rng.chance(SENSOR_DROP_CHANCE) ? null : round(reefer.cargo_temp_f, 1),
    setpoint_f: reefer.range.setpoint_f,
    compressor_on: reefer.compressor_on,
    door_open: truck.parkedMinutes > 0 && rng.chance(0.2),
    ambient_temp_f: round(95 - (position.lat - 25) * 1.5 + rng.between(-3, 3), 1), // warmer in the south
    reefer_fuel_gph: reefer.compressor_on ? round(rng.between(0.4, 0.8), 2) : 0,
    unit_mode: 'CONTINUOUS',
    ingest_ts: iso(simTime + rng.int(1, 5) * 1000),
  }
}

// emitRows = false during warm-up: state moves forward but no rows are built.
function tick(emitRows) {
  simTime += TICK_MINUTES * 60_000
  const telemetry = []
  const reefer = []
  for (const truck of trucks) {
    advanceTruck(truck)
    if (truck.reefer) advanceReefer(truck)
    if (!emitRows) continue
    const position = positionOf(truck)
    telemetry.push(telemetryRow(truck, position))
    if (truck.reefer) reefer.push(reeferRow(truck, position))
  }
  if (emitRows) {
    emit('telemetry', telemetry)
    emit('reefer', reefer)
  }
}

function ensureFleet() {
  if (trucks) return
  const minuteMs = 60_000
  simTime = Math.floor(Date.now() / minuteMs) * minuteMs - WARMUP_TICKS * TICK_MINUTES * minuteMs
  trucks = Array.from({ length: TRUCK_COUNT }, (_, index) => createTruck(index))
  for (let i = 0; i < WARMUP_TICKS; i++) tick(false)
}

export function subscribeSimulator(eventType, onEvent) {
  if (!listeners[eventType]) throw new Error(`Unknown stream event "${eventType}"`)
  ensureFleet()
  listeners[eventType].add(onEvent)
  if (eventType === 'alert') activeAlerts.forEach((alert) => onEvent(alert)) // contract: replay active alerts on connect
  if (!timer) timer = setInterval(() => tick(true), TICK_MS)

  return () => {
    listeners[eventType].delete(onEvent)
    if (Object.values(listeners).every((set) => set.size === 0)) {
      clearInterval(timer)
      timer = null
    }
  }
}
