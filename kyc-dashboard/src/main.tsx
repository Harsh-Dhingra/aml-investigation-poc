import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import CustomerKyc from './pages/CustomerKyc'
import CustomerList from './pages/CustomerList'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/kyc" element={<CustomerList />} />
          <Route path="/kyc/:customerId" element={<CustomerKyc />} />
        </Route>
        <Route path="*" element={<Navigate to="/kyc" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
