# HTTP 网关：为什么用 FastAPI 而不是 MCP Proxy

## 直觉上的疑问

MCP SDK 本身支持 Server 和 Client。理论上可以让网关同时做 MCP Server（面向业务项目）和 MCP Client（连接共享服务），形成一个"MCP Proxy"：

```
方案 A — MCP Proxy：
  项目 A ──[MCP Client]──→ 网关 [MCP Server + MCP Client] ──→ 共享 MCP 服务

方案 B — FastAPI 网关（当前方案）：
  项目 A ──[HTTP Client]──→ 网关 [FastAPI + MCP Client] ──→ 共享 MCP 服务
```

MCP Proxy 看起来更"纯粹"——全链路都是 MCP 协议。那为什么选了 FastAPI？

---

## MCP Proxy 的问题

### 问题 1：MCP Server + MCP Client 同时运行复杂度高

一个进程要同时做两件事：

```
作为 MCP Server：监听来自项目的 MCP 请求
作为 MCP Client：连接 4 个共享服务

  MCP Server 部分              MCP Client 部分
┌──────────────────┐        ┌──────────────────────┐
│ 接收请求          │        │ 管理 4 条连接          │
│ 解析 MCP 协议     │   →    │ 转发到正确的目标服务    │
│ 返回 MCP 响应     │   ←    │ 汇总结果              │
│ 管理会话状态      │        │ 处理连接断开/重连      │
└──────────────────┘        └──────────────────────┘
```

MCP SDK 当前版本对这种"中间人"模式支持有限，需要手动管理会话生命周期、请求路由、错误传播等，代码量大且容易出错。

### 问题 2：治理能力要重新造轮子

网关的核心价值不只是转发，还有认证、日志、限流。这些在 HTTP/REST 生态里有成熟方案：

| 治理能力 | FastAPI 生态 | MCP 协议 |
|----------|-------------|----------|
| API Key 认证 | 中间件 3 行搞定 | 需自定义协议扩展 |
| 请求日志 + Trace ID | 中间件 + 标准 logging | 需拦截 MCP 消息流 |
| Token 配额限流 | 中间件读写计数器 | 需解析 MCP 响应提取用量 |
| Swagger 文档 | 自动生成 | 不适用 |
| 健康检查 | 一个 GET 端点 | 需自定义心跳协议 |

用 FastAPI，上面这些功能全是现成的中间件模式。用 MCP Proxy，每个都要自己实现。

### 问题 3：教学目标不匹配

这个项目的教学重点是**共享 MCP 服务的设计**，不是网关本身。用 FastAPI 做网关，读者一眼就懂：

```python
# 一看就明白：HTTP 请求进来 → 调 MCP → 返回结果
@router.post("/api/tool/call")
async def call_tool(body: ToolCallRequest):
    result = await mcp.call_tool(body.service, body.tool, body.arguments)
    return result
```

如果用 MCP Proxy，读者还得先理解"MCP Server 里面再做 MCP Client"的双向通信模式，注意力全被网关实现细节吸走了。

---

## 两种方案详细对比

### 架构对比

```
方案 A — MCP Proxy：
  项目 A ─┐                                    ┌─ LLM 网关
          ├─[MCP]─→ 网关 (MCP Server/Client) ─[MCP]─┤─ RAG 服务
  项目 B ─┘                                    ├─ 记忆服务
                                               └─ Prompt 中心
  ✅ 全链路 MCP
  ❌ 网关实现复杂
  ❌ 认证/日志/限流要自己造

方案 B — FastAPI 网关（采用）：
  项目 A ─┐                                    ┌─ LLM 网关
          ├─[HTTP]─→ 网关 (FastAPI + MCP Client) ─[MCP]─┤─ RAG 服务
  项目 B ─┘                                    ├─ 记忆服务
                                               └─ Prompt 中心
  ✅ 网关功能开箱即用
  ✅ 治理能力成熟（认证/日志/限流）
  ✅ 项目接入简单（发 HTTP 就行）
  ❌ 项目到网关这段不是 MCP 协议
```

### 项目接入成本对比

```
MCP Proxy 方案 — 项目需要引入 MCP SDK：
  pip install mcp
  from mcp import ClientSession
  from mcp.client.streamable_http import streamablehttp_client
  async with streamablehttp_client(url) as (r, w, _):
      async with ClientSession(r, w) as session:
          await session.initialize()
          result = await session.call_tool("chat_completion", {...})

FastAPI 网关 — 项目只需要发 HTTP：
  resp = await httpx.post("http://localhost:8000/api/tool/call", json={...})
  result = resp.json()
```

HTTP 是所有语言都能发的请求，MCP 需要专门的 SDK。对于业务项目来说，HTTP 更轻量。

---

## 第三种方案：项目直连 MCP 服务

```
方案 C — 直连（不要网关）：
  项目 A ──[MCP Client]──→ LLM 网关
  项目 A ──[MCP Client]──→ RAG 服务
  项目 A ──[MCP Client]──→ 记忆服务
  项目 A ──[MCP Client]──→ Prompt 中心

  项目 B ──[MCP Client]──→ LLM 网关
  项目 B ──[MCP Client]──→ RAG 服务
  ...
```

问题显而易见：

| 维度 | 直连 | 有网关 |
|------|------|--------|
| 连接数 | N 项目 × 4 服务 = 4N 条 | N 项目 → 1 网关 → 4 服务 |
| 认证 | 每个服务各自实现 | 网关统一认证一次 |
| 日志 | 分散在各服务 | 网关统一记录，Trace ID 串联 |
| 配额 | 无法统一管控 | 网关集中限流 |
| 服务地址变更 | 每个项目都要改 | 只改网关配置 |

**网关的核心价值是「收口」**：所有请求经过同一个入口，治理策略集中管理。

---

## 选 FastAPI 的三层原因

### 工程层面——治理能力开箱即用

```python
# main.py：三行中间件 = 日志 + 认证 + 限流
app.add_middleware(QuotaMiddleware, tracker=quota_tracker)    # 限流
app.add_middleware(AuthMiddleware, projects=config["projects"])  # 认证
app.add_middleware(LoggerMiddleware)                            # 日志
```

Starlette 的中间件链天然是洋葱模型，请求先过 Logger（分配 Trace ID）→ Auth（校验 Key）→ Quota（检查配额），响应反向回来。用 MCP Proxy 实现同样的功能需要自己搭建这套拦截链。

### 接入层面——HTTP 最通用

项目只需要 `httpx`（甚至 `curl`）就能调用所有共享服务。不需要引入 MCP SDK，不需要理解 MCP 协议。

### 教学层面——关注点分离

读者在学习时只需关注两个核心概念：
- **共享 MCP 服务**：怎么设计、怎么注册 Tool / Prompt
- **网关治理**：怎么认证、怎么限流、怎么记日志

这两个关注点被清晰地分开了。如果用 MCP Proxy，两者混在一起，学习曲线陡增。

---

## 什么时候 MCP Proxy 更合适

| 场景 | 更适合 | 原因 |
|------|--------|------|
| 全链路 MCP 协议一致性要求高 | MCP Proxy | 无协议转换 |
| AI Agent 框架原生支持 MCP | MCP Proxy | 减少适配层 |
| 需要成熟的 HTTP 治理（认证/日志/限流） | **FastAPI 网关** | 生态成熟 |
| 快速开发，教学演示 | **FastAPI 网关** | 实现简单 |
| 多语言项目接入 | **FastAPI 网关** | HTTP 通用 |

---

## 迁移成本

如果未来 MCP SDK 对 Proxy 模式支持更好了，迁移主要改的是网关入口，共享服务完全不动：

```
当前：项目 ─[HTTP]─→ FastAPI (router.py) ─[MCP Client]─→ 共享服务
未来：项目 ─[MCP]──→ MCP Proxy (proxy.py) ─[MCP Client]─→ 共享服务
                                                          ↑ 完全不用改
```

网关只是「接入层」，改了接入协议，下游的 4 个 MCP 服务一行不动。

---

## 结论

**务实选择，不追求协议纯粹性。**

- FastAPI 网关的认证、日志、限流能力开箱即用，MCP Proxy 需要从零实现
- HTTP 是最通用的接入协议，降低业务项目的对接成本
- 网关本身不是教学重点，应该尽量简单，把注意力留给共享 MCP 服务
- 共享服务之间依然是纯 MCP 协议，不受网关选型影响
