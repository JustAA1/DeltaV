import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { PodiumigamiPage } from './pages/PodiumigamiPage'
import { PredictionsPage } from './pages/PredictionsPage'
import { WhatIfPage } from './pages/WhatIfPage'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<PredictionsPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/podiumigami" element={<PodiumigamiPage />} />
          <Route path="/what-if" element={<WhatIfPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
