import { useState, useEffect } from 'react'
import { Brain, Loader2, CheckCircle2, AlertCircle, Send } from 'lucide-react'

const API = '/api/v1'

export default function EvolutionPage() {
  const [stats, setStats] = useState(null)
  const [lessons, setLessons] = useState([])
  const [loading, setLoading] = useState(true)
  const [sessionId, setSessionId] = useState('')
  const [feedback, setFeedback] = useState('')
  const [rating, setRating] = useState(5)
  const [msg, setMsg] = useState(null)

  const token = localStorage.getItem('auth_token')
  const auth = token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : {}

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [s, l] = await Promise.all([
        fetch(API + '/evolution/stats', { headers: auth }).then(r => r.json()),
        fetch(API + '/feedback/lessons', { headers: auth }).then(r => r.json()),
      ])
      setStats(s.data)
      setLessons(l.data?.lessons || [])
    } catch (e) { showMsg('error', '加载失败') }
    finally { setLoading(false) }
  }

  const showMsg = (type, text) => { setMsg({ type, text }); setTimeout(() => setMsg(null), 4000) }

  const submitFeedback = async () => {
    if (!sessionId.trim() || !feedback.trim()) return showMsg('error', '请填写会话ID和反馈')
    try {
      const res = await fetch(API + '/feedback/submit', {
        method: 'POST', headers: auth,
        body: JSON.stringify({ session_id: sessionId, feedback, rating }),
      })
      const data = await res.json()
      if (data.code === 0) { showMsg('success', '反馈已提交'); loadData() }
      else showMsg('error', data.message || '失败')
    } catch (e) { showMsg('error', '提交失败') }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-primary-400" /></div>

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-3"><Brain className="w-7 h-7 text-primary-400" />自演进引擎</h1>

      {msg && <div className={`p-3 rounded-lg flex items-center gap-2 ${msg.type==='success'?'bg-emerald-900/30 text-emerald-300':'bg-red-900/30 text-red-300'}`}>
        {msg.type==='success'?<CheckCircle2 className="w-4 h-4"/>:<AlertCircle className="w-4 h-4"/>}
        {msg.text}
      </div>}

      {/* 统计卡片 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-center">
          <div className="text-3xl font-bold text-primary-400">{stats?.lessons_learned || 0}</div>
          <div className="text-xs text-slate-500 mt-1">经验教训</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-center">
          <div className="text-3xl font-bold text-emerald-400">{stats?.facts_stored || 0}</div>
          <div className="text-xs text-slate-500 mt-1">事实知识</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-center">
          <div className="text-3xl font-bold text-amber-400">{stats?.average_lesson_importance || '0'}</div>
          <div className="text-xs text-slate-500 mt-1">平均重要性</div>
        </div>
      </div>

      {/* 经验教训列表 */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
        <h2 className="font-semibold mb-3">经验教训</h2>
        {lessons.length === 0 ? <p className="text-sm text-slate-500">暂无，运行Agent后自动积累</p> : (
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {lessons.slice(0,10).map(l => (
              <div key={l.id} className="p-2 rounded bg-slate-800/50 text-sm text-slate-300">
                <span className="text-amber-400 font-mono">[{l.importance}]</span> {l.content}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 反馈表单 */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
        <h2 className="font-semibold mb-3">人类专家反馈</h2>
        <div className="space-y-3">
          <input value={sessionId} onChange={e => setSessionId(e.target.value)} placeholder="会话ID (sess_xxx)" className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm" />
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-400">评分:</span>
            <input type="number" min={1} max={10} value={rating} onChange={e => setRating(Number(e.target.value))} className="w-16 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm" />
          </div>
          <textarea value={feedback} onChange={e => setFeedback(e.target.value)} rows={3} placeholder="你的反馈将触发知识库/技能/记忆/规则更新..." className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm resize-none" />
          <button onClick={submitFeedback} className="px-4 py-2 rounded bg-primary-600 hover:bg-primary-500 text-sm">提交反馈</button>
        </div>
      </div>
    </div>
  )
}
