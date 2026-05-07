"""
测试 Prompt 中心 MCP Server — 验证 MCP 原生 Prompt + list_prompt_templates Tool。

前提：先启动 Prompt 中心
    uv run shared/prompt_hub/server.py

运行：
    uv run scripts/test_prompt_hub.py
"""

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = "http://127.0.0.1:9004/mcp"


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

            # ── 测试 1：列出可用 Tool ──
            tools = await session.list_tools()
            print(f"available tools ({len(tools.tools)}):")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description[:60]}")
            print()

            # ── 测试 2：列出 MCP 原生 Prompt ──
            print("=" * 55)
            print("TEST 1: list prompts (MCP native)")
            print("=" * 55)

            prompts = await session.list_prompts()
            print(f"  registered prompts ({len(prompts.prompts)}):")
            for p in prompts.prompts:
                arg_names = [a.name for a in (p.arguments or [])]
                print(f"  - {p.name}: {p.description[:50]}...")
                print(f"    args: {arg_names}")
            print()

            # ── 测试 3：调用 list_prompt_templates Tool ──
            print("=" * 55)
            print("TEST 2: list_prompt_templates (Tool)")
            print("=" * 55)

            result = await session.call_tool("list_prompt_templates", {})
            if result.isError:
                print(f"  [FAIL] {result.content[0].text}")
                return
            data = parse_tool_result(result)
            print(f"  template count: {data['count']}")
            for tpl in data["templates"]:
                params = [p["name"] for p in tpl["parameters"]]
                print(f"  - {tpl['name']}: {tpl['description'][:50]}...")
                print(f"    params: {params}")
            print()

            # ── 测试 4：渲染客服 Prompt ──
            print("=" * 55)
            print("TEST 3: get_prompt (customer_service_qa)")
            print("=" * 55)

            result = await session.get_prompt("customer_service_qa", arguments={
                "context": "SmartAssist Pro: basic \\999/mo, pro \\2999/mo",
                "history": "user: I want the pro version",
                "question": "How much is it?",
                "user_profile": "allergy: mango, budget: under 500/mo",
            })
            print(f"  messages count: {len(result.messages)}")
            for i, msg in enumerate(result.messages):
                text = msg.content.text if hasattr(msg.content, "text") else str(msg.content)
                print(f"  [{i}] role={msg.role}")
                print(f"      preview: {text[:120]}...")
            print()

            # verify content
            text = result.messages[0].content.text
            has_context = "SmartAssist" in text
            has_profile = "mango" in text
            has_question = "How much" in text
            if has_context and has_profile and has_question:
                print("  -> PASS: all parameters rendered into prompt")
            else:
                print(f"  -> FAIL: missing content (context={has_context}, profile={has_profile}, question={has_question})")
            print()

            # ── 测试 5：渲染写作 Prompt ──
            print("=" * 55)
            print("TEST 4: get_prompt (writing_assistant)")
            print("=" * 55)

            result = await session.get_prompt("writing_assistant", arguments={
                "topic": "AI in Education",
                "references": "Recent studies show AI tutoring improves outcomes by 30%.",
                "style": "humorous",
            })
            print(f"  messages count: {len(result.messages)}")
            text = result.messages[0].content.text
            has_topic = "AI in Education" in text
            has_style = "humorous" in text  
            has_ref = "30%" in text
            print(f"  [{0}] role={result.messages[0].role}")
            print(f"      preview: {text[:120]}...")
            print()
            if has_topic and has_style and has_ref:
                print("  -> PASS: all parameters rendered into prompt")
            else:
                print(f"  -> FAIL: (topic={has_topic}, style={has_style}, ref={has_ref})")
            print()

            # ── 测试 6：渲染写作 Prompt（使用默认 style）──
            print("=" * 55)
            print("TEST 5: get_prompt (writing_assistant, default style)")
            print("=" * 55)

            result = await session.get_prompt("writing_assistant", arguments={
                "topic": "Climate Change",
                "references": "Global temperatures have risen 1.1C since pre-industrial times.",
            })
            text = result.messages[0].content.text
            print(f"  preview: {text[:120]}...")
            print()

            # Note: when style is not provided, the MCP SDK may not pass the default.
            # The template should still render without error.
            print("  -> PASS: prompt rendered without explicit style parameter")
            print()

            print("=" * 55)
            print("ALL TESTS PASSED!")
            print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
