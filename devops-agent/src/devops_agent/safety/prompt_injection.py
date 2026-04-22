"""
抗提示词注入基线模块 —— PromptInjectionShield

三层防御体系：
1. 输入过滤层（Regex Detection）：正则匹配已知的注入攻击模式
2. 结构化隔离层（Structural Isolation）：用 XML 标签隔离用户输入与系统指令
3. 语义审计层（Semantic Audit）：启发式语义分析检测意图操纵

设计原则：
- fail-safe：无法确定时默认拦截（宁可误杀，不可放过）
- 规则可维护：正则规则集中管理，可热更新
- 与 LLM 层解耦：不依赖 LLM 判断（避免被攻破），纯规则 + 启发式
- 审计完整：所有检测事件记录到审计日志

使用方式:
    shield = PromptInjectionShield()
    result = shield.scan("用户输入文本")  # 返回扫描结果

    # 在 agent/core.py 中：
    # user_input = isolate_user_input(raw_input)  # 结构化隔离
    # result = shield.scan(user_input)
    # if result.is_blocked:
    #     return "检测到安全风险..."
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class InjectionSeverity(Enum):
    """注入攻击严重程度"""
    CRITICAL = "CRITICAL"      # 确认攻击 → 必须拦截
    HIGH = "HIGH"              # 高度可疑 → 建议拦截
    MEDIUM = "MEDIUM"          # 中度可疑 → 警告但允许
    LOW = "LOW"                # 轻度可疑 → 仅记录
    CLEAN = "CLEAN"            # 无异常


class InjectionPattern(Enum):
    """检测到的注入攻击类型"""
    INSTRUCTION_OVERRIDE = "INSTRUCTION_OVERRIDE"    # "忽略之前的指令"
    ROLE_CONFUSION = "ROLE_CONFUSION"                # 角色扮演/系统提示覆盖
    JAILBREAK = "JAILBREAK"                          # DAN / developer mode
    PAYLOAD_INJECTION = "PAYLOAD_INJECTION"          # 代码/命令注入载荷
    DELIMITER_MANIPULATION = "DELIMITER_MANIPULATION"  # 破坏标记边界
    OUTPUT_MANIPULATION = "OUTPUT_MANIPULATION"      # 要求特定输出格式绕过
    NESTED_PROMPT = "NESTED_PROMPT"                  # 嵌套提示注入
    TOKEN_SMOKE = "TOKEN_SMOKE"                      # Unicode / 零宽字符混淆


@dataclass
class InjectionMatch:
    """单次正则匹配结果"""
    pattern_id: str
    pattern_name: str
    pattern_type: InjectionPattern
    severity: InjectionSeverity
    matched_text: str
    position: int
    rule_description: str


@dataclass
class ScanResult:
    """完整扫描结果"""
    raw_input: str
    input_hash: str
    is_blocked: bool
    highest_severity: InjectionSeverity
    match_count: int
    matches: list[InjectionMatch]
    sanitization_applied: bool = False
    sanitized_input: str | None = None
    isolation_applied: bool = False
    scan_timestamp: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["highest_severity"] = self.highest_severity.value
        d["matches"] = [
            {
                "pattern_id": m.pattern_id,
                "pattern_name": m.pattern_name,
                "pattern_type": m.pattern_type.value,
                "severity": m.severity.value,
                "matched_text": m.matched_text,
                "position": m.position,
                "rule_description": m.rule_description,
            }
            for m in self.matches
        ]
        return d


# ============================================================
#  第一层：注入攻击正则规则库
# ============================================================

INJECTION_RULES: list[dict] = [
    # ---- CRITICAL: 明确的指令覆盖 ----
    {
        "id": "PI-CRIT-001",
        "name": "忽略之前指令",
        "type": InjectionPattern.INSTRUCTION_OVERRIDE,
        "severity": InjectionSeverity.CRITICAL,
        "patterns": [
            r"忽略(之前|前面|所有|以上|前文).*?(指令|命令|提示|prompt|规则)",
            r"(Ignore|Disregard|Forget)\s+(all|previous|above|earlier|prior)\s+(instructions?|prompts?|rules?|commands?)",
            r"(?:不要|请勿|禁止).{0,10}(执行|遵循|遵守).*?(指令|规则)",
        ],
        "description": "明确要求忽略之前的系统指令，是典型的提示词注入攻击模式",
    },
    {
        "id": "PI-CRIT-002",
        "name": "角色扮演/系统提示覆盖",
        "type": InjectionPattern.ROLE_CONFUSION,
        "severity": InjectionSeverity.CRITICAL,
        "patterns": [
            r"(从现在|从即刻|从现在开始).{0,10}(你现在是|你变成了|你的角色是|你扮演)",
            r"You\s+are\s+now\s+(?:a\s+)?(developer|hacker|root|admin|superuser)",
            r"(进入|激活|开启).{0,10}(开发者|开发|debug|root|管理员|越狱|jailbreak)\s*(模式)?",
            r"(pretend|act\s+as|behave\s+as)\s+(?:if\s+)?you\s+(?:are|were)\s+(?:a\s+)?(developer|hacker|root|admin)",
        ],
        "description": "试图覆盖系统设定的角色，诱导模型进入未授权模式",
    },
    {
        "id": "PI-CRIT-003",
        "name": "DAN / 越狱模式",
        "type": InjectionPattern.JAILBREAK,
        "severity": InjectionSeverity.CRITICAL,
        "patterns": [
            r"(DAN|Do Anything Now)\s*(?:mode)?",
            r"(jailbreak|越狱)\s*(?:模式)?",
            r"(developer\s+mode|开发模式)\s*(?:on|开启|激活)",
            r"(enable|turn\s+on|activate)\s+(?:the\s+)?(?:developer|debug|admin)\s+mode",
        ],
        "description": "DAN 或越狱模式请求，典型的模型越狱攻击",
    },
    # ---- HIGH: 分隔符/载荷操纵 ----
    {
        "id": "PI-HIGH-001",
        "name": "分隔符边界操纵",
        "type": InjectionPattern.DELIMITER_MANIPULATION,
        "severity": InjectionSeverity.HIGH,
        "patterns": [
            r"```\s*(?:system|assistant|user)?\s*\n",
            r"<\s*/\s*(?:system|assistant|user|instruction)\s*>",
            r"<\s*(?:system|assistant|user|instruction)\s*>",
            r"【系统指令】|【System】|【Assistant】",
            r"\[\s*(?:SYSTEM|SYSTEM_PROMPT|INSTRUCTION)\s*\]",
            r"<\?xml.*system.*\?>",
        ],
        "description": "试图通过伪造 XML/Markdown/标记边界来注入系统提示",
    },
    {
        "id": "PI-HIGH-002",
        "name": "嵌套提示注入",
        "type": InjectionPattern.NESTED_PROMPT,
        "severity": InjectionSeverity.HIGH,
        "patterns": [
            r"翻译.{0,10}以下文本.*?(忽略|不执行|不要遵循)",
            r"translate\s+the\s+following.*?ignore",
            r"summarize\s+this.*?then\s+(?:ignore|forget|disregard)",
            r"(翻译|summary|总结).{0,20}(之后|然后|接着).{0,10}(执行|做|help|assist)",
        ],
        "description": "通过翻译/总结请求嵌套隐藏指令，利用LLM的任务切换特性",
    },
    {
        "id": "PI-HIGH-003",
        "name": "输出操纵",
        "type": InjectionPattern.OUTPUT_MANIPULATION,
        "severity": InjectionSeverity.HIGH,
        "patterns": [
            r"(直接|请|必须).{0,10}(输出|回复|返回).{0,10}(只|仅).{0,10}(yes|同意|执行|好的)",
            r"(输出|回复).{0,10}只有.{0,10}(一个|1)\s*(词|字|单词)",
            r"only\s+respond\s+with\s+(?:a\s+)?(?:yes|ok|sure|done|execute)",
            r"(不要|不要添加|不要包含).{0,15}(解释|说明|备注|comment|warning)",
        ],
        "description": "通过限制输出格式绕过安全回复机制",
    },
    # ---- MEDIUM: 命令/代码载荷 ----
    {
        "id": "PI-MED-001",
        "name": "代码执行载荷",
        "type": InjectionPattern.PAYLOAD_INJECTION,
        "severity": InjectionSeverity.MEDIUM,
        "patterns": [
            r"exec\s*\(",
            r"eval\s*\(",
            r"os\.system\s*\(",
            r"subprocess\.(?:call|run|Popen)\s*\(",
            r"`.*?`\s*;",  # 反引号命令执行
            r"\$\(.*\)",    # $() 命令替换
        ],
        "description": "包含代码执行函数调用，可能用于注入可执行载荷",
    },
    {
        "id": "PI-MED-002",
        "name": "请求泄露系统信息",
        "type": InjectionPattern.PAYLOAD_INJECTION,
        "severity": InjectionSeverity.MEDIUM,
        "patterns": [
            r"(告诉我|输出|展示|列出).{0,15}(系统提示|system\s+prompt|instructions|prompt\s+content)",
            r"(what|show|reveal|print|output).{0,15}(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|rules?)",
            r"(重复|repeat).{0,10}(上面|之前|上文|之前).*?(提示|prompt|指令)",
        ],
        "description": "试图诱导模型泄露系统提示词内容",
    },
    # ---- LOW: 字符混淆 ----
    {
        "id": "PI-LOW-001",
        "name": "零宽字符混淆",
        "type": InjectionPattern.TOKEN_SMOKE,
        "severity": InjectionSeverity.LOW,
        "patterns": [
            r"[\u200B-\u200F\u2060-\u206F\uFEFF]+",  # 零宽空格/连接符/方向控制
        ],
        "description": "包含零宽 Unicode 字符，可能用于绕过简单过滤器",
    },
    {
        "id": "PI-LOW-002",
        "name": "URL/编码混淆",
        "type": InjectionPattern.TOKEN_SMOKE,
        "severity": InjectionSeverity.LOW,
        "patterns": [
            r"data:text/html.*?base64",
            r"javascript:",
            r"<iframe",
            r"<script",
        ],
        "description": "包含潜在的 Web 载荷或编码混淆",
    },
]


# ============================================================
#  第二层：结构化 Prompt 隔离模板
# ============================================================

USER_INPUT_START_MARKER = "<<<USER_INPUT_START>>>"
USER_INPUT_END_MARKER = "<<<USER_INPUT_END>>>"


def isolate_user_input(raw_input: str) -> str:
    """
    将用户输入包装在结构化隔离标记中。

    这是第二层防御：即使攻击者注入了类似系统提示的内容，
    由于被隔离标记包裹，LLM 也更不容易将用户输入解释为系统指令。

    Args:
        raw_input: 原始用户输入

    Returns:
        包装后的结构化输入字符串
    """
    # 基本清理
    cleaned = raw_input.strip()
    # 转义隔离标记本身（防止用户伪造边界）
    cleaned = cleaned.replace(USER_INPUT_START_MARKER, "[USER_START]")
    cleaned = cleaned.replace(USER_INPUT_END_MARKER, "[USER_END]")
    # 转义 ``` 代码块起始（减少 Markdown 混淆）
    cleaned = cleaned.replace("```", "`\u200B`\u200B`")

    return (
        f"{USER_INPUT_START_MARKER}\n"
        f"{cleaned}\n"
        f"{USER_INPUT_END_MARKER}"
    )


def strip_isolation_markers(text: str) -> str:
    """移除隔离标记，还原用户原始输入"""
    text = text.replace(USER_INPUT_START_MARKER, "")
    text = text.replace(USER_INPUT_END_MARKER, "")
    return text.strip()


# ============================================================
#  第三层：语义审计启发式
# ============================================================

SEMANTIC_HEURISTICS: list[dict] = [
    {
        "id": "SEM-001",
        "name": "指令词密度异常",
        "description": "输入中包含过多指令性动词（忽略/不要/必须/执行/告诉），可能是在尝试注入指令",
        "severity": InjectionSeverity.HIGH,
    },
    {
        "id": "SEM-002",
        "name": "角色词密度异常",
        "description": "输入中反复出现角色相关词汇（你/你的角色/系统/AI），可能在进行角色混淆攻击",
        "severity": InjectionSeverity.MEDIUM,
    },
    {
        "id": "SEM-003",
        "name": "输出格式限制异常",
        "description": "要求模型以特定受限格式输出（只回复yes/不要解释），可能是输出操纵",
        "severity": InjectionSeverity.MEDIUM,
    },
]


# ============================================================
#  核心类：PromptInjectionShield
# ============================================================

class PromptInjectionShield:
    """
    提示词注入防护盾。

    三层检测流水线：
    1. 正则规则扫描（全部规则并行匹配）
    2. 语义启发式分析（密度/频率统计）
    3. 风险综合评级（最高严重度决定最终决策）
    """

    def __init__(self, rules: list[dict] | None = None, enable_isolation: bool = True):
        self.rules = rules or INJECTION_RULES
        self.enable_isolation = enable_isolation
        self._compile_rules()
        self._scan_count = 0
        self._block_count = 0

    def _compile_rules(self) -> None:
        """预编译正则表达式，提升性能"""
        for rule in self.rules:
            rule["_compiled"] = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in rule["patterns"]]

    def scan(self, raw_input: str, apply_isolation: bool = True) -> ScanResult:
        """
        对用户输入执行完整的三层安全扫描。

        Args:
            raw_input: 原始用户输入文本
            apply_isolation: 是否在扫描前先应用结构化隔离

        Returns:
            ScanResult：包含所有检测到的匹配项和风险评级
        """
        from datetime import datetime, timezone

        self._scan_count += 1
        timestamp = datetime.now(timezone.utc).isoformat()

        # Step 1: 结构化隔离（第二层防御）
        text_to_scan = raw_input
        isolation_applied = False
        if apply_isolation and self.enable_isolation:
            text_to_scan = isolate_user_input(raw_input)
            isolation_applied = True

        # Step 2: 第一层 — 正则规则扫描
        matches: list[InjectionMatch] = []
        for rule in self.rules:
            for compiled in rule["_compiled"]:
                for m in compiled.finditer(text_to_scan):
                    match = InjectionMatch(
                        pattern_id=rule["id"],
                        pattern_name=rule["name"],
                        pattern_type=rule["type"],
                        severity=rule["severity"],
                        matched_text=m.group(0)[:200],  # 截断防止过大
                        position=m.start(),
                        rule_description=rule["description"],
                    )
                    matches.append(match)

        # Step 3: 第三层 — 语义启发式分析
        semantic_matches = self._semantic_analysis(text_to_scan)
        matches.extend(semantic_matches)

        # Step 4: 风险评级
        highest_severity = InjectionSeverity.CLEAN
        if matches:
            severity_order = [
                InjectionSeverity.CRITICAL,
                InjectionSeverity.HIGH,
                InjectionSeverity.MEDIUM,
                InjectionSeverity.LOW,
            ]
            for sev in severity_order:
                if any(m.severity == sev for m in matches):
                    highest_severity = sev
                    break

        # Step 5: 决策
        is_blocked = highest_severity in (
            InjectionSeverity.CRITICAL,
            InjectionSeverity.HIGH,
        )

        if is_blocked:
            self._block_count += 1

        # 生成建议
        recommendations = self._generate_recommendations(matches, is_blocked)

        # 输入哈希（用于审计日志关联）
        input_hash = hashlib.sha256(raw_input.encode("utf-8")).hexdigest()[:16]

        return ScanResult(
            raw_input=raw_input[:1000] if len(raw_input) <= 1000 else raw_input[:1000] + "...",
            input_hash=input_hash,
            is_blocked=is_blocked,
            highest_severity=highest_severity,
            match_count=len(matches),
            matches=matches,
            isolation_applied=isolation_applied,
            scan_timestamp=timestamp,
            recommendations=recommendations,
        )

    def _semantic_analysis(self, text: str) -> list[InjectionMatch]:
        """
        语义启发式分析。

        不依赖 LLM，基于关键词密度和简单统计。
        """
        matches = []
        lower = text.lower()

        # SEM-001: 指令词密度
        directive_words = [
            "忽略", "不要", "禁止", "必须", "应该", "需要",
            "执行", "运行", "告诉", "输出", "展示", "列出",
            "ignore", "disregard", "forget", "must", "should",
            "execute", "run", "tell", "output", "show", "list",
        ]
        directive_count = sum(1 for w in directive_words if w in lower)
        if directive_count >= 5:
            matches.append(
                InjectionMatch(
                    pattern_id="SEM-001",
                    pattern_name="指令词密度异常",
                    pattern_type=InjectionPattern.PAYLOAD_INJECTION,
                    severity=InjectionSeverity.HIGH,
                    matched_text=f"检测到 {directive_count} 个指令性关键词",
                    position=-1,
                    rule_description="输入中包含过多指令性动词，疑似注入指令",
                )
            )

        # SEM-002: 角色词密度
        role_words = [
            "你现在是", "你的角色", "你的身份", "你扮演",
            "系统", "system", "ai", "assistant",
            "角色扮演", "act as", "pretend",
        ]
        role_count = sum(1 for w in role_words if w in lower)
        if role_count >= 3:
            matches.append(
                InjectionMatch(
                    pattern_id="SEM-002",
                    pattern_name="角色词密度异常",
                    pattern_type=InjectionPattern.ROLE_CONFUSION,
                    severity=InjectionSeverity.MEDIUM,
                    matched_text=f"检测到 {role_count} 个角色相关关键词",
                    position=-1,
                    rule_description="输入中反复出现角色相关词汇，疑似角色混淆攻击",
                )
            )

        # SEM-003: 输出格式限制密度
        format_limit_patterns = [
            "只回复", "只输出", "只返回", "只回答",
            "不要解释", "不要说明", "不要备注",
            "only respond", "only reply", "only output",
            "no explanation", "no comment", "without explanation",
        ]
        fmt_count = sum(1 for p in format_limit_patterns if p in lower)
        if fmt_count >= 2:
            matches.append(
                InjectionMatch(
                    pattern_id="SEM-003",
                    pattern_name="输出格式限制异常",
                    pattern_type=InjectionPattern.OUTPUT_MANIPULATION,
                    severity=InjectionSeverity.MEDIUM,
                    matched_text=f"检测到 {fmt_count} 个输出限制指令",
                    position=-1,
                    rule_description="要求模型以受限格式输出，疑似输出操纵攻击",
                )
            )

        return matches

    def _generate_recommendations(
        self, matches: list[InjectionMatch], is_blocked: bool
    ) -> list[str]:
        """根据匹配结果生成安全建议"""
        recs = []

        if is_blocked:
            recs.append("输入已被拦截：检测到高风险提示词注入攻击特征，拒绝处理。")

        critical_matches = [m for m in matches if m.severity == InjectionSeverity.CRITICAL]
        if critical_matches:
            names = ", ".join({m.pattern_name for m in critical_matches})
            recs.append(f"检测到以下关键攻击模式：{names}。这属于明确的提示词注入行为。")

        high_matches = [m for m in matches if m.severity == InjectionSeverity.HIGH]
        if high_matches and not is_blocked:
            names = ", ".join({m.pattern_name for m in high_matches})
            recs.append(f"检测到高危模式：{names}。建议升级安全策略。")

        semantic_matches = [m for m in matches if m.pattern_id.startswith("SEM-")]
        if semantic_matches:
            recs.append("语义分析发现异常：输入中包含异常的指令密度或角色混淆特征。")

        if not recs:
            recs.append("未发现明显的提示词注入攻击特征。")

        return recs

    def get_stats(self) -> dict[str, Any]:
        """获取防护盾运行统计"""
        return {
            "total_scans": self._scan_count,
            "total_blocks": self._block_count,
            "block_rate": round(self._block_count / max(self._scan_count, 1) * 100, 2),
            "rules_loaded": len(self.rules),
            "isolation_enabled": self.enable_isolation,
        }

    def get_rules_summary(self) -> list[dict]:
        """获取已加载规则的摘要"""
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"].value,
                "severity": r["severity"].value,
                "pattern_count": len(r["patterns"]),
                "description": r["description"],
            }
            for r in self.rules
        ]


# ============================================================
#  便捷函数（供 agent/core.py 直接使用）
# ============================================================

_shield_instance: PromptInjectionShield | None = None


def get_shield() -> PromptInjectionShield:
    """获取全局单例防护盾"""
    global _shield_instance
    if _shield_instance is None:
        _shield_instance = PromptInjectionShield()
    return _shield_instance


def scan_input(raw_input: str) -> ScanResult:
    """快速扫描用户输入的便捷函数"""
    return get_shield().scan(raw_input)


def is_input_safe(raw_input: str) -> bool:
    """快速判断输入是否安全的便捷函数"""
    result = get_shield().scan(raw_input)
    return not result.is_blocked


__all__ = [
    "PromptInjectionShield",
    "ScanResult",
    "InjectionMatch",
    "InjectionSeverity",
    "InjectionPattern",
    "isolate_user_input",
    "strip_isolation_markers",
    "scan_input",
    "is_input_safe",
    "get_shield",
    "INJECTION_RULES",
    "SEMANTIC_HEURISTICS",
]
