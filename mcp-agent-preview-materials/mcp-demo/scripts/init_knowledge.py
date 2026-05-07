"""
初始化知识库 — 将演示数据导入 RAG 服务。

通过 HTTP 网关调用 RAG 服务的 ingest_document Tool：
  - products.md       → customer-service 项目的知识库
  - writing_guides.md → writing-assistant 项目的知识库

前提：网关和 RAG 服务已启动
运行：uv run scripts/init_knowledge.py
"""

import asyncio
import sys
from pathlib import Path

import httpx

GATEWAY_URL = "http://127.0.0.1:8000"

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"

DOCS = [
    {
        "file": "products.md",
        "project_id": "customer-service",
        "api_key": "cs-demo-key-001",
        "doc_name": "SmartAssist Pro 产品资料",
    },
    {
        "file": "writing_guides.md",
        "project_id": "writing-assistant",
        "api_key": "wa-demo-key-001",
        "doc_name": "AI 写作素材库",
    },
]


async def ingest(client: httpx.AsyncClient, doc: dict):
    filepath = KNOWLEDGE_DIR / doc["file"]
    if not filepath.exists():
        print(f"  [跳过] {doc['file']} 不存在")
        return

    content = filepath.read_text(encoding="utf-8")
    print(f"  [{doc['project_id']}] 正在导入 {doc['file']} ({len(content)} 字符)...")

    resp = await client.post(
        f"{GATEWAY_URL}/api/tool/call",
        headers={"X-API-Key": doc["api_key"]},
        json={
            "service": "rag-service",
            "tool": "ingest_document",
            "arguments": {
                "project_id": doc["project_id"],
                "doc_name": doc["doc_name"],
                "content": content,
            },
        },
        timeout=60,
    )

    if resp.status_code == 200:
        data = resp.json()
        chunks = data.get("chunks", data.get("chunk_count", "?"))
        print(f"  [{doc['project_id']}] 完成! 分块数: {chunks}")
    else:
        print(f"  [{doc['project_id']}] 失败! status={resp.status_code}")
        print(f"    {resp.text[:200]}")


async def main():
    print("=" * 50)
    print("  知识库初始化")
    print("=" * 50)
    print()

    async with httpx.AsyncClient() as client:
        # 先检查网关是否可达
        try:
            resp = await client.get(f"{GATEWAY_URL}/api/health", timeout=5)
            health = resp.json()
            rag_status = health.get("services", {}).get("rag-service", {}).get("status")
            if rag_status != "ok":
                print("  [错误] RAG 服务未就绪，请先启动 RAG 服务和网关。")
                sys.exit(1)
        except Exception as e:
            print(f"  [错误] 无法连接网关 ({GATEWAY_URL}): {e}")
            print("  请先启动所有服务: uv run scripts/start_all.py")
            sys.exit(1)

        print("  网关连接正常，RAG 服务就绪。\n")

        for doc in DOCS:
            await ingest(client, doc)
            print()

    print("  全部完成!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
