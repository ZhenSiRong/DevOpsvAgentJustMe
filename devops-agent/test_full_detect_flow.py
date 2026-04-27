"""LLM 协议自动探测 —— 全流程 7 步自动化测试

测试内容：
1. 预览探测 detect_llm_protocol()
2. 探测+持久化 apply_detected_config()
3. 验证 DB 覆盖值
4. 验证运行时配置 get_llm_runtime_config()
5. 对话测试 run_agent()
6. CLI client API 测试 detect_llm_config()
7. 恢复默认 reset_all_config()
"""
import asyncio
import time
from datetime import datetime

# ========== 测试参数 ==========
KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_API_KEY = "sk-kimi-AYRDfcc9WUNw7DJch97TxpRaQBI0sEk2o7CA4gIOxhiU7OrJvjmeILOP4a3p7JKA"
KIMI_MODEL = "kimi-for-coding"

PASS = 0
FAIL = 0


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def err(msg: str):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


async def step1_preview_detect():
    """Step 1: 预览探测（不持久化）"""
    print("\n━━ Step 1: 预览探测 ━━")
    from devops_agent.llm.detector import detect_llm_protocol

    result = await detect_llm_protocol(KIMI_BASE_URL, KIMI_API_KEY, KIMI_MODEL)
    if not result.success:
        err(f"探测失败: {result.error}")
        return False
    if result.protocol != "anthropic":
        err(f"预期 anthropic, 实际 {result.protocol}")
        return False
    ok(f"探测成功: protocol={result.protocol}")
    return True


async def step2_apply_detect():
    """Step 2: 探测并持久化到 DB"""
    print("\n━━ Step 2: 探测+持久化 ━━")
    from devops_agent.llm.detector import apply_detected_config

    result = await apply_detected_config(KIMI_BASE_URL, KIMI_API_KEY, KIMI_MODEL)
    if not result.success:
        err(f"持久化失败: {result.error}")
        return False
    ok(f"已持久化: protocol={result.protocol}")
    return True


async def step3_verify_db():
    """Step 3: 验证 DB 中的覆盖值"""
    print("\n━━ Step 3: 验证 DB 覆盖值 ━━")
    from devops_agent.db.config import get_all_configs

    configs = await get_all_configs()
    llm_cfgs = {c.key: c.value for c in configs if c.key.startswith("llm.")}

    checks = [
        ("llm.protocol", "anthropic"),
        ("llm.anthropic_base_url", KIMI_BASE_URL),
        ("llm.anthropic_model", KIMI_MODEL),
    ]
    all_ok = True
    for key, expected in checks:
        actual = llm_cfgs.get(key)
        if actual == expected:
            ok(f"{key} = {actual}")
        else:
            err(f"{key}: 预期 {expected}, 实际 {actual}")
            all_ok = False
    return all_ok


async def step4_verify_runtime():
    """Step 4: 验证运行时配置"""
    print("\n━━ Step 4: 验证运行时配置 ━━")
    from devops_agent.config import get_llm_runtime_config

    cfg = await get_llm_runtime_config()
    checks = [
        ("protocol", cfg.protocol, "anthropic"),
        ("anthropic_base_url", cfg.anthropic_base_url, KIMI_BASE_URL),
        ("anthropic_model", cfg.anthropic_model, KIMI_MODEL),
    ]
    all_ok = True
    for name, actual, expected in checks:
        if actual == expected:
            ok(f"{name} = {actual}")
        else:
            err(f"{name}: 预期 {expected}, 实际 {actual}")
            all_ok = False
    return all_ok


async def step5_chat():
    """Step 5: 对话测试（带 30s 超时保护，防止 run_agent 循环卡住）"""
    print("\n━━ Step 5: 对话测试 ━━")
    from devops_agent.agent.core import run_agent
    from devops_agent.db.sessions import create_session

    try:
        session = await create_session("探测测试")
        # run_agent 内部可能多轮工具调用，每次 LLM timeout=120s，必须加总超时保护
        response = await asyncio.wait_for(
            run_agent(
                session_id=session.id,
                user_input="你好，请说一句话",
            ),
            timeout=30.0,
        )
        if response and len(response) > 0:
            ok(f"Agent 回复: {response[:80]}...")
            return True
        else:
            err("Agent 返回空响应")
            return False
    except asyncio.TimeoutError:
        err("对话超时（30s），run_agent 可能卡在外部 API 调用")
        return False
    except Exception as e:
        err(f"对话异常: {e}")
        return False


async def step6_client_api():
    """Step 6: CLI client API 测试（等效于 TUI /config auto）"""
    print("\n━━ Step 6: CLI client detect API ━━")
    from devops_agent.cli.client import DevOpsClient

    client = DevOpsClient()
    try:
        # 先重置，再重新探测（验证 client 路径也通）
        await client.reset_all_config()
        ok("reset_all_config() 调用成功")

        result = await client.detect_llm_config(
            base_url=KIMI_BASE_URL,
            api_key=KIMI_API_KEY,
            model=KIMI_MODEL,
            apply=True,
        )
        if not result.get("success"):
            err(f"client detect 失败: {result.get('error')}")
            return False
        if result.get("protocol") != "anthropic":
            err(f"预期 anthropic, 实际 {result.get('protocol')}")
            return False
        if not result.get("applied"):
            err("探测成功但未持久化")
            return False
        ok(f"client detect 成功: protocol={result['protocol']}, applied={result['applied']}")
        return True
    except Exception as e:
        err(f"client API 异常: {e}")
        return False
    finally:
        await client.close()


async def step7_reset():
    """Step 7: 恢复默认并验证"""
    print("\n━━ Step 7: 恢复默认 ━━")
    from devops_agent.cli.client import DevOpsClient
    from devops_agent.config import get_llm_runtime_config

    client = DevOpsClient()
    try:
        result = await client.reset_all_config()
        count = result.get("count", 0)
        if count > 0:
            ok(f"已重置 {count} 项配置")
        else:
            err("未重置任何配置")
            return False

        # 验证恢复后回到默认
        cfg = await get_llm_runtime_config()
        if cfg.protocol == "openai" and cfg.model == "MiniMax-M2.1":
            ok(f"恢复默认: protocol={cfg.protocol}, model={cfg.model}")
            return True
        else:
            err(f"未恢复默认: protocol={cfg.protocol}, model={cfg.model}")
            return False
    except Exception as e:
        err(f"恢复默认异常: {e}")
        return False
    finally:
        await client.close()


async def main():
    start_time = time.time()
    start_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 60)
    print("LLM 协议自动探测 —— 全流程自动化测试")
    print(f"开始时间: {start_dt}")
    print("=" * 60)

    results = []
    results.append(await step1_preview_detect())
    results.append(await step2_apply_detect())
    results.append(await step3_verify_db())
    results.append(await step4_verify_runtime())
    results.append(await step5_chat())
    results.append(await step6_client_api())
    results.append(await step7_reset())

    end_time = time.time()
    end_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed = end_time - start_time

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"🎉 全部 {total} 步测试通过！")
    else:
        print(f"⚠️ {passed}/{total} 步通过, {total - passed} 步失败")
    print(f"详细统计: ✅ {PASS} 通过, ❌ {FAIL} 失败")
    print(f"开始时间: {start_dt}")
    print(f"结束时间: {end_dt}")
    print(f"总用时:   {elapsed:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
