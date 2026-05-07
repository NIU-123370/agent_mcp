# LLM 网关架构解析 — 设计思路

> 本文不贴代码逐行分析，而是聚焦于**为什么这样设计**。

---

## 一、LLM 网关要解决什么问题

假设没有 LLM 网关，每个业务项目直接调用豆包 API：

```
项目 A (客服)  ──→  豆包 API
项目 B (写作)  ──→  豆包 API
```

看着简单，但会出现这些问题：

| 问题 | 具体表现 |
|------|---------|
| API Key 散落 | 每个项目都要配一份 API Key，泄露面更大 |
| 无法统一计量 | 不知道哪个项目消耗了多少 token |
| 模型切换要改 N 处 | 想换个模型要每个项目都改代码 |
| 调用逻辑重复 | 错误处理、重试、日志每个项目各写一份 |
| 无法统一限流 | 一个项目打爆 API 配额，所有项目一起挂 |

LLM 网关的核心价值就一句话：**把"调用大模型"这件事收拢到一个地方统一管理**。

```
项目 A  ──┐
          ├──→  LLM 网关  ──→  豆包 API
项目 B  ──┘     (统一入口)
```

---

## 二、四个文件，各管一件事

整个 LLM 网关只有 4 个文件，每个文件只负责一个关注点：

```
你的问题是什么？              对应哪个文件？
──────────────              ──────────────
"对外暴露哪些能力？"          server.py       ← 定义 MCP Tool
"用户说 auto 该调哪个模型？"   router.py       ← 模型选择策略
"怎么跟豆包 API 通信？"       doubao.py       ← API 协议适配
"有哪些模型可用？"            config.yaml     ← 声明式配置
```

这不是巧合，而是刻意按**单一职责原则**拆分。好处是：

- 要换个 LLM 供应商（比如从豆包换成通义千问）？只改 `doubao.py`，其他文件不动
- 要加个新模型？只改 `config.yaml`，不碰任何 Python 代码
- 要加个新 Tool（比如 `stream_completion`）？只在 `server.py` 加一个函数

### 依赖方向

```
config.yaml  ←── router.py
                     ↑
.env ─────→ server.py ──→ doubao.py ──→ 豆包 API
              ↑
         FastMCP SDK
```

注意依赖方向：`server.py` 依赖 `router.py` 和 `doubao.py`，反过来不成立。`router.py` 和 `doubao.py` 互不依赖。这种单向依赖意味着底层模块可以独立测试、独立替换。

---

## 三、核心设计决策

### 3.1 逻辑模型名 vs 物理端点 — 两层命名

这是整个 LLM 网关最重要的设计决策。

```
调用方看到的          config.yaml 定义的          .env 里的实际值
(逻辑名)             (模型参数)                  (物理端点)
───────              ──────────                  ──────────
"auto"         →     "doubao-pro"          →     "doubao-seed-1-8-251228"
"doubao-pro"   →     max_tokens: 4096
"doubao-lite"  →     max_tokens: 2048
```

**为什么要有这一层间接？**

1. **调用方零感知切换模型**：运维修改 `.env` 里的 `ARK_CHAT_MODEL`，把底层模型从 seed-1.8 换成 pro-32k，所有项目无需改一行代码
2. **逻辑语义稳定**：`"doubao-pro"` 永远表示"最强的那个模型"，具体是哪个版本可以随时变
3. **安全隔离**：调用方永远不知道实际的 Endpoint ID，减少信息泄露

这个思路类似于：
- DNS（域名 → IP 地址）
- 数据库连接别名（"主库" → 具体连接串）
- Kubernetes Service（服务名 → Pod IP）

### 3.2 server.py 只做"组装"，不做"实现"

看 `server.py` 的 `chat_completion` Tool：

```
步骤 1：router.resolve("auto")           → 问路由器该用哪个模型
步骤 2：router.get_model_config(...)      → 拿到模型参数限制
步骤 3：doubao.chat_completion(...)       → 让 API 客户端去调用
步骤 4：附上 model + project_id          → 包装元数据返回
```

server.py 自己不做任何"真正的事"——不做模型选择逻辑，不做 HTTP 请求，不做配置解析。它只负责**把各模块串起来**。

这叫做**编排层**（Orchestration Layer）。好处是：你看 server.py 就能看到完整的业务流程，但细节都藏在各自的模块里。

### 3.3 project_id — 埋下多租户的种子

当前 `project_id` 参数只做了两件事：写日志 + 原样返回。看似多余。

但它的真正用途在后续步骤：

```
Step 2 (现在)：project_id 仅用于日志标记
                ↓
Step 6 (网关)：网关从 API Key 提取 project_id，注入到每个 Tool 调用
                ↓
              → 配额模块按 project_id 计量 token
              → 日志模块按 project_id 关联 Trace
              → RAG 服务按 project_id 隔离知识库
```

**设计原则**：在早期就把多租户标识传入，即使暂时不用。如果后面才加，所有 Tool 签名都要改，所有调用方都要适配。

### 3.4 max_tokens 的"谁小听谁"策略

```python
effective_max_tokens = min(max_tokens, model_cfg.get("max_tokens", max_tokens))
```

两个值取较小的那个：

| 调用方传入 | 模型配置上限 | 实际生效 | 为什么 |
|-----------|------------|---------|-------|
| 2000 | 4096 (pro) | 2000 | 尊重调用方意愿 |
| 5000 | 4096 (pro) | 4096 | 保护模型不超限 |
| 2000 | 2048 (lite) | 2000 | 调用方更保守 |
| 5000 | 2048 (lite) | 2048 | lite 模型能力有限 |

这种"双向夹逼"设计既不会限制合理请求，也不会让模型收到超出能力的参数。

---

## 四、Embedding 的适配器模式

### 4.1 问题背景

火山引擎有两种 Embedding API，格式完全不兼容：

```
标准文本 Embedding                    多模态 Embedding
─────────────────                    ──────────────────
POST /api/v3/embeddings              POST /api/v3/embeddings/multimodal
                                     （注意：不同的路径！）

input: ["文本1", "文本2"]             input: [{"type":"text","text":"文本"}]
（字符串数组）                         （对象数组，支持图片/视频）

data: [                              data: {
  {"embedding": [...]},                "embedding": [...]
  {"embedding": [...]}               }
]                                    （注意：data 是 dict 不是 list！）
（data 是 list，多条结果）              （data 是单个结果）
```

### 4.2 设计选择

`doubao.py` 用了**策略模式**（Strategy Pattern）：

```
embedding(model, texts)
    │
    │  模型名含 "vision"?
    ├── Yes → _embedding_multimodal()    用 httpx 直调
    └── No  → _embedding_text()          用 OpenAI SDK
```

为什么用模型名来判断，而不是加个配置项？

- **约定优于配置**：火山引擎的多模态模型命名都带 "vision"，这是 API 提供商的命名约定
- **零配置**：不需要用户额外声明"这个模型是多模态的"
- **可预测**：看到模型名就知道走哪条路径

### 4.3 逐条调用的取舍

多模态端点每次返回**一个**向量（对所有 input 的联合表示），要给 N 条文本生成独立向量就得调 N 次：

```
文本 ["A", "B", "C"]
  → 调用 1：input=[{type:text, text:"A"}]  → 向量 1
  → 调用 2：input=[{type:text, text:"B"}]  → 向量 2
  → 调用 3：input=[{type:text, text:"C"}]  → 向量 3
```

明显的缺点是**N 次网络往返**。但在当前阶段这是合理的：

- 演示场景数据量小（几条到几十条），延迟可接受
- 代码简单直接，不引入并发/批处理复杂度
- 如果将来需要优化，可以加 `asyncio.gather` 并发或换用纯文本模型

---

## 五、配置哲学：.env 与 config.yaml 的分治

```
                    ┌─────────────────────────────────┐
                    │          config.yaml             │
                    │  ┌───────────────────────────┐   │
                    │  │ 模型名: doubao-pro         │   │
                    │  │ 参数:   max_tokens: 4096   │   │  ← 业务逻辑
                    │  │ 路由:   default: doubao-pro│   │     可以提交 Git
                    │  └───────────────────────────┘   │     团队共享
                    └─────────────────────────────────┘

                    ┌─────────────────────────────────┐
                    │             .env                 │
                    │  ┌───────────────────────────┐   │
                    │  │ API Key:  8fe7ae22-...     │   │  ← 环境机密
                    │  │ 模型 ID:  doubao-seed-...  │   │     不提交 Git
                    │  │ Base URL: https://ark...   │   │     每人不同
                    │  └───────────────────────────┘   │
                    └─────────────────────────────────┘
```

**判断标准**：这个值换一台机器部署需要改吗？

- 需要改 → `.env`（API Key、端点地址）
- 不需要改 → `config.yaml`（模型参数、路由规则）

---

## 六、MCP 协议层的设计思考

### 6.1 为什么用 MCP 而不是直接写 FastAPI

这个 LLM 网关完全可以用 FastAPI 写成 REST API。那为什么要用 MCP？

```
直接写 REST API：
  POST /api/chat_completion  ← 自定义接口
  POST /api/embedding        ← 自定义接口
  GET  /api/models           ← 自定义接口

用 MCP 协议：
  POST /mcp                  ← 统一端点
  └── call_tool("chat_completion", {...})
  └── call_tool("embedding", {...})
  └── call_tool("list_models", {})
```

核心区别：MCP 提供**能力自描述**。

客户端连上 MCP Server 后，不需要任何文档就能知道：
1. 有哪些 Tool（`list_tools()`）
2. 每个 Tool 需要什么参数（JSON Schema，从类型标注自动生成）
3. 每个 Tool 做什么（docstring 自动变成 description）

这意味着：**如果 LLM 网关加了一个新 Tool，所有客户端自动感知到，无需更新文档或客户端代码**。

### 6.2 @server.tool() 背后做了什么

```python
@server.tool()
async def chat_completion(
    messages: list[dict],    # ← 类型标注 → JSON Schema
    project_id: str,
    model: str = "auto",     # ← 默认值 → Schema 中 optional
) -> dict:
    """统一的 LLM 对话接口"""  # ← docstring → Tool description
```

这一个装饰器完成了三件事：

| 自动行为 | 来源 | 生成物 |
|---------|------|-------|
| 参数 Schema | 函数签名的类型标注 | `list_tools()` 返回的 inputSchema |
| Tool 描述 | docstring 第一行 | `list_tools()` 返回的 description |
| 执行入口 | 函数体 | `call_tool()` 时实际运行的逻辑 |

所以 MCP 的 Tool 定义天然是 **"代码即文档"** —— 写好函数签名和 docstring，接口定义就自动完成了。

### 6.3 返回值为什么是 dict

三个 Tool 都返回 `dict`，FastMCP 会自动 `json.dumps()` 包装为 `TextContent`。

也可以返回 `str`（纯文本）或 MCP 的 `ImageContent`/`EmbeddedResource`，但对于结构化数据，dict → JSON 是最通用的格式。

客户端需要 `json.loads(result.content[0].text)` 解析回 dict。这是 MCP 协议中"结构化数据通过 JSON 文本传递"的惯用模式。

---

## 七、错误处理策略

```
                         doubao.py 层                    server.py 层
                         ──────────                      ────────────
豆包 API 返回错误  →  捕获 APIError / HTTPStatusError  →  RuntimeError 上抛
                     记录 logger.error                   FastMCP 自动捕获
                     转为 RuntimeError(中文消息)          返回 isError=True
                                                        客户端收到错误文本
```

设计思路：

1. **doubao.py 负责翻译异常**：把 OpenAI SDK 的 `APIError` 和 httpx 的 `HTTPStatusError` 统一转为 `RuntimeError`，附上人类可读的中文消息
2. **server.py 不需要 try/except**：FastMCP 框架会自动捕获 Tool 函数中的异常，设置 `result.isError = True`，把异常消息放入 `result.content`
3. **调用方通过 isError 判断**：不需要解析 HTTP 状态码，MCP 协议层已经标准化了错误传递

---

## 八、总结：设计原则清单

| 原则 | 在 LLM 网关中的体现 |
|------|-------------------|
| **单一职责** | 4 个文件各管一件事：接口 / 路由 / API 调用 / 配置 |
| **依赖倒置** | server.py 依赖抽象（router/doubao 的方法签名），不依赖具体实现细节 |
| **开闭原则** | 加新模型改 config.yaml，加新供应商改 doubao.py，不影响其他文件 |
| **约定优于配置** | 模型名含 "vision" 自动走多模态路径，零额外配置 |
| **关注点分离** | 敏感信息在 .env，业务配置在 config.yaml，逻辑在 Python |
| **面向未来设计** | project_id 现在只做日志，为后续配额/隔离/追踪预留接口 |
| **代码即文档** | Tool 的参数类型和 docstring 自动生成 MCP Schema |
| **防御式编程** | max_tokens 双向夹逼、未知模型名拦截、API 错误中文翻译 |
