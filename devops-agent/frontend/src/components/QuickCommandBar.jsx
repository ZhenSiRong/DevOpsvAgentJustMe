import {
  Activity,
  HardDrive,
  MemoryStick,
  Network,
  FileText,
  Timer,
  FolderOpen,
  Globe,
  ShieldAlert,
  Trash2,
  ChevronRight,
} from 'lucide-react'
import { useState } from 'react'

const COMMAND_GROUPS = [
  {
    label: '系统',
    items: [
      { label: 'top', cmd: 'top -b -n1 | head -20', icon: Activity },
      { label: 'df', cmd: 'df -h', icon: HardDrive },
      { label: 'free', cmd: 'free -h', icon: MemoryStick },
      { label: 'uptime', cmd: 'uptime', icon: Timer },
    ],
  },
  {
    label: '进程网络',
    items: [
      { label: 'ps', cmd: "ps aux | head -20", icon: Activity },
      { label: 'ss', cmd: 'ss -tunlp', icon: Network },
      { label: 'netstat', cmd: 'netstat -tunlp', icon: Globe },
      { label: 'lsof', cmd: 'lsof -i -P -n | head -20', icon: ShieldAlert },
    ],
  },
  {
    label: '日志文件',
    items: [
      { label: 'journal', cmd: 'journalctl -n 50 --no-pager', icon: FileText },
      { label: 'ls', cmd: 'ls -la', icon: FolderOpen },
      { label: 'pwd', cmd: 'pwd', icon: FolderOpen },
      { label: 'du', cmd: 'du -sh /var/log /tmp 2>/dev/null', icon: HardDrive },
    ],
  },
  {
    label: '清理',
    items: [
      { label: 'tmp', cmd: 'find /tmp -type f -atime +7', icon: Trash2 },
    ],
  },
]

export default function QuickCommandBar({ onRunCommand }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="border-t border-slate-800 bg-slate-900/90">
      {/* 折叠栏 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-[11px] text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors"
      >
        <span className="font-medium">快捷命令</span>
        <ChevronRight
          className={`w-3 h-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
        />
      </button>

      {expanded && (
        <div className="px-3 pb-2 flex flex-wrap gap-2">
          {COMMAND_GROUPS.map((group) => (
            <div key={group.label} className="flex items-center gap-1">
              <span className="text-[10px] text-slate-600 font-medium uppercase tracking-wider mr-1">
                {group.label}
              </span>
              {group.items.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.label}
                    onClick={() => onRunCommand(item.cmd)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                      bg-slate-800 hover:bg-slate-700
                      border border-slate-700 hover:border-slate-600
                      text-[11px] text-slate-300 hover:text-slate-100
                      transition-colors"
                    title={item.cmd}
                  >
                    <Icon className="w-3 h-3" />
                    {item.label}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
