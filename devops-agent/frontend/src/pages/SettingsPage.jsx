import { useState, useEffect } from 'react'
import {
  Settings,
  Loader2,
  Save,
  RotateCcw,
  AlertCircle,
  CheckCircle2,
  Cpu,
  KeyRound,
  Thermometer,
  Hash,
  Globe,
  Server,
} from 'lucide-react'
import {
  getLLMConfig,
  updateConfig,
  resetConfig,
  resetAllLLMConfig,
} from '../api/client'

// --- 新增面板的 API 调用（内联 fetch，保持轻量） ---
const API = '/api/v1'
const authHeaders = () => {
  const t = localStorage.getItem('auth_token')
  return t ? { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
}

const LLM_FIELDS = [
  { key: 'llm.protocol', label: '协议类型', icon: Server, type: 'select', options: ['openai', 'anthropic'] },
  { key: 'llm.base_url', label: 'Base URL', icon: Globe, type: 'text' },
  { key: 'llm.api_key', label: 'API Key', icon: KeyRound, type: 'password' },
  { key: 'llm.model', label: '模型名称', icon: Cpu, type: 'text' },
  { key: 'llm.temperature', label: '温度 (0.0-2.0)', icon: Thermometer, type: 'number', min: 0, max: 2, step: 0.1 },
  { key: 'llm.max_tokens', label: '最大 Token 数', icon: Hash, type: 'number', min: 1, max: 8192 },
  { key: 'llm.anthropic_base_url', label: 'Anthropic Base URL', icon: Globe, type: 'text' },
  { key: 'llm.anthropic_api_key', label: 'Anthropic API Key', icon: KeyRound, type: 'password' },
  { key: 'llm.anthropic_model', label: 'Anthropic 模型', icon: Cpu, type: 'text' },
]

export default function SettingsPage() {
  const [config, setConfig] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [editValues, setEditValues] = useState({})
  const [activeTab, setActiveTab] = useState('llm')  // llm | router | evolution | skills

  // --- Model Router state ---
  const [modelPool, setModelPool] = useState([])
  const [poolLoading, setPoolLoading] = useState(false)
  // --- Evolution state ---
  const [evoStats, setEvoStats] = useState(null)
  const [lessons, setLessons] = useState([])
  const [feedbackSession, setFeedbackSession] = useState('')
  const [feedbackText, setFeedbackText] = useState('')
  const [feedbackRating, setFeedbackRating] = useState(5)
  const [evoLoading, setEvoLoading] = useState(false)
  // --- Skills state ---
  const [skillsLoading, setSkillsLoading] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadModelPool = async () => {
    setPoolLoading(true)
    try {
      const res = await fetch(API + '/models/pool', { headers: authHeaders() })
      const data = await res.json()
      setModelPool(data.data?.models || [])
    } catch (e) { showMessage('error', '加载模型池失败') }
    finally { setPoolLoading(false) }
  }
  const resetBreakers = async () => {
    try {
      await fetch(API + '/models/reset', { method: 'POST', headers: authHeaders() })
      showMessage('success', '熔断器已重置')
      loadModelPool()
    } catch (e) { showMessage('error', '重置失败') }
  }
  const loadEvolution = async () => {
    setEvoLoading(true)
    try {
      const [statsRes, lessonsRes] = await Promise.all([
        fetch(API + '/evolution/stats', { headers: authHeaders() }),
        fetch(API + '/feedback/lessons', { headers: authHeaders() }),
      ])
      const stats = await statsRes.json()
      const lessonsData = await lessonsRes.json()
      setEvoStats(stats.data)
      setLessons(lessonsData.data?.lessons || [])
    } catch (e) { showMessage('error', '加载自演进数据失败') }
    finally { setEvoLoading(false) }
  }
  const submitFeedback = async () => {
    if (!feedbackSession.trim() || !feedbackText.trim()) return showMessage('error', '请填写会话ID和反馈内容')
    try {
      const res = await fetch(API + '/feedback/submit', {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ session_id: feedbackSession, feedback: feedbackText, rating: feedbackRating }),
      })
      const data = await res.json()
      if (data.code === 0) { showMessage('success', '反馈已提交，触发演进更新'); loadEvolution() }
      else { showMessage('error', data.message || '提交失败') }
    } catch (e) { showMessage('error', '提交失败: ' + e.message) }
  }
  const loadSkills = async () => {
    setSkillsLoading(true)
    try { showMessage('info', 'Skills 目录: ./skills/ (服务器端)') }
    finally { setSkillsLoading(false) }
  }

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await getLLMConfig()
      setConfig(data)
      // items 是带默认值和覆盖标记的列表
      setItems(data.items || [])
      // 初始化编辑值
      const initial = {}
      ;(data.items || []).forEach((item) => {
        initial[item.key] = item.value
      })
      setEditValues(initial)
    } catch (e) {
      showMessage('error', '加载配置失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const showMessage = (type, text) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  const handleChange = (key, value) => {
    setEditValues((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      // 只提交与默认值不同的项（或所有已修改的项）
      const changed = []
      items.forEach((item) => {
        const newVal = editValues[item.key]
        // 将新值与当前值（已合并后的）比较，若不同则提交
        if (newVal !== undefined && String(newVal) !== String(item.value)) {
          changed.push({ key: item.key, value: String(newVal) })
        }
      })

      if (changed.length === 0) {
        showMessage('info', '没有变更需要保存')
        setSaving(false)
        return
      }

      const res = await updateConfig(changed)
      if (res.errors && res.errors.length > 0) {
        showMessage('error', '部分保存失败: ' + res.errors.join('; '))
      } else {
        showMessage('success', `已保存 ${res.updated.length} 项配置，下次对话生效`)
        // 刷新以显示新的覆盖状态
        await loadConfig()
      }
    } catch (e) {
      showMessage('error', '保存失败: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async (key) => {
    if (!confirm(`确定将 ${key} 重置为默认值吗？`)) return
    try {
      await resetConfig(key)
      showMessage('success', `${key} 已重置为默认值`)
      await loadConfig()
    } catch (e) {
      showMessage('error', '重置失败: ' + e.message)
    }
  }

  const handleResetAll = async () => {
    if (!confirm('确定将所有 LLM 配置重置为默认值吗？')) return
    try {
      await resetAllLLMConfig()
      showMessage('success', '所有配置已重置为默认值')
      await loadConfig()
    } catch (e) {
      showMessage('error', '重置失败: ' + e.message)
    }
  }

  const renderField = (field, item) => {
    const value = editValues[field.key] ?? ''
    const isOverridden = item?.is_overridden

    if (field.type === 'select') {
      return (
        <select
          value={value}
          onChange={(e) => handleChange(field.key, e.target.value)}
          className={`w-full bg-slate-800 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            isOverridden ? 'border-amber-500/50' : 'border-slate-700'
          }`}
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    return (
      <input
        type={field.type === 'password' ? 'password' : field.type}
        value={value}
        onChange={(e) => handleChange(field.key, e.target.value)}
        min={field.min}
        max={field.max}
        step={field.step}
        className={`w-full bg-slate-800 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
          isOverridden ? 'border-amber-500/50' : 'border-slate-700'
        }`}
      />
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-primary-400" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Settings className="w-6 h-6 text-primary-400" />
          <h1 className="text-xl font-bold">系统设置</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleResetAll}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            全部重置
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-primary-600 hover:bg-primary-500 text-white disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            保存配置
          </button>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div
          className={`mb-4 flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
            message.type === 'success'
              ? 'bg-emerald-900/30 text-emerald-300 border border-emerald-800/50'
              : message.type === 'error'
              ? 'bg-red-900/30 text-red-300 border border-red-800/50'
              : 'bg-slate-800 text-slate-300 border border-slate-700'
          }`}
        >
          {message.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          {message.text}
        </div>
      )}

      {/* Current Model Badge */}
      <div className="mb-6 p-4 rounded-xl bg-slate-900 border border-slate-800">
        <div className="text-xs text-slate-500 mb-1">当前使用的 LLM 模型</div>
        <div className="flex items-center gap-4">
          <div className="text-lg font-semibold text-primary-300">{config?.model || '未知'}</div>
          <div className="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-400 border border-slate-700">
            {config?.protocol || 'openai'}
          </div>
          <div className="text-xs text-slate-500">
            temp={config?.temperature} · max_tokens={config?.max_tokens}
          </div>
        </div>
        <div className="mt-2 text-xs text-slate-600">
          Base URL: {config?.base_url}
        </div>
      </div>

      {/* LLM Config Form */}
      <div className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 bg-slate-800/30">
          <h2 className="text-sm font-semibold text-slate-300">LLM 配置</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            修改后点击保存，下一次 Agent 对话自动生效。黄色边框表示该值已覆盖默认值。
          </p>
        </div>

        <div className="divide-y divide-slate-800">
          {LLM_FIELDS.map((field) => {
            const item = items.find((i) => i.key === field.key)
            const Icon = field.icon
            const isOverridden = item?.is_overridden

            return (
              <div key={field.key} className="px-4 py-4 flex items-start gap-4">
                <div className="mt-2 w-8 flex-shrink-0">
                  <Icon className={`w-5 h-5 ${isOverridden ? 'text-amber-400' : 'text-slate-500'}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-sm font-medium text-slate-300">
                      {field.label}
                      {isOverridden && (
                        <span className="ml-2 text-xs text-amber-400 font-normal">(已覆盖)</span>
                      )}
                    </label>
                    {isOverridden && (
                      <button
                        onClick={() => handleReset(field.key)}
                        className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1"
                        title="恢复默认值"
                      >
                        <RotateCcw className="w-3 h-3" />
                        重置
                      </button>
                    )}
                  </div>
                  {renderField(field, item)}
                  {item?.default_value !== undefined && (
                    <div className="mt-1 text-xs text-slate-600">
                      默认值: {item.sensitive ? '***' : item.default_value}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ========== Tab Navigation ========== */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {[
          ['llm', 'LLM 配置'],
          ['router', '模型路由'],
          ['evolution', '自演进'],
          ['skills', 'Skills'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => { setActiveTab(key); if (key === 'router') loadModelPool(); if (key === 'evolution') loadEvolution(); if (key === 'skills') loadSkills() }}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === key ? 'border-primary-400 text-primary-300' : 'border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >{label}</button>
        ))}
      </div>

      {/* ========== Model Router Panel ========== */}
      {activeTab === 'router' && (
        <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-300">模型池状态</h2>
            <button onClick={resetBreakers} className="px-3 py-1 text-xs rounded bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200">重置熔断器</button>
          </div>
          {poolLoading ? <Loader2 className="w-5 h-5 animate-spin text-slate-500 mx-auto" /> : modelPool.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">暂无模型（请设置 API Key 环境变量）</p>
          ) : (
            <table className="w-full text-xs">
              <thead><tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left py-2 font-medium">模型</th><th className="text-left">状态</th><th className="text-right">调用/失败</th><th className="text-right">失败率</th><th className="text-left">优先级</th>
              </tr></thead>
              <tbody>{modelPool.map(m => (
                <tr key={m.name} className="border-b border-slate-800/50">
                  <td className="py-2 text-slate-200">{m.name}</td>
                  <td><span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    m.status === 'healthy' ? 'bg-emerald-900/30 text-emerald-400' :
                    m.status === 'open' ? 'bg-red-900/30 text-red-400' : 'bg-amber-900/30 text-amber-400'
                  }`}>{m.status}</span></td>
                  <td className="text-right text-slate-400 font-mono">{m.total_calls}/{m.total_failures}</td>
                  <td className="text-right font-mono text-slate-400">{m.failure_rate}</td>
                  <td className="text-slate-500">{m.priority === 0 ? '主' : m.priority === 1 ? '备' : '兜底'}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}

      {/* ========== Evolution Panel ========== */}
      {activeTab === 'evolution' && (
        <div className="space-y-4">
          {evoLoading ? <Loader2 className="w-5 h-5 animate-spin text-slate-500 mx-auto" /> : <>
            {/* Stats */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">自演进统计</h2>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center"><div className="text-2xl font-bold text-primary-300">{evoStats?.lessons_learned || 0}</div><div className="text-xs text-slate-500 mt-1">经验教训</div></div>
                <div className="text-center"><div className="text-2xl font-bold text-emerald-300">{evoStats?.facts_stored || 0}</div><div className="text-xs text-slate-500 mt-1">事实知识</div></div>
                <div className="text-center"><div className="text-2xl font-bold text-amber-300">{evoStats?.average_lesson_importance || '0'}</div><div className="text-xs text-slate-500 mt-1">平均重要性</div></div>
              </div>
            </div>

            {/* Lessons */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">经验教训</h2>
              {lessons.length === 0 ? <p className="text-xs text-slate-500 py-3 text-center">暂无——Agent 运行后自动积累</p> : (
                <div className="space-y-2 max-h-48 overflow-y-auto">{lessons.slice(0, 10).map(l => (
                  <div key={l.id} className="p-2 rounded bg-slate-800/50 text-xs text-slate-400">
                    <span className="text-amber-400 font-mono">[{l.importance}]</span> {l.content}
                  </div>
                ))}</div>
              )}
            </div>

            {/* Feedback Form */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">人类专家反馈</h2>
              <div className="space-y-3">
                <div><label className="text-xs text-slate-500 block mb-1">会话 ID</label>
                  <input value={feedbackSession} onChange={e => setFeedbackSession(e.target.value)} className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200" placeholder="sess_xxx" /></div>
                <div><label className="text-xs text-slate-500 block mb-1">评分 (1-10)</label>
                  <input type="number" min={1} max={10} value={feedbackRating} onChange={e => setFeedbackRating(Number(e.target.value))} className="w-20 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200" /></div>
                <div><label className="text-xs text-slate-500 block mb-1">反馈内容</label>
                  <textarea value={feedbackText} onChange={e => setFeedbackText(e.target.value)} rows={3} className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 resize-none" placeholder="你的反馈将触发知识库/技能/记忆/规则更新..." /></div>
                <button onClick={submitFeedback} className="px-4 py-2 rounded bg-primary-600 hover:bg-primary-500 text-sm text-white transition-colors">提交反馈</button>
              </div>
            </div>
          </>}
        </div>
      )}

      {/* ========== Skills Panel ========== */}
      {activeTab === 'skills' && (
        <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Agent Skills</h2>
          <div className="p-4 rounded bg-slate-800/30 border border-slate-700">
            <p className="text-xs text-slate-400 mb-2">Skills 目录：<code className="text-primary-300 bg-slate-800 px-1 rounded">./skills/</code></p>
            <p className="text-xs text-slate-500">当前已加载 <span className="text-primary-300 font-semibold">1</span> 个 Skill</p>
            <div className="mt-2 p-2 rounded bg-slate-800/50 text-xs text-slate-400">
              <span className="text-slate-200 font-medium">disk-cleanup</span> — 磁盘空间清理工作流
            </div>
            <p className="text-xs text-slate-600 mt-3">
              添加新 Skill：在 skills/ 目录下创建 {`{name}/SKILL.md`}，重启服务后自动扫描。
            </p>
          </div>
        </div>
      )}

      {/* Footer hint */}
      <div className="mt-4 text-xs text-slate-600 text-center">
        配置存储在 SQLite configs 表中，重启服务后仍然保留。通过 API 删除配置项可恢复 .env 默认值。
      </div>
    </div>
  )
}
