import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import ProbePage from './pages/ProbePage'
import AuditPage from './pages/AuditPage'
import SafetyPage from './pages/SafetyPage'
import ReasoningPage from './pages/ReasoningPage'
import SettingsPage from './pages/SettingsPage'
import MCPPage from './pages/MCPPage'
import OrchestratorPage from './pages/OrchestratorPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<ChatPage />} />
        <Route path="probe" element={<ProbePage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="safety" element={<SafetyPage />} />
        <Route path="reasoning" element={<ReasoningPage />} />
        <Route path="orchestrator" element={<OrchestratorPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="mcp" element={<MCPPage />} />
      </Route>
    </Routes>
  )
}

export default App
