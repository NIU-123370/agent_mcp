# HTTP 网关架构与流程解析

## 这个网关解决什么问题

4 个共享 MCP 服务各自独立运行，业务项目如果直接对接：

```
没有网关：
  项目 A ──→ LLM 网关 (9001)      每个项目维护 4 条连接
  项目 A ──→ RAG 服务 (9002)      认证逻辑重复写 4 遍
  项目 A ──→ 记忆服务 (9003)      没有统一日志
  项目 A ──→ Prompt 中心 (9004)   无法统一限流

有了网关：
  项目 A ──→ 网关 (8000) ──→ 4 个 MCP 服务
  项目 B ──→ 网关 (8000) ──→ 4 个 MCP 服务

  ✅ 一个入口收口所有请求
  ✅ 统一认证、统一日志、统一限流
  ✅ 项目只需对接一个 HTTP 地址
```

---

## 它在多项目架构中的位置

```
项目 A/B（HTTP Client）                            共享 MCP 服务
┌──────────┐                                    ┌────────────────┐
│ app.py   │    POST /api/tool/call             │ LLM 网关  :9001│
│ agent.py │    POST /api/prompt/get            │ RAG 服务  :9002│
│          │──────────────────────→  网关 (:8000) ──→ │ 记忆服务  :9003│
│ gateway_ │    Header: X-API-Key    │          │ │ Prompt 中心:9004│
│ client.py│                         │          │ └────────────────┘
└──────────┘                         │          │
                                     │  FastAPI │
                                     │  ┌───────┤
                                     │  │Logger │ 分配 Trace ID
                                     │  │Auth   │ 校验 API Key
                                     │  │Quota  │ 检查配额
                                     │  │Router │ 转发到 MCP 服务
                                     │  └───────┤
                                     └──────────┘
```

---

## 六个源文件 + 一个配置文件，各管什么

```
gateway/
├── main.py               # 入口：组装 FastAPI + 中间件
├── auth.py               # 中间件：API Key → project_id
├── logger.py             # 中间件：Trace ID + 耗时日志
├── quota.py              # 中间件：Token 配额限流
├── router.py             # 路由：6 个 HTTP 端点
├── mcp_client_manager.py # MCP 客户端：连接 4 个共享服务
└── config.yaml           # 配置：服务地址 + 项目 Key + 配额
```

### 各文件一句话职责

| 文件 | 做什么 | 读什么/写什么 |
|------|--------|-------------|
| `main.py` | 创建 FastAPI app，按顺序挂载中间件 | 读 config.yaml |
| `logger.py` | 每个请求分配 12 位 Trace ID，记录耗时 | 写日志 + 写响应头 X-Trace-ID |
| `auth.py` | 从 X-API-Key 头提取 project_id | 读 config 中的 key 映射 |
| `quota.py` | 检查项目当天 Token 是否超限 | 读写内存计数器 |
| `router.py` | 6 个 HTTP 端点，转发请求到 MCP 服务 | 调用 mcp_client_manager |
| `mcp_client_manager.py` | 管理到 4 个 MCP Server 的连接 | 通过 Streamable HTTP 调 MCP |
| `config.yaml` | 服务注册表 + 项目 API Key + 配额 | 启动时加载一次 |

---

## 中间件链路详解

FastAPI 中间件遵循**洋葱模型**——最后添加的最先执行：

```python
# main.py 中的注册顺序（代码顺序）
app.add_middleware(QuotaMiddleware, ...)    # ③ 第三个注册 → 第三个执行
app.add_middleware(AuthMiddleware, ...)     # ② 第二个注册 → 第二个执行
app.add_middleware(LoggerMiddleware)        # ① 第一个注册 → 第一个执行（最外层）
```

请求实际经过的顺序：

```
请求进入
  │
  ▼
┌─────────────────────────────────────────────────┐
│ LoggerMiddleware                                 │
│  → 分配 trace_id = "a1b2c3d4e5f6"              │
│  → 记录: [a1b2c3d4e5f6] → POST /api/tool/call  │
│  ┌───────────────────────────────────────────┐  │
│  │ AuthMiddleware                             │  │
│  │  → 读取 X-API-Key: "cs-demo-key-001"     │  │
│  │  → 匹配到 project_id = "customer-service" │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │ QuotaMiddleware                      │  │  │
│  │  │  → 检查 customer-service 今日用量    │  │  │
│  │  │  → 未超限，放行                      │  │  │
│  │  │  ┌───────────────────────────────┐  │  │  │
│  │  │  │ Router (call_tool 端点)       │  │  │  │
│  │  │  │  → 解析 body: service, tool   │  │  │  │
│  │  │  │  → mcp.call_tool(...)         │  │  │  │
│  │  │  │  → 累加 token 用量到 quota    │  │  │  │
│  │  │  │  → 返回结果                   │  │  │  │
│  │  │  └───────────────────────────────┘  │  │  │
│  │  │  ← 放行                             │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │  ← 认证通过                                │  │
│  └───────────────────────────────────────────┘  │
│  ← 记录: [a1b2c3d4e5f6] ← 200  125ms          │
│  ← 写入响应头: X-Trace-ID: a1b2c3d4e5f6        │
└─────────────────────────────────────────────────┘
  │
  ▼
响应返回
```

### 为什么是这个顺序

| 顺序 | 中间件 | 原因 |
|------|--------|------|
| 1 | Logger | 必须最先执行，给后续所有中间件和路由提供 trace_id |
| 2 | Auth | 在检查配额之前，必须先知道是哪个项目 |
| 3 | Quota | 知道 project_id 后才能查对应的配额 |

---

## MCP 客户端管理器

### 连接模式：每次调用独立短连接

```python
# mcp_client_manager.py 的核心逻辑
async with streamablehttp_client(url) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
```

每次调用都是：建立连接 → 初始化会话 → 执行操作 → 关闭。

| 维度 | 短连接（当前） | 长连接池 |
|------|-------------|---------|
| 实现复杂度 | 低 | 高（需管理连接生命周期） |
| 延迟 | 每次有建连开销（~50ms） | 复用连接，延迟更低 |
| 可靠性 | 高（无状态，不怕连接断开） | 需处理连接失效/重连 |
| 适用场景 | 演示项目 | 高并发生产环境 |

### 支持的 MCP 操作

```
MCPClientManager
  ├── call_tool(service, tool, arguments)     → 调用 Tool
  ├── get_prompt(service, prompt, arguments)  → 获取渲染后的 Prompt
  ├── list_tools(service)                     → 列出 Tool 清单
  ├── list_prompts(service)                   → 列出 Prompt 清单
  └── check_health(service)                   → 检查服务是否可连接
```

---

## 配置文件结构

```yaml
# config.yaml
services:                           # 服务注册表
  llm-gateway:
    url: "http://127.0.0.1:9001/mcp"
  rag-service:
    url: "http://127.0.0.1:9002/mcp"
  memory-service:
    url: "http://127.0.0.1:9003/mcp"
  prompt-hub:
    url: "http://127.0.0.1:9004/mcp"

projects:                           # 项目配置
  customer-service:
    api_key: "cs-demo-key-001"      # API Key → project_id 映射
    quota:
      daily_tokens: 100000          # 每日 Token 上限
  writing-assistant:
    api_key: "wa-demo-key-001"
    quota:
      daily_tokens: 100000
```

配置在启动时加载一次，运行中不会重新读取。修改配置需重启网关。

### 服务发现机制

网关不做动态服务发现，所有服务地址在 `config.yaml` 中静态注册。这是有意简化：

```
当前（静态注册）：config.yaml 列出所有服务地址，网关启动时读取
生产方案：      Consul / etcd / Kubernetes Service Discovery
```

静态注册适合演示和小规模部署。需要动态发现时，改 `MCPClientManager.__init__` 的服务加载逻辑即可，路由和中间件不受影响。

---

## 六个 HTTP 端点

| 端点 | 方法 | 认证 | 用途 |
|------|------|------|------|
| `/api/tool/call` | POST | 需要 | 调用 MCP Tool（核心端点） |
| `/api/tool/list` | POST | 需要 | 列出指定服务的 Tool |
| `/api/prompt/get` | POST | 需要 | 获取渲染后的 Prompt |
| `/api/prompt/list` | GET | 需要 | 列出可用 Prompt |
| `/api/health` | GET | 不需要 | 健康检查 + 各服务状态 |
| `/api/quota/usage` | GET | 需要 | 查看当前项目配额使用 |

### 核心端点 vs 治理端点

```
核心端点（转发 MCP 请求）：
  /api/tool/call    → MCPClientManager.call_tool()
  /api/tool/list    → MCPClientManager.list_tools()
  /api/prompt/get   → MCPClientManager.get_prompt()
  /api/prompt/list  → MCPClientManager.list_prompts()

治理端点（网关自身能力）：
  /api/health       → 遍历所有服务做连通性检测
  /api/quota/usage  → 读取内存中的配额计数器
```

---

## Token 配额计量

配额跟踪的完整流程：

```
  1. 请求进入 → QuotaMiddleware 检查该项目今日是否还有余量
     └→ 超限：直接返回 429
     └→ 未超限：放行

  2. Router 调用 MCP Tool

  3. 如果 tool == "chat_completion" 且返回了 usage 字段：
     └→ 提取 total_tokens
     └→ QuotaTracker.add(project_id, total_tokens)   # 累加到今日用量

  4. 下次请求进入时，QuotaMiddleware 拿到更新后的用量检查
```

只有 `chat_completion` 会计量 Token。RAG 检索、记忆读写等操作不消耗 Token 配额。

### 内存计数器结构

```python
# QuotaTracker 内部状态
{
    "customer-service": {
        "2026-04-06": 3582    # 今日已用 3582 tokens
    },
    "writing-assistant": {
        "2026-04-06": 1205    # 今日已用 1205 tokens
    }
}
```

按项目 × 日期隔离，每天自动重置（新日期创建新 key）。内存存储意味着网关重启后清零——对演示场景够用，生产环境换 Redis 即可。

---

## 与共享 MCP 服务的对比

| | HTTP 网关 | LLM 网关 | RAG 服务 | 记忆服务 | Prompt 中心 |
|--|----------|---------|---------|---------|------------|
| **一句话** | 统一入口 + 治理 | 调用大模型 | 检索知识库 | 记住对话 + 画像 | 管理提示词 |
| **协议** | HTTP (FastAPI) | MCP | MCP | MCP | MCP |
| **角色** | MCP Client | MCP Server | MCP Server | MCP Server | MCP Server |
| **存储** | 内存（配额计数器） | 无 | ChromaDB | SQLite | JSON 文件 |
| **端口** | 8000 | 9001 | 9002 | 9003 | 9004 |

网关是唯一一个用 HTTP 而不是 MCP 协议面向外部的组件。它做的事是**协议转换**：把简单的 HTTP/JSON 请求翻译成 MCP 的 `call_tool` / `get_prompt` 调用。

---

## 启动方式

```bash
cd mcp-demo
uv run uvicorn gateway.main:app --port 8000
```

确保 4 个 MCP 服务先于网关启动。网关启动后会输出注册的服务和项目列表。
