# RAG 调用过程与输入输出

用一个具体例子，从入库到检索完整走一遍。每一步列出：调了哪个函数、传进去什么、返回什么。

---

## 案例素材

用下面这段极简 Markdown 作为要入库的文档（从 `products.md` 节选，方便看清每步数据）：

```markdown
# SmartAssist Pro

## 技术规格

- 并发支持：单实例最高 1000 路并发对话
- 响应速度：平均首字延迟 < 500ms

## 定价方案

基础版 ¥999/月，专业版 ¥2999/月。
```

入库参数：`project_id = "demo"`，`doc_name = "products"`。

---

## 第一部分：入库（ingest_document）

### 第 ① 步：MCP 客户端 → server.py

客户端通过 MCP 协议调用 `ingest_document`。

**输入**（Tool 的 arguments）：

```json
{
  "project_id": "demo",
  "doc_name": "products",
  "content": "# SmartAssist Pro\n\n## 技术规格\n\n- 并发支持：单实例最高 1000 路并发对话\n- 响应速度：平均首字延迟 < 500ms\n\n## 定价方案\n\n基础版 ¥999/月，专业版 ¥2999/月。"
}
```

**输出**：此时还没有，等整个流程跑完才返回（见第 ④ 步）。

---

### 第 ② 步：server.py → doc_processor.chunk_document（分块）

`server.py` 第 52 行调用：

```python
chunks = chunk_document(content, doc_name)
```

**输入**：

| 参数 | 值 |
|------|-----|
| `content` | 上面那段 Markdown 字符串 |
| `doc_name` | `"products"` |
| `max_chunk_size` | `500`（默认值，server 没改） |

**内部过程**：

分块器做两件事：

**（a）按 `##` 切章节**

扫描所有 `## xxx` 行，把文档切成 `[(heading, body), ...]`：

| heading | body（该章节的正文） |
|---------|----------------------|
| `(简介)` | `# SmartAssist Pro\n\n`（第一个 `##` 前面的内容） |
| `技术规格` | `\n\n- 并发支持：单实例最高 1000 路并发对话\n- 响应速度：平均首字延迟 < 500ms\n\n` |
| `定价方案` | `\n\n基础版 ¥999/月，专业版 ¥2999/月。` |

注意：`# SmartAssist Pro` 在第一个 `##` 之前，所以被归为 `(简介)`。

**（b）每个章节正文看是否要再切**

三段正文都短于 500 字符，所以**都不再切**，每段直接变成 1 条 chunk。

**输出**（`list[dict]`）：

```json
[
  {
    "text": "# SmartAssist Pro",
    "doc_name": "products",
    "chunk_index": 0,
    "heading": "(简介)"
  },
  {
    "text": "- 并发支持：单实例最高 1000 路并发对话\n- 响应速度：平均首字延迟 < 500ms",
    "doc_name": "products",
    "chunk_index": 1,
    "heading": "技术规格"
  },
  {
    "text": "基础版 ¥999/月，专业版 ¥2999/月。",
    "doc_name": "products",
    "chunk_index": 2,
    "heading": "定价方案"
  }
]
```

3 条 chunk，`chunk_index` 从 0 到 2 连续编号（跨章节不重置）。

---

### 第 ③ 步：server.py → retriever.add_chunks（写入 + 向量化）

`server.py` 第 56 行调用：

```python
count = retriever.add_chunks(project_id, chunks)
```

**输入**：

| 参数 | 值 |
|------|-----|
| `project_id` | `"demo"` |
| `chunks` | 第 ② 步的输出（3 条 dict） |

**内部过程**：

`add_chunks` 做三件事：

**（a）拿到 collection**

调用 `_get_collection("demo")`，得到名为 `rag_demo` 的 ChromaDB collection（不存在则自动创建）。

**（b）从 chunk 列表里拆出三个平行数组**

| 数组 | 第 0 条 | 第 1 条 | 第 2 条 |
|------|---------|---------|---------|
| `ids` | `"products_0"` | `"products_1"` | `"products_2"` |
| `documents` | `"# SmartAssist Pro"` | `"- 并发支持：...< 500ms"` | `"基础版 ¥999/月...¥2999/月。"` |
| `metadatas` | `{doc_name, chunk_index:0, heading:"(简介)"}` | `{..., chunk_index:1, heading:"技术规格"}` | `{..., chunk_index:2, heading:"定价方案"}` |

**（c）调 `collection.upsert`**

```python
collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
```

**这一步是向量化发生的地方。** ChromaDB 拿到 `documents` 里的 3 条字符串，内部用 `all-MiniLM-L6-v2` 模型把每条字符串算出一个向量（384 维浮点数组），然后连同 `ids` 和 `metadatas` 一起写进磁盘（`data/chromadb/`）。

业务代码看不到这些向量数组，`upsert` 没有返回值。

**输出**：

```python
3   # int，等于 len(chunks)
```

---

### 第 ④ 步：server.py → MCP 客户端（最终返回）

`server.py` 把结果包装成 JSON 返回：

**输出**：

```json
{
  "status": "ok",
  "project_id": "demo",
  "doc_name": "products",
  "chunks": 3
}
```

如果第 ② 步的 chunks 是空列表（文档没有有效内容），则不会进入第 ③ 步，直接返回：

```json
{
  "status": "empty",
  "message": "文档内容为空，无可分块内容",
  "chunks": 0
}
```

---

## 第二部分：检索（search_knowledge）

现在库里已经有 3 条 chunk 了，来问一个问题。

### 第 ⑤ 步：MCP 客户端 → server.py

客户端调用 `search_knowledge`。

**输入**：

```json
{
  "query": "并发能支持多少",
  "project_id": "demo",
  "top_k": 3
}
```

---

### 第 ⑥ 步：server.py → retriever.search（检索 + 查询向量化）

`server.py` 第 81 行调用：

```python
results = retriever.search(project_id, query, top_k=top_k)
```

**输入**：

| 参数 | 值 |
|------|-----|
| `project_id` | `"demo"` |
| `query` | `"并发能支持多少"` |
| `top_k` | `3` |

**内部过程**：

`search` 做三件事：

**（a）拿到 collection**

和入库一样，通过 `_get_collection("demo")` 拿到 `rag_demo`。

**（b）检查是否为空**

调 `collection.count()`。如果是 0，直接返回 `[]`，不做任何检索。这里 count=3，继续。

**（c）调 `collection.query`**

```python
results = collection.query(
    query_texts=["并发能支持多少"],
    n_results=min(3, 3)   # min(top_k, count)
)
```

**这一步是查询向量化发生的地方。** ChromaDB 拿到 `"并发能支持多少"` 这个字符串，用同一个内置模型算出一个向量，然后和库里 3 条 chunk 的向量逐一算距离，按距离从小到大排序，返回前 3 条。

ChromaDB 返回的原始结构：

```python
{
    "ids": [["products_1", "products_2", "products_0"]],
    "documents": [["- 并发支持：...< 500ms", "基础版 ¥999/月...", "# SmartAssist Pro"]],
    "distances": [[0.2877, 1.1234, 1.5678]],
    "metadatas": [[{...技术规格...}, {...定价方案...}, {...(简介)...}]]
}
```

（注意：外层都多套了一层列表，因为 `query_texts` 可以传多个查询，这里只传了 1 个。）

**（d）转成业务格式**

遍历结果，把 `distance` 转成 `score`（`score = round(1 - distance, 4)`），组装成：

```python
[
    {"text": "- 并发支持：...< 500ms", "doc_name": "products", "heading": "技术规格", "score": 0.7123},
    {"text": "基础版 ¥999/月...",       "doc_name": "products", "heading": "定价方案", "score": ...},
    {"text": "# SmartAssist Pro",       "doc_name": "products", "heading": "(简介)",   "score": ...},
]
```

排在第一条的是「技术规格」章节的 chunk，因为它的向量和查询 `"并发能支持多少"` 的向量距离最近。

**输出**：上面这个 `list[dict]`。

---

### 第 ⑦ 步：server.py → MCP 客户端（最终返回）

**输出**：

```json
{
  "project_id": "demo",
  "query": "并发能支持多少",
  "results": [
    {
      "text": "- 并发支持：单实例最高 1000 路并发对话\n- 响应速度：平均首字延迟 < 500ms",
      "doc_name": "products",
      "heading": "技术规格",
      "score": 0.7123
    },
    {"text": "...", "doc_name": "products", "heading": "定价方案", "score": "..."},
    {"text": "...", "doc_name": "products", "heading": "(简介)",   "score": "..."}
  ],
  "count": 3
}
```

如果库里没有数据（或 `project_id` 没入过库），`results` 为 `[]`，`count` 为 `0`。

---

## 总结：7 步调用链

| 步骤 | 从 → 到 | 函数 | 输入（关键参数） | 输出 |
|------|---------|------|------------------|------|
| ① | 客户端 → server | `ingest_document` | project_id, doc_name, content | — |
| ② | server → doc_processor | `chunk_document(content, doc_name)` | Markdown 字符串 | `list[dict]`（3 条 chunk） |
| ③ | server → retriever | `add_chunks(project_id, chunks)` | project_id + chunk 列表 | `3`（写入条数） |
|  | retriever → ChromaDB | `collection.upsert(ids, documents, metadatas)` | 3 个平行数组 | 无返回值（**向量化在此发生**） |
| ④ | server → 客户端 | return | — | `{"status":"ok","chunks":3}` |
| ⑤ | 客户端 → server | `search_knowledge` | query, project_id, top_k | — |
| ⑥ | server → retriever | `search(project_id, query, top_k)` | 查询字符串 | `list[dict]`（匹配结果） |
|  | retriever → ChromaDB | `collection.query(query_texts, n_results)` | 查询字符串 | ids, documents, distances, metadatas（**查询向量化在此发生**） |
| ⑦ | server → 客户端 | return | — | `{"results":[...],"count":3}` |

---

## 相关文档

- 模块职责与架构全貌：`RAG服务架构与流程解析.md`
- 启动与测试步骤：`RAG服务测试指南.md`
