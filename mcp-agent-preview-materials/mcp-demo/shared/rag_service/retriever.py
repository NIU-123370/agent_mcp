"""
向量检索器 — 基于 ChromaDB 的文档存储与语义检索。

关键设计：
- 按 project_id 创建独立的 ChromaDB collection，实现多租户数据隔离
- 使用 ChromaDB 内置的 embedding 模型（all-MiniLM-L6-v2，支持中文）
  无需外部 API，ChromaDB 自动将文本转为向量
持久化目录：data/chromadb/
"""

import logging
from pathlib import Path

import chromadb

logger = logging.getLogger("rag-service.retriever")


class Retriever:
    """ChromaDB 向量检索器，支持多项目隔离。

    ChromaDB 内置 embedding：传入文本即可，无需手动调用 embedding API。
    """

    def __init__(self, persist_dir: str | Path | None = None):
        if persist_dir is None:
            persist_dir = Path(__file__).resolve().parent.parent.parent / "data" / "chromadb"
        persist_dir = Path(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info("ChromaDB 持久化目录: %s", persist_dir)

    def _get_collection(self, project_id: str) -> chromadb.Collection:
        """获取或创建项目专属的 collection。

        collection 名 = "rag_{project_id}"，不同项目的数据物理隔离。
        ChromaDB 自动使用内置 embedding 函数。
        """
        name = f"rag_{project_id.replace('-', '_')}"
        return self.client.get_or_create_collection(
            name=name,
            metadata={"project_id": project_id},
        )

    def add_chunks(
        self,
        project_id: str,
        chunks: list[dict],
    ) -> int:
        """将文档 chunk 写入项目的 collection。

        ChromaDB 自动将 documents 转为向量，无需预先 embedding。

        Args:
            project_id: 项目标识
            chunks: doc_processor 输出的 chunk 列表

        Returns:
            写入的 chunk 数量
        """
        collection = self._get_collection(project_id)

        ids = [f"{c['doc_name']}_{c['chunk_index']}" for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {"doc_name": c["doc_name"], "chunk_index": c["chunk_index"], "heading": c["heading"]}
            for c in chunks
        ]

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "写入 %d 个 chunk | project=%s collection=%s",
            len(chunks), project_id, collection.name,
        )
        return len(chunks)

    def search(
        self,
        project_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """在项目的 collection 中语义检索。

        ChromaDB 自动将 query 文本转为向量再检索。

        Args:
            project_id: 项目标识
            query: 查询文本
            top_k: 返回最相关的 k 条结果

        Returns:
            [{"text": str, "doc_name": str, "heading": str, "score": float}, ...]
        """
        collection = self._get_collection(project_id)

        if collection.count() == 0:
            logger.warning("collection 为空 | project=%s", project_id)
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
        )

        items = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i] if results["distances"] else None
            items.append({
                "text": results["documents"][0][i],
                "doc_name": results["metadatas"][0][i]["doc_name"],
                "heading": results["metadatas"][0][i]["heading"],
                "score": round(1 - distance, 4) if distance is not None else None,
            })

        logger.info("检索 %d 条结果 | project=%s query=%s", len(items), project_id, query[:50])
        return items
