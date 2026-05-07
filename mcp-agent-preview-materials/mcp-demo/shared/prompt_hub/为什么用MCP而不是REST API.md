# Prompt 中心：为什么用 MCP 而不是 REST API

## 直觉上的疑问

Prompt 中心干的活就是**管理模板 + 渲染文本**——列出模板、填参数、返回字符串。用 REST API 完全能做：

```
GET    /prompts                          → 列出所有模板
GET    /prompts/customer_service_qa      → 获取模板详情
POST   /prompts/customer_service_qa/render → 传参数，返回渲染后文本
```

FastAPI 写 3 个路由就搞定。甚至更简单：直接在业务代码里用 Jinja2 渲染模板，连独立服务都不需要。那为什么要用 MCP？

---

## 单看这个服务：MCP 确实"重"了

Prompt 中心连数据库都没有，就是读 YAML + 字符串替换。相比 REST：

```
REST：  POST /prompts/render  →  返回渲染后文本     （一次 HTTP 往返）
MCP ：  初始化会话 → get_prompt("name", args)        （有会话管理开销）
```

甚至：
```
不用服务：  Python 代码里直接 template.format(**args)  （零网络开销）
```

对一个纯文本模板服务来说，MCP 的协议开销不是必要的。

---

## 放到整个架构里看：统一协议的价值

关键在于 Prompt 中心**不是独立存在的**，它是四个共享服务之一。

### 如果协议不统一

```
网关 (gateway)
  ├─ MCP Client  ──→  LLM 网关     (MCP)
  ├─ MCP Client  ──→  RAG 服务     (MCP)
  ├─ MCP Client  ──→  记忆服务     (MCP)
  └─ HTTP Client ──→  Prompt 中心  (REST)      ← 独一个异类
```

网关要维护两套逻辑：MCP 连接管理 + HTTP 请求管理、两种错误处理、两种服务发现方式。

### 如果协议统一

```
网关 (gateway)
  ├─ MCP Client  ──→  LLM 网关     (MCP)
  ├─ MCP Client  ──→  RAG 服务     (MCP)
  ├─ MCP Client  ──→  记忆服务     (MCP)
  └─ MCP Client  ──→  Prompt 中心  (MCP)      ← 同一套
```

一个 `mcp_client_manager.py` 管全部，调用方式全是 `call_tool` / `get_prompt`。

### 对比表

| 维度 | 全部 MCP | 混合（MCP + REST） |
|------|---------|-------------------|
| 连接管理 | 一套 | 两套 |
| 调用方式 | 统一 `call_tool` / `get_prompt` | `call_tool` + `httpx.get` |
| 服务发现 | `list_tools()` + `list_prompts()` 自描述 | REST 需额外维护文档 |
| 错误处理 | 一套 MCP 错误模型 | 两套 |
| 新增服务 | 注册 MCP Server，网关零改动 | 要看是 MCP 还是 REST |

**一句话：不是 Prompt 中心需要 MCP，是整个架构需要统一协议。**

---

## 选 MCP 还有一个独特优势：原生 Prompt 原语

MCP 协议专门为模板管理设计了 Prompt 原语，这是 REST API 没有的：

### REST 方式

```python
# 调用方需要知道 API 路径、参数结构
resp = httpx.post("/prompts/customer_service_qa/render", json={
    "context": "...", "history": "...", "question": "..."
})
rendered_text = resp.json()["text"]
```

调用方需要事先知道有哪些模板、每个模板需要什么参数，通常靠文档或配置。

### MCP 方式

```python
# 先自动发现
prompts = await session.list_prompts()
# → [{"name": "customer_service_qa", "arguments": [{"name": "context", "required": true}, ...]}]

# 再调用（参数结构已知）
result = await session.get_prompt("customer_service_qa", arguments={...})
# → 直接返回 {role: "user", content: "渲染后的 Prompt"}
```

Agent 可以**运行时自动发现**有哪些模板、需要哪些参数、哪些必填哪些可选——不需要任何事先配置或文档。

### 对比

| | MCP 原生 Prompt | REST API |
|--|----------------|----------|
| 服务发现 | `list_prompts()` 自动获取 | 需要文档 / Swagger |
| 返回格式 | `{role, content}` 可直接喂 LLM | 自定义 JSON，还需二次加工 |
| 参数校验 | MCP SDK 内置 | 自己实现 |
| Agent 友好度 | 高——天然自描述 | 中——需要额外集成 |

**对 AI Agent 来说，「自描述」是最大的价值。** Agent 不看文档，它需要在运行时知道"我能用什么模板、要传什么参数"。MCP 的 `list_prompts()` 天然提供了这个能力。

---

## 选 MCP 的三层原因

### 架构层面——统一协议简化治理

网关的代码只需要两种调用方式：

```python
# 调用 Tool（LLM 网关、RAG 服务、记忆服务）
result = await session.call_tool(tool_name, args)

# 获取 Prompt（Prompt 中心）
result = await session.get_prompt(prompt_name, arguments=args)
```

都走同一个 MCP Client，连接管理、错误处理、重试逻辑全复用。

### 协议层面——原生 Prompt 原语

MCP 是目前唯一一个在协议层面支持「Prompt 模板」语义的通信协议。REST / gRPC / GraphQL 都需要自己定义模板管理的 API 规范。

### 教学层面——概念聚焦

这个项目要演示 MCP 的三个核心原语：**Tool、Resource、Prompt**。LLM 网关 / RAG / 记忆服务展示了 Tool，Prompt 中心专门展示 Prompt 原语。如果 Prompt 中心用 REST，读者就看不到 MCP Prompt 怎么用了。

---

## 什么时候 REST 比 MCP 更合适

| 场景 | 更适合 | 原因 |
|------|--------|------|
| 高频调用（每秒数百次渲染） | REST | 更轻量，无会话开销 |
| 纯后端渲染，不涉及 Agent | REST | 不需要自描述能力 |
| 模板管理需要 CRUD UI | REST | Swagger + Admin 界面生态成熟 |
| 统一架构内的共享能力 | **MCP** | 协议一致，网关好管 |
| AI Agent 动态发现和调用 | **MCP** | `list_prompts()` 天然自描述 |
| 教学演示 MCP 能力 | **MCP** | 展示 Prompt 原语 |

---

## 迁移成本很低

代码结构极其简单，换协议就是换 `server.py` 的注册方式：

```
当前（MCP）：  MCP Client → server.py (@server.prompt + @server.tool)  → _templates (YAML)
改成 REST ：  HTTP Client → api.py (@app.get + @app.post)             → _templates (YAML)
                                                                          ↑ 完全不用改
```

YAML 模板和加载逻辑一行不动，只需要把 `@server.prompt()` 替换成 FastAPI 的路由。整个 `server.py` 才 104 行，迁移工作量极小。

---

## 甚至可以不要独立服务

Prompt 模板管理最极端的简化方案是直接在业务代码里渲染：

```python
# 不用服务，直接在 agent.py 里
import yaml
with open("templates/customer_service_qa.yaml") as f:
    tpl = yaml.safe_load(f)
prompt = tpl["template"].format(context=..., history=..., question=...)
```

**为什么不这样做：**
- 每个项目都要维护一份模板副本，或者约定一个共享目录
- 模板更新需要每个项目重启
- 失去了 MCP 的自描述能力（Agent 无法动态发现可用模板）
- 架构上和其他三个共享服务不一致

Prompt 中心的价值不在于「渲染有多复杂」，而在于**集中管理 + 协议统一 + 自描述**。

---

## 结论

**合理，且比记忆服务更有理由用 MCP。**

- 在本项目中：Prompt 中心是**唯一一个展示 MCP 原生 Prompt 原语的服务**，不用 MCP 就没法演示这个能力
- 架构一致性：四个共享服务全部 MCP，网关一套代码管全部
- 在生产环境中：如果不需要 Agent 自描述能力，换 REST 或嵌入式渲染都完全合理
- 无论怎么换：YAML 模板不受影响，迁移成本极低
