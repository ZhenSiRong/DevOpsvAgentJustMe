import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Network,
  Loader2,
  AlertCircle,
  Play,
  RotateCcw,
  Clock,
  CheckCircle2,
  XCircle,
  ChevronRight,
  ChevronDown,
  Layers,
  Zap,
  ShieldAlert,
  Terminal,
  Trash2,
  RefreshCw,
} from 'lucide-react'
import {
  parseDAG,
  runDAG,
  listDAGRuns,
  getDAGRun,
  confirmDAGRollback,
  checkDAGApplicability,
} from '../api/client'

// ============================================================
//  状态颜色映射
// ============================================================
const STATUS_CONFIG = {
  pending: { label: '待执行', color: 'text-slate-400', bg: 'bg-slate-800/50', border: 'border-slate-700' },
  running: { label: '执行中', color: 'text-primary-400', bg: 'bg-primary-900/20', border: 'border-primary-800/30' },
  success: { label: '成功', color: 'text-emerald-400', bg: 'bg-emerald-900/20', border: 'border-emerald-800/30' },
  failed: { label: '失败', color: 'text-red-400', bg: 'bg-red-900/20', border: 'border-red-800/30' },
  timeout: { label: '超时', color: 'text-amber-400', bg: 'bg-amber-900/20', border: 'border-amber-800/30' },
  rejected: { label: '已拒绝', color: 'text-orange-400', bg: 'bg-orange-900/20', border: 'border-orange-800/30' },
  skipped: { label: '已跳过', color: 'text-slate-500', bg: 'bg-slate-800/30', border: 'border-slate-700/50' },
  rollback_done: { label: '已回滚', color: 'text-cyan-400', bg: 'bg-cyan-900/20', border: 'border-cyan-800/30' },
}

const RUN_STATUS_CONFIG = {
  pending: { label: '待执行', icon: Clock, color: 'text-slate-400' },
  running: { label: '执行中', icon: Loader2, color: 'text-primary-400' },
  completed: { label: '已完成', icon: CheckCircle2, color: 'text-emerald-400' },
  failed: { label: '失败', icon: XCircle, color: 'text-red-400' },
  partial: { label: '部分成功', icon: AlertCircle, color: 'text-amber-400' },
  rolling_back: { label: '回滚中', icon: RotateCcw, color: 'text-cyan-400' },
  rolled_back: { label: '已回滚', icon: CheckCircle2, color: 'text-cyan-400' },
}

const TOOL_TYPE_CONFIG = {
  read_only: { label: '只读', color: 'text-cyan-400', bg: 'bg-cyan-900/20' },
  write: { label: '写操作', color: 'text-amber-400', bg: 'bg-amber-900/20' },
  unknown: { label: '未知', color: 'text-slate-500', bg: 'bg-slate-800/30' },
}

// ============================================================
//  DAG 拓扑图 SVG 渲染
// ============================================================
function DAGGraph({ layers, nodeStatusMap, onNodeClick }) {
  const svgRef = useRef(null)
  const [dimensions, setDimensions] = useState({ width: 600, height: 300 })

  useEffect(() => {
    if (svgRef.current) {
      const rect = svgRef.current.getBoundingClientRect()
      setDimensions({ width: rect.width, height: Math.max(300, layers.length * 120 + 60) })
    }
  }, [layers])

  if (!layers || layers.length === 0) return null

  const nodeWidth = 140
  const nodeHeight = 56
  const layerGapY = 100
  const nodeGapX = 20

  const nodes = []
  const edges = []
  const nodePositions = {}

  layers.forEach((layer, layerIdx) => {
    const layerWidth = layer.nodes.length * nodeWidth + (layer.nodes.length - 1) * nodeGapX
    const startX = (dimensions.width - layerWidth) / 2
    const y = layerIdx * layerGapY + 40

    layer.nodes.forEach((node, nodeIdx) => {
      const x = startX + nodeIdx * (nodeWidth + nodeGapX)
      nodePositions[node.id] = { x, y, layerIdx, nodeIdx }
      nodes.push({ ...node, x, y })

      // 收集边（从依赖指向当前节点）
      if (node.deps && node.deps.length > 0) {
        node.deps.forEach((depId) => {
          if (nodePositions[depId]) {
            edges.push({ from: depId, to: node.id })
          }
        })
      }
    })
  })

  // 补全跨层依赖边（正向遍历后反向补）
  layers.forEach((layer) => {
    layer.nodes.forEach((node) => {
      if (node.deps) {
        node.deps.forEach((depId) => {
          if (nodePositions[depId]) {
            const exists = edges.some((e) => e.from === depId && e.to === node.id)
            if (!exists) edges.push({ from: depId, to: node.id })
          }
        })
      }
    })
  })

  const getNodeFill = (node) => {
    const status = nodeStatusMap?.[node.id] || node.status || 'pending'
    const map = STATUS_CONFIG[status] || STATUS_CONFIG.pending
    return map.bg.replace('bg-', 'fill-').replace('/20', '').replace('/50', '')
  }

  const getNodeStroke = (node) => {
    const status = nodeStatusMap?.[node.id] || node.status || 'pending'
    const map = STATUS_CONFIG[status] || STATUS_CONFIG.pending
    // 从 border class 提取颜色
    const colorMap = {
      'border-slate-700': '#334155',
      'border-primary-800/30': 'rgba(99,102,241,0.3)',
      'border-emerald-800/30': 'rgba(16,185,129,0.3)',
      'border-red-800/30': 'rgba(239,68,68,0.3)',
      'border-amber-800/30': 'rgba(245,158,11,0.3)',
      'border-orange-800/30': 'rgba(249,115,22,0.3)',
      'border-cyan-800/30': 'rgba(6,182,212,0.3)',
    }
    return colorMap[map.border] || '#334155'
  }

  const getStatusDot = (node) => {
    const status = nodeStatusMap?.[node.id] || node.status || 'pending'
    const colorMap = {
      pending: '#94a3b8',
      running: '#818cf8',
      success: '#34d399',
      failed: '#f87171',
      timeout: '#fbbf24',
      rejected: '#fb923c',
      skipped: '#64748b',
      rollback_done: '#22d3ee',
    }
    return colorMap[status] || '#94a3b8'
  }

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={dimensions.height}
      viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
      className="select-none"
    >
      <defs>
        <marker id="dagArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M2 1L8 5L2 9" fill="none" stroke="#475569" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>

      {/* 边 */}
      {edges.map((edge, idx) => {
        const from = nodePositions[edge.from]
        const to = nodePositions[edge.to]
        if (!from || !to) return null
        const x1 = from.x + nodeWidth / 2
        const y1 = from.y + nodeHeight
        const x2 = to.x + nodeWidth / 2
        const y2 = to.y
        return (
          <line
            key={idx}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="#475569"
            strokeWidth="1"
            strokeDasharray="4 2"
            markerEnd="url(#dagArrow)"
          />
        )
      })}

      {/* 节点 */}
      {nodes.map((node) => {
        const pos = nodePositions[node.id]
        const toolType = TOOL_TYPE_CONFIG[node.tool_type] || TOOL_TYPE_CONFIG.unknown
        const statusColor = getStatusDot(node)
        return (
          <g
            key={node.id}
            transform={`translate(${pos.x}, ${pos.y})`}
            onClick={() => onNodeClick?.(node)}
            className="cursor-pointer"
          >
            <rect
              width={nodeWidth}
              height={nodeHeight}
              rx="8"
              fill={getNodeFill(node)}
              stroke={getNodeStroke(node)}
              strokeWidth="1"
            />
            {/* 状态指示点 */}
            <circle cx="12" cy="12" r="4" fill={statusColor} />
            {/* 工具类型标签 */}
            <rect x="22" y="6" width="36" height="14" rx="3" fill={toolType.bg.replace('bg-', 'fill-').replace('/20', '')} opacity="0.5" />
            <text x="40" y="16" textAnchor="middle" fill={toolType.color.replace('text-', '')} fontSize="8" fontWeight="500">
              {toolType.label}
            </text>
            {/* 工具名称 */}
            <text x={nodeWidth / 2} y="38" textAnchor="middle" fill="#e2e8f0" fontSize="11" fontWeight="500">
              {node.tool_name}
            </text>
            {/* 节点 ID */}
            <text x={nodeWidth / 2} y="50" textAnchor="middle" fill="#64748b" fontSize="8" fontFamily="monospace">
              {node.id.slice(0, 12)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ============================================================
//  主页面
// ============================================================
export default function OrchestratorPage() {
  const [activeTab, setActiveTab] = useState('parse') // parse | history
  const [toolCallsInput, setToolCallsInput] = useState('')
  const [parsedGraph, setParsedGraph] = useState(null)
  const [runResult, setRunResult] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [nodeStatusMap, setNodeStatusMap] = useState({})
  const [rollbackConfirming, setRollbackConfirming] = useState(false)
  const [rollbackResult, setRollbackResult] = useState(null)

  // 加载历史记录
  const loadRuns = useCallback(async () => {
    try {
      const res = await listDAGRuns()
      if (res.code === 0) {
        setRuns(res.data || [])
      }
    } catch (e) {
      console.error('加载执行历史失败:', e)
    }
  }, [])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  // 解析 DAG
  const handleParse = async () => {
    let toolCalls
    try {
      toolCalls = JSON.parse(toolCallsInput)
      if (!Array.isArray(toolCalls)) throw new Error('tool_calls 必须是数组')
    } catch (e) {
      setError('JSON 格式错误: ' + e.message)
      return
    }
    setLoading(true)
    setError(null)
    setParsedGraph(null)
    setRunResult(null)
    try {
      const res = await parseDAG(toolCalls)
      if (res.code === 0) {
        setParsedGraph(res.data)
        // 初始化节点状态
        const statusMap = {}
        res.data.layers?.forEach((layer) => {
          layer.nodes?.forEach((n) => {
            statusMap[n.id] = n.status || 'pending'
          })
        })
        setNodeStatusMap(statusMap)
      } else {
        setError(res.message)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // 执行 DAG
  const handleRun = async () => {
    let toolCalls
    try {
      toolCalls = JSON.parse(toolCallsInput)
      if (!Array.isArray(toolCalls)) throw new Error('tool_calls 必须是数组')
    } catch (e) {
      setError('JSON 格式错误: ' + e.message)
      return
    }
    setLoading(true)
    setError(null)
    setRunResult(null)
    try {
      const res = await runDAG(toolCalls)
      if (res.code === 0) {
        setRunResult(res.data)
        // 更新节点状态
        const statusMap = {}
        res.data.graph_summary?.layers?.forEach((layer) => {
          layer.nodes?.forEach((n) => {
            statusMap[n.id] = n.status || 'pending'
          })
        })
        setNodeStatusMap(statusMap)
        await loadRuns()
      } else {
        setError(res.message)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // 查看执行详情
  const handleViewRun = async (runId) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDAGRun(runId)
      if (res.code === 0) {
        setSelectedRun(res.data)
        setActiveTab('detail')
        const statusMap = {}
        res.data.graph_summary?.layers?.forEach((layer) => {
          layer.nodes?.forEach((n) => {
            statusMap[n.id] = n.status || 'pending'
          })
        })
        setNodeStatusMap(statusMap)
      } else {
        setError(res.message)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // 回滚
  const handleRollback = async (runId) => {
    setRollbackConfirming(true)
    setRollbackResult(null)
    try {
      const res = await confirmDAGRollback(runId, false)
      if (res.code === 0) {
        setRollbackResult({ ...res.data, runId, stage: 'confirm' })
      } else {
        setError(res.message)
        setRollbackConfirming(false)
      }
    } catch (e) {
      setError(e.message)
      setRollbackConfirming(false)
    }
  }

  const handleConfirmRollback = async () => {
    if (!rollbackResult?.runId) return
    try {
      const res = await confirmDAGRollback(rollbackResult.runId, true)
      if (res.code === 0) {
        setRollbackResult({ ...res.data, stage: 'done' })
        await loadRuns()
      } else {
        setError(res.message)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setRollbackConfirming(false)
    }
  }

  const formatTime = (iso) => {
    if (!iso) return '-'
    const d = new Date(iso)
    return d.toLocaleString('zh-CN')
  }

  const formatDuration = (ms) => {
    if (!ms) return '-'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  // 示例 tool_calls
  const exampleToolCalls = `[
  {"name": "execute_command", "arguments": {"command": "ps aux --sort=-%cpu | head -10"}},
  {"name": "execute_command", "arguments": {"command": "df -h /var/log"}},
  {"name": "execute_command", "arguments": {"command": "systemctl status nginx"}}
]`

  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto">
      {/* 页面标题 */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Network className="w-6 h-6 text-primary-400" />
          <h1 className="text-2xl font-bold text-slate-100">任务编排引擎</h1>
        </div>
        <p className="text-sm text-slate-500">DAG 并行调度 — 规则驱动的工具调用编排与可视化</p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 mb-6 bg-slate-900/50 border border-slate-800 rounded-xl p-1 w-fit">
        {[
          { key: 'parse', label: '解析与执行', icon: Zap },
          { key: 'history', label: '执行历史', icon: Clock },
        ].map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-primary-900/30 text-primary-300 border border-primary-800/50'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-800/30 rounded-xl text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">×</button>
        </div>
      )}

      {/* ====== 解析与执行 Tab ====== */}
      {activeTab === 'parse' && (
        <div className="space-y-6">
          {/* 输入区域 */}
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-medium text-slate-300">Tool Calls JSON</label>
              <button
                onClick={() => setToolCallsInput(exampleToolCalls)}
                className="text-xs text-primary-400 hover:text-primary-300"
              >
                填入示例
              </button>
            </div>
            <textarea
              value={toolCallsInput}
              onChange={(e) => setToolCallsInput(e.target.value)}
              placeholder='[{"name": "execute_command", "arguments": {"command": "ps aux"}}]'
              className="w-full h-40 bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm text-slate-200 font-mono focus:outline-none focus:border-primary-500/50 resize-y"
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleParse}
                disabled={loading || !toolCallsInput.trim()}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium text-slate-200 transition-colors flex items-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />}
                解析 DAG
              </button>
              <button
                onClick={handleRun}
                disabled={loading || !toolCallsInput.trim()}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                解析并执行
              </button>
            </div>
          </div>

          {/* 解析结果 — DAG 拓扑图 */}
          {parsedGraph && (
            <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Network className="w-4 h-4 text-primary-400" />
                  <span className="font-medium text-slate-200">DAG 拓扑结构</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span>{parsedGraph.node_count} 节点</span>
                  <span>{parsedGraph.total_layers} 层</span>
                  {parsedGraph.has_parallel && (
                    <span className="text-cyan-400 flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      可并行
                    </span>
                  )}
                </div>
              </div>
              <div className="p-4 overflow-x-auto">
                <DAGGraph
                  layers={parsedGraph.layers}
                  nodeStatusMap={nodeStatusMap}
                  onNodeClick={(node) => console.log('Node clicked:', node)}
                />
              </div>

              {/* 层级详情 */}
              <div className="px-4 pb-4">
                {parsedGraph.layers?.map((layer) => (
                  <div key={layer.layer_idx} className="mb-3 last:mb-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-medium text-slate-400">层 {layer.layer_idx}</span>
                      <span className="text-xs text-slate-600">({layer.node_count} 节点)</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {layer.nodes?.map((node) => {
                        const status = nodeStatusMap[node.id] || node.status || 'pending'
                        const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending
                        const toolType = TOOL_TYPE_CONFIG[node.tool_type] || TOOL_TYPE_CONFIG.unknown
                        return (
                          <div
                            key={node.id}
                            className={`px-3 py-1.5 rounded-lg border text-xs ${statusCfg.bg} ${statusCfg.border}`}
                          >
                            <div className="flex items-center gap-1.5">
                              <span className={`w-2 h-2 rounded-full ${statusCfg.color.replace('text-', 'bg-')}`} />
                              <span className={`font-medium ${statusCfg.color}`}>{node.tool_name}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] ${toolType.bg} ${toolType.color}`}>
                                {toolType.label}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono mt-0.5">{node.id}</div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 执行结果 */}
          {runResult && (
            <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Play className="w-4 h-4 text-primary-400" />
                  <span className="font-medium text-slate-200">执行结果</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {(() => {
                    const cfg = RUN_STATUS_CONFIG[runResult.status] || RUN_STATUS_CONFIG.pending
                    const Icon = cfg.icon
                    return (
                      <span className={`flex items-center gap-1 ${cfg.color}`}>
                        <Icon className="w-3.5 h-3.5" />
                        {cfg.label}
                      </span>
                    )
                  })()}
                  <span className="text-slate-500">{formatDuration(runResult.total_execution_ms)}</span>
                </div>
              </div>
              <div className="p-4 space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-slate-200">{runResult.total_nodes}</div>
                    <div className="text-[10px] text-slate-500">总节点</div>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-emerald-400">{runResult.success_count}</div>
                    <div className="text-[10px] text-slate-500">成功</div>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-red-400">{runResult.failed_count}</div>
                    <div className="text-[10px] text-slate-500">失败</div>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-primary-400">{formatDuration(runResult.total_execution_ms)}</div>
                    <div className="text-[10px] text-slate-500">耗时</div>
                  </div>
                </div>

                {/* 回滚区域 */}
                {runResult.rollback_available && runResult.rollback_commands?.length > 0 && (
                  <div className="bg-amber-900/10 border border-amber-800/20 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <ShieldAlert className="w-4 h-4 text-amber-400" />
                      <span className="text-sm font-medium text-amber-300">回滚计划</span>
                    </div>
                    <div className="space-y-1">
                      {runResult.rollback_commands.map((cmd, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs">
                          <span className="text-slate-500 font-mono">{cmd.task_id?.slice(0, 12)}</span>
                          <code className="flex-1 bg-slate-950/50 px-2 py-1 rounded text-slate-300 font-mono">{cmd.rollback_cmd}</code>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => handleRollback(runResult.run_id)}
                      disabled={rollbackConfirming}
                      className="mt-2 px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:bg-slate-700 rounded text-xs font-medium text-white transition-colors flex items-center gap-1.5"
                    >
                      {rollbackConfirming ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                      确认回滚
                    </button>
                  </div>
                )}

                {/* 回滚确认结果 */}
                {rollbackResult?.stage === 'confirm' && (
                  <div className="bg-cyan-900/10 border border-cyan-800/20 rounded-lg p-3">
                    <p className="text-sm text-cyan-300 mb-2">{rollbackResult.message}</p>
                    <div className="flex gap-2">
                      <button
                        onClick={handleConfirmRollback}
                        className="px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 rounded text-xs font-medium text-white transition-colors"
                      >
                        确认执行
                      </button>
                      <button
                        onClick={() => setRollbackResult(null)}
                        className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs font-medium text-slate-200 transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
                {rollbackResult?.stage === 'done' && (
                  <div className="bg-emerald-900/10 border border-emerald-800/20 rounded-lg p-3">
                    <p className="text-sm text-emerald-300">{rollbackResult.message}</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ====== 执行历史 Tab ====== */}
      {activeTab === 'history' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">共 {runs.length} 条记录</span>
            <button
              onClick={loadRuns}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs text-slate-300 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新
            </button>
          </div>

          {runs.length === 0 ? (
            <div className="text-center py-16 text-slate-600">
              <Clock className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="text-sm">暂无 DAG 执行记录</p>
            </div>
          ) : (
            <div className="space-y-3">
              {runs.map((run) => {
                const cfg = RUN_STATUS_CONFIG[run.status] || RUN_STATUS_CONFIG.pending
                const Icon = cfg.icon
                return (
                  <div
                    key={run.run_id}
                    className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors cursor-pointer"
                    onClick={() => handleViewRun(run.run_id)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Icon className={`w-5 h-5 ${cfg.color}`} />
                        <div>
                          <div className="text-sm font-medium text-slate-200 font-mono">{run.run_id}</div>
                          <div className="text-xs text-slate-500">{run.session_id || '无会话'}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          {run.success_count}/{run.total_nodes}
                        </span>
                        <span>{formatDuration(run.total_execution_ms)}</span>
                        <ChevronRight className="w-4 h-4 text-slate-600" />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ====== 执行详情 Tab（从历史点击进入） ====== */}
      {activeTab === 'detail' && selectedRun && (
        <div className="space-y-6">
          <button
            onClick={() => setActiveTab('history')}
            className="flex items-center gap-1 text-sm text-primary-400 hover:text-primary-300"
          >
            <ChevronRight className="w-4 h-4 rotate-180" />
            返回历史
          </button>

          <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-primary-400" />
                <span className="font-medium text-slate-200">执行详情</span>
              </div>
              {(() => {
                const cfg = RUN_STATUS_CONFIG[selectedRun.status] || RUN_STATUS_CONFIG.pending
                const Icon = cfg.icon
                return (
                  <span className={`flex items-center gap-1 text-xs ${cfg.color}`}>
                    <Icon className="w-3.5 h-3.5" />
                    {cfg.label}
                  </span>
                )
              })()}
            </div>
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-slate-200">{selectedRun.total_nodes}</div>
                  <div className="text-[10px] text-slate-500">总节点</div>
                </div>
                <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-emerald-400">{selectedRun.success_count}</div>
                  <div className="text-[10px] text-slate-500">成功</div>
                </div>
                <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-red-400">{selectedRun.failed_count}</div>
                  <div className="text-[10px] text-slate-500">失败</div>
                </div>
                <div className="bg-slate-900/50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-primary-400">{formatDuration(selectedRun.total_execution_ms)}</div>
                  <div className="text-[10px] text-slate-500">耗时</div>
                </div>
              </div>

              {/* DAG 图 */}
              {selectedRun.graph_summary && (
                <div>
                  <h3 className="text-sm font-medium text-slate-300 mb-3">执行拓扑图</h3>
                  <div className="overflow-x-auto bg-slate-950/30 rounded-lg p-4">
                    <DAGGraph
                      layers={selectedRun.graph_summary.layers}
                      nodeStatusMap={nodeStatusMap}
                    />
                  </div>
                </div>
              )}

              {/* 回滚 */}
              {selectedRun.rollback_available && selectedRun.rollback_commands?.length > 0 && (
                <div className="bg-amber-900/10 border border-amber-800/20 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldAlert className="w-4 h-4 text-amber-400" />
                    <span className="text-sm font-medium text-amber-300">回滚计划</span>
                  </div>
                  <div className="space-y-1">
                    {selectedRun.rollback_commands.map((cmd, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs">
                        <span className="text-slate-500 font-mono">{cmd.task_id?.slice(0, 12)}</span>
                        <code className="flex-1 bg-slate-950/50 px-2 py-1 rounded text-slate-300 font-mono">{cmd.rollback_cmd}</code>
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={() => handleRollback(selectedRun.run_id)}
                    disabled={rollbackConfirming}
                    className="mt-2 px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:bg-slate-700 rounded text-xs font-medium text-white transition-colors flex items-center gap-1.5"
                  >
                    {rollbackConfirming ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                    确认回滚
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
