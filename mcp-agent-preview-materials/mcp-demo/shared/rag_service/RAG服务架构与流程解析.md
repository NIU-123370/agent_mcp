# RAG 服务架构与流程解析

## 这个服务是什么

一个独立的 MCP 进程，端口 9002，对外提供两个 Tool：

- **`ingest_document`** — 把一篇文档切成小块，存进向量数据库。
- **`search_knowledge`** — 用一句话在向量数据库里做语义搜索。

服务地址：`http://127.0.0.1:9002/mcp`（传输协议 `streamable-http`）。

---

## 三个源文件，各管什么

```
rag_service/
├── server.py           # 入口：注册 MCP Tool，串联下面两个模块
├── doc_processor.py    # 分块：把长文档切成短文本片段
└── retriever.py        # 存取：把片段写入 / 从 ChromaDB 检索
```

### server.py（入口与胶水）

- 初始化 `FastMCP` 服务和 `Retriever` 实例。
- 注册 `ingest_document` 和 `search_knowledge` 两个 Tool。
- **自己不做分块，也不做向量计算**，只负责调用 `doc_processor` 和 `retriever`，把结果包装成 JSON 返回给 MCP 客户端。

### doc_processor.py（分块器）

**职责**：把一篇 Markdown 文档拆成多条短文本。

**只处理字符串，不涉及向量。**

分块分两轮：

| 轮次 | 做什么 | 依据 |
|------|--------|------|
| 第一轮 | 按 `## 标题` 把文档切成若干「章节」 | 正则 `^##\s+(.+)$` |
| 第二轮 | 如果某个章节正文超过 500 字符，再按空行拆成更小的段 | `\n\s*\n` 分割后贪心合并 |

三种特殊情况：

| 情况 | 处理方式 |
|------|----------|
| 整篇文档没有任何 `##` | 全文算一个章节，标题记为 `(全文)` |
| 第一个 `##` 前面有正文 | 那段正文单独成章，标题记为 `(简介)` |
| 某章节正文为空 | 跳过，不产生 chunk |

每条 chunk 是一个字典，固定四个字段：

```python
{
    "text": "这条 chunk 的正文",
    "doc_name": "文档名（入参传进来的）",
    "chunk_index": 0,   # 从 0 起，全文档连续递增
    "heading": "所属章节标题"
}
```

### retriever.py（向量存取器）

**职责**：管理 ChromaDB，负责「写入」和「检索」。

核心概念：

- **collection**：ChromaDB 里的一张「表」。每个 `project_id` 对应一个独立的 collection，命名为 `rag_{project_id}`（`-` 替换为 `_`）。不同项目的数据完全隔离。
- **embedding**：本服务**没有**手写任何 embedding 代码。ChromaDB 内置了 `all-MiniLM-L6-v2` 模型，在调用 `upsert` 和 `query` 时**自动**把文本转成向量。

两个关键方法：

| 方法 | 做什么 |
|------|--------|
| `add_chunks(project_id, chunks)` | 把 chunk 列表写入 ChromaDB。内部调用 `collection.upsert`，ChromaDB 自动对每条 `text` 做 embedding 后存储。 |
| `search(project_id, query, top_k)` | 用一句查询文本检索。内部调用 `collection.query`，ChromaDB 自动对 `query` 做 embedding，和库里的向量算距离，返回最相似的 top_k 条。 |

---

## 入库流程（ingest_document）

MCP 客户端调 `ingest_document`，服务端内部经过三步：

```
MCP 客户端
   │
   │  传入 project_id, doc_name, content
   ▼
server.py ── ingest_document
   │
   │  ① 调用 doc_processor.chunk_document(content, doc_name)
   │     → 得到 chunk 列表（纯文本，无向量）
   │
   │  如果列表为空 → 直接返回 status="empty"，流程结束
   │
   │  ② 调用 retriever.add_chunks(project_id, chunks)
   │     → 内部：把每条 chunk 的 text 作为 document 传给 ChromaDB
   │     → ChromaDB 自动做 embedding，生成向量，连同 id 和 metadata 一起落盘
   │     → 返回写入条数（int）
   │
   │  ③ 组装返回值
   ▼
MCP 客户端收到 {"status":"ok", "project_id":..., "doc_name":..., "chunks": N}
```

**向量化发生在哪一步**：第 ② 步，`collection.upsert(documents=...)` 的时候。ChromaDB 拿到 `documents` 列表里的每条字符串，内部调内置模型算出向量，然后存储。业务代码看不到向量数组。

---

## 检索流程（search_knowledge）

MCP 客户端调 `search_knowledge`，服务端内部经过两步：

```
MCP 客户端
   │
   │  传入 query, project_id, top_k(默认3)
   ▼
server.py ── search_knowledge
   │
   │  ① 调用 retriever.search(project_id, query, top_k)
   │     → 内部：
   │        a. 拿到该 project 的 collection
   │        b. 如果 collection 为空 → 返回 []
   │        c. 调用 collection.query(query_texts=[query], n_results=...)
   │           → ChromaDB 自动对 query 做 embedding
   │           → 和库里每条向量算距离
   │           → 返回最近的 N 条
   │        d. 把 Chroma 原始结果转成业务格式的 list[dict]
   │
   │  ② 组装返回值
   ▼
MCP 客户端收到 {"project_id":..., "query":..., "results":[...], "count": N}
```

**向量化发生在哪一步**：第 ①c 步，`collection.query(query_texts=...)` 的时候。ChromaDB 拿到查询字符串，内部算出向量，再和库里的向量比对距离。

---

## 多租户隔离

靠 `project_id` 实现。

- 入库时传 `project_id="customer-service"` → 数据写进 collection `rag_customer_service`。
- 检索时也传 `project_id="customer-service"` → 只在这个 collection 里搜。
- 换一个 `project_id="writing-assistant"` → 完全不同的 collection，互不干扰。

**入库和检索必须用同一个 `project_id`**，否则等于在两个不同的库里操作。

---

## 幂等与覆盖

- 每条 chunk 在 ChromaDB 里的 id = `{doc_name}_{chunk_index}`。
- 写入方式是 `upsert`（有则更新，无则插入）。
- 所以对同一篇文档重复 ingest，会覆盖旧数据。
- 但如果新版本的 chunk 数量比旧版本少，多出来的旧 chunk 不会被自动删除（当前实现未做「先删后写」）。

---

## 持久化

ChromaDB 数据存储在 `mcp-demo/data/chromadb/` 目录下，服务重启后数据仍在。

---

## 启动方式

在 `mcp-demo` 目录下执行：

```bash
uv run shared/rag_service/server.py
```

也可通过 `scripts/start_all.py` 一键启动所有服务。
