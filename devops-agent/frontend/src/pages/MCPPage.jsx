import { useState, useEffect, useCallback } from 'react'
import {
  Plug,
  Unplug,
  Heart,
  Wrench,
  Plus,
  Trash2,
  Edit3,
  RefreshCw,
  Loader2,
  Server,
  Terminal,
  Globe,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  XCircle,
  FileJson,
  Cpu,
  Download,
  AlertTriangle,
  Info,
  Package,
} from 'lucide-react'
import {
  listMCPServers,
  getMCPServer,
  createMCPServer,
  updateMCPServer,
  deleteMCPServer,
  connectMCPServer,
  disconnectMCPServer,
  pingMCPServer,
  getMCPServerTools,
  listConnectedMCPServers,
  checkMCPEnv,
  importMCPServers,
  listRegistryTools,
} from '../api/client'

const TRANSPORT_LABELS = {
  stdio: 'stdio（子进程）',
  sse: 'SSE（HTTP 流）',
}

const TRANSPORT_ICONS = {
  stdio: Terminal,
  sse: Globe,
}

export default function MCPPage() {
  const [servers, setServers] = useState([])
  const [connectedInfo, setConnectedInfo] = useState([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState({})
  const [modalOpen, setModalOpen] = useState(false)
  const [modalTab, setModalTab] = useState('form') // 'form' | 'json'
  const [editingServer, setEditingServer] = useState(null)
  const [toolsModal, setToolsModal] = useState(null)
  const [error, setError] = useState(null)

  // 环境检测
  const [envInfo, setEnvInfo] = useState(null)
  const [envLoading, setEnvLoading] = useState(false)

  // JSON 导入
  const [jsonText, setJsonText] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [importResult, setImportResult] = useState(null)

  // 注册中心工具
  const [registryTools, setRegistryTools] = useState([])
  const [registryLoading, setRegistryLoading] = useState(false)
  const [registryExpanded, setRegistryExpanded] = useState(false)

  const [form, setForm] = useState({
    id: '',
    name: '',
    transport: 'stdio',
    command: '',
    args: '',
    env: '',
    url: '',
    cwd: '',
  })

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [serversRes, connectedRes] = await Promise.all([
        listMCPServers(),
        listConnectedMCPServers().catch(() => ({ code: 0, data: [] })),
      ])
      if (serversRes.code === 0) {
        setServers(serversRes.data || [])
      } else {
        setError(serversRes.message || '加载失败')
      }
      if (connectedRes.code === 0) {
        setConnectedInfo(connectedRes.data || [])
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadEnv = useCallback(async () => {
    setEnvLoading(true)
    try {
      const res = await checkMCPEnv()
      if (res.code === 0) {
        setEnvInfo(res.data)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setEnvLoading(false)
    }
  }, [])

  const loadRegistry = useCallback(async () => {
    setRegistryLoading(true)
    try {
      const res = await listRegistryTools()
      if (res.code === 0) {
        setRegistryTools(res.data?.tools || [])
      }
    } catch (e) {
      console.error('加载注册中心工具失败:', e)
    } finally {
      setRegistryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    loadEnv()
    loadRegistry()
  }, [loadData, loadEnv, loadRegistry])

  const isConnected = (serverId) =>
    connectedInfo.some((c) => c.id === serverId && c.connected)

  const getConnectedTools = (serverId) => {
    const info = connectedInfo.find((c) => c.id === serverId)
    return info ? info.tool_names || [] : []
  }

  const handleOpenAdd = () => {
    setEditingServer(null)
    setModalTab('form')
    setImportResult(null)
    setForm({
      id: '',
      name: '',
      transport: 'stdio',
      command: '',
      args: '',
      env: '',
      url: '',
      cwd: '',
    })
    setModalOpen(true)
  }

  const handleOpenJsonImport = () => {
    setEditingServer(null)
    setModalTab('json')
    setImportResult(null)
    setJsonText('')
    setModalOpen(true)
  }

  const handleAddBuiltin = async (builtin) => {
    try {
      const res = await createMCPServer(builtin)
      if (res.code !== 0) throw new Error(res.message)
      await loadData()
    } catch (e) {
      alert('添加内置 Server 失败: ' + e.message)
    }
  }

  const handleImportJson = async () => {
    if (!jsonText.trim()) {
      alert('请粘贴 JSON 配置')
      return
    }
    setImportLoading(true)
    setImportResult(null)
    try {
      const res = await importMCPServers(jsonText)
      setImportResult(res)
      if (res.code === 0) {
        await loadData()
      }
    } catch (e) {
      setImportResult({ code: -1, message: e.message })
    } finally {
      setImportLoading(false)
    }
  }

  const handleOpenEdit = (srv) => {
    setEditingServer(srv)
    setForm({
      id: srv.id,
      name: srv.name,
      transport: srv.transport,
      command: srv.command || '',
      args: Array.isArray(srv.args) ? srv.args.join('\n') : srv.args || '',
      env: srv.env && typeof srv.env === 'object'
        ? Object.entries(srv.env).map(([k, v]) => `${k}=${v}`).join('\n')
        : srv.env || '',
      url: srv.url || '',
      cwd: srv.cwd || '',
    })
    setModalOpen(true)
  }

  const parseArgs = (raw) =>
    raw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)

  const parseEnv = (raw) => {
    const obj = {}
    raw.split('\n').forEach((line) => {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) return
      const idx = trimmed.indexOf('=')
      if (idx > 0) {
        obj[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim()
      }
    })
    return obj
  }

  const handleSave = async () => {
    if (!form.id.trim() || !form.name.trim()) {
      alert('ID 和名称不能为空')
      return
    }
    const payload = {
      id: form.id.trim(),
      name: form.name.trim(),
      transport: form.transport,
      command: form.command.trim() || undefined,
      args: parseArgs(form.args),
      env: parseEnv(form.env),
      url: form.url.trim() || undefined,
      cwd: form.cwd.trim() || undefined,
    }
    try {
      if (editingServer) {
        const res = await updateMCPServer(payload.id, payload)
        if (res.code !== 0) throw new Error(res.message)
      } else {
        const res = await createMCPServer(payload)
        if (res.code !== 0) throw new Error(res.message)
      }
      setModalOpen(false)
      await loadData()
    } catch (e) {
      alert('保存失败: ' + e.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(`确定删除 MCP Server "${id}"？`)) return
    try {
      const res = await deleteMCPServer(id)
      if (res.code !== 0) throw new Error(res.message)
      await loadData()
    } catch (e) {
      alert('删除失败: ' + e.message)
    }
  }

  const _needsDependency = (srv) => {
    const cmd = (srv.command || '').toLowerCase()
    if (cmd.includes('node') || cmd.includes('npm') || cmd.includes('npx')) {
      return { type: 'node', name: 'Node.js' }
    }
    if (cmd.includes('uv')) {
      return { type: 'uv', name: 'uv' }
    }
    if (cmd.includes('python') || cmd.includes('python3')) {
      return { type: 'python', name: 'Python' }
    }
    return null
  }

  const handleConnect = async (srv) => {
    const id = typeof srv === 'string' ? srv : srv.id
    const server = typeof srv === 'string' ? servers.find((s) => s.id === srv) : srv

    // 依赖预检查
    const dep = _needsDependency(server)
    if (dep && envInfo) {
      // Python 特殊处理：同时检查 python3 和 python，任一可用即通过
      let depAvailable = false
      if (dep.type === 'python') {
        depAvailable = envInfo.dependencies?.some(
          (d) => (d.name === 'python3' || d.name === 'python') && d.available
        )
      } else {
        depAvailable = envInfo.dependencies?.find((d) => d.name === dep.type)?.available
      }
      if (!depAvailable) {
        const ok = confirm(
          `⚠️ 依赖缺失\n\n该 MCP Server 需要 ${dep.name}，但当前环境未检测到。\n\n` +
          `在龙芯(loongarch64)架构下，${dep.name} 通常无预编译包，可能导致连接失败。\n\n` +
          `是否仍尝试连接？`
        )
        if (!ok) return
      }
    }

    setActionLoading((p) => ({ ...p, [id]: 'connect' }))
    try {
      const res = await connectMCPServer(id)
      if (res.code !== 0) throw new Error(res.message)
      await loadData()
    } catch (e) {
      alert('连接失败: ' + e.message)
    } finally {
      setActionLoading((p) => ({ ...p, [id]: undefined }))
    }
  }

  const handleDisconnect = async (id) => {
    setActionLoading((p) => ({ ...p, [id]: 'disconnect' }))
    try {
      const res = await disconnectMCPServer(id)
      if (res.code !== 0) throw new Error(res.message)
      await loadData()
    } catch (e) {
      alert('断开失败: ' + e.message)
    } finally {
      setActionLoading((p) => ({ ...p, [id]: undefined }))
    }
  }

  const handlePing = async (id) => {
    setActionLoading((p) => ({ ...p, [id]: 'ping' }))
    try {
      const res = await pingMCPServer(id)
      if (res.code !== 0) throw new Error(res.message)
      alert(`心跳测试: ${res.data.alive ? '✅ 正常' : '❌ 无响应'} (${res.data.latency_ms}ms)`)
    } catch (e) {
      alert('心跳失败: ' + e.message)
    } finally {
      setActionLoading((p) => ({ ...p, [id]: undefined }))
    }
  }

  const handleViewTools = async (id) => {
    setActionLoading((p) => ({ ...p, [id]: 'tools' }))
    try {
      const res = await getMCPServerTools(id)
      if (res.code !== 0) throw new Error(res.message)
      setToolsModal({ serverId: id, tools: res.data || [] })
    } catch (e) {
      alert('获取工具列表失败: ' + e.message)
    } finally {
      setActionLoading((p) => ({ ...p, [id]: undefined }))
    }
  }

  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            <Plug className="w-6 h-6 text-primary-400" />
            MCP Server 管理
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            连接外部 MCP Server，将第三方工具接入 Agent 推理链路
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleOpenJsonImport}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-sm font-medium transition-colors"
          >
            <FileJson className="w-4 h-4" />
            JSON 导入
          </button>
          <button
            onClick={handleOpenAdd}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            新增配置
          </button>
        </div>
      </div>

      {/* 环境检测信息栏 */}
      <div className="mb-4 bg-slate-900/60 border border-slate-800 rounded-xl p-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Cpu className="w-3.5 h-3.5" />
            <span className="font-medium">运行环境:</span>
          </div>
          {envLoading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
          ) : envInfo?.dependencies ? (
            envInfo.dependencies.map((dep) => (
              <span
                key={dep.name}
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-mono ${
                  dep.available
                    ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/30'
                    : 'bg-red-900/20 text-red-400 border border-red-800/20'
                }`}
                title={dep.version || ''}
              >
                {dep.available ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {dep.name}
              </span>
            ))
          ) : null}
          <button
            onClick={loadEnv}
            disabled={envLoading}
            className="ml-auto flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${envLoading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        {envInfo?.summary?.python_ready && !envInfo?.summary?.node_ready && (
          <div className="mt-2 flex items-start gap-2 text-xs text-amber-400/80">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>
              检测到 Node.js 不可用。龙芯(loongarch64)架构下 npm MCP Server 无法运行，
              建议使用下方「内置 Python MCP Server」或纯 Python 实现的 Server。
            </span>
          </div>
        )}
      </div>

      {/* 内置 Python MCP Server 快捷添加 */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Package className="w-4 h-4 text-slate-400" />
          <span className="text-sm font-medium text-slate-300">内置 Python MCP Server（零外部依赖，龙芯兼容）</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            {
              id: 'builtin-filesystem',
              name: '文件系统',
              icon: '📁',
              config: {
                id: 'builtin-filesystem',
                name: '文件系统 MCP',
                transport: 'stdio',
                command: 'python3',
                args: ['/root/devops-agent/scripts/mcp_servers/filesystem_server.py'],
                env: {},
              },
            },
            {
              id: 'builtin-fetch',
              name: 'HTTP 请求',
              icon: '🌐',
              config: {
                id: 'builtin-fetch',
                name: 'HTTP Fetch MCP',
                transport: 'stdio',
                command: 'python3',
                args: ['/root/devops-agent/scripts/mcp_servers/fetch_server.py'],
                env: {},
              },
            },
            {
              id: 'builtin-time',
              name: '时间日期',
              icon: '🕐',
              config: {
                id: 'builtin-time',
                name: 'Time MCP',
                transport: 'stdio',
                command: 'python3',
                args: ['/root/devops-agent/scripts/mcp_servers/time_server.py'],
                env: {},
              },
            },
          ].map((builtin) => {
            const exists = servers.some((s) => s.id === builtin.id)
            return (
              <button
                key={builtin.id}
                onClick={() => handleAddBuiltin(builtin.config)}
                disabled={exists}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  exists
                    ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
                }`}
              >
                <span>{builtin.icon}</span>
                {builtin.name}
                {exists && <span className="text-slate-500">(已添加)</span>}
              </button>
            )
          })}
        </div>
      </div>

      {/* 注册中心工具 */}
      <div className="mb-4 bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden">
        <button
          onClick={() => setRegistryExpanded((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Wrench className="w-4 h-4 text-primary-400" />
            <span className="text-sm font-medium text-slate-200">注册中心工具</span>
            {registryLoading ? (
              <Loader2 className="w-3 h-3 animate-spin text-slate-500" />
            ) : (
              <span className="text-xs text-slate-500">
                共 {registryTools.length} 个
                {registryTools.length > 0 && (
                  <>
                    <span className="ml-1 text-emerald-400/80">
                      内置 {registryTools.filter((t) => t.source === 'builtin').length}
                    </span>
                    <span className="ml-1 text-blue-400/80">
                      MCP {registryTools.filter((t) => t.source === 'mcp').length}
                    </span>
                    <span className="ml-1 text-amber-400/80">
                      动态 {registryTools.filter((t) => t.source === 'dynamic').length}
                    </span>
                  </>
                )}
              </span>
            )}
          </div>
          {registryExpanded ? (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-500" />
          )}
        </button>

        {registryExpanded && (
          <div className="px-4 pb-4">
            {registryLoading ? (
              <div className="py-4 text-center text-xs text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin inline mr-1" />
                加载中...
              </div>
            ) : registryTools.length === 0 ? (
              <div className="py-4 text-center text-xs text-slate-600">暂无已注册工具</div>
            ) : (
              <div className="space-y-3">
                {/* 内置工具 */}
                {(() => {
                  const builtins = registryTools.filter((t) => t.source === 'builtin')
                  return builtins.length > 0 ? (
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-xs font-medium text-emerald-400/90">内置工具</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400/80 border border-emerald-800/30">
                          {builtins.length}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                        {builtins.map((tool) => (
                          <div
                            key={tool.name}
                            className="flex items-start gap-2 px-2.5 py-2 bg-slate-800/50 border border-slate-700/50 rounded-lg"
                            title={tool.description}
                          >
                            <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-emerald-400/60 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-slate-300 truncate">
                                {tool.name}
                              </div>
                              <div className="text-[11px] text-slate-500 truncate leading-tight mt-0.5">
                                {tool.description}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null
                })()}

                {/* MCP 工具 */}
                {(() => {
                  const mcps = registryTools.filter((t) => t.source === 'mcp')
                  return mcps.length > 0 ? (
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-xs font-medium text-blue-400/90">MCP 工具</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-900/30 text-blue-400/80 border border-blue-800/30">
                          {mcps.length}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                        {mcps.map((tool) => (
                          <div
                            key={tool.name}
                            className="flex items-start gap-2 px-2.5 py-2 bg-slate-800/50 border border-slate-700/50 rounded-lg"
                            title={tool.description}
                          >
                            <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-blue-400/60 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-slate-300 truncate">
                                {tool.name}
                              </div>
                              <div className="text-[11px] text-slate-500 truncate leading-tight mt-0.5">
                                {tool.description}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null
                })()}

                {/* 动态工具 */}
                {(() => {
                  const dynamics = registryTools.filter((t) => t.source === 'dynamic')
                  return dynamics.length > 0 ? (
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-xs font-medium text-amber-400/90">动态工具</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-400/80 border border-amber-800/30">
                          {dynamics.length}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                        {dynamics.map((tool) => (
                          <div
                            key={tool.name}
                            className="flex items-start gap-2 px-2.5 py-2 bg-slate-800/50 border border-slate-700/50 rounded-lg"
                            title={tool.description}
                          >
                            <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-400/60 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-slate-300 truncate">
                                {tool.name}
                              </div>
                              <div className="text-[11px] text-slate-500 truncate leading-tight mt-0.5">
                                {tool.description}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null
                })()}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-800/30 rounded-lg text-sm text-red-200">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Server Cards */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          加载中...
        </div>
      ) : servers.length === 0 ? (
        <div className="text-center py-20 text-slate-600">
          <Server className="w-12 h-12 mx-auto mb-4 text-slate-700" />
          <p className="text-sm">暂无 MCP Server 配置</p>
          <p className="text-xs mt-1">点击右上角「新增配置」添加第一个 Server</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {servers.map((srv) => {
            const connected = isConnected(srv.id)
            const toolNames = getConnectedTools(srv.id)
            const TransportIcon = TRANSPORT_ICONS[srv.transport] || Terminal

            return (
              <div
                key={srv.id}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors"
              >
                {/* Card Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        connected
                          ? 'bg-emerald-900/30 border border-emerald-800/50'
                          : 'bg-slate-800 border border-slate-700'
                      }`}
                    >
                      {connected ? (
                        <Plug className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Unplug className="w-5 h-5 text-slate-500" />
                      )}
                    </div>
                    <div>
                      <div className="font-medium text-slate-100">{srv.name}</div>
                      <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                        <span className="font-mono bg-slate-800 px-1.5 py-0.5 rounded">{srv.id}</span>
                        <span className="flex items-center gap-1">
                          <TransportIcon className="w-3 h-3" />
                          {TRANSPORT_LABELS[srv.transport] || srv.transport}
                        </span>
                        {connected ? (
                          <span className="flex items-center gap-1 text-emerald-400">
                            <CheckCircle2 className="w-3 h-3" />
                            已连接
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-slate-500">
                            <XCircle className="w-3 h-3" />
                            未连接
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleOpenEdit(srv)}
                      className="p-1.5 text-slate-500 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
                      title="编辑"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(srv.id)}
                      className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-slate-800 rounded-lg transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Config details */}
                <div className="bg-slate-950/50 rounded-lg px-3 py-2 mb-3 space-y-1 text-xs font-mono text-slate-400">
                  {srv.command && (
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600 shrink-0 w-12">命令</span>
                      <span className="text-slate-300 truncate">{srv.command}</span>
                    </div>
                  )}
                  {srv.args && srv.args.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600 shrink-0 w-12">参数</span>
                      <span className="text-slate-300 truncate">
                        {Array.isArray(srv.args) ? srv.args.join(' ') : srv.args}
                      </span>
                    </div>
                  )}
                  {srv.url && (
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600 shrink-0 w-12">URL</span>
                      <span className="text-slate-300 truncate">{srv.url}</span>
                    </div>
                  )}
                  {srv.cwd && (
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600 shrink-0 w-12">目录</span>
                      <span className="text-slate-300 truncate">{srv.cwd}</span>
                    </div>
                  )}
                </div>

                {/* Tool chips */}
                {toolNames.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {toolNames.map((tn) => (
                      <span
                        key={tn}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-900/20 border border-primary-800/30 rounded text-xs text-primary-300"
                      >
                        <Wrench className="w-3 h-3" />
                        {tn}
                      </span>
                    ))}
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex items-center gap-2">
                  {connected ? (
                    <>
                      <button
                        onClick={() => handleDisconnect(srv.id)}
                        disabled={actionLoading[srv.id] === 'disconnect'}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        {actionLoading[srv.id] === 'disconnect' ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Unplug className="w-3 h-3" />
                        )}
                        断开
                      </button>
                      <button
                        onClick={() => handlePing(srv.id)}
                        disabled={actionLoading[srv.id] === 'ping'}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        {actionLoading[srv.id] === 'ping' ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Heart className="w-3 h-3" />
                        )}
                        心跳
                      </button>
                      <button
                        onClick={() => handleViewTools(srv.id)}
                        disabled={actionLoading[srv.id] === 'tools'}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        {actionLoading[srv.id] === 'tools' ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Wrench className="w-3 h-3" />
                        )}
                        工具 ({toolNames.length})
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => handleConnect(srv)}
                      disabled={actionLoading[srv.id] === 'connect'}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 hover:bg-primary-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {actionLoading[srv.id] === 'connect' ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Plug className="w-3 h-3" />
                      )}
                      连接
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Add/Edit/Import Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
              <h3 className="font-semibold text-slate-100">
                {editingServer ? '编辑 MCP Server' : '新增 MCP Server'}
              </h3>
              <button
                onClick={() => setModalOpen(false)}
                className="text-slate-500 hover:text-slate-200"
              >
                ×
              </button>
            </div>

            {/* Tab 切换（仅在非编辑模式显示） */}
            {!editingServer && (
              <div className="flex border-b border-slate-800">
                <button
                  onClick={() => setModalTab('form')}
                  className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                    modalTab === 'form'
                      ? 'text-primary-400 border-b-2 border-primary-500'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  手动配置
                </button>
                <button
                  onClick={() => setModalTab('json')}
                  className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                    modalTab === 'json'
                      ? 'text-primary-400 border-b-2 border-primary-500'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  JSON 导入
                </button>
              </div>
            )}

            {modalTab === 'form' || editingServer ? (
              <div className="px-5 py-4 space-y-4">
                {/* ID */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    唯一标识符 <span className="text-red-400">*</span>
                  </label>
                  <input
                    value={form.id}
                    onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
                    disabled={!!editingServer}
                    placeholder="例如：filesystem"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500 disabled:opacity-50"
                  />
                </div>

                {/* Name */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    显示名称 <span className="text-red-400">*</span>
                  </label>
                  <input
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="例如：文件系统 MCP"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500"
                  />
                </div>

                {/* Transport */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    传输方式
                  </label>
                  <select
                    value={form.transport}
                    onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-primary-500"
                  >
                    <option value="stdio">stdio — 本地子进程</option>
                    <option value="sse">SSE — HTTP Server-Sent Events</option>
                  </select>
                </div>

                {form.transport === 'stdio' ? (
                  <>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">
                        命令（可执行文件路径）
                      </label>
                      <input
                        value={form.command}
                        onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                        placeholder="例如：python3 或 npx"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">
                        参数（每行一个）
                      </label>
                      <textarea
                        value={form.args}
                        onChange={(e) => setForm((f) => ({ ...f, args: e.target.value }))}
                        placeholder="/path/to/server.py&#10;--verbose"
                        rows={3}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">
                        环境变量（每行一个 KEY=VALUE）
                      </label>
                      <textarea
                        value={form.env}
                        onChange={(e) => setForm((f) => ({ ...f, env: e.target.value }))}
                        placeholder="API_KEY=sk-xxxx&#10;DEBUG=1"
                        rows={3}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">
                        工作目录
                      </label>
                      <input
                        value={form.cwd}
                        onChange={(e) => setForm((f) => ({ ...f, cwd: e.target.value }))}
                        placeholder="/root/devops-agent"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500"
                      />
                    </div>
                  </>
                ) : (
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">
                      SSE 端点 URL
                    </label>
                    <input
                      value={form.url}
                      onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                      placeholder="http://localhost:3000/sse"
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500"
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="px-5 py-4 space-y-4">
                <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-3 text-xs text-slate-400 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Info className="w-3.5 h-3.5 text-primary-400" />
                    <span className="font-medium text-slate-300">支持 Claude Desktop 配置格式</span>
                  </div>
                  <p>粘贴包含 mcpServers 对象的 JSON，系统将自动解析并导入每个 Server 配置。</p>
                  <p className="text-slate-500">npm/uv 类命令会被标记为龙芯不兼容，建议改用内置 Python Server。</p>
                </div>

                <textarea
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                  placeholder={`{\n  "mcpServers": {\n    "filesystem": {\n      "command": "python3",\n      "args": ["/path/to/server.py"]\n    }\n  }\n}`}
                  rows={10}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-primary-500 font-mono"
                />

                {importResult && (
                  <div className={`rounded-lg p-3 text-xs space-y-1 ${
                    importResult.code === 0
                      ? 'bg-emerald-900/20 border border-emerald-800/30'
                      : 'bg-red-900/20 border border-red-800/30'
                  }`}>
                    <div className={`font-medium ${importResult.code === 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                      {importResult.message}
                    </div>
                    {importResult.data?.imported?.length > 0 && (
                      <div className="space-y-1 mt-1">
                        {importResult.data.imported.map((item) => (
                          <div key={item.id} className="flex items-center gap-2">
                            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                            <span className="text-slate-300">{item.name}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              item.compat?.compatible === true
                                ? 'bg-emerald-900/30 text-emerald-400'
                                : item.compat?.compatible === false
                                ? 'bg-red-900/30 text-red-400'
                                : 'bg-slate-800 text-slate-500'
                            }`}>
                              {item.compat?.type || 'unknown'}
                            </span>
                            {item.compat?.compatible === false && (
                              <span className="text-red-400/80">{item.compat.reason}</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {importResult.data?.errors?.length > 0 && (
                      <div className="space-y-1 mt-1">
                        {importResult.data.errors.map((err) => (
                          <div key={err.id} className="flex items-center gap-2 text-red-400">
                            <XCircle className="w-3 h-3 shrink-0" />
                            <span>{err.id}: {err.error}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-slate-800">
              <button
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                取消
              </button>
              {modalTab === 'json' && !editingServer ? (
                <button
                  onClick={handleImportJson}
                  disabled={importLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:bg-slate-700 rounded-lg text-sm font-medium transition-colors"
                >
                  {importLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  导入
                </button>
              ) : (
                <button
                  onClick={handleSave}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-medium transition-colors"
                >
                  {editingServer ? '保存修改' : '创建配置'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tools Modal */}
      {toolsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[85vh] overflow-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
              <h3 className="font-semibold text-slate-100 flex items-center gap-2">
                <Wrench className="w-4 h-4 text-primary-400" />
                {toolsModal.serverId} — 工具列表
              </h3>
              <button
                onClick={() => setToolsModal(null)}
                className="text-slate-500 hover:text-slate-200"
              >
                ×
              </button>
            </div>

            <div className="px-5 py-4 space-y-3">
              {toolsModal.tools.length === 0 ? (
                <div className="text-center py-8 text-slate-500 text-sm">暂无工具</div>
              ) : (
                toolsModal.tools.map((tool) => (
                  <details key={tool.name} className="group bg-slate-950/50 rounded-lg border border-slate-800">
                    <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer select-none list-none">
                      <ChevronRight className="w-4 h-4 text-slate-500 group-open:hidden" />
                      <ChevronDown className="w-4 h-4 text-slate-500 hidden group-open:inline" />
                      <span className="font-mono text-sm text-primary-300">{tool.name}</span>
                      <span className="text-xs text-slate-500 ml-2">{tool.description}</span>
                    </summary>
                    <div className="px-4 pb-4">
                      <div className="text-xs text-slate-400 mb-1.5 font-medium">参数 Schema:</div>
                      <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300 overflow-auto">
                        {JSON.stringify(tool.inputSchema || tool.parameters || {}, null, 2)}
                      </pre>
                    </div>
                  </details>
                ))
              )}
            </div>

            <div className="flex items-center justify-end px-5 py-4 border-t border-slate-800">
              <button
                onClick={() => setToolsModal(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
