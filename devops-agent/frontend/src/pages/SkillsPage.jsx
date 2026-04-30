import { useState, useEffect } from 'react'
import { Sparkles, Loader2, FolderOpen } from 'lucide-react'

export default function SkillsPage() {
  const [loading, setLoading] = useState(true)

  useEffect(() => { setLoading(false) }, [])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-primary-400" /></div>

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-3"><Sparkles className="w-7 h-7 text-primary-400" />Agent Skills</h1>

      <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
        <h2 className="font-semibold mb-4 flex items-center gap-2"><FolderOpen className="w-5 h-5" />Skills 目录结构</h2>
        <pre className="text-sm text-slate-400 font-mono bg-slate-800/50 p-4 rounded-lg overflow-x-auto">
{`skills/
├── disk-cleanup/
│   └── SKILL.md          # YAML frontmatter + Markdown 指令
├── network-troubleshoot/
│   └── SKILL.md
└── ...
`}
        </pre>
        <p className="text-sm text-slate-500 mt-4">
          Skills 目录: <code className="text-primary-400 bg-slate-800 px-1 rounded">./skills/</code>
        </p>
      </div>

      <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
        <h2 className="font-semibold mb-4">已加载的 Skills</h2>
        <div className="space-y-2">
          <div className="p-3 rounded bg-slate-800/50 border border-slate-700">
            <div className="font-medium text-slate-200">disk-cleanup</div>
            <div className="text-sm text-slate-400 mt-1">磁盘空间清理工作流：分析 → 分类 → 清理 → 报告</div>
          </div>
        </div>
      </div>

      <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
        <h2 className="font-semibold mb-4">如何添加新 Skill</h2>
        <ol className="list-decimal list-inside text-sm text-slate-400 space-y-2">
          <li>在 <code className="text-primary-400">skills/</code> 目录下创建 <code className="text-primary-400">{`{skill-name}/`}</code> 文件夹</li>
          <li>在文件夹中创建 <code className="text-primary-400">SKILL.md</code> 文件</li>
          <li>编写 YAML frontmatter 和 Markdown 指令：</li>
        </ol>
        <pre className="text-sm text-slate-400 font-mono bg-slate-800/50 p-4 rounded-lg mt-4 overflow-x-auto">
{`---
name: my-skill
description: "当用户需要 X 时使用此技能。"
---

# 我的技能

## 适用场景
...

## 工作流
1. ...
2. ...
`}
        </pre>
      </div>
    </div>
  )
}
