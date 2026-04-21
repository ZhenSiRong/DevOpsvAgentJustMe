"""安全护栏子系统"""
from .validator import (
    SecurityResult,
    ValidationResult,
    BatchValidationResult,
    validate_command,
    validate_command_with_context,
    validate_batch_commands,
)
from .rules import (
    DEFAULT_SUDO_ALLOWLIST,
    is_readonly_command,
)
from .executor import (
    ExecutionStatus,
    ExecutionResult,
    ExecutionRejectedError,
    execute,
    execute_safe,
    is_command_allowed,
    EXECUTION_WHITELIST,
)

__all__ = [
    # 安全校验器
    "SecurityResult",
    "ValidationResult",
    "BatchValidationResult",
    "validate_command",
    "validate_command_with_context",
    "validate_batch_commands",
    # 规则库
    "DEFAULT_SUDO_ALLOWLIST",
    "is_readonly_command",
    # 执行引擎
    "ExecutionStatus",
    "ExecutionResult",
    "ExecutionRejectedError",
    "execute",
    "execute_safe",
    "is_command_allowed",
    "EXECUTION_WHITELIST",
]
