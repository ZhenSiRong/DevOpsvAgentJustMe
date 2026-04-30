import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import PrivateRoute from './components/PrivateRoute'
import LoginPage from './pages/LoginPage'
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
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={
          <PrivateRoute><Layout /></PrivateRoute>
        }>
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
    </AuthProvider>
  )
}

export default App
