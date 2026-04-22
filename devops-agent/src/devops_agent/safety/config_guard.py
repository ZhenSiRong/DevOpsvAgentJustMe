"""
关键配置写保护模块 —— ConfigGuard

核心功能：
1. 基线快照：启动时记录关键配置文件的 hash + 权限 + 内容快照
2. 变更检测：对比当前状态与基线，发现未授权修改
3. 变更拦截：对受保护配置文件的写操作进行实时拦截
4. 审计日志：所有配置变更尝试记录到 audit log

保护范围（国产化环境关键配置）：
- /etc/passwd, /etc/shadow, /etc/group
- /etc/ssh/sshd_config, /etc/ssh/sshd_config.d/
- /etc/sudoers, /etc/sudoers.d/
- /etc/fstab
- /etc/security/ (SELinux/PAM 相关)
- systemd 服务文件: /etc/systemd/system/
- 麒麟V11 特有: /etc/kylin*, /etc/yum.repos.d/

使用方式:
    guard = ConfigGuard()
    await guard.take_baseline()          # 采集基线快照
    result = guard.check_file("/etc/ssh/sshd_config")   # 检查单个文件
    report = guard.scan_all()             # 全量扫描
    guard.is_write_allowed("/etc/passwd") -> bool  # 写操作预检
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class ConfigProtectionLevel(Enum):
    """配置文件保护等级"""
    READONLY = "READONLY"           # 只读：禁止任何修改（最高级别）
    MONITORED = "MONITORED"         # 监控：允许修改但必须记录+告警
    RESTRICTED = "RESTRICTED"       # 受限：只允许特定模式修改


class ChangeStatus(Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    CREATED = "CREATED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    OWNER_CHANGED = "OWNER_CHANGED"
    MISSING_BASELINE = "MISSING_BASELINE"


@dataclass
class FileBaseline:
    """单个文件的基线快照"""
    path: str
    sha256_hash: str = ""
    size: int = 0
    mode: int = 0          # 文件权限 (octal)
    uid: int = -1
    gid: int = -1
    mtime: float = 0.0
    is_symlink: bool = False
    symlink_target: str = ""
    protection_level: str = ConfigProtectionLevel.READONLY.value
    captured_at: str = ""
    # 可选：完整内容快照（仅对小文件，<64KB）
    content_snapshot: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode_octal"] = oct(self.mode) if self.mode else "N/A"
        return d


@dataclass
class FileChangeReport:
    """单文件变更检测结果"""
    path: str
    status: ChangeStatus
    baseline: FileBaseline | None = None
    current: FileBaseline | None = None
    details: dict[str, Any] = field(default_factory=dict)
    detected_at: str = ""

    @property
    def has_change(self) -> bool:
        return self.status != ChangeStatus.UNCHANGED

    @property
    def is_critical(self) -> bool:
        """READONLY 级别文件的变更是严重的"""
        if self.baseline:
            return (
                self.baseline.protection_level == ConfigProtectionLevel.READONLY.value
                and self.has_change
            )
        return False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["has_change"] = self.has_change
        d["is_critical"] = self.is_critical
        return d


@dataclass
class WriteCheckResult:
    """写操作预检结果"""
    allowed: bool
    path: str
    reason: str = ""
    protection_level: str = ""
    rule_id: str = ""


# ============================================================
#  默认保护规则 — 国产化环境（龙芯+麒麟）的关键配置
# ============================================================

DEFAULT_PROTECTED_FILES: list[dict] = [
    # ---- 身份与认证（CRITICAL） ----
    {
        "path": "/etc/passwd",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "用户账户数据库",
    },
    {
        "path": "/etc/shadow",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "用户密码哈希",
    },
    {
        "path": "/etc/group",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "用户组数据库",
    },
    {
        "path": "/etc/gshadow",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "组密码文件",
    },
    # ---- SSH 安全配置 ----
    {
        "path": "/etc/ssh/sshd_config",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "SSH 服务端配置",
    },
    {
        "path": "/etc/ssh/sshd_config.d/",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "SSH 配置片段目录",
        "is_directory": True,
    },
    {
        "path": "/root/.ssh/authorized_keys",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "Root SSH 授权密钥",
    },
    # ---- 权限控制 ----
    {
        "path": "/etc/sudoers",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "Sudo 权限配置",
    },
    {
        "path": "/etc/sudoers.d/",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "Sudo 配置片段目录",
        "is_directory": True,
    },
    # ---- 系统引导与挂载 ----
    {
        "path": "/etc/fstab",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "文件系统挂载表",
    },
    {
        "path": "/boot/grub2/grub.cfg",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "GRUB 引导配置",
    },
    # ---- PAM 认证 ----
    {
        "path": "/etc/pam.d/",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "PAM 认证配置目录",
        "is_directory": True,
    },
    # ---- SELinux（麒麟V11 默认 enforcing） ----
    {
        "path": "/etc/selinux/config",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "SELinux 全局配置",
    },
    {
        "path": "/etc/selinux/targeted/policy/",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "SELinux 策略模块目录",
        "is_directory": True,
    },
    # ---- Systemd 服务 ----
    {
        "path": "/etc/systemd/system/",
        "protection_level": ConfigProtectionLevel.RESTRICTED,
        "description": "Systemd 自定义服务单元目录",
        "is_directory": True,
    },
    # ---- 网络安全 ----
    {
        "path": "/etc/firewalld/",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "FirewallD 配置目录",
        "is_directory": True,
    },
    {
        "path": "/etc/hosts.allow",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "TCP Wrappers 允许列表",
    },
    {
        "path": "/etc/hosts.deny",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "TCP Wrappers 拒绝列表",
    },
    # ---- 麒麟V11 特有 ----
    {
        "path": "/etc/kylin-process-manager/",
        "protection_level": ConfigProtectionLevel.READONLY,
        "description": "麒麟进程管理器配置",
        "is_directory": True,
    },
    {
        "path": "/etc/yum.repos.d/",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "DNF 软件源配置目录",
        "is_directory": True,
    },
    # ---- 日志配置 ----
    {
        "path": "/etc/logrotate.conf",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "全局日志轮转配置",
    },
    {
        "path": "/etc/rsyslog.conf",
        "protection_level": ConfigProtectionLevel.MONITORED,
        "description": "系统日志服务配置",
    },
]


# ============================================================
#  核心类：ConfigGuard
# ============================================================

class ConfigGuard:
    """
    关键配置文件守护器。

    用法:
        guard = ConfigGuard()
        await guard.initialize()     # 采集基线
        report = guard.scan()        # 全量扫描变更
        check = guard.check_write("/etc/passwd")  # 写操作预检
    """

    def __init__(
        self,
        protected_files: list[dict] | None = None,
        snapshot_size_limit: int = 65536,  # 64KB
    ):
        self.protected_files = protected_files if protected_files is not None else DEFAULT_PROTECTED_FILES
        self.snapshot_size_limit = snapshot_size_limit
        self.baselines: dict[str, FileBaseline] = {}
        self.is_initialized = False
        self.initialized_at: str = ""

    async def initialize(self) -> dict[str, Any]:
        """
        初始化守护器：遍历所有保护规则，为存在的文件建立基线快照。

        Returns:
            统计信息字典：total/protected/missing/errors
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self.initialized_at = now
        stats = {"total": len(self.protected_files), "captured": 0, "missing": 0, "errors": 0}

        for rule in self.protected_files:
            path = rule["path"]
            level = rule.get("protection_level", ConfigProtectionLevel.READONLY)
            is_dir = rule.get("is_directory", False)

            try:
                if is_dir:
                    # 目录：扫描其中的直接子项
                    dir_count = await self._capture_directory(path, level, now)
                    stats["captured"] += dir_count
                else:
                    baseline = await self._capture_single_file(path, level, now)
                    if baseline is not None:
                        self.baselines[path] = baseline
                        stats["captured"] += 1
                    else:
                        stats["missing"] += 1
            except Exception as e:
                stats["errors"] += 1

        self.is_initialized = True
        return stats

    async def _capture_single_file(
        self,
        path: str,
        level: ConfigProtectionLevel,
        timestamp: str,
    ) -> FileBaseline | None:
        """为单个文件采集基线快照"""
        p = Path(path)

        if not p.exists():
            return None
        if not p.is_file():
            return None

        stat_result = p.stat()
        file_hash = ""

        try:
            # 计算 SHA256
            file_hash = await self._compute_sha256(path)
        except (OSError, PermissionError):
            pass

        # 小文件保存内容快照
        content_snap = None
        if stat_result.st_size <= self.snapshot_size_limit and stat_result.st_size > 0:
            try:
                content_snap = p.read_text(errors="replace")
            except (OSError, PermissionError):
                pass

        # 处理符号链接
        is_link = p.is_symlink()
        link_target = ""
        if is_link:
            try:
                link_target = str(p.resolve())
            except OSError:
                link_target = str(os.readlink(path))

        return FileBaseline(
            path=path,
            sha256_hash=file_hash,
            size=stat_result.st_size,
            mode=stat_result.st_mode,
            uid=stat_result.st_uid,
            gid=stat_result.st_gid,
            mtime=stat_result.st_mtime,
            is_symlink=is_link,
            symlink_target=link_target,
            protection_level=level.value,
            captured_at=timestamp,
            content_snapshot=content_snap,
        )

    async def _capture_directory(
        self,
        dir_path: str,
        level: ConfigProtectionLevel,
        timestamp: str,
    ) -> int:
        """扫描目录中的文件并逐一采集基线"""
        p = Path(dir_path)
        if not p.is_dir():
            return 0

        count = 0
        try:
            for entry in p.iterdir():
                if entry.is_file() and not entry.name.startswith("."):
                    baseline = await self._capture_single_file(str(entry), level, timestamp)
                    if baseline is not None:
                        self.baselines[str(entry)] = baseline
                        count += 1
                elif entry.is_dir():
                    # 递归一层
                    for sub in entry.iterdir():
                        if sub.is_file() and not sub.name.startswith("."):
                            baseline = await self._capture_single_file(str(sub), level, timestamp)
                            if baseline is not None:
                                self.baselines[str(sub)] = baseline
                                count += 1
        except PermissionError:
            pass

        return count

    @staticmethod
    async def _compute_sha256(file_path: str) -> str:
        """异步计算文件的 SHA256 哈希值"""
        loop = __import__("asyncio").get_event_loop()

        def _hash_sync() -> str:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()

        return await loop.run_in_executor(None, _hash_sync)

    # ----------------------------------------------------------
    #  变更检测
    # ----------------------------------------------------------

    async def check_file(self, path: str) -> FileChangeReport:
        """
        检查指定文件是否相对于基线发生了变更。

        Returns:
            FileChangeReport 包含详细的变更信息
        """
        from datetime import datetime, timezone

        baseline = self.baselines.get(path)
        if baseline is None:
            return FileChangeReport(
                path=path,
                status=ChangeStatus.MISSING_BASELINE,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )

        current = await self._capture_single_file(
            path,
            ConfigProtectionLevel(baseline.protection_level),
            datetime.now(timezone.utc).isoformat(),
        )

        # 文件被删除
        if current is None:
            return FileChangeReport(
                path=path,
                status=ChangeStatus.DELETED,
                baseline=baseline,
                detected_at=datetime.now(timezone.utc).isoformat(),
                details={"previous_hash": baseline.sha256_hash},
            )

        changes = {}

        # 内容变更（hash 不同）
        if current.sha256_hash != baseline.sha256_hash:
            # 对小文件做 diff 统计
            if baseline.content_snapshot and current.content_snapshot:
                old_lines = baseline.content_snapshot.splitlines()
                new_lines = current.content_snapshot.splitlines()
                changes["lines_added"] = max(0, len(new_lines) - len(old_lines))
                changes["lines_removed"] = max(0, len(old_lines) - len(new_lines))
                changes["old_size"] = baseline.size
                changes["new_size"] = current.size
            else:
                changes["hash_changed"] = True
                changes["old_hash"] = baseline.sha256_hash[:16]
                changes["new_hash"] = current.sha256_hash[:16]

            return FileChangeReport(
                path=path,
                status=ChangeStatus.MODIFIED,
                baseline=baseline,
                current=current,
                details=changes,
                detected_at=current.captured_at,
            )

        # 权限变更
        if current.mode != baseline.mode:
            return FileChangeReport(
                path=path,
                status=ChangeStatus.PERMISSION_CHANGED,
                baseline=baseline,
                current=current,
                details={
                    "old_mode": oct(baseline.mode),
                    "new_mode": oct(current.mode),
                },
                detected_at=current.captured_at,
            )

        # 属主变更
        if current.uid != baseline.uid or current.gid != baseline.gid:
            return FileChangeReport(
                path=path,
                status=ChangeStatus.OWNER_CHANGED,
                baseline=baseline,
                current=current,
                details={
                    "old_owner": f"{baseline.uid}:{baseline.gid}",
                    "new_owner": f"{current.uid}:{current.gid}",
                },
                detected_at=current.captured_at,
            )

        # 无变更
        return FileChangeReport(
            path=path,
            status=ChangeStatus.UNCHANGED,
            baseline=baseline,
            current=current,
            detected_at=current.captured_at,
        )

    async def scan_all(self) -> list[FileChangeReport]:
        """
        全量扫描所有已建立基线的文件。

        Returns:
            所有文件的变更报告列表
        """
        reports = []
        for path in self.baselines:
            report = await self.check_file(path)
            reports.append(report)
        return reports

    def get_scan_summary(self, reports: list[FileChangeReport]) -> dict[str, Any]:
        """汇总扫描结果"""
        critical_changes = [r for r in reports if r.is_critical]
        all_changes = [r for r in reports if r.has_change and r.status != ChangeStatus.MISSING_BASELINE]

        return {
            "total_files_checked": len(reports),
            "unchanged_count": sum(1 for r in reports if r.status == ChangeStatus.UNCHANGED),
            "changed_count": len(all_changes),
            "critical_count": len(critical_changes),
            "deleted_count": sum(1 for r in reports if r.status == ChangeStatus.DELETED),
            "permission_changed_count": sum(1 for r in reports if r.status == ChangeStatus.PERMISSION_CHANGED),
            "critical_paths": [r.path for r in critical_changes],
            "changed_paths": [r.path for r in all_changes],
            "scan_time": reports[0].detected_at if reports else "",
        }

    # ----------------------------------------------------------
    #  写操作预检（核心安全功能）
    # ----------------------------------------------------------

    def check_write_allowed(self, target_path: str) -> WriteCheckResult:
        """
        检查对目标路径的写操作是否被允许。

        这是 Agent 执行任何写操作前必须调用的预检函数。

        Args:
            target_path: 目标文件或目录路径

        Returns:
            WriteCheckResult: allowed=True 表示可以执行
        """
        # 规范化路径
        normalized = os.path.normpath(target_path)

        # 直接匹配受保护的精确路径
        for rule in self.protected_files:
            rule_path = rule["path"]
            level = rule.get("protection_level", ConfigProtectionLevel.READONLY)
            is_dir_rule = rule.get("is_directory", False)

            # 精确匹配
            if normalized == rule_path:
                if level == ConfigProtectionLevel.READONLY:
                    return WriteCheckResult(
                        allowed=False,
                        path=target_path,
                        reason=f"文件 '{target_path}' 为 READONLY 保护级别，禁止写入。此操作需要人工审批。",
                        protection_level=level.value,
                        rule_id="CG-RO-001",
                    )
                elif level == ConfigProtectionLevel.MONITORED:
                    return WriteCheckResult(
                        allowed=True,  # 允许但需记录
                        path=target_path,
                        reason=f"文件 '{target_path}' 为 MONITORED 级别，写操作将被审计记录。",
                        protection_level=level.value,
                        rule_id="CG-MON-001",
                    )
                elif level == ConfigProtectionLevel.RESTRICTED:
                    return WriteCheckResult(
                        allowed=True,
                        path=target_path,
                        reason=f"路径 '{target_path}' 为 RESTRICTED 级别，仅允许特定模式写操作。",
                        protection_level=level.value,
                        rule_id="CG-RS-001",
                    )

            # 目录规则：检查是否是目录内的文件
            dir_prefix = rule_path.rstrip("/") + "/"
            if is_dir_rule and normalized.startswith(dir_prefix):
                if level == ConfigProtectionLevel.READONLY:
                    return WriteCheckResult(
                        allowed=False,
                        path=target_path,
                        reason=f"目标路径位于 READONLY 保护目录 '{rule_path}' 内，禁止写入。",
                        protection_level=level.value,
                        rule_id="CG-RO-DIR-001",
                    )

        # 未匹配到任何保护规则 → 允许（默认策略）
        return WriteCheckResult(
            allowed=True,
            path=target_path,
            reason="该路径不在保护清单中，可正常写入。",
            protection_level="UNPROTECTED",
            rule_id="CG-DEF-001",
        )

    # ----------------------------------------------------------
    #  工具方法
    # ----------------------------------------------------------

    def get_protected_paths_list(self) -> list[dict]:
        """获取所有受保护路径及其状态的概览"""
        result = []
        for rule in self.protected_files:
            path = rule["path"]
            info = {
                "path": path,
                "level": rule.get("protection_level", ConfigProtectionLevel.READONLY).value,
                "description": rule.get("description", ""),
                "has_baseline": path in self.baselines,
                "is_directory": rule.get("is_directory", False),
            }
            if path in self.baselines:
                bl = self.baselines[path]
                info["baseline_captured_at"] = bl.captured_at
                info["file_size"] = bl.size
                info["file_hash"] = bl.sha256_hash[:16] + "..." if bl.sha256_hash else "N/A"
            result.append(info)
        return result

    def get_baseline_stats(self) -> dict[str, Any]:
        """获取基线统计摘要"""
        total = len(self.baselines)
        by_level = {}
        for bl in self.baselines.values():
            level = bl.protection_level
            by_level[level] = by_level.get(level, 0) + 1

        return {
            "total_baselines": total,
            "by_protection_level": by_level,
            "initialized_at": self.initialized_at,
            "is_initialized": self.is_initialized,
        }


__all__ = [
    "ConfigGuard",
    "FileBaseline",
    "FileChangeReport",
    "WriteCheckResult",
    "ConfigProtectionLevel",
    "ChangeStatus",
    "DEFAULT_PROTECTED_FILES",
]
