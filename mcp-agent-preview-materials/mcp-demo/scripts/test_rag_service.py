"""
测试 RAG 检索服务 MCP Server — 验证 ingest_document 和 search_knowledge。

前提：先启动 RAG 服务
    uv run shared/rag_service/server.py

运行：
    uv run scripts/test_rag_service.py
"""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = "http://127.0.0.1:9002/mcp"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_tool_result(result) -> dict | str:
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return text


async def main():
    print(f"正在连接 RAG 服务: {SERVER_URL}")

    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("连接成功!\n")

            tools = await session.list_tools()
            print(f"可用工具 ({len(tools.tools)} 个):")
            for t in tools.tools:
                print(f"  - {t.name}")
            print()

            # ── 测试 1：上传产品知识库 ──
            print("=" * 50)
            print("测试 1: ingest_document (产品资料 → 客服项目)")
            print("=" * 50)
            products_md = (PROJECT_ROOT / "data" / "knowledge" / "products.md").read_text(encoding="utf-8")
            result = await session.call_tool("ingest_document", {
                "project_id": "customer-service",
                "doc_name": "products",
                "content": products_md,
            })
            if result.isError:
                print(f"  错误: {result.content[0].text}")
                return
            data = parse_tool_result(result)
            print(f"  状态: {data['status']}")
            print(f"  分块数: {data['chunks']}")
            print()

            # ── 测试 2：上传写作素材库 ──
            print("=" * 50)
            print("测试 2: ingest_document (写作素材 → 写作项目)")
            print("=" * 50)
            writing_md = (PROJECT_ROOT / "data" / "knowledge" / "writing_guides.md").read_text(encoding="utf-8")
            result = await session.call_tool("ingest_document", {
                "project_id": "writing-assistant",
                "doc_name": "writing_guides",
                "content": writing_md,
            })
            if result.isError:
                print(f"  错误: {result.content[0].text}")
                return
            data = parse_tool_result(result)
            print(f"  状态: {data['status']}")
            print(f"  分块数: {data['chunks']}")
            print()

            # ── 测试 3：在客服知识库中检索 ──
            print("=" * 50)
            print("测试 3: search_knowledge (客服项目搜'产品价格')")
            print("=" * 50)
            result = await session.call_tool("search_knowledge", {
                "query": "产品价格是多少",
                "project_id": "customer-service",
                "top_k": 2,
            })
            if result.isError:
                print(f"  错误: {result.content[0].text}")
            else:
                data = parse_tool_result(result)
                print(f"  结果数: {data['count']}")
                for i, r in enumerate(data["results"]):
                    print(f"  [{i}] score={r['score']} heading={r['heading']}")
                    print(f"      {r['text'][:80]}...")
            print()

            # ── 测试 4：验证数据隔离 ──
            print("=" * 50)
            print("测试 4: 数据隔离 (写作项目搜'产品价格')")
            print("=" * 50)
            result = await session.call_tool("search_knowledge", {
                "query": "产品价格是多少",
                "project_id": "writing-assistant",
                "top_k": 2,
            })
            if result.isError:
                print(f"  错误: {result.content[0].text}")
            else:
                data = parse_tool_result(result)
                print(f"  结果数: {data['count']}")
                for i, r in enumerate(data["results"]):
                    print(f"  [{i}] score={r['score']} heading={r['heading']}")
                    print(f"      {r['text'][:80]}...")
                if data["count"] > 0 and all("产品" not in r["text"] and "价格" not in r["text"] for r in data["results"]):
                    print("  → 隔离验证通过：写作项目搜不到产品相关内容")
                elif data["count"] == 0:
                    print("  → 隔离验证通过：写作项目无产品数据")
            print()

            print("所有测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
