import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import ProbePage from './pages/ProbePage'
import AuditPage from './pages/AuditPage'
import SafetyPage from './pages/SafetyPage'
import ReasoningPage from './pages/ReasoningPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<ChatPage />} />
        <Route path="probe" element={<ProbePage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="safety" element={<SafetyPage />} />
        <Route path="reasoning" element={<ReasoningPage />} />
      </Route>
    </Routes>
  )
}

export default App
