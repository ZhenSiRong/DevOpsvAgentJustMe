import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Shield, Loader2, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

/**
 * 登录页面
 *
 * 使用场景：
 * - 首次访问：直接进入登录页
 * - Token 过期：PrivateRoute 重定向到 /login?redirect=xxx
 */
export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // 已登录则直接跳转
  if (isAuthenticated) {
    const from = location.state?.from?.pathname || '/'
    navigate(from, { replace: true })
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    setError('')
    setLoading(true)

    try {
      await login(username.trim(), password)
      const from = location.state?.from?.pathname || '/'
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="w-full max-w-md px-6">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-600 to-purple-600 mb-4">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-xl font-medium text-slate-100">DevOps Agent</h1>
          <p className="text-sm text-slate-500 mt-1">安全智能运维平台</p>
        </div>

        {/* 登录表单 */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="text-sm font-medium text-slate-300 mb-4">账号登录</h2>

          {error && (
            <div className="flex items-center gap-2 px-3 py-2 mb-4 rounded-lg bg-red-900/20 border border-red-800/30">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-xs text-red-300">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">用户名</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                placeholder="admin"
                autoFocus
                disabled={loading}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">密码</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                placeholder="输入密码"
                disabled={loading}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  登录中...
                </>
              ) : (
                '登录'
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          DevOps Agent v0.1.0 — 面向国产化环境的运维智能体
        </p>
      </div>
    </div>
  )
}

export default LoginPage
