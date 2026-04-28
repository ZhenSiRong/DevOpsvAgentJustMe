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
  const [actionLoading, setActionLoading] = useState({}) // { [serverId]: 'connect' | 'disconnect' | 'ping' | 'tools' }
  const [modalOpen, setModalOpen] = useState(false)
  const [editingServer, setEditingServer] = useState(null)
  const [toolsModal, setToolsModal] = useState(null) // { serverId, tools: [] }
  const [error, setError] = useState(null)

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

  useEffect(() => {
    loadData()
  }, [loadData])

  const isConnected = (serverId) =>
    connectedInfo.some((c) => c.id === serverId && c.connected)

  const getConnectedTools = (serverId) => {
    const info = connectedInfo.find((c) => c.id === serverId)
    return info ? info.tool_names || [] : []
  }

  const handleOpenAdd = () => {
    setEditingServer(null)
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

  const handleConnect = async (id) => {
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            <Plug className="w-6 h-6 text-primary-400" />
            MCP Server 管理
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            连接外部 MCP Server，将第三方工具接入 Agent 推理链路
          </p>
        </div>
        <button
          onClick={handleOpenAdd}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          新增配置
        </button>
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
                      onClick={() => handleConnect(srv.id)}
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

      {/* Add/Edit Modal */}
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

            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-slate-800">
              <button
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-medium transition-colors"
              >
                {editingServer ? '保存修改' : '创建配置'}
              </button>
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
