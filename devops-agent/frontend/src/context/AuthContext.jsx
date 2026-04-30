import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const API_BASE = '/api/v1'

const AuthContext = createContext(null)

/**
 * 认证上下文 Provider
 *
 * 提供：
 * - user: 当前用户信息 { username, role } | null
 * - token: JWT token 字符串 | null
 * - login(username, password): 登录
 * - logout(): 登出
 * - isAuthenticated: 是否已认证
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  // 初始化时校验已有 token 是否有效
  useEffect(() => {
    if (token) {
      fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(res => res.json())
        .then(data => {
          if (data.code === 0 && data.data) {
            setUser(data.data)
          } else {
            // Token 无效，清除
            localStorage.removeItem('auth_token')
            setToken(null)
            setUser(null)
          }
        })
        .catch(() => {
          localStorage.removeItem('auth_token')
          setToken(null)
          setUser(null)
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [token])

  const login = useCallback(async (username, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json()
    if (!res.ok || data.code !== 0) {
      throw new Error(data.detail || data.message || '登录失败')
    }
    const newToken = data.data.access_token
    localStorage.setItem('auth_token', newToken)
    setToken(newToken)
    setUser({ username, role: 'admin' })
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAuthenticated: !!user, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用')
  }
  return ctx
}

export default AuthContext
