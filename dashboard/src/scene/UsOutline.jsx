import { useMemo } from 'react'
import * as THREE from 'three'
import { mesh } from 'topojson-client'
import us from 'us-atlas/states-10m.json'
import { project } from './projection'

// Lower-48 bounding box: drops Alaska and Hawaii, which are outside the fleet's corridors.
const isContiguous = ([lon, lat]) => lon > -125 && lon < -66 && lat > 24 && lat < 50

// State borders drawn as line segments (bundled with the app, no external map service).
export default function UsOutline() {
  const geometry = useMemo(() => {
    const positions = []
    for (const line of mesh(us, us.objects.states).coordinates) {
      for (let i = 1; i < line.length; i++) {
        const [from, to] = [line[i - 1], line[i]]
        if (!isContiguous(from) || !isContiguous(to)) continue
        positions.push(...project(from[1], from[0]), ...project(to[1], to[0]))
      }
    }
    return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  }, [])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#334155" />
    </lineSegments>
  )
}
