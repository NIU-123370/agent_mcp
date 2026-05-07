"""
MCP Client 端 —— 连接 Server，用 LLM 自动选择并调用 Tool

运行方式：uv run client.py
前提：需要设置环境变量 OPENAI_API_KEY（或替换为其他 LLM）
"""
import asyncio
import json
import os

from openai import OpenAI
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


# ─── 1. LLM 客户端 ──────────────────────────────────
llm = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ─── 2. 将 MCP Tool 定义转换为 OpenAI Function 格式 ───
def mcp_tools_to_openai_functions(mcp_tools):
    """把 MCP 的 Tool 列表转成 OpenAI 的 tools 格式"""
    functions = []
    for tool in mcp_tools:
        functions.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        })
    return functions


# ─── 3. 核心流程 ─────────────────────────────────────
async def chat(user_input: str):
    """一次完整的对话：用户输入 → LLM 决策 → 调用 Tool → 返回结果"""

    # 3.1 启动 MCP Server 并连接
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 3.2 获取所有 Tool 的定义
            tools_result = await session.list_tools()
            mcp_tools = tools_result.tools
            openai_tools = mcp_tools_to_openai_functions(mcp_tools)

            print(f"已加载 {len(mcp_tools)} 个 Tool：")
            for t in mcp_tools:
                print(f"  - {t.name}: {t.description[:30]}...")
            print()

            # 3.3 第一轮：把用户输入 + Tool 列表发给 LLM
            print(f"用户：{user_input}")
            print("-" * 50)

            messages = [{"role": "user", "content": user_input}]

            response = llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=openai_tools,  # ← 关键：把 Tool 定义传给 LLM
            )

            message = response.choices[0].message

            # 3.4 循环处理：LLM 可能连续调用多个 Tool
            while message.tool_calls:
                print(f"LLM 决定调用 {len(message.tool_calls)} 个 Tool：")

                messages.append(message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"  → {tool_name}({tool_args})")

                    # 通过 MCP 协议调用 Server 端的 Tool
                    result = await session.call_tool(tool_name, tool_args)
                    tool_result = result.content[0].text

                    print(f"  ← 返回：{tool_result}")

                    # 把 Tool 结果反馈给 LLM
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })

                # 再次请求 LLM（带上 Tool 结果，看是否还需要调用其他 Tool）
                response = llm.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=openai_tools,
                )
                message = response.choices[0].message

            # 3.5 LLM 不再需要调用 Tool，输出最终回答
            print("-" * 50)
            print(f"LLM：{message.content}")


# ─── 4. 测试不同场景 ─────────────────────────────────
async def main():
    print("=" * 60)
    print("场景 1：只需要一个 Tool")
    print("=" * 60)
    await chat("北京今天天气怎么样？")

    print("\n")

    print("=" * 60)
    print("场景 2：需要两个 Tool（先查数据，再发邮件）")
    print("=" * 60)
    await chat("帮我查一下上周的销售数据，然后把结果发邮件给 zhang@company.com")

    print("\n")

    print("=" * 60)
    print("场景 3：不需要任何 Tool")
    print("=" * 60)
    await chat("你好，今天星期几？")


if __name__ == "__main__":
    asyncio.run(main())
