"""
Day 2: 安全校验器测试 —— 赛题核心功能点

TDD 红阶段：先定义安全校验器必须满足的 8 个行为契约
这些测试在写 validator.py 之前运行应该全部失败（红色）

8 个测试用例覆盖：
1. rm -rf / → BLOCKED（路径保护规则）
2. 删除 /var/lib/mysql/ 下文件 → BLOCKED（数据库日志保护）
3. chmod 777 /etc/passwd → BLOCKED（敏感配置修改）
4. 清理 /tmp 下临时文件 → PASSED
5. df -h 只读命令 → PASSED（跳过校验）
6. 操作被 mysqld 进程持有的日志文件 → WARNING（进程持有检测）
7. 需要 root 的命令 → ESCALATE + sudo 白名单检查
8. 批量操作混入危险指令 → 危险那条 BLOCKED 其余 PASSED

运行方式：
    pytest tests/test_safety_validator.py -v
"""

from __future__ import annotations

import pytest


# ============================================================
#  从源码导入安全校验类型（TDD 绿阶段：使用真实实现）
# ============================================================
from devops_agent.safety.validator import (  # noqa: E402
    BatchValidationResult,
    SecurityResult,
    ValidationResult,
    validate_batch_commands,
    validate_command,
)


# ============================================================
#  测试用例 1-3：危险路径保护（必须拦截）
# ============================================================
class TestDangerousPathProtection:
    """路径保护规则 —— 绝对不能放过的危险操作"""

    def test_01_rm_rf_root_blocked(self) -> None:
        """[TC-01] 'rm -rf /' 应返回 BLOCKED，原因含'根目录'
        
        这是最高优先级的防护规则：任何形式的根目录删除操作
        必须被无条件拦截。
        """
        from devops_agent.safety.validator import validate_command

        result = validate_command("rm -rf /")
        assert result.result == SecurityResult.BLOCKED
        assert "根目录" in result.reason or "/" in result.reason or "root" in result.reason.lower()

    def test_02_delete_mysql_data_dir_blocked(self) -> None:
        """[TC-02] 删除 '/var/lib/mysql/' 下的文件应返回 BLOCKED
        
        数据库数据目录是系统关键资产，误删会导致数据丢失。
        即使 Agent "推理出"要清理空间，也不能碰这个目录。
        """
        from devops_agent.safety.validator import validate_command

        # 各种变体都应该被拦
        for cmd in [
            "rm -f /var/lib/mysql/ibdata1",
            "rm -rf /var/lib/mysql/",
            "find /var/lib/mysql/ -name '*.log' -delete",
        ]:
            result = validate_command(cmd)
            assert result.result == SecurityResult.BLOCKED, (
                f"命令 '{cmd}' 应该被 BLOCKED 但得到 {result.result}"
            )
            assert "mysql" in result.reason.lower() or "数据库" in result.reason

    def test_03_chmod_etc_passwd_blocked(self) -> None:
        """[TC-03] 'chmod 777 /etc/passwd' 应返回 BLOCKED
        
        敏感配置文件的权限修改是典型攻击手段，
        安全校验器必须识别 /etc/passwd, /etc/shadow 等。
        """
        from devops_agent.safety.validator import validate_command

        result = validate_command("chmod 777 /etc/passwd")
        assert result.result == SecurityResult.BLOCKED
        assert "passwd" in result.reason.lower() or "敏感" in result.reason or "shadow" in result.reason.lower()

        # 变体：chmod 对 shadow 文件
        result2 = validate_command("chmod 644 /etc/shadow")
        assert result2.result == SecurityResult.BLOCKED


# ============================================================
#  测试用例 4-5：安全操作放行
# ============================================================
class TestSafeOperationsPass:
    """正常运维操作应该放行或跳过深度校验"""

    def test_04_cleanup_tmp_passed(self) -> None:
        """[TC-04] 清理 /tmp 下超过7天的临时文件应 PASSED
        
        /tmp 是专门用于临时文件的目录，清理是合理运维操作。
        """
        from devops_agent.safety.validator import validate_command

        result = validate_command("find /tmp -type f -mtime +7 -delete")
        assert result.result == SecurityResult.PASSED, (
            f"清理 /tmp 应该 PASSED 但得到 {result.result}: {result.reason}"
        )

    def test_05_readonly_command_skipped_or_passed(self) -> None:
        """[TC-05] df -h, ps aux, cat /var/log/syslog 等只读命令应 PASSED。

        只读探针命令不修改系统状态，不需要做深度安全校验，
        但仍应经过基本检查（如不含管道注入）。
        """
        from devops_agent.safety.validator import validate_command

        readonly_cmds = [
            "df -h",
            "ps aux | grep mysql",
            "cat /var/log/syslog | tail -50",
            "ls -la /home/",
            "netstat -tlnp",
            "ss -tulw",
            "journalctl -u nginx --since '1 hour ago'",
        ]
        for cmd in readonly_cmds:
            result = validate_command(cmd)
            assert result.result == SecurityResult.PASSED, (
                f"只读命令 '{cmd}' 应该 PASSED 但得到 {result.result}: {result.reason}"
            )


# ============================================================
#  测试用例 6：进程持有检测 (WARNING)
# ============================================================
class TestProcessHoldingDetection:
    """进程持有文件时的 WARNING 级别提示"""

    @pytest.mark.skip(reason="需要 mock /proc 或 psutil，Day 3 探针模块完成后再启用")
    def test_06_file_held_by_process_warning(self) -> None:
        """[TC-06] 操作被活跃进程持有的日志文件应 WARNING
        
        例如 mysqld 正在写入 /var/log/mysql/error.log，
        如果 Agent 尝试删除或移动该文件，应给出 WARNING 提示
        可能导致 MySQL 异常。
        
        此测试依赖 probe 模块的进程检测能力，
        Day 3 探针模块完成后启用。
        """
        from devops_agent.safety.validator import validate_command_with_context

        # 模拟上下文：mysql error.log 被 mysqld 进程持有
        context = {"held_by": "mysqld", "pid": 1234}
        result = validate_command_with_context(
            "rm /var/log/mysql/error.log",
            process_context=context,
        )
        assert result.result == SecurityResult.WARNING
        assert "mysqld" in result.reason or "进程" in result.reason


# ============================================================
#  测试用例 7：权限提升检测 (ESCALATE)
# ============================================================
class TestPrivilegeEscalation:
    """sudo / root 权限请求的处理"""

    def test_07_sudo_command_escalation(self) -> None:
        """[TC-07] 需要 sudo 的命令应返回 ESCALATE，并检查白名单
        
        不是所有 sudo 命令都拒绝，白名单内的命令可以放行。
        白名单外的 sudo 命令应该 BLOCKED。
        """
        from devops_agent.safety.validator import validate_command

        # 白名单内的 sudo 命令 → ESCALATE（表示需要提权但允许）
        allowed_sudo = "systemctl restart nginx"
        result_allowed = validate_command(allowed_sudo)
        assert result_allowed.result in (SecurityResult.ESCALATE, SecurityResult.PASSED), (
            f"白名单内命令 '{allowed_sudo}' 应为 ESCALATE/PASSED，实际 {result_allowed.result}"
        )

        # 白名单外的 sudo 命令 → BLOCKED
        blocked_sudo = "apt-get install htop"
        result_blocked = validate_command(blocked_sudo)
        assert result_blocked.result == SecurityResult.BLOCKED, (
            f"白名单外命令 '{blocked_sudo}' 应该 BLOCKED，实际 {result_blocked.result}"
        )


# ============================================================
#  测试用例 8：批量操作混合校验
# ============================================================
class TestBatchValidation:
    """批量操作中逐条校验，一条危险则整批标记"""

    def test_08_batch_mixed_safe_and_dangerous(self) -> None:
        """[TC-08] 批量操作中混入危险指令：
        
        - 安全指令：PASSED
        - 危险指令：BLOCKED
        - 整体结果：is_all_passed=False
        """
        from devops_agent.safety.validator import validate_batch_commands

        batch = [
            "find /tmp -type f -mtime +30 -delete",   # 安全：清理旧临时文件
            "rm -rf /var/log/old_logs/",               # 安全：清理旧日志
            "chmod 777 /etc/passwd",                   # 危险！敏感文件
            "systemctl restart nginx",                 # 安全：重启服务
        ]

        batch_result = validate_batch_commands(batch)

        # 应有 1 个 PASSED(find /tmp) + 2 个 BLOCKED(chmod + rm /var/log/) + 1 个 ESCALATE(systemctl)
        assert batch_result.passed_count == 1
        assert batch_result.blocked_count == 2
        assert batch_result.is_all_passed is False

        # 确认被拦的命令（不依赖顺序）
        blocked_results = [r for r in batch_result.results if r.result == SecurityResult.BLOCKED]
        assert len(blocked_results) == 2
        blocked_commands = {r.command for r in blocked_results}
        assert "chmod 777 /etc/passwd" in blocked_commands
        assert "rm -rf /var/log/old_logs/" in blocked_commands

        # 确认 ESCALATE 的命令
        escalate_results = [r for r in batch_result.results if r.result == SecurityResult.ESCALATE]
        assert len(escalate_results) == 1
        assert escalate_results[0].command == "systemctl restart nginx"

