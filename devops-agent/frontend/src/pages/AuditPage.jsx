import { useState, useEffect } from 'react'
import { ClipboardList, Loader2, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react'
import { queryAudit, auditStats } from '../api/client'

const STATUS_STYLES = {
  SUCCESS: 'bg-emerald-900/30 text-emerald-400 border-emerald-800/30',
  FAILED: 'bg-red-900/30 text-red-400 border-red-800/30',
  TIMEOUT: 'bg-amber-900/30 text-amber-400 border-amber-800/30',
  REJECTED: 'bg-orange-900/30 text-orange-400 border-orange-800/30',
  BLOCKED: 'bg-red-900/50 text-red-300 border-red-700/50',
}

export default function AuditPage() {
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    loadAudit()
    loadStats()
  }, [page, statusFilter])

  const loadAudit = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: pageSize }
      if (statusFilter) params.status = statusFilter
      const res = await queryAudit(params)
      if (res.code === 0) {
        setLogs(res.data.items || [])
        setTotal(res.data.total || 0)
        setTotalPages(res.data.total_pages || 0)
      } else {
        setError(res.message)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const res = await auditStats()
      if (res.code === 0) {
        setStats(res.data)
      }
    } catch (e) {
      console.error('加载统计失败:', e)
    }
  }

  const formatTime = (iso) => {
    if (!iso) return '-'
    const d = new Date(iso)
    return d.toLocaleString('zh-CN')
  }

  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100 mb-1">审计日志</h1>
        <p className="text-sm text-slate-500">所有命令执行的可追溯记录</p>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          {[
            { label: '总记录', value: stats.total_count || 0, color: 'text-slate-200' },
            { label: '成功', value: stats.success_count || 0, color: 'text-emerald-400' },
            { label: '失败', value: stats.failed_count || 0, color: 'text-red-400' },
            { label: '拦截', value: stats.blocked_count || 0, color: 'text-orange-400' },
            { label: '平均耗时', value: `${(stats.avg_duration_ms || 0).toFixed(0)}ms`, color: 'text-primary-400' },
          ].map(item => (
            <div key={item.label} className="bg-slate-800/50 border border-slate-800 rounded-xl p-4">
              <div className="text-xs text-slate-500 mb-1">{item.label}</div>
              <div className={`text-xl font-bold ${item.color}`}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 过滤器 */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
        >
          <option value="">全部状态</option>
          <option value="SUCCESS">成功</option>
          <option value="FAILED">失败</option>
          <option value="TIMEOUT">超时</option>
          <option value="REJECTED">拒绝</option>
          <option value="BLOCKED">拦截</option>
        </select>
        <button
          onClick={loadAudit}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm text-slate-300 transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ClipboardList className="w-4 h-4" />}
          刷新
        </button>
      </div>

      {/* 错误 */}
      {error && (
        <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-800/30 rounded-xl text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* 表格 */}
      <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3">ID</th>
                <th className="text-left px-4 py-3">时间</th>
                <th className="text-left px-4 py-3">命令</th>
                <th className="text-left px-4 py-3">状态</th>
                <th className="text-right px-4 py-3">耗时</th>
                <th className="text-left px-4 py-3">安全结果</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {logs.map(log => (
                <tr key={log.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">#{log.id}</td>
                  <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{formatTime(log.timestamp)}</td>
                  <td className="px-4 py-3">
                    <code className="text-xs text-slate-300 bg-slate-900 px-2 py-1 rounded font-mono">{log.command}</code>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border ${STATUS_STYLES[log.status] || 'bg-slate-800 text-slate-400 border-slate-700'}`}>
                      {log.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-slate-400">{log.execution_time_ms}ms</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{log.security_result || '-'}</td>
                </tr>
              ))}
              {logs.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-600">
                    暂无审计记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <div className="text-sm text-slate-500">
            共 {total} 条 · 第 {page}/{totalPages} 页
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 rounded-lg transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 rounded-lg transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
