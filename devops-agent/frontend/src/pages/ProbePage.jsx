import { useState } from 'react'
import {
  HardDrive,
  Activity,
  Network,
  FileText,
  Loader2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react'
import { probeDisk, probeProcesses, probeNetwork, probeLogs } from '../api/client'

const tabs = [
  { key: 'disk', label: '磁盘', icon: HardDrive },
  { key: 'process', label: '进程', icon: Activity },
  { key: 'network', label: '网络', icon: Network },
  { key: 'logs', label: '日志', icon: FileText },
]

export default function ProbePage() {
  const [activeTab, setActiveTab] = useState('disk')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const [diskPath, setDiskPath] = useState('/var/log')
  const [procFilter, setProcFilter] = useState('')
  const [netAction, setNetAction] = useState('connections')
  const [netHost, setNetHost] = useState('')
  const [logUnit, setLogUnit] = useState('system')
  const [logLines, setLogLines] = useState(50)
  const [logGrep, setLogGrep] = useState('')

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      let res
      switch (activeTab) {
        case 'disk':
          res = await probeDisk(diskPath)
          break
        case 'process':
          res = await probeProcesses({ filter_by_name: procFilter || undefined, limit: 50 })
          break
        case 'network':
          res = await probeNetwork(netAction, netHost || undefined)
          break
        case 'logs':
          res = await probeLogs({ unit: logUnit, lines: logLines, grep: logGrep || undefined })
          break
        default:
          return
      }
      if (res.code === 0) {
        setData(res.data)
      } else {
        setError(res.message || '请求失败')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const renderDisk = () => {
    if (!data) return null
    const usage = data.usage || {}
    const largeFiles = data.large_files || []
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: '总空间', value: usage.total_human || '-' },
            { label: '已用', value: usage.used_human || '-' },
            { label: '可用', value: usage.free_human || '-' },
            { label: '使用率', value: `${usage.percent || 0}%` },
          ].map(item => (
            <div key={item.label} className="bg-slate-800/50 border border-slate-800 rounded-xl p-4">
              <div className="text-xs text-slate-500 mb-1">{item.label}</div>
              <div className="text-lg font-semibold text-slate-200">{item.value}</div>
            </div>
          ))}
        </div>

        {usage.percent !== undefined && (
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-slate-400">磁盘使用率</span>
              <span className={usage.percent > 90 ? 'text-red-400' : usage.percent > 70 ? 'text-amber-400' : 'text-emerald-400'}>
                {usage.percent}%
              </span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  usage.percent > 90 ? 'bg-red-500' : usage.percent > 70 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.min(usage.percent, 100)}%` }}
              />
            </div>
          </div>
        )}

        {largeFiles.length > 0 && (
          <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 font-medium text-sm">大文件 TOP {largeFiles.length}</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-900/50 text-slate-400">
                <tr>
                  <th className="text-left px-4 py-2">路径</th>
                  <th className="text-right px-4 py-2">大小</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {largeFiles.map((f, i) => (
                  <tr key={i} className="hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono text-xs text-slate-300 truncate max-w-[300px]">{f.path}</td>
                    <td className="px-4 py-2 text-right text-slate-400">{f.size_human}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  const renderProcess = () => {
    if (!data) return null
    const processes = data.processes || []
    return (
      <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-sm text-slate-400">
          共 {data.count || processes.length} 个进程
          {data.filter && data.filter !== 'all' && ` · 过滤: ${data.filter}`}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">PID</th>
                <th className="text-left px-4 py-2">名称</th>
                <th className="text-right px-4 py-2">CPU%</th>
                <th className="text-right px-4 py-2">MEM%</th>
                <th className="text-left px-4 py-2">用户</th>
                <th className="text-left px-4 py-2">命令</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {processes.slice(0, 100).map((p, i) => (
                <tr key={i} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2 font-mono text-slate-300">{p.pid}</td>
                  <td className="px-4 py-2 text-slate-200 font-medium">{p.name}</td>
                  <td className={`px-4 py-2 text-right font-mono ${(p.cpu_percent || 0) > 50 ? 'text-red-400' : 'text-slate-300'}`}>
                    {(p.cpu_percent || 0).toFixed(1)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-slate-300">{(p.memory_percent || 0).toFixed(1)}</td>
                  <td className="px-4 py-2 text-slate-400">{p.username}</td>
                  <td className="px-4 py-2 text-slate-500 font-mono text-xs truncate max-w-[200px]">{p.cmdline}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const renderNetwork = () => {
    if (!data) return null
    if (netAction === 'dns') {
      const dns = data.dns || {}
      return (
        <div className="bg-slate-800/50 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="text-sm"><span className="text-slate-500">主机:</span> <span className="text-slate-200">{dns.hostname}</span></div>
          <div className="text-sm"><span className="text-slate-500">解析时间:</span> <span className="text-slate-200">{dns.resolve_time_ms}ms</span></div>
          <div>
            <div className="text-sm text-slate-500 mb-1">IP 地址:</div>
            <div className="space-y-1">
              {(dns.ips || []).map((ip, i) => (
                <div key={i} className="font-mono text-sm text-primary-300 bg-primary-900/20 px-3 py-1.5 rounded-lg inline-block mr-2">{ip}</div>
              ))}
            </div>
          </div>
        </div>
      )
    }

    if (netAction === 'interfaces') {
      const ifaces = data.interfaces || []
      return (
        <div className="space-y-3">
          {ifaces.map((iface, i) => (
            <div key={i} className="bg-slate-800/50 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2 h-2 rounded-full ${iface.state === 'UP' ? 'bg-emerald-500' : 'bg-slate-500'}`} />
                <span className="font-medium text-slate-200">{iface.name}</span>
                <span className="text-xs text-slate-500">{iface.state}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {(iface.addresses || []).map((addr, j) => (
                  <div key={j} className="font-mono text-slate-400 text-xs">{addr}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )
    }

    const conns = data.connections || []
    return (
      <div className="bg-slate-800/50 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-sm text-slate-400">共 {data.count || conns.length} 个连接</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">协议</th>
                <th className="text-left px-4 py-2">本地地址</th>
                <th className="text-left px-4 py-2">远程地址</th>
                <th className="text-left px-4 py-2">状态</th>
                <th className="text-left px-4 py-2">进程</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {conns.slice(0, 200).map((c, i) => (
                <tr key={i} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2"><span className="text-xs bg-slate-700 px-2 py-0.5 rounded">{c.proto}</span></td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-300">{c.local_addr}</td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-300">{c.remote_addr}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs ${c.state === 'ESTAB' ? 'text-emerald-400' : 'text-slate-400'}`}>{c.state}</span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-400">{c.process_name} ({c.pid})</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const renderLogs = () => {
    if (!data) return null
    const logs = data.logs || []
    return (
      <div className="space-y-3">
        <div className="text-sm text-slate-500">
          模式: {data.mode} · 共 {data.count || logs.length} 条
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-1 max-h-[600px] overflow-y-auto scrollbar-thin">
          {logs.map((log, i) => (
            <div key={i} className="text-slate-300 break-all">{log.message || log.raw || String(log)}</div>
          ))}
        </div>
      </div>
    )
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'disk': return renderDisk()
      case 'process': return renderProcess()
      case 'network': return renderNetwork()
      case 'logs': return renderLogs()
      default: return null
    }
  }

  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100 mb-1">OS 探针</h1>
        <p className="text-sm text-slate-500">只读查询系统状态，不修改任何配置</p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-6 border-b border-slate-800 pb-1">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key); setData(null); setError(null) }}
              className={`
                flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors
                ${activeTab === tab.key
                  ? 'text-primary-300 border-b-2 border-primary-500'
                  : 'text-slate-400 hover:text-slate-200'
                }
              `}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* 参数控制区 */}
      <div className="bg-slate-800/30 border border-slate-800 rounded-xl p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          {activeTab === 'disk' && (
            <>
              <div>
                <label className="block text-xs text-slate-500 mb-1">路径</label>
                <input
                  value={diskPath}
                  onChange={(e) => setDiskPath(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-primary-500/50"
                />
              </div>
            </>
          )}
          {activeTab === 'process' && (
            <>
              <div>
                <label className="block text-xs text-slate-500 mb-1">进程名过滤</label>
                <input
                  value={procFilter}
                  onChange={(e) => setProcFilter(e.target.value)}
                  placeholder="留空显示全部"
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-primary-500/50"
                />
              </div>
            </>
          )}
          {activeTab === 'network' && (
            <>
              <div>
                <label className="block text-xs text-slate-500 mb-1">操作</label>
                <select
                  value={netAction}
                  onChange={(e) => setNetAction(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-primary-500/50"
                >
                  <option value="connections">连接列表</option>
                  <option value="interfaces">网络接口</option>
                  <option value="dns">DNS 解析</option>
                </select>
              </div>
              {netAction === 'dns' && (
                <div>
                  <label className="block text-xs text-slate-500 mb-1">主机名</label>
                  <input
                    value={netHost}
                    onChange={(e) => setNetHost(e.target.value)}
                    placeholder="example.com"
                    className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-primary-500/50"
                  />
                </div>
              )}
            </>
          )}
          {activeTab === 'logs' && (
            <>
              <div>
                <label className="block text-xs text-slate-500 mb-1">日志单元</label>
                <select
                  value={logUnit}
                  onChange={(e) => setLogUnit(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                >
                  <option value="system">system</option>
                  <option value="kernel">kernel</option>
                  <option value="user">user</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">行数</label>
                <input
                  type="number"
                  value={logLines}
                  onChange={(e) => setLogLines(Number(e.target.value))}
                  min={1}
                  max={1000}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 w-24"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">关键词过滤</label>
                <input
                  value={logGrep}
                  onChange={(e) => setLogGrep(e.target.value)}
                  placeholder="grep 关键词"
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-primary-500/50"
                />
              </div>
            </>
          )}
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:bg-slate-700 rounded-lg text-sm font-medium text-white transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            查询
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-6 flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-800/30 rounded-xl text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* 数据展示 */}
      {renderContent()}

      {!data && !loading && !error && (
        <div className="text-center py-16 text-slate-600">
          <RefreshCw className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm">点击"查询"获取数据</p>
        </div>
      )}
    </div>
  )
}
