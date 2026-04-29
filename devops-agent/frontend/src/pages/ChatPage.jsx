import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  Send, Loader2, Bot, User, Sparkles, Terminal, AlertTriangle, MessageSquare,
  ChevronDown, ChevronRight, ChevronLeft, PanelRightOpen, PanelRightClose,
  PanelLeftOpen, PanelLeftClose, Network,
  Play, Eye, Brain, ListTodo, Wrench, FileText, CheckCircle2,
  X, Clock, Zap, Layers, RefreshCw, GitCompareArrows, ArrowRightLeft, Copy,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamChatFetch, sendChat, listSessions, getSession, deleteSession, retryMessage } from '../api/client'
import TerminalPanel from '../components/TerminalPanel'
import QuickCommandBar from '../components/QuickCommandBar'
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'

const EVENT_LABELS = {
  start: '开始处理',
  sense: '环境感知',
  analyze: '分析推理',
  plan: '制定方案',
  execute: '执行工具',
  execute_done: '工具完成',
  output: '生成回复',
  done: '完成',
  error: '错误',
  dag_start: 'DAG 开始',
  dag_layer_start: 'DAG 层执行',
  dag_node_start: 'DAG 节点开始',
  dag_node_done: 'DAG 节点完成',
  dag_done: 'DAG 完成',
}

const EVENT_COLORS = {
  start: 'text-slate-400',
  sense: 'text-cyan-400',
  analyze: 'text-amber-400',
  plan: 'text-violet-400',
  execute: 'text-orange-400',
  execute_done: 'text-emerald-400',
  output: 'text-primary-400',
  done: 'text-emerald-400',
  error: 'text-red-400',
  dag_start: 'text-primary-400',
  dag_layer_start: 'text-cyan-400',
  dag_node_start: 'text-orange-400',
  dag_node_done: 'text-emerald-400',
  dag_done: 'text-emerald-400',
}

// ============================================================
//  阶段配置 — 用于流程图式推理链路分组
// ============================================================
const PHASE_CONFIG = {
  startup: {
    key: 'startup',
    label: '启动',
    icon: Play,
    color: '#94a3b8',
    bgClass: 'bg-slate-800/30',
    borderClass: 'border-slate-700/50',
    textClass: 'text-slate-400',
    events: ['start'],
  },
  sense: {
    key: 'sense',
    label: '环境感知',
    icon: Eye,
    color: '#22d3ee',
    bgClass: 'bg-cyan-900/15',
    borderClass: 'border-cyan-800/30',
    textClass: 'text-cyan-400',
    events: ['sense'],
  },
  reasoning: {
    key: 'reasoning',
    label: '分析推理',
    icon: Brain,
    color: '#fbbf24',
    bgClass: 'bg-amber-900/15',
    borderClass: 'border-amber-800/30',
    textClass: 'text-amber-400',
    events: ['analyze'],
  },
  planning: {
    key: 'planning',
    label: '制定方案',
    icon: ListTodo,
    color: '#a78bfa',
    bgClass: 'bg-violet-900/15',
    borderClass: 'border-violet-800/30',
    textClass: 'text-violet-400',
    events: ['plan'],
  },
  execution: {
    key: 'execution',
    label: '执行工具',
    icon: Wrench,
    color: '#fb923c',
    bgClass: 'bg-orange-900/15',
    borderClass: 'border-orange-800/30',
    textClass: 'text-orange-400',
    events: ['execute', 'execute_done', 'dag_start', 'dag_layer_start', 'dag_node_start', 'dag_node_done', 'dag_done'],
  },
  output: {
    key: 'output',
    label: '生成回复',
    icon: FileText,
    color: '#60a5fa',
    bgClass: 'bg-primary-900/15',
    borderClass: 'border-primary-800/30',
    textClass: 'text-primary-400',
    events: ['output', 'done', 'error'],
  },
}

const PHASE_ORDER = ['startup', 'sense', 'reasoning', 'planning', 'execution', 'output']

/** 根据事件类型获取所属阶段 */
function getPhaseKey(eventType) {
  for (const [key, phase] of Object.entries(PHASE_CONFIG)) {
    if (phase.events.includes(eventType)) return key
  }
  return 'execution' // 兜底
}

/** 格式化耗时 */
function formatDurationMs(ms) {
  if (!ms || ms < 0) return null
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// ============================================================
//  推理链路 — 流程图式可视化组件
// ============================================================

function ReasoningFlowViewer({ events }) {
  const [expandedPhases, setExpandedPhases] = useState(() => new Set(PHASE_ORDER))
  const [selectedNode, setSelectedNode] = useState(null)
  const [viewMode, setViewMode] = useState('flow') // flow | list

  if (!events || events.length === 0) return null

  // 按阶段分组 + execute/done 配对
  const grouped = useMemo(() => {
    const groups = {}
    PHASE_ORDER.forEach(k => { groups[k] = [] })

    const pairedEvents = []
    const pendingExecutes = new Map() // tool_name → event

    for (let i = 0; i < events.length; i++) {
      const evt = events[i]
      const type = evt.type

      if (type === 'execute') {
        pendingExecutes.set(evt.payload?.tool_name || `exec_${i}`, { ...evt, index: i })
      } else if (type === 'execute_done') {
        const toolName = evt.payload?.tool_name
        const execEvt = pendingExecutes.get(toolName) || pendingExecutes.get(`exec_${i - 1}`)
        if (execEvt) {
          pairedEvents.push({
            ...execEvt,
            doneEvent: evt,
            duration: evt.time - execEvt.time,
            status: 'success',
          })
          pendingExecutes.delete(toolName)
          pendingExecutes.delete(`exec_${i - 1}`)
        } else {
          pairedEvents.push({ ...evt, index: i })
        }
      } else {
        // DAG 事件：尝试配对 node_start ↔ node_done
        if (type === 'dag_node_start') {
          const nodeId = evt.payload?.node_id || evt.payload?.task_id || `node_${i}`
          pendingExecutes.set(`dag_${nodeId}`, { ...evt, index: i, isDAG: true })
        } else if (type === 'dag_node_done') {
          const nodeId = evt.payload?.node_id || evt.payload?.task_id
          const dagStart = pendingExecutes.get(`dag_${nodeId}`) || pendingExecutes.get(`dag_node_${i - 1}`)
          if (dagStart) {
            pairedEvents.push({
              ...dagStart,
              doneEvent: evt,
              duration: evt.time - dagStart.time,
              isDAG: true,
              status: evt.payload?.status || 'success',
            })
            pendingExecutes.delete(`dag_${nodeId}`)
            pendingExecues.delete(`dag_node_${i - 1}`)
          } else {
            pairedEvents.push({ ...evt, index: i, isDAG: true })
          }
        } else {
          // 其他事件直接加入（dag_start, dag_layer_start, dag_done 等）
          pairedEvents.push({ ...evt, index: i, isDAG: type.startsWith('dag_') && type !== 'dag_node_start' && type !== 'dag_node_done' })
        }
      }
    }

    // 将未配对的 execute 也加入
    pendingExecutes.forEach((v) => { pairedEvents.push(v) })

    for (const pe of pairedEvents) {
      const phaseKey = getPhaseKey(pe.type)
      if (groups[phaseKey]) {
        groups[phaseKey].push(pe)
      } else {
        groups.execution.push(pe)
      }
    }

    return groups
  }, [events])

  const togglePhase = (key) => {
    setExpandedPhases(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const toggleExpandAll = () => {
    const allExpanded = expandedPhases.size === PHASE_ORDER.length
    setExpandedPhases(allExpanded ? new Set() : new Set(PHASE_ORDER))
  }

  // 计算总耗时
  const totalDuration = events.length >= 2
    ? events[events.length - 1].time - events[0].time
    : null

  return (
    <div className="mt-1.5 group">
      {/* 头部工具栏 */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={toggleExpandAll}
          className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer hover:text-slate-300 select-none transition-colors"
        >
          {expandedPhases.size === PHASE_ORDER.length ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
          <span className="font-medium">推理链路</span>
        </button>
        <span className="text-xs text-slate-600">({events.length} 事件)</span>
        {totalDuration !== null && (
          <span className="text-[10px] text-slate-600 font-mono ml-1">
            ⏱ {formatDurationMs(totalDuration)}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => setViewMode('flow')}
            className={`p-1 rounded transition-colors ${viewMode === 'flow' ? 'bg-primary-900/30 text-primary-400' : 'text-slate-600 hover:text-slate-400'}`}
            title="流程图视图"
          >
            <Layers className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`p-1 rounded transition-colors ${viewMode === 'list' ? 'bg-primary-900/30 text-primary-400' : 'text-slate-600 hover:text-slate-400'}`}
            title="列表视图"
          >
            <ListTodo className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 流程图视图 */}
      {viewMode === 'flow' ? (
        <FlowTimelineView
          grouped={grouped}
          expandedPhases={expandedPhases}
          onTogglePhase={togglePhase}
          onSelectNode={setSelectedNode}
        />
      ) : (
        <ListView events={events} onSelectNode={setSelectedNode} />
      )}

      {/* 节点详情侧滑面板 */}
      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  )
}

// ============================================================
//  流程图时间线子视图
// ============================================================

function FlowTimelineView({ grouped, expandedPhases, onTogglePhase, onSelectNode }) {
  const hasContent = PHASE_ORDER.some(k => grouped[k]?.length > 0)

  if (!hasContent) return null

  let prevHasNext = false

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden">
      <div className="relative pl-6 pr-3 py-2 space-y-0.5">
        {/* 左侧竖线 */}
        <div className="absolute left-[11px] top-2 bottom-2 w-[2px] bg-slate-700/50" />

        {PHASE_ORDER.map((phaseKey, idx) => {
          const phase = PHASE_CONFIG[phaseKey]
          const phaseEvents = grouped[phaseKey] || []
          if (phaseEvents.length === 0 && idx > 0) return null
          const isExpanded = expandedPhases.has(phaseKey)
          const hasNext = idx < PHASE_ORDER.length - 1 &&
            PHASE_ORDER.slice(idx + 1).some(k => (grouped[k] || []).length > 0)
          prevHasNext = hasNext
          const PhaseIcon = phase.icon

          return (
            <div key={phaseKey}>
              {/* 阶段标题 */}
              <button
                onClick={() => onTogglePhase(phaseKey)}
                className="relative flex items-center gap-2 w-full py-1.5 hover:bg-slate-800/30 rounded-r-lg transition-colors group/phase"
              >
                {/* 时间线节点 */}
                <div className="absolute -left-6 w-[22px] h-[22px] flex items-center justify-center">
                  <div
                    className="w-[10px] h-[10px] rounded-full ring-4 ring-slate-900"
                    style={{ backgroundColor: phase.color }}
                  />
                </div>
                {isExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-600" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                )}
                <PhaseIcon className="w-3.5 h-3.5" style={{ color: phase.color }} />
                <span className={`text-xs font-medium ${phase.textClass}`}>{phase.label}</span>
                <span className="text-[10px] text-slate-600">({phaseEvents.length})</span>
                {/* 阶段总耗时 */}
                {phaseEvents.length >= 2 && (
                  <span className="text-[10px] text-slate-600 font-mono ml-auto opacity-60">
                    {formatDurationMs(phaseEvents[phaseEvents.length - 1].time - phaseEvents[0].time)}
                  </span>
                )}
              </button>

              {/* 展开的事件列表 */}
              {isExpanded && phaseEvents.length > 0 && (
                <div className="ml-5 pl-3 border-l border-slate-800/50 space-y-1 py-1">
                  {phaseEvents.map((pevt, eIdx) => (
                    <PhaseNodeItem
                      key={`${pevt.type}-${pevt.index ?? eIdx}-${pevt.time}`}
                      event={pevt}
                      phaseColor={phase.color}
                      onClick={() => onSelectNode(pevt)}
                      isLast={eIdx === phaseEvents.length - 1 && !hasNext}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================
//  单个节点卡片（流程图中的事件行）
// ============================================================

function PhaseNodeItem({ event, phaseColor, onClick, isLast }) {
  const eventType = event.type
  const payload = event.payload || {}
  const isExecuteDone = eventType === 'execute_done'
  const isPaired = !!event.doneEvent
  const isDAGNode = event.isDAG && (eventType === 'dag_node_start' || (event.doneEvent && event.isDAG))

  // 获取显示标签
  const label = EVENT_LABELS[eventType] || eventType
  const toolName = payload.tool_name || ''

  // 状态颜色
  let statusDot = phaseColor
  if (isPaired || isExecuteDone) {
    statusDot = event.status === 'success' ? '#34d399' :
                 event.status === 'failed' ? '#f87171' : '#fbbf24'
  }

  // 耗时
  const dur = event.duration || null

  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer
        hover:bg-slate-800/60 border border-transparent hover:border-slate-700/50 transition-all group/node`}
    >
      {/* 状态点 */}
      <div
        className="w-2 h-2 rounded-full shrink-0 mt-0.5"
        style={{ backgroundColor: statusDot }}
      />

      {/* 事件信息 */}
      <div className="flex-1 min-w-0 flex items-center gap-1.5 flex-wrap">
        <span className="text-[11px] font-medium whitespace-nowrap">{label}</span>

        {toolName && (
          <>
            <span className="text-slate-600 text-[11px]">→</span>
            <code className="text-[11px] font-mono text-emerald-300/90 bg-emerald-900/20 px-1.5 py-0.5 rounded">{toolName}</code>
          </>
        )}

        {payload.reply_preview && (
          <span className="text-[10px] text-slate-500 truncate max-w-[180px]" title={payload.reply_preview}>
            {payload.reply_preview}
          </span>
        )}
        {payload.detail && !payload.reply_preview && (
          <span className="text-[10px] text-slate-500 truncate max-w-[180px]}" title={payload.detail}>
            {payload.detail}
          </span>
        )}

        {/* DAG 标签 */}
        {(payload.execution_mode === 'dag_parallel' || event.isDAG) && (
          <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded bg-primary-900/25 text-primary-400 border border-primary-800/20">
            <Zap className="w-2.5 h-2.5" />DAG
          </span>
        )}

        {/* 执行完成状态 */}
        {(isPaired || isExecuteDone) && !event.isDAG && (
          <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
        )}
      </div>

      {/* 耗时 */}
      {dur !== null && dur > 0 && (
        <span className="text-[10px] text-slate-600 font-mono shrink-0">
          {formatDurationMs(dur)}
        </span>
      )}

      {/* 展开 hint */}
      <ChevronRight className="w-3 h-3 text-slate-700 opacity-0 group-hover/node:opacity-100 shrink-0 transition-opacity" />
    </div>
  )
}

// ============================================================
//  列表视图（紧凑模式）
// ============================================================

function ListView({ events, onSelectNode }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg overflow-hidden">
      {events.map((evt, idx) => (
        <div
          key={evt.time + idx}
          onClick={() => onSelectNode(evt)}
          className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer hover:bg-slate-800/40 transition-colors border-b border-slate-800/30 last:border-b-0"
        >
          <span className={`font-medium shrink-0 ${EVENT_COLORS[evt.type] || 'text-slate-400'}`}>
            {EVENT_LABELS[evt.type] || evt.type}
          </span>
          {evt.payload?.tool_name && (
            <span className="text-slate-500 font-mono text-[11px]">{evt.payload.tool_name}</span>
          )}
          {evt.payload?.reply_preview && (
            <span className="text-slate-500 truncate max-w-[200px] text-[11px]">
              {evt.payload.reply_preview}
            </span>
          )}
          {evt.payload?.detail && (
            <span className="text-slate-500 truncate max-w-[200px] text-[11px]">
              {evt.payload.detail}
            </span>
          )}
          {evt.payload?.execution_mode === 'dag_parallel' && (
            <span className="flex items-center gap-1 text-primary-400">
              <Network className="w-3 h-3" />DAG
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

// ============================================================
//  节点详情侧滑面板
// ============================================================

function NodeDetailPanel({ node, onClose }) {
  const payload = node.payload || {}
  const donePayload = node.doneEvent?.payload || {}
  const eventType = node.type
  const phaseKey = getPhaseKey(eventType)
  const phase = PHASE_CONFIG[phaseKey]
  const PhaseIcon = phase?.icon || Zap
  const label = EVENT_LABELS[eventType] || eventType

  // 计算与上一个事件的间隔（如果有）
  const duration = node.duration || null

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* 侧面板 */}
      <div
        className="relative w-full max-w-md bg-slate-900 border-l border-slate-700 shadow-2xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 面板头部 */}
        <div className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${phase?.color || '#64748b'}20` }}>
              <PhaseIcon className="w-4 h-4" style={{ color: phase?.color || '#94a3b8' }} />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-200 truncate">{label}</div>
              <div className="text-[11px] text-slate-500">{phase?.label || ''}{payload.tool_name ? ` · ${payload.tool_name}` : ''}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 面板内容 */}
        <div className="p-4 space-y-4">
          {/* 元数据卡片 */}
          <div className="grid grid-cols-2 gap-2">
            <MetaCard label="事件类型" value={eventType} mono />
            {payload.tool_name && (
              <MetaCard label="工具名称" value={payload.tool_name} mono />
            )}
            {duration != null && duration >= 0 && (
              <MetaCard label="执行耗时" value={formatDurationMs(duration)} highlight />
            )}
            {payload.execution_mode && (
              <MetaCard label="执行模式" value={
                <span className="inline-flex items-center gap-1 text-primary-400">
                  <Zap className="w-3 h-3" />{payload.execution_mode}
                </span>
              } />
            )}
            {payload.layer_idx != null && (
              <MetaCard label="DAG 层级" value={`第 ${payload.layer_idx} 层`} mono />
            )}
            {node.isDAG && payload.node_id && (
              <MetaCard label="节点 ID" value={payload.node_id.slice(0, 16)} mono />
            )}
            {node.status && (
              <MetaCard label="状态" value={
                <span className={
                  node.status === 'success' ? 'text-emerald-400' :
                  node.status === 'failed' ? 'text-red-400' : 'text-amber-400'
                }>
                  {node.status === 'success' ? '✓ 成功' : node.status === 'failed' ? '✕ 失败' : node.status}
                </span>
              } />
            )}
          </div>

          {/* Payload 详情 */}
          {Object.keys(payload).length > 0 && (
            <div>
              <h4 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">请求 Payload</h4>
              <pre className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
                {JSON.stringify(payload, null, 2)}
              </pre>
            </div>
          )}

          {/* Done Event（如果配对成功） */}
          {node.doneEvent && Object.keys(donePayload).length > 0 && (
            <div>
              <h4 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                响应结果
                {donePayload.reply_preview && (
                  <span className="normal-case tracking-normal text-emerald-400/70 ml-2 font-normal">
                    ({donePayload.reply_preview})
                  </span>
                )}
              </h4>
              <pre className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
                {JSON.stringify(donePayload, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** 元数据小卡片 */
function MetaCard({ label, value, mono = false, highlight = false }) {
  return (
    <div className="bg-slate-800/50 border border-slate-800/50 rounded-lg p-2">
      <div className="text-[10px] text-slate-500 mb-0.5">{label}</div>
      <div className={`text-xs font-medium ${mono ? 'font-mono' : ''} ${
        highlight ? 'text-primary-300' : 'text-slate-200'
      }`}>
        {value}
      </div>
    </div>
  )
}

// ============================================================
//  回复重试 + 版本对比组件
// ============================================================

/**
 * DiffViewer — 左右分栏对比两个版本的回复
 * 简单的行级 diff 高亮（纯前端，无额外依赖）
 */
function DiffViewer({ original, revised, onClose }) {
  const originalLines = original ? original.split('\n') : ['(空)']
  const revisedLines = revised ? revised.split('\n') : ['(空)']

  // 简单逐行 diff 标记
  const diffResult = useMemo(() => {
    const origLines = [...originalLines]
    const revLines = [...revisedLines]
    const maxLen = Math.max(origLines.length, revLines.length)
    const result = []

    for (let i = 0; i < maxLen; i++) {
      const oLine = origLines[i]
      const rLine = revLines[i]
      if (i >= origLines.length) {
        result.push({ type: 'add', num: i + 1, original: null, revised: rLine })
      } else if (i >= revLines.length) {
        result.push({ type: 'remove', num: i + 1, original: oLine, revised: null })
      } else if (oLine === rLine) {
        result.push({ type: 'same', num: i + 1, original: oLine, revised: rLine })
      } else {
        result.push({ type: 'change', num: i + 1, original: oLine, revised: rLine })
      }
    }
    return result
  }, [originalLines, revisedLines])

  const copyToClipboard = (text) => {
    navigator.clipboard?.writeText(text || '')
  }

  return (
    <div className="mt-2 border border-slate-700/60 rounded-xl overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800/80 border-b border-slate-700/50">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
          <GitCompareArrows className="w-3.5 h-3.5 text-primary-400" />
          <span>版本对比</span>
          <span className="text-[10px] text-slate-500 font-normal">
            ({diffResult.filter(d => d.type !== 'same').length} 处差异)
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 对比区域：左右分栏 */}
      <div className="grid grid-cols-2 divide-x divide-slate-700/50">
        {/* 原版本（左侧） */}
        <div className="bg-slate-900/40">
          <div className="sticky top-0 px-3 py-1.5 bg-red-950/20 border-b border-slate-800/50 text-[11px] font-medium text-red-400 flex items-center gap-1">
            <span>原版本</span>
          </div>
          <div className="max-h-[360px] overflow-y-auto text-[11px] font-mono leading-relaxed">
            {diffResult.map((d, idx) => (
              <div
                key={idx}
                className={`flex px-3 py-0.5 ${
                  d.type === 'remove' ? 'bg-red-900/15 text-red-300' :
                  d.type === 'change' ? 'bg-amber-900/10 text-amber-200/80' :
                  'text-slate-500'
                }`}
              >
                <span className="w-6 shrink-0 text-right opacity-40 mr-2 select-none">{d.num}</span>
                <span className="break-all whitespace-pre-wrap min-w-0">
                  {d.original || <span className="text-slate-600 italic">(空)</span>}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 新版本（右侧） */}
        <div className="bg-slate-900/40">
          <div className="sticky top-0 px-3 py-1.5 bg-emerald-950/20 border-b border-slate-800/50 text-[11px] font-medium text-emerald-400 flex items-center gap-1">
            <span>新版本</span>
            <button
              onClick={() => copyToClipboard(revised)}
              className="ml-auto p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300"
              title="复制新版本"
            >
              <Copy className="w-3 h-3" />
            </button>
          </div>
          <div className="max-h-[360px] overflow-y-auto text-[11px] font-mono leading-relaxed">
            {diffResult.map((d, idx) => (
              <div
                key={idx}
                className={`flex px-3 py-0.5 ${
                  d.type === 'add' ? 'bg-emerald-900/15 text-emerald-300' :
                  d.type === 'change' ? 'bg-amber-900/10 text-amber-200/80' :
                  'text-slate-500'
                }`}
              >
                <span className="w-6 shrink-0 text-right opacity-40 mr-2 select-none">{d.num}</span>
                <span className="break-all whitespace-pre-wrap min-w-0">
                  {d.revised || <span className="text-slate-600 italic">(空)</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * MessageActions — 单条 assistant 消息的操作栏
 */
function MessageActions({ msgIndex, msg, onRetry, hasVersions, onCompare }) {
  return (
    <div className="flex items-center gap-1.5 mt-1 opacity-0 group-hover/msg:opacity-100 transition-opacity duration-200">
      {/* 重新生成按钮 */}
      <button
        onClick={(e) => { e.stopPropagation(); onRetry(msgIndex) }}
        disabled={msg._isRetrying}
        className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium
                     text-slate-400 hover:text-primary-300 hover:bg-primary-900/20
                     border border-transparent hover:border-primary-800/30
                     transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title="重新生成回复"
      >
        {msg._isRetrying ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <RefreshCw className="w-3 h-3" />
        )}
        <span>重新生成</span>
      </button>

      {/* 版本对比入口 */}
      {hasVersions && (
        <>
          <span className="text-slate-700">|</span>
          <button
            onClick={(e) => { e.stopPropagation(); onCompare(msg.id) }}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium
                     text-amber-400/70 hover:text-amber-300 hover:bg-amber-900/15
                     border border-amber-800/20 hover:border-amber-700/30
                     transition-colors"
            title="对比不同版本的回复"
          >
            <ArrowRightLeft className="w-3 h-3" />
            <span>对比版本</span>
          </button>
        </>
      )}
    </div>
  )
}

export default function ChatPage() {
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamEvents, setStreamEvents] = useState([])
  const [activeEvent, setActiveEvent] = useState(null)
  // ---- 回复重试相关 state ----
  const [messageVersions, setMessageVersions] = useState(() => new Map()) // msgId → [{content, reasoningEvents, timestamp}]
  const [comparingMsgId, setComparingMsgId] = useState(null) // 当前正在对比的消息 ID
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const terminalRef = useRef(null)
  const chatPanelRef = useRef(null)
  const terminalPanelRef = useRef(null)
  const [terminalOpen, setTerminalOpen] = useState(false)
  const [sessionPanelOpen, setSessionPanelOpen] = useState(true)
  const [chatPanelOpen, setChatPanelOpen] = useState(true)

  // 快捷命令发送到终端
  const handleRunQuickCommand = useCallback((cmd) => {
    terminalPanelRef.current?.expand()
    // 延迟执行，等面板展开后终端 ready
    setTimeout(() => {
      terminalRef.current?.runCommand(cmd)
    }, 150)
  }, [])

  // 加载会话列表
  useEffect(() => {
    loadSessions()
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamEvents])

  const loadSessions = async () => {
    try {
      const res = await listSessions(1, 50)
      if (res.code === 0) {
        setSessions(res.data.items || [])
      }
    } catch (e) {
      console.error('加载会话失败:', e)
    }
  }

  const loadSessionMessages = async (sessionId) => {
    try {
      const res = await getSession(sessionId)
      if (res.code === 0) {
        const msgs = (res.data.messages || []).map(m => ({
          role: m.role,
          content: m.content,
          id: Math.random().toString(36).slice(2),
        }))
        setMessages(msgs)
      }
    } catch (e) {
      console.error('加载消息失败:', e)
    }
  }

  const handleNewChat = () => {
    setCurrentSessionId(null)
    setMessages([])
    setInput('')
    inputRef.current?.focus()
  }

  const handleSelectSession = (sessionId) => {
    setCurrentSessionId(sessionId)
    loadSessionMessages(sessionId)
  }

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation()
    if (!confirm('确定删除此会话？')) return
    try {
      await deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      if (currentSessionId === sessionId) {
        handleNewChat()
      }
    } catch (e) {
      alert('删除失败: ' + e.message)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return

    const userMessage = input.trim()
    setInput('')
    setIsStreaming(true)
    setStreamEvents([])
    setActiveEvent(null)

    // 添加用户消息到界面
    const userMsgId = Date.now().toString()
    setMessages(prev => [...prev, { role: 'user', content: userMessage, id: userMsgId }])

    let assistantReply = ''
    let finalSessionId = currentSessionId
    let streamError = null
    const currentStreamEvents = []

    try {
      await streamChatFetch(userMessage, currentSessionId, (eventType, payload) => {
        setActiveEvent(eventType)
        const evt = { type: eventType, payload, time: Date.now() }
        setStreamEvents(prev => [...prev, evt])
        currentStreamEvents.push(evt)

        if (eventType === 'output') {
          assistantReply = payload.reply || ''
          finalSessionId = payload.session_id || currentSessionId
        }
        if (eventType === 'error') {
          streamError = payload.detail || payload.message || '未知错误'
        }
      })

      // 添加助手回复（或错误提示），绑定推理链路
      if (assistantReply) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: assistantReply,
          id: 'assistant-' + Date.now(),
          reasoningEvents: currentStreamEvents.length > 0 ? [...currentStreamEvents] : undefined,
        }])
      } else if (streamError) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `❌ Agent 推理异常: ${streamError}`,
          id: 'error-' + Date.now(),
          isError: true,
          reasoningEvents: currentStreamEvents.length > 0 ? [...currentStreamEvents] : undefined,
        }])
      }

      // 更新当前会话ID
      if (finalSessionId && finalSessionId !== currentSessionId) {
        setCurrentSessionId(finalSessionId)
        await loadSessions()
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `❌ 请求失败: ${err.message}`,
        id: 'error-' + Date.now(),
        isError: true,
      }])
    } finally {
      setIsStreaming(false)
      setActiveEvent(null)
    }
  }

  const formatTime = (iso) => {
    if (!iso) return ''
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  // ---- 回复重试处理 ----
  const handleRetry = useCallback(async (msgIndex) => {
    if (!currentSessionId || isStreaming) return

    // 找到要重试的消息（必须是 assistant 消息）
    const targetMsg = messages[msgIndex]
    if (!targetMsg || targetMsg.role !== 'assistant') return

    // 标记正在重试
    setMessages(prev => prev.map((m, i) =>
      i === msgIndex ? { ...m, _isRetrying: true } : m
    ))
    setIsStreaming(true)
    setStreamEvents([])
    setActiveEvent('start')

    let retryReply = ''
    let retryError = null
    const retryEvents = []

    try {
      await retryMessage(currentSessionId, (eventType, payload) => {
        setActiveEvent(eventType)
        const evt = { type: eventType, payload, time: Date.now() }
        setStreamEvents(prev => [...prev, evt])
        retryEvents.push(evt)

        if (eventType === 'output') {
          retryReply = payload.reply || ''
        }
        if (eventType === 'error') {
          retryError = payload.detail || payload.message || '未知错误'
        }
      })

      // 将原消息保存到版本历史中
      setMessageVersions(prev => {
        const next = new Map(prev)
        const existing = next.get(targetMsg.id) || []
        // 只在第一次重试时保存原始版本
        if (existing.length === 0) {
          existing.unshift({
            content: targetMsg.content,
            reasoningEvents: targetMsg.reasoningEvents ? [...targetMsg.reasoningEvents] : undefined,
            timestamp: Date.now(),
            label: 'v1 原版',
          })
        }
        // 添加新版本
        existing.push({
          content: retryReply || '(空回复)',
          reasoningEvents: retryEvents.length > 0 ? [...retryEvents] : undefined,
          timestamp: Date.now(),
          label: `v${existing.length + 1} 重试`,
        })
        next.set(targetMsg.id, existing)
        return next
      })

      // 替换当前消息内容为最新版本
      setMessages(prev => prev.map((m, i) => {
        if (i !== msgIndex) return m
        return {
          ...m,
          content: retryReply || `❌ 重试异常: ${retryError}`,
          isError: !!retryError && !retryReply,
          reasoningEvents: retryEvents.length > 0 ? [...retryEvents] : m.reasoningEvents,
          _isRetrying: false,
          _retryCount: (m._retryCount || 0) + 1,
        }
      }))

    } catch (err) {
      setMessages(prev => prev.map((m, i) =>
        i === msgIndex ? { ...m, _isRetrying: false } : m
      ))
      console.error('重试失败:', err)
    } finally {
      setIsStreaming(false)
      setActiveEvent(null)
    }
  }, [currentSessionId, isStreaming, messages])

  /** 切换对比面板 */
  const handleCompare = useCallback((msgId) => {
    setComparingMsgId(prev => prev === msgId ? null : msgId)
  }, [])

  // 提取 <think> 思考块
  function parseThinkBlock(content) {
    const matches = [...content.matchAll(/<think>([\s\S]*?)<\/think>/gi)]
    if (matches.length === 0) return { main: content, think: null }
    const think = matches.map(m => m[1].trim()).join('\n\n')
    const main = content.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
    return { main, think }
  }

  // Markdown 自定义组件样式
  const mdComponents = {
    table({ node, ...props }) {
      return <table className="w-full text-xs border-collapse border border-slate-700 my-2" {...props} />
    },
    thead({ node, ...props }) {
      return <thead className="bg-slate-700/50" {...props} />
    },
    th({ node, ...props }) {
      return <th className="border border-slate-700 px-2 py-1 text-left font-medium" {...props} />
    },
    td({ node, ...props }) {
      return <td className="border border-slate-700 px-2 py-1" {...props} />
    },
    tr({ node, ...props }) {
      return <tr className="even:bg-slate-800/30" {...props} />
    },
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      return !inline ? (
        <pre className="bg-slate-900/80 border border-slate-700 rounded-lg p-3 overflow-x-auto my-2">
          <code className={`text-xs font-mono ${match ? `language-${match[1]}` : ''}`} {...props}>
            {children}
          </code>
        </pre>
      ) : (
        <code className="bg-slate-700/50 px-1 py-0.5 rounded text-xs font-mono" {...props}>
          {children}
        </code>
      )
    },
    p({ node, ...props }) {
      return <p className="mb-2 last:mb-0" {...props} />
    },
    ul({ node, ...props }) {
      return <ul className="ml-4 mb-2 list-disc" {...props} />
    },
    ol({ node, ...props }) {
      return <ol className="ml-4 mb-2 list-decimal" {...props} />
    },
    li({ node, ...props }) {
      return <li className="mb-0.5" {...props} />
    },
    h1({ node, ...props }) {
      return <h1 className="text-base font-semibold mb-2 mt-3" {...props} />
    },
    h2({ node, ...props }) {
      return <h2 className="text-sm font-semibold mb-2 mt-3" {...props} />
    },
    h3({ node, ...props }) {
      return <h3 className="text-sm font-semibold mb-1 mt-2" {...props} />
    },
    a({ node, ...props }) {
      return <a className="text-primary-400 hover:underline" target="_blank" rel="noopener noreferrer" {...props} />
    },
    blockquote({ node, ...props }) {
      return <blockquote className="border-l-2 border-slate-600 pl-3 text-slate-400 italic my-2" {...props} />
    },
    hr({ node, ...props }) {
      return <hr className="border-slate-700 my-3" {...props} />
    },
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] lg:h-screen">
      {/* 会话侧边栏 */}
      <div
        className={`hidden md:flex flex-col border-r border-slate-800 bg-slate-900/50 transition-all duration-200 overflow-hidden ${
          sessionPanelOpen ? 'w-64' : 'w-0'
        }`}
      >
        {/* 顶部工具栏 */}
        <div className={`flex items-center justify-between border-b border-slate-800 shrink-0 ${sessionPanelOpen ? 'p-3' : 'px-0 py-3'}`}>
          {sessionPanelOpen && (
            <button
              onClick={handleNewChat}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-medium transition-colors"
            >
              <Sparkles className="w-4 h-4" />
              新对话
            </button>
          )}
          <button
            onClick={() => setSessionPanelOpen(v => !v)}
            className={`text-slate-400 hover:text-slate-200 transition-colors ${sessionPanelOpen ? 'ml-2' : 'w-full flex justify-center'}`}
            title={sessionPanelOpen ? '收起会话列表' : '展开会话列表'}
          >
            {sessionPanelOpen ? (
              <PanelLeftClose className="w-4 h-4" />
            ) : (
              <PanelLeftOpen className="w-4 h-4" />
            )}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin">
          {sessions.map(session => (
            <div
              key={session.session_id}
              onClick={() => handleSelectSession(session.session_id)}
              className={`
                group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors
                ${currentSessionId === session.session_id
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }
              `}
            >
              <MessageSquare className="w-4 h-4 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="truncate">{session.title || '新对话'}</div>
                <div className="text-xs text-slate-500">{formatTime(session.updated_at)}</div>
              </div>
              <button
                onClick={(e) => handleDeleteSession(e, session.session_id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
              >
                ×
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="text-center text-slate-600 text-sm py-8">暂无会话</div>
          )}
        </div>
      </div>

      {/* 聊天主区域 + 终端侧板 — 可拖拽面板组 */}
      <PanelGroup direction="horizontal" className="flex-1">
        <Panel
          ref={chatPanelRef}
          collapsible
          collapsedSize={0}
          minSize={30}
          defaultSize={65}
          onCollapse={() => setChatPanelOpen(false)}
          onExpand={() => setChatPanelOpen(true)}
          className="flex flex-col"
        >
          {/* Session ID 标签栏 */}
          <div className="shrink-0 px-4 py-1.5 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">会话ID:</span>
              <span className="font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
                {currentSessionId || '新对话'}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {isStreaming && (
                <div className="flex items-center gap-1.5 text-xs text-primary-400">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>{EVENT_LABELS[activeEvent] || '处理中...'}</span>
                </div>
              )}
              <button
                onClick={() => chatPanelRef.current?.collapse()}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                title="收起聊天"
              >
                <PanelLeftClose className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">收起</span>
              </button>
              <button
                onClick={() => terminalOpen ? terminalPanelRef.current?.collapse() : terminalPanelRef.current?.expand()}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                  terminalOpen
                    ? 'bg-primary-900/30 text-primary-300 border border-primary-800/50'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
                title={terminalOpen ? '关闭终端' : '打开终端'}
              >
                {terminalOpen ? (
                  <>
                    <PanelRightClose className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">关闭终端</span>
                  </>
                ) : (
                  <>
                    <PanelRightOpen className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">终端</span>
                  </>
                )}
              </button>
            </div>
          </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <Bot className="w-12 h-12 mb-4 text-slate-600" />
              <h2 className="text-xl font-semibold text-slate-300 mb-2">DevOps Agent</h2>
              <p className="text-sm max-w-md text-center">
                面向国产化环境的运维智能体。您可以询问系统状态、执行诊断命令或请求运维操作。
              </p>
              <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg w-full">
                {['查看磁盘使用情况', '分析系统日志', '检查网络连接', '列出高 CPU 进程'].map((demo) => (
                  <button
                    key={demo}
                    onClick={() => { setInput(demo); inputRef.current?.focus() }}
                    className="px-4 py-2.5 bg-slate-800/50 hover:bg-slate-800 rounded-lg text-sm text-left text-slate-300 transition-colors border border-slate-800"
                  >
                    {demo}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, msgIndex) => {
            const versions = messageVersions.get(msg.id)
            const hasMultipleVersions = versions && versions.length > 1
            const isComparing = comparingMsgId === msg.id

            return (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} ${msg.role === 'assistant' ? 'group/msg' : ''}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-primary-900/50 border border-primary-800/50 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-primary-400" />
                </div>
              )}
              <div className="max-w-[85%] sm:max-w-[75%]">
                {/* 版本标签（有多个版本时显示） */}
                {hasMultipleVersions && !isComparing && (
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400/80 border border-amber-800/20">
                      v{versions.length} · 已重试 {(versions.length - 1)} 次
                    </span>
                    <button
                      onClick={() => handleCompare(msg.id)}
                      className="text-[10px] text-slate-500 hover:text-amber-400 transition-colors"
                    >
                      查看对比 →
                    </button>
                  </div>
                )}
                <div
                  className={`
                    rounded-2xl px-4 py-3 text-sm leading-relaxed
                    ${msg.role === 'user' || msg.isError ? 'whitespace-pre-wrap' : ''}
                    ${msg.role === 'user'
                      ? 'bg-primary-600 text-white'
                      : msg.isError
                        ? 'bg-red-900/20 border border-red-800/30 text-red-200'
                        : 'bg-slate-800 text-slate-200'
                    }
                  `}
                >
                  {(() => {
                    if (msg.role === 'assistant' && !msg.isError) {
                      const { main, think } = parseThinkBlock(msg.content)
                      return (
                        <>
                          {think && (
                            <details className="mb-3 group border-b border-slate-700/50 pb-2">
                              <summary className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer hover:text-slate-400 select-none list-none">
                                <ChevronRight className="w-3 h-3 group-open:hidden" />
                                <ChevronDown className="w-3 h-3 hidden group-open:inline" />
                                <span>思考过程</span>
                              </summary>
                              <div className="mt-2 text-xs text-slate-500 whitespace-pre-wrap leading-relaxed">
                                {think}
                              </div>
                            </details>
                          )}
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                            {main}
                          </ReactMarkdown>
                        </>
                      )
                    }
                    return msg.content
                  })()}
                </div>
                {/* 推理链路流程图（仅 assistant 消息） */}
                {msg.role === 'assistant' && msg.reasoningEvents && msg.reasoningEvents.length > 0 && (
                  <ReasoningFlowViewer events={msg.reasoningEvents} />
                )}
                {/* 操作栏：重试按钮 + 版本对比 */}
                {msg.role === 'assistant' && !isStreaming && (
                  <MessageActions
                    msgIndex={msgIndex}
                    msg={msg}
                    onRetry={handleRetry}
                    hasVersions={hasMultipleVersions}
                    onCompare={handleCompare}
                  />
                )}
                {/* 对比面板（内联展开） */}
                {isComparing && hasMultipleVersions && (
                  <div className="mt-2 space-y-2">
                    {/* 版本选择 Tab */}
                    <div className="flex items-center gap-1.5">
                      {versions.map((v, vi) => (
                        <button
                          key={vi}
                          onClick={() => {
                            // 切换显示版本内容
                            setMessages(prev => prev.map((m) =>
                              m.id === msg.id
                                ? { ...m, content: v.content, reasoningEvents: v.reasoningEvents }
                                : m
                            ))
                          }}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                            vi === versions.length - 1
                              ? 'bg-emerald-900/25 text-emerald-400 border border-emerald-800/30'
                              : 'bg-slate-800 text-slate-400 border border-slate-700/50 hover:border-slate-600'
                          }`}
                        >
                          {v.label || `v${vi + 1}`}
                        </button>
                      ))}
                      <span className="text-slate-700 mx-0.5">vs</span>
                    </div>
                    {/* Diff 对比视图 — 显示最新版 vs 原版 */}
                    {(() => {
                      if (versions.length < 2) return null
                      const orig = versions[0]
                      const latest = versions[versions.length - 1]
                      return (
                        <DiffViewer
                          original={orig.content}
                          revised={latest.content}
                          onClose={() => setComparingMsgId(null)}
                        />
                      )
                    })()}
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-slate-300" />
                </div>
              )}
            </div>
            )
          })}

          {/* 流式推理进度 */}
          {isStreaming && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary-900/50 border border-primary-800/50 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4 text-primary-400" />
              </div>
              <div className="bg-slate-800 rounded-2xl px-4 py-3 max-w-[85%] sm:max-w-[75%]">
                {/* 推理阶段指示器 */}
                <div className="flex items-center gap-2 mb-3">
                  <Loader2 className="w-4 h-4 animate-spin text-primary-400" />
                  <span className="text-sm text-primary-300 font-medium">
                    {EVENT_LABELS[activeEvent] || '处理中...'}
                  </span>
                </div>

                {/* 推理事件时间线 — 带阶段分组 */}
                <div className="space-y-2">
                  {(() => {
                    // 按阶段分组最近的流式事件
                    const recent = streamEvents.slice(-12)
                    const phaseGroups = { startup: [], sense: [], reasoning: [], planning: [], execution: [], output: [] }
                    recent.forEach(evt => {
                      const pk = getPhaseKey(evt.type)
                      if (phaseGroups[pk]) phaseGroups[pk].push(evt)
                      else phaseGroups.execution.push(evt)
                    })

                    return PHASE_ORDER.map(pk => {
                      const evts = phaseGroups[pk]
                      if (evts.length === 0) return null
                      const phase = PHASE_CONFIG[pk]
                      const PIcon = phase.icon
                      return (
                        <div key={pk} className="flex items-start gap-1.5">
                          <PIcon className="w-3 h-3 mt-0.5 shrink-0" style={{ color: phase.color, opacity: 0.7 }} />
                          <div className="flex-1 space-y-0.5">
                            {evts.map((evt, idx) => (
                              <div key={evt.time + idx} className="flex items-center gap-1.5 text-[11px]">
                                <span className={`font-medium shrink-0 ${EVENT_COLORS[evt.type] || 'text-slate-400'}`}>
                                  {EVENT_LABELS[evt.type] || evt.type}
                                </span>
                                {evt.payload?.tool_name && (
                                  <code className="font-mono text-emerald-300/80 bg-emerald-900/15 px-1 py-px rounded text-[10px]">{evt.payload.tool_name}</code>
                                )}
                                {evt.payload?.reply_preview && (
                                  <span className="text-slate-500 truncate max-w-[160px] text-[10px]">{evt.payload.reply_preview}</span>
                                )}
                                {(evt.payload?.execution_mode === 'dag_parallel' || evt.type?.startsWith('dag_')) && (
                                  <span className="inline-flex items-center gap-0.5 text-[9px] font-medium px-1 py-px rounded bg-primary-900/20 text-primary-400 border border-primary-800/20">
                                    <Zap className="w-2.5 h-2.5" />DAG
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )
                    })
                  })()}
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="border-t border-slate-800 p-4 bg-slate-900/30">
          <form onSubmit={handleSubmit} className="flex gap-3 max-w-4xl mx-auto">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isStreaming ? 'Agent 正在思考...' : '输入运维问题或指令...'}
              disabled={isStreaming}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm
                         text-slate-100 placeholder-slate-500
                         focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50
                         disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            />
            <button
              type="submit"
              disabled={isStreaming || !input.trim()}
              className="px-5 py-3 bg-primary-600 hover:bg-primary-500 disabled:bg-slate-700 disabled:text-slate-500
                         rounded-xl text-white transition-colors flex items-center gap-2"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              <span className="hidden sm:inline">发送</span>
            </button>
          </form>
          <div className="max-w-4xl mx-auto mt-2 flex items-center gap-4 text-xs text-slate-600">
            <span className="flex items-center gap-1">
              <Terminal className="w-3 h-3" />
              支持自然语言运维查询
            </span>
            <span className="flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              危险操作需经安全校验
            </span>
          </div>
        </div>
      </Panel>

      <PanelResizeHandle className="w-1 bg-slate-800 hover:bg-primary-500 data-[resize-handle-active]:bg-primary-500 cursor-col-resize" />

      <Panel
        ref={terminalPanelRef}
        collapsible
        collapsedSize={0}
        minSize={20}
        defaultSize={35}
        onCollapse={() => setTerminalOpen(false)}
        onExpand={() => setTerminalOpen(true)}
        className="flex flex-col"
      >
        <div className="flex-1 min-h-0">
          <TerminalPanel ref={terminalRef} visible={terminalOpen} chatCollapsed={!chatPanelOpen} onExpandChat={() => chatPanelRef.current?.expand()} />
        </div>
        <QuickCommandBar onRunCommand={handleRunQuickCommand} />
      </Panel>
    </PanelGroup>
  </div>
  )
}
