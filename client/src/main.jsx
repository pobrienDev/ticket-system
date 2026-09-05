// Browser entry point: mounts the React tree into #root (see index.html).
// StrictMode double-invokes effects in development to surface side-effect
// bugs early; it has no effect in production builds.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
