import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Landing from './pages/Landing'
import SectorRotation from './pages/SectorRotation'
import StockScreener from './pages/StockScreener'
import QuantGen from './pages/QuantGen'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route element={<Layout />}>
          <Route path="sectors" element={<SectorRotation />} />
          <Route path="screener" element={<StockScreener />} />
          <Route path="quantgen/*" element={<QuantGen />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App