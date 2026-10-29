// Mock reference data with the catalog's column names (facilities, routes, cold-chain ranges, lookups).

export const padId = (prefix, number, width = 5) => `${prefix}${String(number).padStart(width, '0')}`

const FACILITY_ROWS = [
  ['Chicago', 'IL', 41.88, -87.63, 'Terminal'],
  ['Atlanta', 'GA', 33.75, -84.39, 'Distribution Center'],
  ['Dallas', 'TX', 32.78, -96.8, 'Terminal'],
  ['Los Angeles', 'CA', 34.05, -118.24, 'Distribution Center'],
  ['Houston', 'TX', 29.76, -95.37, 'Cross-Dock'],
  ['Phoenix', 'AZ', 33.45, -112.07, 'Warehouse'],
  ['Denver', 'CO', 39.74, -104.99, 'Terminal'],
  ['Seattle', 'WA', 47.61, -122.33, 'Distribution Center'],
  ['Kansas City', 'MO', 39.1, -94.58, 'Cross-Dock'],
  ['Memphis', 'TN', 35.15, -90.05, 'Distribution Center'],
  ['Nashville', 'TN', 36.16, -86.78, 'Warehouse'],
  ['Columbus', 'OH', 39.96, -83.0, 'Distribution Center'],
  ['Charlotte', 'NC', 35.23, -80.84, 'Warehouse'],
  ['Jacksonville', 'FL', 30.33, -81.66, 'Cross-Dock'],
  ['Salt Lake City', 'UT', 40.76, -111.89, 'Terminal'],
  ['Indianapolis', 'IN', 39.77, -86.16, 'Warehouse'],
  ['Newark', 'NJ', 40.74, -74.17, 'Distribution Center'],
  ['Minneapolis', 'MN', 44.98, -93.27, 'Terminal'],
]

export const FACILITIES = FACILITY_ROWS.map(([city, state, latitude, longitude, facility_type], index) => ({
  facility_id: padId('FAC', index + 1),
  facility_name: `${city} ${facility_type}`,
  facility_type,
  city,
  state,
  latitude,
  longitude,
}))

export function haversineMiles(lat1, lon1, lat2, lon2) {
  const toRad = (degrees) => (degrees * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 3958.8 * 2 * Math.asin(Math.sqrt(a))
}

// Road distance ~18% longer than straight line.
const ROAD_FACTOR = 1.18

function makeRoute(origin, destination) {
  return {
    origin_city: origin.city,
    origin_state: origin.state,
    destination_city: destination.city,
    destination_state: destination.state,
    typical_distance_miles: Math.round(
      haversineMiles(origin.latitude, origin.longitude, destination.latitude, destination.longitude) * ROAD_FACTOR,
    ),
    // Coordinates of the two facilities, needed to draw the lane on the map.
    origin_latitude: origin.latitude,
    origin_longitude: origin.longitude,
    destination_latitude: destination.latitude,
    destination_longitude: destination.longitude,
  }
}

// Each facility connects to the ones 1, 4 and 7 places ahead; every lane exists in both directions (like the catalog).
const LANE_STEPS = [1, 4, 7]

export const ROUTES = FACILITIES.flatMap((origin, index) =>
  LANE_STEPS.flatMap((step) => {
    const destination = FACILITIES[(index + step) % FACILITIES.length]
    return [makeRoute(origin, destination), makeRoute(destination, origin)]
  }),
).map((route, index) => ({ route_id: padId('RTE', index + 1), ...route }))

// Cold chain ranges: simulation assumptions from Notion_Data_Catalog.md A.7 (the future dbt seed).
export const COMMODITIES = [
  { commodity: 'Pharma', setpoint_f: 41, min_temp_f: 36, max_temp_f: 46 },
  { commodity: 'Chilled', setpoint_f: 36, min_temp_f: 33, max_temp_f: 41 },
  { commodity: 'Frozen', setpoint_f: -5, min_temp_f: -10, max_temp_f: 0 },
]

export const MAKES = ['Peterbilt', 'Freightliner', 'Mack', 'Volvo', 'International', 'Kenworth']
export const CUSTOMER_TYPES = ['Contract', 'Spot', 'Dedicated']
export const CUSTOMER_NAMES = [
  'Northwind Foods', 'Apex Retail', 'Blue Ridge Pharma', 'Summit Electronics', 'Great Lakes Industrial',
  'Pacific Produce', 'Lone Star Beverages', 'Metro Consumer Goods', 'Harbor Automotive', 'Prairie Grocers',
  'Evergreen Health', 'Coastal Distributors',
]
export const FIRST_NAMES = ['James', 'Maria', 'Robert', 'Linda', 'Michael', 'Ana', 'David', 'Susan', 'Carlos', 'Karen', 'Daniel', 'Grace']
export const LAST_NAMES = ['Smith', 'Garcia', 'Johnson', 'Brown', 'Miller', 'Davis', 'Lopez', 'Wilson', 'Moore', 'Taylor', 'Clark', 'Lewis']
export const MAINTENANCE_TYPES = ['Inspection', 'Repair', 'Preventive', 'Engine', 'Tire', 'Transmission', 'Brake']
export const INCIDENT_TYPES = ['DOT Violation', 'Equipment Damage', 'Accident', 'Customer Complaint', 'Moving Violation']

// Batch tables landed in S3 (used for the reconciliation chart).
export const BATCH_TABLES = [
  'trucks', 'trailers', 'drivers', 'customers', 'facilities', 'routes', 'diesel_prices',
  'loads', 'trips', 'delivery_events', 'fuel_purchases', 'maintenance_records', 'safety_incidents',
]
