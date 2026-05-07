# Step 2 核心流程与架构解析 — LLM 网关 MCP Server

> 截至 Step 2 完成，项目已搭建工程脚手架并实现第一个共享 MCP 服务（LLM 网关）。
> 本文从整体架构到逐行代码，完整解析当前系统的设计与运行原理。

---

## 一、项目全景

### 1.1 最终架构目标（全部 9 步完成后）

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  项目 A (客服)          项目 B (写作)                           │
│      │                      │                                  │
│      └──── HTTP REST ───────┘                                  │
│                │                                               │
│                ▼                                               │
│     ┌─────────────────────┐                                    │
│     │   HTTP 网关 :8000   │  认证 / 日志 / 配额 / 路由        │
│     │  (FastAPI, 治理层)  │                                    │
│     └────────┬────────────┘                                    │
│              │ MCP Client (Streamable HTTP)                    │
│              ▼                                                 │
│  ┌──────────┬──────────┬──────────┬──────────┐                │
│  │ LLM 网关 │ RAG 服务 │ 记忆服务 │ Prompt   │                │
│  │  :9001   │  :9002   │  :9003   │ 中心:9004│                │
│  │ (MCP Srv)│ (MCP Srv)│ (MCP Srv)│ (MCP Srv)│                │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┘                │
│       │          │          │          │                       │
│    豆包 API   ChromaDB   SQLite    YAML 模板                  │
│    (云端)     (本地)     (本地)    (本地)                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 1.2 当前已完成部分（Step 1 + Step 2）

```
已完成                         待做
─────────                      ─────
✅ 工程脚手架 + Hello World     ❌ RAG 服务 (Step 3)
✅ LLM 网关 MCP Server          ❌ 记忆服务 (Step 4)
                                ❌ Prompt 中心 (Step 5)
                                ❌ HTTP 网关 (Step 6)
                                ❌ 项目 A/B (Step 7/8)
```

当前可独立运行验证的部分：

```
┌────────────────────┐     MCP (Streamable HTTP)     ┌──────────────────┐
│ test_llm_gateway.py│ ────────────────────────────→ │ LLM 网关 :9001   │
│ (MCP Client)       │     http://127.0.0.1:9001/mcp │ (MCP Server)     │
└────────────────────┘                                └───────┬──────────┘
                                                              │
                                              ┌───────────────┼──────────────┐
                                              │               │              │
                                              ▼               ▼              ▼
                                         chat_completion  embedding     list_models
                                              │               │
                                              ▼               ▼
                                     豆包 Chat API    豆包 Embedding API
                                   /chat/completions  /embeddings/multimodal
```

---

## 二、当前工程结构

```
mcp-demo/
├── shared/                          # 共享 MCP 服务
│   ├── __init__.py
│   └── llm_gateway/                 # ← Step 2 新增：LLM 统一网关
│       ├── __init__.py
│       ├── server.py                # MCP Server 入口，注册 3 个 Tool
│       ├── doubao.py                # 豆包 API 调用封装（chat + embedding）
│       ├── router.py                # 模型路由策略（auto → doubao-pro）
│       └── config.yaml              # 模型列表与路由规则
│
├── scripts/
│   ├── hello_server.py              # Step 1：Hello World MCP Server
│   ├── test_hello.py                # Step 1：连通性测试
│   ├── test_llm_gateway.py          # ← Step 2 新增：LLM 网关测试
│   └── start_all.py                 # 一键启动脚本（等全部 Step 完成后可用）
│
├── pyproject.toml                   # 依赖声明（uv 管理）
├── .env                             # 环境变量（API Key、模型 ID）
├── .env.example                     # 环境变量模板
└── STARTUP.md                       # 启动指南
```

---

## 三、核心概念：MCP 协议在本项目中的角色

### 3.1 MCP 是什么

MCP（Model Context Protocol）是一个标准化的通信协议，定义了三种原语：

| 原语 | 用途 | 本项目使用情况 |
|------|------|---------------|
| **Tool** | 可执行的函数调用 | `chat_completion`、`embedding`、`list_models` |
| **Prompt** | 可复用的提示词模板 | Step 5 实现 |
| **Resource** | 可读取的数据源 | 本项目未使用 |

### 3.2 MCP 通信模型

```
MCP Client                          MCP Server
─────────                           ──────────
  │                                     │
  │──── initialize() ─────────────────→│   建立会话
  │                                     │
  │──── list_tools() ─────────────────→│   发现能力
  │←─── [tool1, tool2, ...] ──────────│
  │                                     │
  │──── call_tool("chat_completion",  →│   调用工具
  │       {messages, project_id})       │
  │←─── {content, usage} ────────────│   返回结果
  │                                     │
```

- **传输方式**：Streamable HTTP（MCP SDK v1.26+ 推荐）
- **端点格式**：`http://host:port/mcp`
- **SDK 封装**：服务端用 `FastMCP`，客户端用 `streamablehttp_client` + `ClientSession`

### 3.3 为什么用 MCP 而不是直接 HTTP API？

| 直接写 REST API | 用 MCP 协议 |
|---|---|
| 每个服务自己定义接口格式 | 统一的 Tool/Prompt/Resource 原语 |
| 客户端需要知道每个接口的 URL | 客户端只需要知道 MCP 端点，通过 `list_tools()` 自动发现能力 |
| 接口文档各自维护 | Tool 的 description 和参数类型就是文档 |
| 无标准的能力协商机制 | `initialize()` → `list_tools()` 自动协商 |

---

## 四、LLM 网关 — 模块拆解

### 4.1 四个文件的职责分工

```
                      ┌──────────────────────────┐
                      │      server.py           │  对外暴露 MCP Tool
                      │  (MCP Server 入口)       │  组装各模块
                      └──────┬──────────┬────────┘
                             │          │
                    ┌────────┘          └────────┐
                    ▼                            ▼
          ┌─────────────────┐          ┌─────────────────┐
          │   router.py     │          │   doubao.py     │
          │ (模型路由策略)   │          │ (豆包 API 封装) │
          └────────┬────────┘          └────────┬────────┘
                   │                            │
                   ▼                            ▼
          ┌─────────────────┐          ┌─────────────────┐
          │  config.yaml    │          │  .env 环境变量   │
          │ (模型列表/路由)  │          │ (API Key/端点)   │
          └─────────────────┘          └─────────────────┘
```

| 文件 | 职责 | 核心类/函数 |
|------|------|------------|
| `server.py` | MCP Server 入口，注册 Tool，组装 router 和 doubao | `FastMCP("llm-gateway")` + 3 个 `@server.tool()` |
| `doubao.py` | 封装豆包 API 调用细节，屏蔽 API 差异 | `DoubaoClient` 类 |
| `router.py` | 将逻辑模型名解析为实际调用参数 | `ModelRouter` 类 |
| `config.yaml` | 声明式配置，定义可用模型和路由规则 | YAML 数据文件 |

### 4.2 config.yaml — 声明式模型配置

```yaml
models:
  doubao-pro:                                    # 逻辑模型名
    description: "豆包主力模型，适合复杂推理..."   # 人类可读描述
    max_tokens: 4096                             # 该模型最大生成 token
    temperature: 0.7                             # 默认温度
  doubao-lite:
    description: "豆包轻量模型，响应快..."
    max_tokens: 2048
    temperature: 0.5

routing:
  default: "doubao-pro"                          # model="auto" 时的选择
```

**设计要点**：
- 逻辑模型名（doubao-pro）与实际 API Endpoint（环境变量 `ARK_CHAT_MODEL`）解耦
- 修改配置文件即可切换默认模型，无需改代码
- 为后续网关的"模型切换"演示场景铺路

### 4.3 router.py — 模型路由策略

```
调用方传入 model 参数          ModelRouter 处理            最终结果
─────────────────             ─────────────              ─────────
  "auto"            ───→  查 config.yaml default  ───→  "doubao-pro"
  "doubao-pro"      ───→  直接匹配                ───→  "doubao-pro"
  "doubao-lite"     ───→  直接匹配                ───→  "doubao-lite"
  "gpt-4"           ───→  不在 models 中          ───→  ValueError!
```

核心方法：

```python
def resolve(self, model="auto") -> str:
    if model == "auto":
        model = self.default_model      # 查配置
    if model not in self.models:
        raise ValueError(...)           # 未知模型
    return model

def get_model_config(self, model) -> dict:
    resolved = self.resolve(model)
    return {"name": resolved, **self.models[resolved]}
    # → {"name": "doubao-pro", "max_tokens": 4096, "temperature": 0.7, ...}
```

### 4.4 doubao.py — 豆包 API 调用封装

**核心设计决策**：Chat 和 Embedding 使用不同的调用方式。

```
                    DoubaoClient
                    ────────────
                         │
            ┌────────────┴────────────┐
            │                         │
     chat_completion()           embedding()
            │                         │
            │                    模型名含 "vision"?
            │                    ┌────┴────┐
            ▼                    │ Yes     │ No
     OpenAI SDK                  ▼         ▼
  /chat/completions      httpx 直调    OpenAI SDK
                      /embeddings/    /embeddings
                       multimodal
```

**为什么 Embedding 不能统一用 OpenAI SDK？**

火山引擎的多模态 Embedding 模型（`doubao-embedding-vision-*`）使用的是专有端点和输入格式：

| 对比项 | 标准文本 Embedding | 多模态 Embedding |
|--------|-------------------|-----------------|
| 端点路径 | `/api/v3/embeddings` | `/api/v3/embeddings/multimodal` |
| 输入格式 | `input: ["文本1", "文本2"]` | `input: [{"type":"text","text":"文本"}]` |
| 返回格式 | `data: [{"embedding":[...]}, ...]` | `data: {"embedding":[...]}` |
| OpenAI SDK | 兼容 | **不兼容** |

因此 `doubao.py` 的 `embedding()` 方法根据模型名自动选择调用路径：

```python
async def embedding(self, model, texts):
    if "vision" in model:
        return await self._embedding_multimodal(model, texts)  # httpx
    return await self._embedding_text(model, texts)            # OpenAI SDK
```

多模态端点每次调用返回**一个**向量（对整个 input 的联合表示），所以对多条文本需要**逐条调用**：

```python
async def _embedding_multimodal(self, model, texts):
    for text in texts:
        payload = {"model": model, "input": [{"type": "text", "text": text}]}
        resp = await http.post(url, headers=headers, json=payload)
        vectors.append(resp.json()["data"]["embedding"])  # data 是 dict，不是 list
```

### 4.5 server.py — MCP Server 组装

**启动时序**：

```
1. 加载 .env             ← PROJECT_ROOT / ".env"
2. 创建 DoubaoClient     ← api_key + base_url
3. 创建 ModelRouter      ← config.yaml
4. 读取 Endpoint ID      ← ARK_CHAT_MODEL, ARK_EMBEDDING_MODEL
5. 创建 FastMCP Server   ← host=127.0.0.1, port=9001
6. 注册 3 个 Tool        ← @server.tool() 装饰器
7. 启动 Streamable HTTP  ← server.run(transport="streamable-http")
```

**注册的 3 个 Tool**：

| Tool 名 | 入参 | 出参 | 用途 |
|---------|------|------|------|
| `chat_completion` | messages, project_id, model, temperature, max_tokens | {content, usage, model, project_id} | 统一 LLM 对话 |
| `embedding` | texts, project_id | {embeddings, dimensions, project_id} | 文本向量化 |
| `list_models` | (无) | {models: [...]} | 列出可用模型 |

---

## 五、核心调用流程（以 chat_completion 为例）

### 5.1 完整时序图

```
test_llm_gateway.py          server.py             router.py          doubao.py           豆包 ARK API
    (MCP Client)            (MCP Server)          (ModelRouter)      (DoubaoClient)        (云端)
        │                       │                      │                  │                   │
   1    │── streamablehttp ────→│                      │                  │                   │
        │   连接 :9001/mcp      │                      │                  │                   │
        │                       │                      │                  │                   │
   2    │── initialize() ─────→│                      │                  │                   │
        │←─ capabilities ──────│                      │                  │                   │
        │                       │                      │                  │                   │
   3    │── list_tools() ─────→│                      │                  │                   │
        │←─ [chat_completion,  │                      │                  │                   │
        │    embedding,         │                      │                  │                   │
        │    list_models] ─────│                      │                  │                   │
        │                       │                      │                  │                   │
   4    │── call_tool ─────────→│                      │                  │                   │
        │   ("chat_completion", │                      │                  │                   │
        │    {messages: [...],  │                      │                  │                   │
        │     project_id:"test",│                      │                  │                   │
        │     model:"auto"})    │                      │                  │                   │
        │                       │                      │                  │                   │
   5    │                       │── resolve("auto") ─→│                  │                   │
        │                       │←─ "doubao-pro" ─────│                  │                   │
        │                       │                      │                  │                   │
   6    │                       │── get_model_config ─→│                  │                   │
        │                       │←─ {max_tokens:4096} │                  │                   │
        │                       │                      │                  │                   │
   7    │                       │── chat_completion ───────────────────→│                   │
        │                       │   (model=CHAT_ENDPOINT,               │                   │
        │                       │    messages=[...],                    │                   │
        │                       │    temperature=0.7,                   │                   │
        │                       │    max_tokens=2000)                   │                   │
        │                       │                                       │                   │
   8    │                       │                                       │── POST ──────────→│
        │                       │                                       │   /chat/completions│
        │                       │                                       │   (OpenAI SDK)     │
        │                       │                                       │                   │
   9    │                       │                                       │←─ 200 OK ────────│
        │                       │                                       │   {choices, usage} │
        │                       │                                       │                   │
  10    │                       │←─ {content, usage} ──────────────────│                   │
        │                       │                                                           │
  11    │                       │  附加 model + project_id                                  │
        │                       │                                                           │
  12    │←─ {content, usage, ──│                                                           │
        │    model, project_id} │                                                           │
        │                       │                                                           │
```

### 5.2 关键步骤详解

**步骤 4-5：模型路由**

调用方传入 `model="auto"`，server.py 调用 `router.resolve("auto")`：

```python
# server.py 第 64-66 行
model_name = router.resolve(model)            # "auto" → "doubao-pro"
model_cfg = router.get_model_config(model_name)
effective_max_tokens = min(max_tokens, model_cfg.get("max_tokens", max_tokens))
#                      min(2000,      4096)  → 2000
```

路由的价值：调用方不需要关心实际用哪个模型，说 `"auto"` 就行。运维只需改 `config.yaml` 就能全局切换默认模型。

**步骤 7-10：API 调用**

server.py 把路由后的参数传给 `doubao.chat_completion()`，注意这里传的是 `CHAT_ENDPOINT`（环境变量），而不是逻辑模型名：

```python
# server.py 第 73-78 行
result = await doubao.chat_completion(
    model=CHAT_ENDPOINT,          # ← 实际的 API Endpoint ID（如 "doubao-seed-1-8-251228"）
    messages=messages,
    temperature=temperature,
    max_tokens=effective_max_tokens,
)
```

doubao.py 内部通过 OpenAI SDK 发起请求：

```python
# doubao.py 第 38-43 行
response = await self.client.chat.completions.create(
    model=model,                  # ← "doubao-seed-1-8-251228"
    messages=messages,            # ← [{"role":"user","content":"用一句话介绍 MCP"}]
    temperature=temperature,      # ← 0.7
    max_tokens=max_tokens,        # ← 2000
)
```

**步骤 11-12：结果包装**

server.py 在原始结果上附加元数据后返回：

```python
# server.py 第 79-80 行
result["model"] = model_name      # "doubao-pro"（逻辑名，不暴露实际 Endpoint）
result["project_id"] = project_id  # "test"（调用方标识，为配额/日志铺路）
```

最终客户端收到：

```json
{
  "content": "MCP 是一个多媒体控制协议...",
  "usage": {"prompt_tokens": 57, "completion_tokens": 386, "total_tokens": 443},
  "model": "doubao-pro",
  "project_id": "test"
}
```

---

## 六、Embedding 调用流程

与 chat 类似，但 API 层走了不同的路径：

```
test_llm_gateway.py     server.py         doubao.py                  豆包 API
       │                    │                 │                         │
       │── call_tool ──────→│                 │                         │
       │  ("embedding",     │                 │                         │
       │   {texts:["A","B"],│                 │                         │
       │    project_id:...})│                 │                         │
       │                    │                 │                         │
       │                    │── embedding() ─→│                         │
       │                    │  (model=         │                         │
       │                    │   "doubao-       │                         │
       │                    │    embedding-    │                         │
       │                    │    vision-...")   │                         │
       │                    │                 │                         │
       │                    │                 │  模型含 "vision"         │
       │                    │                 │  → _embedding_multimodal │
       │                    │                 │                         │
       │                    │                 │── POST ────────────────→│
       │                    │                 │  /embeddings/multimodal  │
       │                    │                 │  input:[{type:text,      │
       │                    │                 │         text:"A"}]       │
       │                    │                 │←─ {data:{embedding:[]}} │
       │                    │                 │                         │
       │                    │                 │── POST ────────────────→│  (第二条文本)
       │                    │                 │  input:[{type:text,      │
       │                    │                 │         text:"B"}]       │
       │                    │                 │←─ {data:{embedding:[]}} │
       │                    │                 │                         │
       │                    │←─ {embeddings:  │                         │
       │                    │    [[...],[...]]│                         │
       │                    │    dimensions:   │                         │
       │                    │    2048}         │                         │
       │                    │                 │                         │
       │←─ result ─────────│                 │                         │
```

---

## 七、MCP 协议交互细节

### 7.1 Streamable HTTP 传输

```
客户端                                    服务端 (Uvicorn :9001)
  │                                          │
  │── POST /mcp ───────────────────────────→│  发送 JSON-RPC 请求
  │   Content-Type: application/json         │
  │   Body: {"jsonrpc":"2.0",                │
  │          "method":"tools/call",          │
  │          "params":{...},                 │
  │          "id":1}                         │
  │                                          │
  │←── 200 OK ─────────────────────────────│  返回 JSON-RPC 响应
  │    Content-Type: application/json        │
  │    Body: {"jsonrpc":"2.0",               │
  │           "result":{...},                │
  │           "id":1}                        │
  │                                          │
  │── DELETE /mcp ─────────────────────────→│  关闭会话
  │←── 200 OK ─────────────────────────────│
```

底层是标准的 JSON-RPC over HTTP，MCP SDK 完全封装了这些细节。开发者只需要：

- **服务端**：`FastMCP` + `@server.tool()` 装饰器
- **客户端**：`streamablehttp_client()` + `session.call_tool()`

### 7.2 Tool 注册机制

`@server.tool()` 装饰器做了三件事：

```python
@server.tool()
async def chat_completion(
    messages: list[dict],       # ← 1. 从类型标注生成 JSON Schema
    project_id: str,
    model: str = "auto",        # ← 有默认值 → schema 中 optional
    ...
) -> dict:
    """统一的 LLM 对话接口..."""  # ← 2. docstring 作为 Tool 的 description
    ...                          # ← 3. 函数体作为 Tool 的执行逻辑
```

客户端调用 `list_tools()` 时，收到的就是从这些信息自动生成的 Tool Schema。

---

## 八、配置与环境变量体系

### 8.1 两层配置的分工

```
.env（运行环境相关，敏感信息）          config.yaml（业务逻辑，可提交 Git）
───────────────────────────            ─────────────────────────────────
ARK_API_KEY=8fe7ae22-...               models:
ARK_BASE_URL=https://ark...              doubao-pro:
ARK_CHAT_MODEL=doubao-seed-...             max_tokens: 4096
ARK_EMBEDDING_MODEL=doubao-embedding-...   doubao-lite:
                                            max_tokens: 2048
                                         routing:
                                           default: "doubao-pro"
```

| 维度 | .env | config.yaml |
|------|------|-------------|
| 内容 | API 密钥、端点 ID | 模型参数、路由规则 |
| 是否提交 Git | 否（.gitignore） | 是 |
| 修改频率 | 部署时一次性配置 | 运营时按需调整 |
| 加载方式 | `python-dotenv` | `PyYAML` |

### 8.2 配置加载流程

```python
# server.py 启动时的完整加载流程

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # mcp-demo/
load_dotenv(PROJECT_ROOT / ".env")                            # 加载环境变量

doubao = DoubaoClient(
    api_key=os.environ["ARK_API_KEY"],      # ← 从 .env
    base_url=os.environ["ARK_BASE_URL"],    # ← 从 .env
)

router = ModelRouter()                       # ← 内部加载同目录 config.yaml

CHAT_ENDPOINT = os.environ["ARK_CHAT_MODEL"]       # ← 从 .env
EMBEDDING_ENDPOINT = os.environ["ARK_EMBEDDING_MODEL"]  # ← 从 .env
```

---

## 九、测试流程解析

### 9.1 test_llm_gateway.py 的结构

```python
# 1. 建立 MCP 连接
async with streamablehttp_client(SERVER_URL) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # 2. 发现能力
        tools = await session.list_tools()

        # 3. 调用 Tool 并验证
        result = await session.call_tool("list_models", {})
        result = await session.call_tool("chat_completion", {...})
        result = await session.call_tool("embedding", {...})
```

### 9.2 结果解析

MCP Tool 返回的结果是 `CallToolResult`，其中 `content` 是 `TextContent` 列表。对于返回 `dict` 的 Tool，FastMCP 会自动 `json.dumps()`，客户端需要 `json.loads()` 还原：

```python
def parse_tool_result(result):
    text = result.content[0].text     # JSON 字符串
    return json.loads(text)           # 解析为 dict
```

---

## 十、关键设计模式总结

### 10.1 分层解耦

```
┌─────────────────────────────────────────────┐
│  MCP 协议层 (server.py)                     │  对外接口：Tool 定义
│    - 定义入参/出参                           │  不关心 API 细节
│    - 组装调用链                              │
├─────────────────────────────────────────────┤
│  业务逻辑层 (router.py)                     │  路由策略
│    - 模型选择                               │  不关心 MCP/API
│    - 参数校验                               │
├─────────────────────────────────────────────┤
│  API 适配层 (doubao.py)                     │  API 封装
│    - 协议差异处理                            │  不关心业务逻辑
│    - 错误处理                               │
├─────────────────────────────────────────────┤
│  配置层 (config.yaml + .env)                │  声明式配置
│    - 模型定义                               │  不含任何代码
│    - 密钥管理                               │
└─────────────────────────────────────────────┘
```

### 10.2 为多项目共享铺路

当前 Tool 的 `project_id` 参数看似多余（只做了日志打印），但为后续 Step 6 的网关层提供了基础：

```
Step 2（当前）：project_id 仅用于日志
Step 6（网关）：project_id 用于 → 认证（验证 API Key 对应的项目）
                              → 配额（按项目计量 token 消耗）
                              → 日志（Trace ID 关联项目来源）
                              → 隔离（RAG 按 project_id 分 collection）
```

### 10.3 下一步展望

```
Step 3 (RAG 服务)：会复用 doubao.py 中相同的 embedding 调用逻辑
                   但直接 httpx 调用，不走 LLM 网关（避免服务间依赖）

Step 6 (HTTP 网关)：作为 MCP Client 连接 LLM 网关
                   调用方式与 test_llm_gateway.py 完全相同
                   只是多了认证/日志/配额中间件
```

---

## 附录：快速验证命令

```bash
# 终端 1：启动 LLM 网关
cd mcp-demo
uv run shared/llm_gateway/server.py

# 终端 2：运行测试
cd mcp-demo
uv run scripts/test_llm_gateway.py
```

预期看到 3 个测试全部通过：`list_models` + `chat_completion` + `embedding`。
