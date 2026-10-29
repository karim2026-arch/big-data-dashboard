import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useTheme } from '../hooks/useTheme'
import { MAP_SCALE } from './projection'
import UsOutline from './UsOutline'

const BACKGROUND = { light: '#f1f5f9', dark: '#020617' }
// Start view shows the whole US, so it moves away with the map size. Closest zoom stays fixed: it is about seeing one truck.
const CAMERA_POSITION = [0, 30 * MAP_SCALE, 24 * MAP_SCALE]
const MIN_DISTANCE = 6
const MAX_DISTANCE = 70 * MAP_SCALE

// 3D US map frame; layers (trucks, route arcs) are passed as children.
export default function MapCanvas({ children }) {
  const { theme } = useTheme()
  return (
    <Canvas camera={{ position: CAMERA_POSITION, fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={[BACKGROUND[theme]]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[10, 25, 10]} intensity={0.8} />
      <UsOutline />
      {children}
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.2} minDistance={MIN_DISTANCE} maxDistance={MAX_DISTANCE} />
    </Canvas>
  )
}
