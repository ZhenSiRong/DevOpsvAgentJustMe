import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { MessageSquare } from 'lucide-react'
import { executeCommand } from '../api/client'
import '@xterm/xterm/css/xterm.css'

const PROMPT = '\r\n\x1b[1;32mroot@kylin\x1b[0m:\x1b[1;34m~\x1b[0m# '

const TerminalPanel = forwardRef(function TerminalPanel({ visible, chatCollapsed, onExpandChat }, ref) {
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const fitAddonRef = useRef(null)
  const inputBufferRef = useRef('')
  const historyRef = useRef([])
  const historyIndexRef = useRef(-1)
  const isExecutingRef = useRef(false) // 用 ref 替代 state，避免 useEffect 不稳定依赖
  const [isReady, setIsReady] = useState(false)
  const [isExecuting, setIsExecuting] = useState(false) // 仅用于 UI 状态显示

  // 稳定引用：不依赖外部 state，避免触发 useEffect 重跑
  const writePromptStable = useRef(() => {
    if (termRef.current) {
      termRef.current.write(PROMPT)
    }
  })

  const runCommandStable = useRef(async (cmd) => {
    if (isExecutingRef.current) return
    if (!termRef.current) return
    if (!cmd.trim()) {
      writePromptStable.current()
      return
    }

    isExecutingRef.current = true
    setIsExecuting(true)
    const term = termRef.current

    try {
      const res = await executeCommand(cmd.trim(), 30, false, null)
      const data = res.data || res
      if (data.stdout) {
        term.write('\r\n' + data.stdout)
      }
      if (data.stderr) {
        term.write('\r\n\x1b[1;31m' + data.stderr + '\x1b[0m')
      }
      if (data.status === 'BLOCKED' || data.status === 'REJECTED') {
        term.write('\r\n\x1b[1;31m[安全拦截] ' + (data.error_message || data.status) + '\x1b[0m')
      }
      if (data.exit_code !== undefined && data.exit_code !== 0 && data.exit_code !== null) {
        term.write('\r\n\x1b[1;31mexit code: ' + data.exit_code + '\x1b[0m')
      }
    } catch (err) {
      term.write('\r\n\x1b[1;31mError: ' + (err.message || String(err)) + '\x1b[0m')
    } finally {
      isExecutingRef.current = false
      setIsExecuting(false)
      writePromptStable.current()
    }
  })

  // 初始化终端（只执行一次，依赖为空数组）
  useEffect(() => {
    if (!containerRef.current || termRef.current) return

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'JetBrains Mono, "Fira Code", Consolas, monospace',
      fontSize: 13,
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
        cursor: '#38bdf8',
        selectionBackground: '#334155',
        black: '#020617',
        red: '#ef4444',
        green: '#22c55e',
        yellow: '#eab308',
        blue: '#3b82f6',
        magenta: '#a855f7',
        cyan: '#06b6d4',
        white: '#f1f5f9',
      },
      scrollback: 5000,
      rows: 24,
      cols: 80,
      allowProposedApi: true,
      convertEol: true,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)

    term.open(containerRef.current)
    fitAddon.fit()

    term.writeln('\x1b[1;36m╔══════════════════════════════════════════╗\x1b[0m')
    term.writeln('\x1b[1;36m║     DevOps Agent — 安全运维终端          ║\x1b[0m')
    term.writeln('\x1b[1;36m╚══════════════════════════════════════════╝\x1b[0m')
    term.writeln('\x1b[2m提示：命令通过安全校验器执行，危险操作将被拦截。\x1b[0m')
    term.writeln('')

    term.onData((data) => {
      const code = data.charCodeAt(0)

      if (data === '\r' || data === '\n') {
        const cmd = inputBufferRef.current
        historyRef.current.push(cmd)
        historyIndexRef.current = historyRef.current.length
        inputBufferRef.current = ''
        term.write('\r\n')
        runCommandStable.current(cmd)
        return
      }

      if (data === '\x7f' || data === '\b') {
        if (inputBufferRef.current.length > 0) {
          inputBufferRef.current = inputBufferRef.current.slice(0, -1)
          term.write('\b \b')
        }
        return
      }

      if (data === '\x03') {
        inputBufferRef.current = ''
        term.write('^C')
        term.write('\r\n')
        writePromptStable.current()
        return
      }

      if (data === '\x0c') {
        term.clear()
        writePromptStable.current()
        return
      }

      if (data === '\x1b[A') {
        if (historyRef.current.length === 0) return
        if (historyIndexRef.current > 0) {
          historyIndexRef.current -= 1
        }
        const prev = historyRef.current[historyIndexRef.current] || ''
        const currentLen = inputBufferRef.current.length
        for (let i = 0; i < currentLen; i++) term.write('\b \b')
        inputBufferRef.current = prev
        term.write(prev)
        return
      }

      if (data === '\x1b[B') {
        if (historyRef.current.length === 0) return
        if (historyIndexRef.current < historyRef.current.length - 1) {
          historyIndexRef.current += 1
          const next = historyRef.current[historyIndexRef.current] || ''
          const currentLen = inputBufferRef.current.length
          for (let i = 0; i < currentLen; i++) term.write('\b \b')
          inputBufferRef.current = next
          term.write(next)
        } else {
          historyIndexRef.current = historyRef.current.length
          const currentLen = inputBufferRef.current.length
          for (let i = 0; i < currentLen; i++) term.write('\b \b')
          inputBufferRef.current = ''
        }
        return
      }

      if (code < 32 && data !== '\t') {
        return
      }

      inputBufferRef.current += data
      term.write(data)
    })

    termRef.current = term
    fitAddonRef.current = fitAddon
    setIsReady(true)
    writePromptStable.current()

    const handleResize = () => {
      try { fitAddon.fit() } catch (e) { /* ignore */ }
    }
    window.addEventListener('resize', handleResize)

    const ro = new ResizeObserver(() => {
      try { fitAddon.fit() } catch (e) { /* ignore */ }
    })
    if (containerRef.current) {
      ro.observe(containerRef.current)
    }

    return () => {
      window.removeEventListener('resize', handleResize)
      ro.disconnect()
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
    }
  }, [])  // 空依赖：终端只初始化一次，函数引用通过 ref 稳定化

  // 暴露方法给父组件（通过 ref 稳定引用）
  useImperativeHandle(ref, () => ({
    runCommand: (cmd) => {
      if (termRef.current) {
        termRef.current.write(cmd)
        termRef.current.write('\r\n')
      }
      runCommandStable.current(cmd)
    },
  }))

  // 当面板从隐藏变为显示时，重新 fit
  useEffect(() => {
    if (visible && fitAddonRef.current) {
      // 延迟执行，等 DOM 渲染完成
      const timer = setTimeout(() => {
        try {
          fitAddonRef.current.fit()
        } catch (e) {
          // ignore
        }
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [visible])

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* 终端标题栏 */}
      <div className="flex items-center justify-between px-3 h-9 border-b border-slate-800 bg-slate-900/80">
        <div className="flex items-center gap-2">
          {chatCollapsed && onExpandChat && (
            <button
              onClick={onExpandChat}
              className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] text-primary-300 hover:text-primary-200 hover:bg-primary-900/30 rounded transition-colors"
              title="展开聊天"
            >
              <MessageSquare className="w-3 h-3" />
              <span>展开聊天</span>
            </button>
          )}
          <div className={`w-2 h-2 rounded-full ${isExecuting ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'}`} />
            <span className="text-xs text-amber-400">执行中...</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              if (termRef.current) {
                termRef.current.clear()
                writePromptStable.current()
              }
            }}
            className="px-2 py-0.5 text-[10px] text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            title="清屏"
          >
            清屏
          </button>
        </div>
      </div>

      {/* 终端画布 */}
      <div className="flex-1 relative min-h-0">
        <div
          ref={containerRef}
          className="absolute inset-0 p-2"
          style={{ opacity: isReady ? 1 : 0, transition: 'opacity 0.2s' }}
        />
        {!isReady && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
            终端初始化中...
          </div>
        )}
      </div>
    </div>
  )
})

export default TerminalPanel
