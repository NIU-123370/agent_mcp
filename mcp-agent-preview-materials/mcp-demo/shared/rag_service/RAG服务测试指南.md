# RAG 服务测试指南

---

## 快速测试（一键跑通）

两个终端，三步搞定：

### 终端 1：启动 RAG 服务

```bash
cd mcp-demo
uv run shared/rag_service/server.py
```

看到这行就成功了：

```
Uvicorn running on http://127.0.0.1:9002 (Press CTRL+C to quit)
```

> 首次启动会自动下载 ChromaDB 内置 embedding 模型（约 80MB），需等一会。

### 终端 2：运行测试脚本

```bash
cd mcp-demo
uv run scripts/test_rag_service.py
```

### 预期输出

```
正在连接 RAG 服务: http://127.0.0.1:9002/mcp
连接成功!

可用工具 (2 个):
  - ingest_document
  - search_knowledge

==================================================
测试 1: ingest_document (产品资料 → 客服项目)
==================================================
  状态: ok
  分块数: 7

==================================================
测试 2: ingest_document (写作素材 → 写作项目)
==================================================
  状态: ok
  分块数: 6

==================================================
测试 3: search_knowledge (客服项目搜'产品价格')
==================================================
  结果数: 2
  [0] score=xxx heading=xxx
      （应命中产品资料中的定价方案相关内容）

==================================================
测试 4: 数据隔离 (写作项目搜'产品价格')
==================================================
  结果数: 2
  [0] score=xxx heading=xxx
      （应返回写作素材内容，搜不到产品信息）
  → 隔离验证通过：写作项目搜不到产品相关内容

所有测试完成!
```

### 验证要点

| 测试项 | 通过标准 |
|--------|---------|
| 测试 1 | 状态 `ok`，分块数 > 0 |
| 测试 2 | 状态 `ok`，分块数 > 0 |
| 测试 3 | 返回结果中包含产品定价相关内容 |
| 测试 4 | 返回的是写作素材，不含产品信息 → 数据隔离生效 |

测完后在终端 1 按 `Ctrl+C` 停掉服务。

---

## 测试脚本干了什么（流程解析）

```
测试脚本                        RAG Server (:9002)              ChromaDB
   │                                │                              │
   │── ingest_document ───────────→│                              │
   │   project_id="customer-service"│── chunk_document() ─→ 7块   │
   │   content=products.md          │── collection.upsert() ─────→│  写入 rag_customer_service
   │←─ {status:ok, chunks:7} ─────│                              │
   │                                │                              │
   │── ingest_document ───────────→│                              │
   │   project_id="writing-assistant│── chunk_document() ─→ 6块   │
   │   content=writing_guides.md    │── collection.upsert() ─────→│  写入 rag_writing_assistant
   │←─ {status:ok, chunks:6} ─────│                              │
   │                                │                              │
   │── search_knowledge ──────────→│                              │
   │   query="产品价格是多少"        │── collection.query() ──────→│  在 rag_customer_service 中搜
   │   project_id="customer-service"│←─ 命中定价方案 ──────────────│
   │←─ {results:[...]} ───────────│                              │
   │                                │                              │
   │── search_knowledge ──────────→│                              │
   │   query="产品价格是多少"        │── collection.query() ──────→│  在 rag_writing_assistant 中搜
   │   project_id="writing-assistant│←─ 只有写作素材 ──────────────│  ← 搜不到产品信息！
   │←─ {results:[...]} ───────────│                              │
```

数据隔离原理：`project_id` 不同 → ChromaDB collection 不同 → 数据物理隔离。

---

## 常见问题

### Q: 首次运行特别慢？

正常。ChromaDB 首次使用会下载 embedding 模型（all-MiniLM-L6-v2，约 80MB）。后续运行会缓存在本地，秒级启动。

### Q: 想清空知识库重新导入？

```bash
# 删除 ChromaDB 持久化数据
Remove-Item -Recurse -Force data/chromadb    # Windows PowerShell
# 或
rm -rf data/chromadb                         # Mac/Linux
```

然后重新启动服务并运行测试脚本即可。

### Q: score 是负数正常吗？

正常。ChromaDB 默认用欧氏距离（L2），我们的代码做了 `1 - distance` 转换。当距离较大时 score 可能为负。score 越大（越接近 1）表示越相关。
