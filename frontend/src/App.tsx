import { BrowserRouter, Routes, Route } from 'react-router-dom'
import QueryProvider from './components/QueryProvider'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/layout/Layout'
import Landing from './pages/Landing'
import SectorRotation from './pages/SectorRotation'
import StockScreener from './pages/StockScreener'
import QuantGen from './pages/QuantGen'
import EarningsCalendar from './pages/EarningsCalendar'

function App() {
  return (
    <QueryProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={
            <ErrorBoundary>
              <Landing />
            </ErrorBoundary>
          } />
          <Route element={<Layout />}>
            <Route path="sectors" element={
              <ErrorBoundary>
                <SectorRotation />
              </ErrorBoundary>
            } />
            <Route path="screener" element={
              <ErrorBoundary>
                <StockScreener />
              </ErrorBoundary>
            } />
            <Route path="earnings" element={
              <ErrorBoundary>
                <EarningsCalendar />
              </ErrorBoundary>
            } />
            <Route path="quantgen/*" element={
              <ErrorBoundary>
                <QuantGen />
              </ErrorBoundary>
            } />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryProvider>
  )
}

export default App
