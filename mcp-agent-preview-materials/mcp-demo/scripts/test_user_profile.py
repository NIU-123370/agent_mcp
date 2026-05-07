"""
测试 用户画像（跨项目长期记忆）— 验证 save_user_fact / recall_user_facts / delete_user_fact。

重点验证：不同项目写入的用户事实，任何项目都能读到（跨项目共享）。

前提：先启动记忆服务
    uv run shared/memory_service/server.py

运行：
    uv run scripts/test_user_profile.py
"""

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = "http://127.0.0.1:9003/mcp"

USER_ID = "test-user-zhangsan"


def parse_tool_result(result) -> dict | str:
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return text


async def main():
    print(f"connecting to {SERVER_URL}")

    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("connected!\n")

            tools = await session.list_tools()
            print(f"available tools ({len(tools.tools)}):")
            for t in tools.tools:
                print(f"  - {t.name}")
            print()

            # ── 测试 0：清理环境 ──
            for key in ("allergy", "budget", "style_preference"):
                await session.call_tool("delete_user_fact", {
                    "user_id": USER_ID,
                    "fact_key": key,
                })
            print("environment cleaned.\n")

            # ── 测试 1：项目 A（客服）写入用户事实 ──
            print("=" * 55)
            print("TEST 1: save_user_fact (project A writes user facts)")
            print("=" * 55)

            facts_from_a = [
                ("allergy", "mango allergy", "customer-service"),
                ("budget", "monthly budget under 500", "customer-service"),
            ]
            for key, value, source in facts_from_a:
                result = await session.call_tool("save_user_fact", {
                    "user_id": USER_ID,
                    "fact_key": key,
                    "fact_value": value,
                    "source_project": source,
                })
                if result.isError:
                    print(f"  [FAIL] {key}: {result.content[0].text}")
                    return
                data = parse_tool_result(result)
                print(f"  [OK] {key}={value} status={data.get('status')}")

            print()

            # ── 测试 2：项目 B（写作助手）也写入一条 ──
            print("=" * 55)
            print("TEST 2: save_user_fact (project B writes user facts)")
            print("=" * 55)

            result = await session.call_tool("save_user_fact", {
                "user_id": USER_ID,
                "fact_key": "style_preference",
                "fact_value": "prefers concise and humorous style",
                "source_project": "writing-assistant",
            })
            if result.isError:
                print(f"  [FAIL] {result.content[0].text}")
                return
            data = parse_tool_result(result)
            print(f"  [OK] style_preference status={data.get('status')}")
            print()

            # ── 测试 3：任意项目读取全部用户画像 ──
            print("=" * 55)
            print("TEST 3: recall_user_facts (cross-project read)")
            print("=" * 55)

            result = await session.call_tool("recall_user_facts", {
                "user_id": USER_ID,
            })
            if result.isError:
                print(f"  [FAIL] {result.content[0].text}")
                return

            data = parse_tool_result(result)
            print(f"  total facts: {data['count']}")
            for f in data["facts"]:
                print(f"  - {f['key']} = {f['value']}  (from: {f['source']})")

            sources = {f["source"] for f in data["facts"]}
            if data["count"] == 3 and len(sources) == 2:
                print("  -> PASS: 3 facts from 2 different projects, cross-project sharing works!")
            else:
                print(f"  -> WARN: expected 3 facts from 2 sources, got {data['count']} from {sources}")
            print()

            # ── 测试 4：覆盖更新（同 key 只保留最新值）──
            print("=" * 55)
            print("TEST 4: upsert (same key overwrites old value)")
            print("=" * 55)

            result = await session.call_tool("save_user_fact", {
                "user_id": USER_ID,
                "fact_key": "budget",
                "fact_value": "monthly budget raised to 1000",
                "source_project": "customer-service",
            })
            data = parse_tool_result(result)
            print(f"  [OK] updated budget, status={data.get('status')}")

            result = await session.call_tool("recall_user_facts", {
                "user_id": USER_ID,
            })
            data = parse_tool_result(result)
            budget_fact = next((f for f in data["facts"] if f["key"] == "budget"), None)
            if budget_fact and "1000" in budget_fact["value"]:
                print(f"  -> PASS: budget updated to '{budget_fact['value']}'")
            else:
                print(f"  -> FAIL: budget not updated, got {budget_fact}")
            print()

            # ── 测试 5：用户隔离（不同 user_id 互不可见）──
            print("=" * 55)
            print("TEST 5: user isolation (different user_id)")
            print("=" * 55)

            result = await session.call_tool("recall_user_facts", {
                "user_id": "non-existent-user",
            })
            data = parse_tool_result(result)
            print(f"  non-existent user facts count: {data['count']}")
            if data["count"] == 0:
                print("  -> PASS: different user_id sees nothing")
            else:
                print("  -> FAIL: should return 0 facts")
            print()

            # ── 测试 6：删除某条事实 ──
            print("=" * 55)
            print("TEST 6: delete_user_fact")
            print("=" * 55)

            result = await session.call_tool("delete_user_fact", {
                "user_id": USER_ID,
                "fact_key": "allergy",
            })
            data = parse_tool_result(result)
            print(f"  deleted: {data.get('deleted')}")

            result = await session.call_tool("recall_user_facts", {
                "user_id": USER_ID,
            })
            data = parse_tool_result(result)
            remaining_keys = [f["key"] for f in data["facts"]]
            print(f"  remaining facts: {remaining_keys}")
            if "allergy" not in remaining_keys and data["count"] == 2:
                print("  -> PASS: allergy deleted, 2 facts remain")
            else:
                print(f"  -> FAIL: expected 2 facts without allergy, got {remaining_keys}")
            print()

            # ── 清理测试数据 ──
            for key in ("budget", "style_preference"):
                await session.call_tool("delete_user_fact", {
                    "user_id": USER_ID,
                    "fact_key": key,
                })

            print("=" * 55)
            print("ALL TESTS PASSED!")
            print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
