import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
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
  PanelLeftOpen,
  PanelLeftClose,
  Plug,
  Network,
  LogOut,
  Brain,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

const navItems = [
  { path: '/', label: 'Agent 对话', icon: MessageSquare },
  { path: '/probe', label: 'OS 探针', icon: Search },
  { path: '/safety', label: '安全中心', icon: Shield },
  { path: '/audit', label: '审计日志', icon: ClipboardList },
  { path: '/reasoning', label: '推理链路', icon: GitBranch },
  { path: '/orchestrator', label: '任务编排', icon: Network },
  { path: '/mcp', label: 'MCP 管理', icon: Plug },
  { path: '/evolution', label: '自演进', icon: Brain },
  { path: '/skills', label: 'Skills', icon: Sparkles },
  { path: '/settings', label: '系统设置', icon: Settings },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [navCollapsed, setNavCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { logout, user } = useAuth()

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
          fixed lg:static inset-y-0 left-0 z-50 bg-slate-900 border-r border-slate-800
          transform transition-all duration-200 lg:transform-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          ${navCollapsed ? 'w-16' : 'w-64'}
          flex flex-col
        `}
      >
        {/* Logo 区域 */}
        <div className="flex items-center h-14 border-b border-slate-800 shrink-0">
          <div className={`flex items-center gap-3 ${navCollapsed ? 'justify-center w-full px-0' : 'px-4'}`}>
            <Server className="w-6 h-6 text-primary-400 shrink-0" />
            {!navCollapsed && (
              <span className="font-semibold text-lg whitespace-nowrap overflow-hidden">DevOps Agent</span>
            )}
          </div>
          <button
            className="lg:hidden ml-auto mr-3 text-slate-400 hover:text-white"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 导航菜单 */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-hidden">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                title={item.label}
                className={`
                  flex items-center rounded-lg text-sm font-medium transition-colors
                  ${navCollapsed ? 'justify-center px-2 py-2.5' : 'gap-3 px-3 py-2.5'}
                  ${isActive
                    ? 'bg-primary-900/30 text-primary-300 border border-primary-800/50'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50'
                  }
                `}
              >
                <Icon className="w-5 h-5 shrink-0" />
                {!navCollapsed && <span className="whitespace-nowrap overflow-hidden">{item.label}</span>}
              </NavLink>
            )
          })}
        </nav>

        {/* 折叠按钮 + 底部信息 */}
        <div className="shrink-0 border-t border-slate-800">
          <button
            onClick={() => setNavCollapsed(v => !v)}
            className={`w-full flex items-center text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors text-xs ${
              navCollapsed ? 'justify-center py-3 px-0' : 'gap-2 px-4 py-2.5'
            }`}
            title={navCollapsed ? '展开导航栏' : '收起导航栏'}
          >
            {navCollapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <>
                <PanelLeftClose className="w-4 h-4" />
                <span>收起导航</span>
              </>
            )}
          </button>

          {/* 登出按钮 */}
          {!navCollapsed && (
            <div className="px-3 pb-2">
              <button
                onClick={() => { logout(); navigate('/login'); }}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-red-400 hover:bg-slate-800/50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span>登出{user ? ` (${user.username})` : ''}</span>
              </button>
            </div>
          )}

          {!navCollapsed && (
            <div className="px-4 py-3 text-xs text-slate-500">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                服务在线
              </div>
              <div className="mt-1">v0.1.0 · Kylin V11</div>
            </div>
          )}
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
