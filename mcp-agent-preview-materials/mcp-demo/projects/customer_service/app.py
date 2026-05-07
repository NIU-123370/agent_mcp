"""
智能客服 — 命令行交互入口。

通过 HTTP 网关调用所有共享 MCP 服务，实现：知识库问答、对话记忆、用户画像。

启动前确保网关和各共享服务已运行：
    uv run scripts/start_all.py       # 一键启动
    uv run projects/customer_service/app.py

命令：
    /clear   清空当前会话记忆
    /profile 查看当前用户画像
    /quit    退出
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import CustomerServiceAgent
from gateway_client import GatewayClient

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(message)s",
)

API_KEY = "cs-demo-key-001"
PROJECT_ID = "customer-service"
DEFAULT_USER = "demo-user"


async def cmd_clear(gw: GatewayClient, session_id: str):
    """清空当前会话记忆。"""
    await gw.call_tool("memory-service", "clear_memory", {
        "project_id": PROJECT_ID,
        "session_id": session_id,
    })
    print("  [系统] 会话记忆已清空。\n")


async def cmd_profile(gw: GatewayClient, user_id: str):
    """查看当前用户画像。"""
    data = await gw.call_tool("memory-service", "recall_user_facts", {
        "user_id": user_id,
    })
    facts = data.get("facts", [])
    if not facts:
        print("  [系统] 暂无用户画像。\n")
        return
    print("  [系统] 当前用户画像：")
    for f in facts:
        source = f" (来源: {f['source']})" if f.get("source") else ""
        print(f"    • {f['key']}: {f['value']}{source}")
    print()


async def main():
    user_id = DEFAULT_USER
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    print("=" * 55)
    print("  SmartAssist Pro — 智能客服演示")
    print("=" * 55)
    print(f"  用户: {user_id}  |  会话: {session_id}")
    print("  命令: /clear 清空记忆  /profile 查看画像  /quit 退出")
    print("=" * 55)
    print()

    async with GatewayClient(API_KEY) as gw:
        agent = CustomerServiceAgent(gw, user_id=user_id, session_id=session_id)

        print("[客服] 你好！我是 SmartAssist Pro 智能客服，有什么可以帮你的？\n")

        while True:
            try:
                user_input = input("[你]   ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n  再见！")
                break

            if not user_input:
                continue

            if user_input.lower() in ("/quit", "/exit", "/q"):
                print("\n  再见！")
                break
            if user_input.lower() == "/clear":
                await cmd_clear(gw, session_id)
                continue
            if user_input.lower() == "/profile":
                await cmd_profile(gw, user_id)
                continue

            try:
                print("[客服] 思考中...", end="", flush=True)
                reply = await agent.handle_message(user_input)
                print(f"\r[客服] {reply}\n")
            except Exception as e:
                print(f"\r[客服] 出错了: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
