# tests/unit/test_approval.py
"""HITL 审批门单元测试"""

import pytest
from devops_agent.orchestrator.approval import (
    is_dangerous_operation,
    ApprovalGate,
    ApprovalStatus,
)


class TestDangerDetection:
    def test_rm_rf_is_dangerous(self):
        assert is_dangerous_operation("execute_command", {"command": "rm -rf /tmp/test"})

    def test_ls_is_not_dangerous(self):
        assert not is_dangerous_operation("execute_command", {"command": "ls -la"})

    def test_systemctl_stop_is_dangerous(self):
        assert is_dangerous_operation("execute_command", {"command": "systemctl stop nginx"})

    def test_disk_usage_not_dangerous(self):
        assert not is_dangerous_operation("disk_usage", {"path": "/"})

    def test_kill_9_is_dangerous(self):
        assert is_dangerous_operation("execute_command", {"command": "kill -9 1234"})

    def test_chmod_R_is_dangerous(self):
        assert is_dangerous_operation("execute_command", {"command": "chmod -R 777 /var/www"})

    def test_redirect_system_dir_is_dangerous(self):
        assert is_dangerous_operation("execute_command", {"command": "echo x > /etc/hosts"})


class TestApprovalGate:
    def test_request_approval(self):
        gate = ApprovalGate()
        req = gate.request_approval("run1", "node1", "execute_command", "rm -rf /tmp", "危险")
        assert req["status"] == ApprovalStatus.PENDING
        assert req["run_id"] == "run1"

    def test_approve(self):
        gate = ApprovalGate()
        gate.request_approval("run1", "node1", "t", "cmd", "")
        assert gate.approve("run1", "node1")
        pending = gate.get_pending("run1")
        assert len(pending) == 0  # approved, no longer pending

    def test_reject(self):
        gate = ApprovalGate()
        gate.request_approval("run1", "node1", "t", "cmd", "")
        assert gate.reject("run1", "node1")

    def test_get_pending_empty(self):
        gate = ApprovalGate()
        assert gate.get_pending("nonexistent") == []
