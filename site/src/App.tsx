import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { PodigamiPage } from './pages/PodigamiPage'
import { ReplayDetailPage } from './pages/ReplayDetailPage'
import { ReplaysPage } from './pages/ReplaysPage'
import { WhatIfPage } from './pages/WhatIfPage'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<LeaderboardPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/replays" element={<ReplaysPage />} />
          <Route path="/replays/:season/:round/sprint" element={<ReplayDetailPage />} />
          <Route path="/replays/:season/:round" element={<ReplayDetailPage />} />
          <Route path="/podigami" element={<PodigamiPage />} />
          <Route path="/podiumigami" element={<Navigate to="/podigami" replace />} />
          <Route path="/what-if" element={<WhatIfPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
