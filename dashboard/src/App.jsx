import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { DASHBOARDS } from './dashboards'
import ColdChainPage from './pages/ColdChainPage'
import DeliveryPage from './pages/DeliveryPage'
import ExecutivePage from './pages/ExecutivePage'
import FuelPage from './pages/FuelPage'
import LiveMapPage from './pages/LiveMapPage'
import MaintenancePage from './pages/MaintenancePage'
import PlatformPage from './pages/PlatformPage'
import SafetyPage from './pages/SafetyPage'

// dashboard id (src/dashboards.js) -> page component
const PAGES = {
  live: LiveMapPage,
  executive: ExecutivePage,
  delivery: DeliveryPage,
  cold_chain: ColdChainPage,
  fuel: FuelPage,
  safety: SafetyPage,
  maintenance: MaintenancePage,
  platform: PlatformPage,
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          {DASHBOARDS.map(({ id, path }) => {
            const Page = PAGES[id]
            return <Route key={id} path={path} element={<Page />} />
          })}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
