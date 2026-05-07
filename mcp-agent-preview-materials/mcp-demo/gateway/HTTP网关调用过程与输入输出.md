# HTTP 网关调用过程与输入输出

用具体场景把 6 个端点从头到尾走一遍。每一步列出：调了什么、传进去什么、返回什么。

---

## 场景设定

模拟客服项目通过网关调用共享服务的全过程：

```
项目 A（智能客服）通过 HTTP 网关：
  1. 检查服务健康状态
  2. 保存一条对话记录（调用记忆服务 Tool）
  3. 获取客服 Prompt（调用 Prompt 中心 Prompt）
  4. 查看配额使用情况
```

网关地址：`http://127.0.0.1:8000`
API Key：`cs-demo-key-001`（对应 project_id = `customer-service`）

---

## 第一部分：健康检查（无需认证）

### 第 ① 步：GET /api/health

启动后首先确认所有服务都正常。

**请求**：

```http
GET /api/health HTTP/1.1
Host: 127.0.0.1:8000
```

不需要 API Key，任何人都能调用。

**正常响应**（全部服务在线）：

```json
{
  "status": "ok",
  "services": {
    "llm-gateway": {"service": "llm-gateway", "status": "ok", "tools": 3},
    "rag-service": {"service": "rag-service", "status": "ok", "tools": 2},
    "memory-service": {"service": "memory-service", "status": "ok", "tools": 6},
    "prompt-hub": {"service": "prompt-hub", "status": "ok", "tools": 1}
  }
}
```

**降级响应**（部分服务未启动）：

```json
{
  "status": "degraded",
  "services": {
    "llm-gateway": {"service": "llm-gateway", "status": "error", "message": "连接被拒绝"},
    "rag-service": {"service": "rag-service", "status": "ok", "tools": 2},
    "memory-service": {"service": "memory-service", "status": "ok", "tools": 6},
    "prompt-hub": {"service": "prompt-hub", "status": "ok", "tools": 1}
  }
}
```

| 字段 | 说明 |
|------|------|
| status | `"ok"` 全部正常，`"degraded"` 有服务不可用 |
| services[name].tools | 该服务注册的 Tool 数量 |

**内部流程**：网关对每个服务调用 `MCPClientManager.check_health()` → 建立 MCP 会话 → `list_tools()` → 关闭。能连上就是 ok，连不上就是 error。

---

## 第二部分：认证机制

### 第 ② 步：无 Key 请求 → 401

**请求**（没有 X-API-Key 头）：

```http
POST /api/tool/call HTTP/1.1
Content-Type: application/json

{"service": "memory-service", "tool": "recall_memory", "arguments": {"project_id": "test", "session_id": "s1"}}
```

**响应**：

```json
HTTP/1.1 401 Unauthorized

{"error": "无效的 API Key", "hint": "请在请求头中设置 X-API-Key"}
```

### 第 ③ 步：错误 Key → 401

**请求**：

```http
POST /api/tool/call HTTP/1.1
X-API-Key: wrong-key-xxx
Content-Type: application/json

{"service": "memory-service", "tool": "recall_memory", "arguments": {"project_id": "test", "session_id": "s1"}}
```

**响应**：同上 401。

### 认证通过后

请求头带上正确的 API Key，AuthMiddleware 将其映射为 project_id：

```
X-API-Key: "cs-demo-key-001"  →  project_id = "customer-service"
X-API-Key: "wa-demo-key-001"  →  project_id = "writing-assistant"
```

project_id 写入 `request.state.project_id`，供 Quota 中间件和 Router 使用。

---

## 第三部分：调用 MCP Tool

### 第 ④ 步：POST /api/tool/call（保存对话记录）

**请求**：

```http
POST /api/tool/call HTTP/1.1
X-API-Key: cs-demo-key-001
Content-Type: application/json

{
  "service": "memory-service",
  "tool": "save_memory",
  "arguments": {
    "project_id": "customer-service",
    "session_id": "session-001",
    "role": "user",
    "content": "专业版多少钱？"
  }
}
```

**请求体字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| service | str | 目标 MCP 服务名（对应 config.yaml 中的 services 键） |
| tool | str | 要调用的 Tool 名称 |
| arguments | dict | Tool 的参数（原样传给 MCP Server） |

**成功响应**：

```json
{
  "status": "ok",
  "id": 42,
  "project_id": "customer-service",
  "session_id": "session-001"
}
```

响应头包含：`X-Trace-ID: a1b2c3d4e5f6`

**内部流程**：

```
Router.call_tool()
  │
  ├─ 解析 body: service=memory-service, tool=save_memory
  │
  ├─ MCPClientManager.call_tool("memory-service", "save_memory", {...})
  │   ├─ 从 config 查到 url = "http://127.0.0.1:9003/mcp"
  │   ├─ streamablehttp_client(url) → 建立 MCP 连接
  │   ├─ session.initialize()
  │   ├─ session.call_tool("save_memory", arguments)
  │   ├─ 解析结果 JSON
  │   └─ 关闭连接
  │
  └─ 返回 MCP Tool 的响应 JSON
```

### 第 ⑤ 步：POST /api/tool/call（调用 LLM）

**请求**：

```json
{
  "service": "llm-gateway",
  "tool": "chat_completion",
  "arguments": {
    "messages": [{"role": "user", "content": "你好，请介绍一下专业版"}],
    "project_id": "customer-service",
    "model": "auto",
    "temperature": 0.7,
    "max_tokens": 1000
  }
}
```

**成功响应**：

```json
{
  "content": "专业版是我们面向中大型企业的解决方案...",
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 156,
    "total_tokens": 184
  },
  "model": "doubao-pro",
  "project_id": "customer-service"
}
```

**Token 计量**：Router 检测到 tool == `"chat_completion"` 且响应含 `usage` 字段，自动将 `total_tokens` (184) 累加到 customer-service 的今日配额用量。

---

## 第四部分：获取 MCP Prompt

### 第 ⑥ 步：POST /api/prompt/get

**请求**：

```http
POST /api/prompt/get HTTP/1.1
X-API-Key: cs-demo-key-001
Content-Type: application/json

{
  "service": "prompt-hub",
  "prompt": "customer_service_qa",
  "arguments": {
    "context": "专业版每月 2999 元，含高级分析功能。",
    "history": "用户: 我想了解专业版\n客服: 好的，专业版是我们的核心产品。",
    "question": "多少钱？",
    "user_profile": "budget: 月预算 5000 以内"
  }
}
```

**请求体字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| service | str | 目标 MCP 服务名 |
| prompt | str | Prompt 名称（MCP 原生 Prompt） |
| arguments | dict | Prompt 的参数 |

**成功响应**：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "你是一个专业的客服助手。请严格根据提供的参考资料回答用户问题。\n如果参考资料中没有相关信息，请诚实地说\u201c抱歉，我没有找到相关信息\u201d。\n回答要简洁专业，使用中文。\n\n## 参考资料\n专业版每月 2999 元，含高级分析功能。\n\n## 用户画像\nbudget: 月预算 5000 以内\n\n## 对话历史\n用户: 我想了解专业版\n客服: 好的，专业版是我们的核心产品。\n\n## 用户问题\n多少钱？\n"
    }
  ]
}
```

**内部流程**：网关调用 `MCPClientManager.get_prompt()` → MCP 会话的 `session.get_prompt("customer_service_qa", arguments)` → Prompt 中心渲染模板 → 返回 `{role, content}` 格式的消息。

### 第 ⑦ 步：GET /api/prompt/list

**请求**：

```http
GET /api/prompt/list?service=prompt-hub HTTP/1.1
X-API-Key: cs-demo-key-001
```

**响应**：

```json
{
  "prompts": [
    {
      "name": "customer_service_qa",
      "description": "客服问答 — 基于知识库、用户画像和历史对话回答用户问题",
      "arguments": [
        {"name": "context", "description": "", "required": true},
        {"name": "history", "description": "", "required": true},
        {"name": "question", "description": "", "required": true},
        {"name": "user_profile", "description": "", "required": false}
      ]
    },
    {
      "name": "writing_assistant",
      "description": "写作生成 — 基于主题和参考资料生成文章",
      "arguments": [
        {"name": "topic", "description": "", "required": true},
        {"name": "references", "description": "", "required": true},
        {"name": "style", "description": "", "required": false},
        {"name": "user_profile", "description": "", "required": false}
      ]
    }
  ],
  "count": 2
}
```

---

## 第五部分：配额查询

### 第 ⑧ 步：GET /api/quota/usage

**请求**：

```http
GET /api/quota/usage HTTP/1.1
X-API-Key: cs-demo-key-001
```

**响应**：

```json
{
  "project_id": "customer-service",
  "date": "2026-04-06",
  "used_tokens": 184,
  "daily_limit": 100000,
  "remaining": 99816
}
```

| 字段 | 说明 |
|------|------|
| used_tokens | 今日已消耗的 Token 数 |
| daily_limit | 每日限额 |
| remaining | 剩余可用（limit - used） |

---

## 第六部分：错误场景

### 服务不可用 → 502

MCP 服务未启动时调用 Tool：

```json
HTTP/1.1 502 Bad Gateway

{
  "error": "MCP 服务调用失败: [Errno 111] Connection refused",
  "hint": "请确认 llm-gateway 服务已启动",
  "trace_id": "a1b2c3d4e5f6"
}
```

### 未知服务名 → 502

```json
HTTP/1.1 502 Bad Gateway

{
  "error": "未知服务: unknown-service（可用: llm-gateway, rag-service, memory-service, prompt-hub）",
  "trace_id": "a1b2c3d4e5f6"
}
```

### 配额用尽 → 429

```json
HTTP/1.1 429 Too Many Requests

{
  "error": "Token 配额已用尽",
  "project_id": "customer-service",
  "date": "2026-04-06",
  "used_tokens": 100023,
  "daily_limit": 100000,
  "remaining": 0
}
```

---

## 完整场景时间线

```
时间轴 ─────────────────────────────────────────────────────────────→

10:00  启动 4 个 MCP 服务 + 网关
       网关日志: 注册服务: llm-gateway, rag-service, memory-service, prompt-hub
       网关日志: 注册项目: customer-service, writing-assistant

10:05  项目 A（客服 Agent）                 10:10  项目 B（写作 Agent）

  请求: POST /api/tool/call                  请求: POST /api/tool/call
  Header: X-API-Key: cs-demo-key-001        Header: X-API-Key: wa-demo-key-001
    │                                          │
    │ 网关处理链:                              │ 网关处理链:
    ├─ Logger: trace=abc123                   ├─ Logger: trace=def456
    ├─ Auth: project=customer-service         ├─ Auth: project=writing-assistant
    ├─ Quota: 已用 0/100000, 放行              ├─ Quota: 已用 0/100000, 放行
    ├─ Router: → memory-service.save_memory   ├─ Router: → rag-service.search_knowledge
    │   └─ MCP Client → :9003/mcp            │   └─ MCP Client → :9002/mcp
    └─ 200 OK (85ms)                          └─ 200 OK (120ms)
      │                                          │
      ├─ POST /api/prompt/get                   ├─ POST /api/prompt/get
      │  → prompt-hub.customer_service_qa       │  → prompt-hub.writing_assistant
      │  → 200 OK (60ms)                        │  → 200 OK (55ms)
      │                                          │
      ├─ POST /api/tool/call                    ├─ POST /api/tool/call
      │  → llm-gateway.chat_completion          │  → llm-gateway.chat_completion
      │  → 200 OK, +184 tokens (1200ms)         │  → 200 OK, +312 tokens (1800ms)
      │                                          │
      └─ 配额: 184/100000                       └─ 配额: 312/100000
```

---

## 端点速查表

| 端点 | 方法 | 认证 | 输入 | 输出 | 说明 |
|------|------|------|------|------|------|
| `/api/tool/call` | POST | 是 | `{service, tool, arguments}` | Tool 返回的 JSON | 核心端点 |
| `/api/tool/list` | POST | 是 | `{service}` | `{tools, count}` | 发现能力 |
| `/api/prompt/get` | POST | 是 | `{service, prompt, arguments}` | `{messages}` | 获取渲染 Prompt |
| `/api/prompt/list` | GET | 是 | `?service=xxx` | `{prompts, count}` | 列出 Prompt |
| `/api/health` | GET | 否 | 无 | `{status, services}` | 健康检查 |
| `/api/quota/usage` | GET | 是 | 无 | `{used_tokens, daily_limit, ...}` | 配额查询 |
