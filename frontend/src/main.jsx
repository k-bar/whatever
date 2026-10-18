import React from 'react'
import ReactDOM from 'react-dom/client'
import { MotionConfig } from 'framer-motion'
import App from './App'
import { ConfigProvider } from './config/store'
import { LangProvider } from './i18n'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LangProvider>
      <ConfigProvider>
        {/* the phone / computer's "reduce motion" setting calms framer's movement too (CSS: end of global.css) */}
        <MotionConfig reducedMotion="user">
          <App />
        </MotionConfig>
      </ConfigProvider>
    </LangProvider>
  </React.StrictMode>,
)
