"""
RAG 检索服务 MCP Server — 统一的知识库管理与语义检索入口。

暴露 Tool：
  - ingest_document  : 将文档分块并写入向量数据库
  - search_knowledge : 在指定项目的知识库中语义检索

Embedding 方案：使用 ChromaDB 内置模型（all-MiniLM-L6-v2），无需外部 API。

启动：uv run shared/rag_service/server.py
端口：9002
传输：Streamable HTTP → http://127.0.0.1:9002/mcp
"""

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from doc_processor import chunk_document
from retriever import Retriever

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("rag-service")

# ── 初始化 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

server = FastMCP("rag-service", host="127.0.0.1", port=9002)

retriever = Retriever(persist_dir=PROJECT_ROOT / "data" / "chromadb")


# ── Tools ───────────────────────────────────────────────

@server.tool()
async def ingest_document(
    project_id: str,
    doc_name: str,
    content: str,
) -> dict:
    """将文档分块并写入向量数据库。

    Args:
        project_id: 项目标识（不同项目的知识库相互隔离）
        doc_name: 文档名称（用于标识来源）
        content: 文档全文（支持 Markdown 格式）
    """
    logger.info("ingest_document | project=%s doc=%s len=%d", project_id, doc_name, len(content))

    chunks = chunk_document(content, doc_name)
    if not chunks:
        return {"status": "empty", "message": "文档内容为空，无可分块内容", "chunks": 0}

    count = retriever.add_chunks(project_id, chunks)

    return {
        "status": "ok",
        "project_id": project_id,
        "doc_name": doc_name,
        "chunks": count,
    }


@server.tool()
async def search_knowledge(
    query: str,
    project_id: str,
    top_k: int = 3,
) -> dict:
    """在指定项目的知识库中语义检索。

    Args:
        query: 查询文本
        project_id: 项目标识（只搜索该项目的知识库）
        top_k: 返回最相关的结果数量
    """
    logger.info("search_knowledge | project=%s query=%s top_k=%d", project_id, query[:50], top_k)

    results = retriever.search(project_id, query, top_k=top_k)

    return {
        "project_id": project_id,
        "query": query,
        "results": results,
        "count": len(results),
    }


# ── 入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("RAG 检索服务 MCP Server 启动中...")
    logger.info("  Embedding: ChromaDB 内置模型 (all-MiniLM-L6-v2)")
    logger.info("  ChromaDB 目录: %s", PROJECT_ROOT / "data" / "chromadb")
    server.run(transport="streamable-http")
