import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import UsOutline from './UsOutline'

// 3D US map frame; layers (trucks, route arcs) are passed as children.
export default function MapCanvas({ children }) {
  return (
    <Canvas camera={{ position: [0, 30, 24], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={['#020617']} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[10, 25, 10]} intensity={0.8} />
      <UsOutline />
      {children}
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.2} minDistance={6} maxDistance={70} />
    </Canvas>
  )
}
