import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  MessageSquare,
  Search,
  Shield,
  ClipboardList,
  GitBranch,
  Server,
  Menu,
  X,
  Settings,
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { path: '/', label: 'Agent 对话', icon: MessageSquare },
  { path: '/probe', label: 'OS 探针', icon: Search },
  { path: '/safety', label: '安全中心', icon: Shield },
  { path: '/audit', label: '审计日志', icon: ClipboardList },
  { path: '/reasoning', label: '推理链路', icon: GitBranch },
  { path: '/settings', label: '系统设置', icon: Settings },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800
          transform transition-transform duration-200 lg:transform-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          flex flex-col
        `}
      >
        <div className="flex items-center gap-3 px-4 h-14 border-b border-slate-800">
          <Server className="w-6 h-6 text-primary-400" />
          <span className="font-semibold text-lg">DevOps Agent</span>
          <button
            className="lg:hidden ml-auto text-slate-400 hover:text-white"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                  ${isActive
                    ? 'bg-primary-900/30 text-primary-300 border border-primary-800/50'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50'
                  }
                `}
              >
                <Icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        <div className="px-4 py-3 border-t border-slate-800 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            服务在线
          </div>
          <div className="mt-1">v0.1.0 · Kylin V11</div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-slate-800 flex items-center px-4 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-slate-400 hover:text-white"
          >
            <Menu className="w-6 h-6" />
          </button>
          <span className="ml-3 font-medium">DevOps Agent</span>
        </header>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
