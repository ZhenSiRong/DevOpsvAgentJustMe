"""
安全规则库 —— 安全校验器的规则定义

三层防护体系：
1. 路径保护规则 (PathProtectionRule)：拦截对危险路径的操作
2. 危险模式匹配规则 (DangerPatternRule)：正则匹配危险命令模式
3. 权限白名单规则 (SudoAllowlistRule)：sudo 命令白名单检查

每条规则包含：
- rule_id: 唯一编号（如 PATH-001）
- name: 规则名称
- description: 规则描述
- severity: 严重程度（CRITICAL / HIGH / MEDIUM / LOW）
- check(command) -> ValidationResult | None: 校验函数，返回 None 表示不命中
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class RuleSeverity(Enum):
    CRITICAL = "CRITICAL"   # 必须拦截，无条件 BLOCKED
    HIGH = "HIGH"           # 强烈建议拦截
    MEDIUM = "MEDIUM"       # 需要关注
    LOW = "LOW"             # 信息提示


@dataclass
class SecurityRule:
    """安全规则的基类数据结构"""
    rule_id: str
    name: str
    description: str
    severity: RuleSeverity

    def check(self, command: str) -> tuple[bool, str]:
        """
        检查命令是否违反本规则。
        返回: (is_violated, reason)
        - is_violated=True 表示违反了此规则
        - reason 是人类可读的原因说明
        """
        raise NotImplementedError


# ============================================================
#  第一层：路径保护规则
# ============================================================

# 需要绝对保护的系统关键路径
PROTECTED_PATHS: list[dict] = [
    {
        "rule_id": "PATH-001",
        "name": "根目录删除保护",
        "pattern": r"rm\s+(-[a-zA-Z]*\s*)*[/]$|rm\s+(-[a-zA-Z]*\s)+-r\s*[/]|rm\s+-rf\s+[/]\s*$",
        "description": "禁止任何形式的根目录(/)删除操作",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "危险操作：根目录删除被禁止。命令 '{cmd}' 可能导致系统毁灭性破坏。",
    },
    {
        "rule_id": "PATH-002",
        "name": "数据库数据目录保护",
        "pattern": r"rm\s+.*?/var/lib/mysql/|rm\s+.*?/var/lib/postgresql/|rm\s+.*?/data/(mysql|postgres|mongodb)/",
        "description": "禁止删除数据库数据目录下的文件",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "危险操作：数据库数据目录不可删除。'{path}' 包含重要业务数据。",
    },
    {
        "rule_id": "PATH-003",
        "name": "系统引导目录保护",
        "pattern": r"rm\s+.*?/boot/|rm\s+.*?/efi/",
        "description": "禁止删除系统引导文件",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "危险操作：系统引导目录不可修改。可能导致系统无法启动。",
    },
    {
        "rule_id": "PATH-004",
        "name": "日志目录删除保护",
        "pattern": r"rm\s+(-[a-zA-Z]*\s*)*.*/var/log/|find\s+.*/var/log/.*\s+-delete|find\s+.*/var/log/.*\s+-exec\s+rm",
        "description": "禁止删除系统日志目录下的文件（日志轮转由 logrotate 管理）",
        "severity": RuleSeverity.HIGH,
        "reason_template": "危险操作：系统日志目录 /var/log/ 不可手动删除。日志是运维审计和故障排查的基础。",
    },
    {
        "rule_id": "PATH-005",
        "name": "数据库目录 find-delete 保护",
        "pattern": r"find\s+.*/var/lib/mysql/.*\s+-delete|find\s+.*/var/lib/mysql/.*\s+-exec\s+rm|find\s+.*/var/lib/postgresql/.*\s+-delete",
        "description": "禁止通过 find -delete 绕过删除数据库文件",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "危险操作：数据库数据目录不可通过任何方式删除。'{path}' 包含重要业务数据。",
    },
]

# 敏感配置文件列表（修改权限或删除都会触发）
SENSITIVE_FILES: list[dict] = [
    {
        "rule_id": "FILE-001",
        "name": "/etc/passwd 保护",
        "patterns": [r"chmod.*?/etc/passwd", r"chown.*?/etc/passwd", r"rm.*?/etc/passwd"],
        "description": "禁止修改 /etc/passwd 文件权限",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "敏感配置文件 /etc/passwd 不可修改，这是账户安全的基础。",
    },
    {
        "rule_id": "FILE-002",
        "name": "/etc/shadow 保护",
        "patterns": [r"chmod.*?/etc/shadow", r"chown.*?/etc/shadow", r"rm.*?/etc/shadow"],
        "description": "禁止修改 /etc/shadow 密码文件",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "敏感配置文件 /etc/shadow 包含用户密码哈希，绝对不可修改。",
    },
    {
        "rule_id": "FILE-003",
        "name": "SSH 配置保护",
        "patterns": [
            r"chmod.*?/etc/ssh/sshd_config",
            r"rm.*?/authorized_keys",
            r".*?>\s*/etc/ssh/sshd_config",   # 重定向写入
        ],
        "description": "禁止修改 SSH 服务端配置",
        "severity": RuleSeverity.HIGH,
        "reason_template": "SSH 配置变更可能导致远程访问中断或安全漏洞。",
    },
]


# ============================================================
#  第二层：危险命令模式正则表
# ============================================================

DANGER_PATTERNS: list[dict] = [
    {
        "rule_id": "CMD-001",
        "name": "dd 破坏性写盘",
        "pattern": r"dd\s+if=.*of=/dev/[sd]",
        "description": "禁止 dd 直接写磁盘设备",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "'dd' 写入磁盘设备可能覆盖整个分区，这是破坏性操作。",
    },
    {
        "rule_id": "CMD-002",
        "name": "mkfs 格式化",
        "pattern": r"mkfs(\.[ext|xfs|btrfs|ntfs|fat]+)?\s+/dev/",
        "description": "禁止格式化磁盘分区",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "格式化操作将清除分区内所有数据且不可恢复。",
    },
    {
        "rule_id": "CMD-003",
        "name": ":(){ :|:& };: fork bomb",
        "pattern": r"\{?\s*\}\s*[|&]",
        "description": "检测 fork bomb 模式",
        "severity": RuleSeverity.CRITICAL,
        "reason_template": "检测到可能的 fork bomb 模式，将耗尽所有系统资源。",
    },
    {
        "rule_id": "CMD-004",
        "name": "历史记录清除",
        "pattern": r">(?:unset\s+HISTFILE|history\s+-c|shred\s+.*bash_history|rm\s+.*bash_history)",
        "description": "检测清除 shell 历史记录的尝试",
        "severity": RuleSeverity.HIGH,
        "reason_template": "清除操作历史记录违反审计要求，所有操作应可追溯。",
    },
    {
        "rule_id": "CMD-005",
        "name": "包管理器安装/卸载",
        "pattern": r"(?:apt-get|yum|dnf|pacman)\s+(?:install|remove|purge|erase)\s",
        "description": "软件包安装/卸载需要审批",
        "severity": RuleSeverity.HIGH,
        "reason_template": "系统软件变更需要通过正规流程，不允许 Agent 自行安装/卸载软件包。",
    },
]


# ============================================================
#  第三层：只读白名单（这些命令模式不需要深度校验）
# ============================================================

READONLY_WHITELIST_PATTERNS: list[str] = [
    # 磁盘信息
    r"^df\b",
    r"^du\b",
    r"^ls\b",
    r"^find\b(?!.*(?:-delete|-exec\s+rm))",  # find 但不带 -delete 或 -exec rm
    # 进程查看
    r"^ps\b",
    r"^top\b",
    r"^htop\b",
    r"^pgrep\b",
    r"^pidstat\b",
    # 网络状态
    r"^netstat\b",
    r"^ss\b",
    r"^ip\b(?:\s+(?:addr|link|route|neigh))",  # ip addr/link/route 只读子命令
    # 日志查看
    r"^journalctl\b",
    r"^cat\b",
    r"^less\b",
    r"^more\b",
    r"^head\b",
    r"^tail\b",
    r"^grep\b",
    r"^egrep\b",
    r"^fgrep\b",
    r"^wc\b",
    r"^sort\b",
    r"^uniq\b",
    r"^cut\b",
    r"^awk\b",
    r"^sed\b(?!.*>.*(?:/etc/|/usr/bin/))",  # sed 不写敏感路径
    r"^file\b",
    r"^stat\b",
    r"^strings\b",
    r"^hexdump\b",
    r"^od\b",
    # 系统状态
    r"^systemctl\s+status",
    r"^uptime\b",
    r"^free\b",
    r"^vmstat\b",
    r"^iostat\b",
    r"^mpstat\b",
    r"^who\b",
    r"^w\b",
    r"^id\b",
    r"^whoami\b",
    r"^date\b",
    r"^uname\b",
    r"^hostnamectl\b",
    # DNS 解析
    r"^dig\b",
    r"^nslookup\b",
    r"^host\b",
    r"^getent\b",
]


def is_readonly_command(command: str) -> bool:
    """判断是否为只读探针命令（不需要深度校验）"""
    cmd_stripped = command.strip()
    for pattern in READONLY_WHITELIST_PATTERNS:
        if re.match(pattern, cmd_stripped):
            return True
    return False


# ============================================================
#  Sudo 白名单（允许提权的命令列表）
# ============================================================

DEFAULT_SUDO_ALLOWLIST: list[str] = [
    "logrotate",
    "systemctl status",
    "systemctl restart",
    "systemctl start",
    "systemctl stop",
    "journalctl",
    "df",
    "du",
    "ps",
    "netstat",
    "ss",
    "cat",
    "ls",
    "find",
    "grep",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "cut",
    "awk",
    "sed",
]


def matches_sudo_allowlist(command: str, allowlist: list[str] | None = None) -> bool:
    """
    检查命令是否在 sudo 白名单中。
    
    匹配逻辑：
    - 如果命令以白名单中任一前缀开头 → 匹配
    - 例如 allowlist 含 "systemctl restart"，则 "systemctl restart nginx" 匹配
    """
    if allowlist is None:
        allowlist = DEFAULT_SUDO_ALLOWLIST
    
    cmd_stripped = command.strip().lower()
    for allowed in allowlist:
        if cmd_stripped.startswith(allowed.lower()):
            return True
    return False


def needs_privilege_escalation(command: str) -> bool:
    """判断命令是否需要 sudo/root 权限"""
    # 常见的需要提权的命令模式
    escalation_patterns = [
        r"(?:sudo\s+)",
        r"(?:systemctl\s+restart)",
        r"(?:service\s+\w+\s+(?:restart|start|stop))",
        r"(?:chmod\s+[0-9]{3,4}\s*/(?:etc|var|usr)/)",  # 修改系统目录权限
        r"(?:chown\s+)",
        r"(?:useradd|userdel|groupadd)",
        r"(?:iptables|nft|firewall-cmd)",
    ]
    
    for pattern in escalation_patterns:
        if re.search(pattern, command):
            return True
    return False
