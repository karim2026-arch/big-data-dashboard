// Flat lat/lon -> scene projection centered on the contiguous US. MAP_SCALE scene units = 1 degree of latitude (~69 mi).
// Accurate enough at country scale for a visual map (not for distance math).
// MAP_SCALE = map size against the trucks (trucks keep their size): bigger = more space between trucks.
export const MAP_SCALE = 3
const CENTER_LAT = 38
const CENTER_LON = -96
const LON_SCALE = Math.cos((CENTER_LAT * Math.PI) / 180)

export function project(lat, lon, y = 0) {
  return [(lon - CENTER_LON) * LON_SCALE * MAP_SCALE, y, -(lat - CENTER_LAT) * MAP_SCALE]
}
