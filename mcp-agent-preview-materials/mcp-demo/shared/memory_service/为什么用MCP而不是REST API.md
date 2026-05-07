# 记忆服务：为什么用 MCP 而不是 REST API

## 直觉上的疑问

记忆服务干的活就是**增删查**——存对话、取对话、存用户事实、取用户事实。用 REST API 完全能做：

```
对话记忆：
  POST   /memory/save       → 存一条
  GET    /memory/recall      → 取 N 条
  DELETE /memory/clear       → 清空

用户画像：
  POST   /profile/save       → 存事实
  GET    /profile/recall      → 取事实
  DELETE /profile/delete      → 删事实
```

FastAPI 写 6 个路由就搞定，比 MCP 还简单。那为什么要用 MCP？

---

## 单看这个服务：MCP 确实"重"了

MCP 相比 REST 多了协议层开销：

```
REST：  POST /memory/save  →  返回 JSON          （一次 HTTP 往返）
MCP ：  初始化会话 → call_tool("save_memory", {})  （有会话管理开销）
```

对一个纯 CRUD 服务来说，这些都不是必要的。

---

## 放到整个架构里看：统一协议的价值

关键在于记忆服务**不是独立存在的**，它是四个共享服务之一。

### 如果协议不统一

```
网关 (gateway)
  ├─ MCP Client  ──→  LLM 网关     (MCP)
  ├─ MCP Client  ──→  RAG 服务     (MCP)
  ├─ HTTP Client ──→  记忆服务     (REST)      ← 独一个异类
  └─ MCP Client  ──→  Prompt 中心  (MCP)
```

网关要维护两套逻辑：MCP 连接管理 + HTTP 请求管理、两种错误处理、两种服务发现方式。

### 如果协议统一

```
网关 (gateway)
  ├─ MCP Client  ──→  LLM 网关     (MCP)
  ├─ MCP Client  ──→  RAG 服务     (MCP)
  ├─ MCP Client  ──→  记忆服务     (MCP)      ← 同一套
  └─ MCP Client  ──→  Prompt 中心  (MCP)
```

一个 `mcp_client_manager.py` 管全部，调用方式全是 `call_tool(name, args)`。

### 对比表

| 维度 | 全部 MCP | 混合（MCP + REST） |
|------|---------|-------------------|
| 连接管理 | 一套 | 两套 |
| 调用方式 | 统一 `call_tool` | `call_tool` + `httpx.post` |
| 服务发现 | `list_tools()` 自描述 | REST 需额外维护文档 |
| 错误处理 | 一套 MCP 错误模型 | 两套 |
| 新增服务 | 注册 MCP Server，网关零改动 | 要看是 MCP 还是 REST |

**一句话：不是记忆服务需要 MCP，是整个架构需要统一协议。**

---

## 选 MCP 的两层原因

### 架构层面——统一协议简化治理

网关的路由代码只需要一种调用方式：

```python
async def call_service(service_name: str, tool_name: str, args: dict):
    session = await mcp_client_manager.get_session(service_name)
    return await session.call_tool(tool_name, args)
```

无论是调大模型、检索知识、存取记忆还是获取 Prompt，全是同一个 `call_tool`。

### 教学层面——概念聚焦

这个项目是为了演示「MCP 如何在多项目间共享服务」。如果记忆服务用 REST，读者会困惑——"哪些该用 MCP、哪些该用 REST？边界在哪？"。全部 MCP 把概念讲得更清晰。

---

## 什么时候 REST 比 MCP 更合适

| 场景 | 更适合 | 原因 |
|------|--------|------|
| 高频调用（每秒数百次） | REST | 更轻量，无会话开销 |
| 需要 HTTP 语义（缓存、分页） | REST | 原生支持 |
| 独立对外暴露给第三方 | REST | Swagger 生态成熟 |
| 统一架构内的共享能力 | **MCP** | 协议一致，网关好管 |
| AI Agent 动态发现和调用 | **MCP** | `list_tools()` 天然自描述 |

---

## 迁移成本很低

代码分层设计保证了**协议层和存储层解耦**：

```
当前（MCP）：  MCP Client → server.py (6个Tool)  → store.py (SQLite)
改成 REST ：  HTTP Client → api.py (6个路由)     → store.py (SQLite)
                                                     ↑ 完全不用改
```

`store.py` 的 251 行存储逻辑一行不动，只需要把 `server.py` 的 6 个 `@server.tool()` 替换成 FastAPI 的 6 个 `@app.post()`。这也印证了当前架构的合理性——换协议不影响业务。

---

## 结论

**合理，但要知道这是权衡选择。**

- 在本项目中：统一 MCP 是更好的选择（架构一致 + 教学清晰）
- 在生产环境中：如果调用量大或需要对外暴露，换 REST 完全合理
- 无论怎么换：`store.py` 不受影响，迁移成本极低
