import { useState } from 'react'
import {
  GitBranch,
  Loader2,
  AlertCircle,
  Search,
  Brain,
  Eye,
  Lightbulb,
  Wrench,
  MessageSquare,
  Clock,
} from 'lucide-react'
import { getReasoningChain, getReasoningSummary } from '../api/client'

const PHASE_CONFIG = {
  SENSE: { label: '感知', icon: Eye, color: 'text-cyan-400', bg: 'bg-cyan-900/20 border-cyan-800/30' },
  ANALYZE: { label: '分析', icon: Brain, color: 'text-amber-400', bg: 'bg-amber-900/20 border-amber-800/30' },
  PLAN: { label: '规划', icon: Lightbulb, color: 'text-violet-400', bg: 'bg-violet-900/20 border-violet-800/30' },
  EXECUTE: { label: '执行', icon: Wrench, color: 'text-orange-400', bg: 'bg-orange-900/20 border-orange-800/30' },
  OUTPUT: { label: '输出', icon: MessageSquare, color: 'text-primary-400', bg: 'bg-primary-900/20 border-primary-800/30' },
}

export default function ReasoningPage() {
  const [sessionId, setSessionId] = useState('')
  const [chain, setChain] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleQuery = async () => {
    if (!sessionId.trim()) return
    setLoading(true)
    setError(null)
    try {
      const [chainRes, summaryRes] = await Promise.all([
        getReasoningChain(sessionId.trim()),
        getReasoningSummary(sessionId.trim()),
      ])
      if (chainRes.code === 0) setChain(chainRes.data)
      else setError(chainRes.message)
      if (summaryRes.code === 0) setSummary(summaryRes.data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (iso) => {
    if (!iso) return '-'
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  }

  const groupByRound = (entries) => {
    const groups = {}
    for (const entry of entries) {
      const round = entry.round_number || 0
      if (!groups[round]) groups[round] = []
      groups[round].push(entry)
    }
    return Object.entries(groups).sort((a, b) => Number(a[0]) - Number(b[0]))
  }

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100 mb-1">推理链路</h1>
        <p className="text-sm text-slate-500">查看 Agent 的完整思考与执行过程</p>
      </div>

      {/* 查询 */}
      <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 mb-6">
        <div className="flex gap-2">
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
            placeholder="输入会话 ID，例如: sess_abc123"
            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-200 font-mono focus:outline-none focus:border-primary-500/50"
          />
          <button
            onClick={handleQuery}
            disabled={loading}
            className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-slate-700 rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            查询
          </button>
        </div>
      </div>

      {/* 错误 */}
      {error && (
        <div className="mb-6 flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-800/30 rounded-xl text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* 摘要 */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-slate-200">{summary.total_rounds || 0}</div>
            <div className="text-xs text-slate-500">总轮数</div>
          </div>
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-primary-400">{summary.total_entries || 0}</div>
            <div className="text-xs text-slate-500">总条目</div>
          </div>
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-orange-400">{summary.tool_call_count || 0}</div>
            <div className="text-xs text-slate-500">工具调用</div>
          </div>
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-emerald-400">{summary.duration_seconds || 0}s</div>
            <div className="text-xs text-slate-500">总耗时</div>
          </div>
        </div>
      )}

      {/* 链路详情 */}
      {chain && (
        <div className="space-y-6">
          {groupByRound(chain.chain).map(([round, entries]) => (
            <div key={round} className="bg-slate-800/30 border border-slate-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-slate-900/50 border-b border-slate-800 flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-primary-400" />
                <span className="font-medium text-slate-200">推理轮次 #{round}</span>
                <span className="text-xs text-slate-500 ml-2">{entries.length} 个阶段</span>
              </div>

              <div className="p-4 space-y-3">
                {entries.map((entry, idx) => {
                  const phase = PHASE_CONFIG[entry.phase] || {
                    label: entry.phase,
                    icon: Clock,
                    color: 'text-slate-400',
                    bg: 'bg-slate-800 border-slate-700',
                  }
                  const Icon = phase.icon
                  return (
                    <div key={idx} className={`rounded-lg border p-3 ${phase.bg}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <Icon className={`w-4 h-4 ${phase.color}`} />
                        <span className={`text-sm font-medium ${phase.color}`}>{phase.label}</span>
                        <span className="text-xs text-slate-500 ml-auto">{formatTime(entry.timestamp)}</span>
                      </div>
                      <div className="text-sm text-slate-300 whitespace-pre-wrap font-mono text-xs bg-slate-950/50 rounded-lg p-3">
                        {entry.content}
                      </div>
                      {entry.tool_name && (
                        <div className="mt-2 flex items-center gap-2">
                          <span className="text-xs text-slate-500">工具:</span>
                          <span className="text-xs bg-slate-900 px-2 py-0.5 rounded text-primary-300 font-mono">{entry.tool_name}</span>
                        </div>
                      )}
                      {entry.tool_arguments && (
                        <div className="mt-1">
                          <span className="text-xs text-slate-500">参数:</span>
                          <code className="ml-2 text-xs text-slate-400 font-mono">{JSON.stringify(entry.tool_arguments)}</code>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {!chain && !loading && !error && (
        <div className="text-center py-16 text-slate-600">
          <GitBranch className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm">输入会话 ID 查看推理链路</p>
        </div>
      )}
    </div>
  )
}
