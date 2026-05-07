# MCP 多项目共享服务 — 演示项目实现路径 v2

> 两个业务项目 + 一套共享 MCP 服务，从零搭建，直接按最终架构落地。

---

## 架构决策记录

### 决策 1：原生 Python + MCP SDK（不用 LangChain）

| 维度 | 原生 Python + MCP SDK | LangChain |
|---|---|---|
| **MCP 概念清晰度** | 直接操作 MCP 协议，读者一眼看懂 | 被 LangChain 抽象包裹，MCP 概念模糊 |
| **依赖复杂度** | 依赖少，`mcp` + `httpx` 就够 | 依赖链长，版本冲突风险高 |
| **学习目标匹配** | 本教程核心是学 MCP，不是学 LangChain | LangChain 会喧宾夺主 |
| **灵活性** | 完全掌控通信细节 | 受框架约束 |
| **调试友好度** | 调用栈清晰 | 层层封装，排错困难 |

**结论：用原生 Python + MCP Python SDK。**

### 决策 2：HTTP 网关模式（不用 MCP Proxy）

项目 A/B 通过 HTTP 调用 FastAPI 网关，网关内部作为 MCP Client 调用共享服务。

```
项目 A/B                    网关 (FastAPI)                    共享 MCP 服务
┌─────────┐   HTTP/REST    ┌──────────┐   MCP(Streamable HTTP)  ┌──────────────┐
│ app.py  │ ──────────────→│ main.py  │───────────────────────→ │ LLM 网关     │
│ agent.py│   POST /api/.. │ auth.py  │  call_tool()            │ RAG 服务     │
│         │                │ router.py│  get_prompt()           │ 记忆服务     │
│ (HTTP   │                │ quota.py │                         │ Prompt 中心  │
│  Client)│                │ logger.py│  (MCP Client)           │ (MCP Server) │
└─────────┘                └──────────┘                         └──────────────┘
```

**为什么不用 MCP Proxy？**
- 网关同时做 MCP Server + MCP Client 实现复杂，SDK 对该模式支持不够成熟
- FastAPI 做认证/日志/限流有成熟方案，不需要在 MCP 层重新造轮子
- 教程重点是共享 MCP 服务的设计，不是网关本身

### 决策 3：RAG 服务直接调用豆包 Embedding API（不走 LLM 网关）

```
简单方案（采用）：RAG 服务内部直连豆包 Embedding API
   RAG Server  ──[httpx]──→  豆包 Embedding API

复杂方案（不用）：RAG 服务通过 MCP 调用 LLM 网关的 embedding Tool
   RAG Server  ──[MCP Client]──→  LLM Gateway Server
```

**理由：** 避免 MCP Server 之间互相调用带来的复杂度（连接管理、循环依赖风险）。RAG 服务只是需要把文本变成向量，直接调 API 最简单。LLM 网关的 `embedding` Tool 仍然保留，供业务项目通过网关直接调用。

### 决策 4：MCP 通信使用 Streamable HTTP 传输

```
传输方式：Streamable HTTP（MCP SDK v1.26+ 默认推荐）
原因：MCP 官方 SDK 推荐的 HTTP 传输方式，比旧版 SSE 更稳定
端点：各服务 http://localhost:PORT/mcp
```

### 决策 5：Prompt 中心使用 MCP 原生 Prompt 能力

MCP 协议有原生的 Prompt 原语（`server.prompt()`），专门用于模板管理。作为教 MCP 的项目，应该展示这个原生能力。

### 决策 6：只用豆包云端 API（不用 Ollama）

所有 LLM 和 Embedding 调用都走火山引擎豆包 API，不引入本地模型。简化环境依赖。

---

## 技术栈总览

```
语言：       Python 3.11+
包管理：     uv
MCP SDK：    mcp[cli] v1.26+ (官方 Python SDK，Streamable HTTP 传输)
大模型：     豆包（火山引擎 ARK API，兼容 OpenAI 格式）
Embedding：  豆包 Embedding API
向量数据库： ChromaDB（轻量，零配置，持久化到本地）
数据存储：   SQLite
HTTP 框架：  FastAPI + Uvicorn（网关层）
HTTP 客户端：httpx（调用豆包 API + 项目调用网关）
配置管理：   PyYAML + python-dotenv
```

---

## 两个业务项目设计

> 业务刻意做到**最简**，只保留足以演示 MCP 共享模式的最小功能。

### 项目 A：智能客服机器人

```
功能：回答用户关于"产品"的问题
流程：用户提问 → 读取用户画像 → 检索知识库 → LLM 生成回答 → 记住对话

用到的共享服务：
  ✅ LLM 网关（调用豆包生成回答）
  ✅ RAG 服务（检索产品知识库）
  ✅ 记忆服务 — 对话记忆（记住本次对话上下文）
  ✅ 记忆服务 — 用户画像（读写跨项目的用户偏好，如过敏、预算等）
  ✅ Prompt 中心（客服专用 Prompt 模板）
```

### 项目 B：AI 写作助手

```
功能：基于主题生成/润色文本
流程：用户输入主题 → 读取用户画像 → 检索参考资料 → LLM 生成内容

用到的共享服务：
  ✅ LLM 网关（调用豆包生成文本）
  ✅ RAG 服务（检索写作素材库）
  ✅ 记忆服务 — 对话记忆（记住用户写作上下文）
  ✅ 记忆服务 — 用户画像（读取用户偏好，如风格喜好、忌讳话题等）
  ✅ Prompt 中心（写作专用 Prompt 模板）
```

### 共享 vs 独有能力矩阵

```
                    项目A(客服)    项目B(写作)    → 应该放哪？
LLM 调用              ✅            ✅          → 共享 LLM 网关
知识库检索             ✅            ✅          → 共享 RAG 服务
对话记忆               ✅            ✅          → 共享记忆服务（按 project+session 隔离）
用户画像               ✅            ✅          → 共享记忆服务（按 user_id 跨项目共享）
Prompt 模板            ✅            ✅          → 共享 Prompt 中心
客服话术逻辑           ✅            ❌          → 项目A 私有
写作生成逻辑           ❌            ✅          → 项目B 私有
```

---

## 完整协议链路图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        完整调用链路                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  项目 A/B (HTTP Client)                                             │
│      │                                                              │
│      │  POST http://localhost:8000/api/tool/call                    │
│      │  POST http://localhost:8000/api/prompt/get                   │
│      │  Header: X-API-Key: project-a-key                           │
│      ▼                                                              │
│  网关 (FastAPI, port 8000)                                          │
│      │  ┌─ 认证中间件：校验 API Key → 提取 project_id              │
│      │  ├─ 日志中间件：记录请求（Trace ID）                         │
│      │  ├─ 配额中间件：检查 Token 余量                              │
│      │  └─ 路由逻辑：根据 service 名找到 MCP Server 地址           │
│      │                                                              │
│      │  内置 MCP Client，通过 Streamable HTTP 连接各共享服务         │
│      ▼                                                              │
│  共享 MCP 服务（各自独立进程，Streamable HTTP 传输）                │
│      ├─ LLM 网关     (port 9001)  ──→ 豆包 ARK API (云端)         │
│      ├─ RAG 服务     (port 9002)  ──→ 豆包 Embedding API (云端)   │
│      │                            ──→ ChromaDB (本地文件)          │
│      ├─ 记忆服务     (port 9003)  ──→ SQLite (对话记忆 + 用户画像) │
│      └─ Prompt 中心  (port 9004)  ──→ YAML 模板文件 (本地)        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 最终工程结构

```
mcp-demo/
├── shared/                            # 共享 MCP 服务
│   ├── llm_gateway/                   # 共享服务①：LLM 统一网关
│   │   ├── server.py                  # MCP Server 入口（Streamable HTTP）
│   │   ├── router.py                  # 模型路由策略（doubao-pro / doubao-lite）
│   │   ├── doubao.py                  # 豆包 API 调用封装（兼容 OpenAI 格式）
│   │   └── config.yaml                # 模型列表、路由规则
│   │
│   ├── rag_service/                   # 共享服务②：RAG 检索服务
│   │   ├── server.py                  # MCP Server 入口（Streamable HTTP）
│   │   ├── embedder.py                # 直接调用豆包 Embedding API
│   │   ├── retriever.py               # ChromaDB 存储 + 检索
│   │   └── doc_processor.py           # 文档读取 → 分块
│   │
│   ├── memory_service/                # 共享服务③：会话记忆 + 用户画像
│   │   ├── server.py                  # MCP Server 入口（对话记忆 + 用户画像 Tool）
│   │   └── store.py                   # SQLite 存取（memory_messages 表 + user_facts 表）
│   │
│   └── prompt_hub/                    # 共享服务④：Prompt 管理中心
│       ├── server.py                  # MCP Server 入口（Streamable HTTP，原生 Prompt）
│       └── templates/                 # Prompt 模板 YAML 文件
│           ├── customer_service_qa.yaml
│           └── writing_assistant.yaml
│
├── gateway/                           # HTTP 网关（FastAPI）
│   ├── main.py                        # FastAPI 入口，组装中间件
│   ├── auth.py                        # 项目级 API Key 认证
│   ├── router.py                      # 请求路由（HTTP → MCP 转发）
│   ├── mcp_client_manager.py          # MCP Client 连接池管理
│   ├── logger.py                      # 统一日志（Trace ID）
│   ├── quota.py                       # 按项目 Token 配额限流
│   └── config.yaml                    # 服务注册表 + 项目配置
│
├── projects/                          # 业务项目
│   ├── customer_service/              # 项目A：智能客服
│   │   ├── app.py                     # 命令行入口
│   │   ├── agent.py                   # 客服 Agent 编排逻辑
│   │   └── gateway_client.py          # 封装网关 HTTP 调用
│   │
│   └── writing_assistant/             # 项目B：AI 写作助手
│       ├── app.py                     # 命令行入口
│       ├── agent.py                   # 写作 Agent 编排逻辑
│       └── gateway_client.py          # 封装网关 HTTP 调用
│
├── data/                              # 演示数据
│   ├── knowledge/                     # 知识库源文档
│   │   ├── products.md                # 产品资料（项目A 用）
│   │   └── writing_guides.md          # 写作素材（项目B 用）
│   ├── chromadb/                      # ChromaDB 持久化目录
│   └── sqlite/                        # SQLite 数据库目录
│
├── scripts/                           # 启动脚本
│   ├── start_all.py                   # 一键启动所有服务
│   └── init_knowledge.py              # 初始化知识库数据
│
├── pyproject.toml                     # uv 项目配置 + 依赖声明
├── .env.example                       # 环境变量模板
├── .gitignore
└── README.md
```

---

## 分步实现路径

### Step 1：工程脚手架 + 环境搭建

```
目标：创建项目结构，安装依赖，配置豆包 API，跑通最小 MCP Server
产出：一个能通过 Streamable HTTP 连接的 Hello World MCP Server
```

具体任务：
- [x] 创建 `mcp-demo/` 完整目录结构
- [x] 编写 `pyproject.toml`（uv 管理依赖，mcp v1.26+）
- [x] 编写 `.env.example` 和 `.gitignore`
- [x] 写一个最简 MCP Server（注册一个 `hello` Tool，Streamable HTTP 传输），验证 SDK 能跑通

涉及大纲章节：第 3 章

---

### Step 2：共享 LLM 网关

```
目标：搭建统一的 LLM 调用服务，所有项目通过它访问豆包
产出：一个 MCP Server，暴露 chat_completion / embedding Tool
```

具体任务：
- [x] 实现 `doubao.py` — 豆包 API 调用封装（chat 用 OpenAI SDK，embedding 用 httpx 直调多模态端点）
- [x] 实现 `router.py` — 模型路由策略（doubao-pro / doubao-lite 按配置选择）
- [x] 实现 `server.py` — 注册 `chat_completion`、`embedding`、`list_models` 三个 Tool
- [x] 配置 `config.yaml` — 模型列表、默认模型、路由规则

涉及大纲章节：第 8 章

核心 Tool 设计：
```python
@server.tool()
async def chat_completion(
    messages: list[dict],       # [{"role": "user", "content": "..."}]
    project_id: str,            # 调用方项目标识
    model: str = "auto",        # auto / doubao-pro / doubao-lite
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> dict:
    """统一的 LLM 对话接口，自动路由到配置的模型"""
    # 返回 {"content": "...", "usage": {"prompt_tokens": N, "completion_tokens": N}}

@server.tool()
async def embedding(
    texts: list[str],
    project_id: str,
) -> dict:
    """统一的文本向量化接口"""
    # 返回 {"embeddings": [[0.1, 0.2, ...], ...]}
```

---

### Step 3：共享 RAG 服务

```
目标：搭建统一的知识库检索服务，支持多项目各自的知识库
产出：一个 MCP Server，暴露文档上传 + 语义检索 Tool
```

具体任务：
- [x] ~~实现 `embedder.py`~~ — 改用 ChromaDB 内置 embedding（all-MiniLM-L6-v2），无需外部 API
- [x] 实现 `doc_processor.py` — 文档按 Markdown 标题 + 段落分块
- [x] 实现 `retriever.py` — ChromaDB 存储 + 语义检索（持久化到 `data/chromadb/`）
- [x] 实现 `server.py` — 注册 `ingest_document` 和 `search_knowledge` Tool
- [x] 准备演示数据：`products.md`、`writing_guides.md`

涉及大纲章节：第 9 章

关键设计 — 多租户隔离（按 project_id 分 ChromaDB collection）：
```python
@server.tool()
async def ingest_document(
    project_id: str,            # 隔离不同项目的知识库
    doc_name: str,              # 文档名称
    content: str,               # 文档内容
) -> dict:
    """将文档分块并写入向量数据库"""

@server.tool()
async def search_knowledge(
    query: str,
    project_id: str,
    top_k: int = 3,
) -> dict:
    """在指定项目的知识库中语义检索"""
```

---

### Step 4：共享记忆服务

```
目标：搭建统一的会话记忆存取服务
产出：一个 MCP Server，暴露记忆读写 Tool
```

具体任务：
- [x] 实现 `store.py` — SQLite 存储对话记忆（按 project_id + session_id 隔离）
- [x] 实现 `server.py` — 注册 `save_memory`、`recall_memory`、`clear_memory` Tool

涉及大纲章节：第 10 章

```python
@server.tool()
async def save_memory(
    project_id: str,
    session_id: str,
    role: str,              # "user" / "assistant"
    content: str,
) -> dict:
    """保存一条对话记录"""

@server.tool()
async def recall_memory(
    project_id: str,
    session_id: str,
    last_n: int = 10,
) -> dict:
    """召回指定会话的最近 N 条历史记录"""

@server.tool()
async def clear_memory(
    project_id: str,
    session_id: str,
) -> dict:
    """清空指定会话的记忆"""
```

---

### Step 5：记忆服务增强 — 用户画像（跨项目长期记忆）

```
目标：在记忆服务中新增「用户事实」存储，实现跨项目的长期用户画像
产出：memory_service 新增 user_facts 表 + 三个 Tool，按 user_id 共享用户偏好
```

**解决什么问题：**

Step 4 的对话记忆按 `project_id + session_id` 隔离，项目之间互不可见。但有些用户信息天然是跨项目的：

```
场景：用户在客服项目说"我芒果过敏"
      → 零食推荐项目应该自动排除芒果类
      → 当前的对话记忆做不到，因为数据被 project_id 隔离了
```

对话记忆 vs 用户画像，是两种不同层次的「记忆」：

| | 对话记忆（Step 4 已实现） | 用户画像（本 Step 新增） |
|--|------------------------|----------------------|
| 存什么 | 一轮轮的对话原文 | 提炼出的用户事实 / 偏好 |
| 生命周期 | 跟随会话，可清空 | 跟随用户，长期存在 |
| 隔离粒度 | project_id + session_id | **仅 user_id**，跨项目共享 |
| 举例 | "用户问了专业版多少钱" | "该用户芒果过敏" |
| 谁能读 | 只有同项目同会话 | 所有项目都能查 |

具体任务：
- [x] 在 `store.py` 新增 `user_facts` 表（按 `user_id` 存取，不绑定 project_id）
- [x] 新增 Tool：`save_user_fact(user_id, fact_key, fact_value, source_project)` — 写入用户事实
- [x] 新增 Tool：`recall_user_facts(user_id)` — 读取该用户的所有事实（跨项目）
- [x] 新增 Tool：`delete_user_fact(user_id, fact_key)` — 删除某条事实
- [x] 编写测试脚本验证跨项目读写

涉及大纲章节：第 10 章（扩展）

数据模型：
```sql
CREATE TABLE IF NOT EXISTS user_facts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL,           -- 用户标识（跨项目唯一）
    fact_key       TEXT NOT NULL,           -- 事实类别（allergy / preference / ...）
    fact_value     TEXT NOT NULL,           -- 事实内容（"芒果过敏"）
    source_project TEXT,                    -- 谁写入的（"customer-service"）
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, fact_key)              -- 同一用户同一 key 只保留最新值
);
```

核心 Tool 设计：
```python
@server.tool()
async def save_user_fact(
    user_id: str,
    fact_key: str,           # "allergy" / "budget" / "style_preference" / ...
    fact_value: str,         # "芒果过敏" / "月预算500以内" / "喜欢简约风"
    source_project: str = "",
) -> dict:
    """保存一条用户事实（跨项目共享）。同一 user_id + fact_key 会覆盖旧值。"""

@server.tool()
async def recall_user_facts(
    user_id: str,
) -> dict:
    """读取该用户的所有事实标签（任何项目都可调用）。"""
    # 返回 {"user_id": "...", "facts": [{"key":"allergy","value":"芒果过敏","source":"customer-service"}, ...]}

@server.tool()
async def delete_user_fact(
    user_id: str,
    fact_key: str,
) -> dict:
    """删除某条用户事实。"""
```

跨项目协作流程：
```
项目 A（客服）：
  用户说 "我芒果过敏"
  → AI 识别这是用户偏好
  → save_user_fact(user_id="张三", fact_key="allergy", fact_value="芒果")

项目 B（零食推荐）：
  用户说 "给我推荐零食"
  → recall_user_facts(user_id="张三")
  → 得到 [{"key":"allergy", "value":"芒果", "source":"customer-service"}]
  → AI 推荐零食时自动排除芒果类
```

**与 Step 4 的关系**：同属 memory_service，复用同一个 SQLite 数据库和 MCP Server 进程，只是新增一张表和三个 Tool。

---

### Step 6：共享 Prompt 中心（使用 MCP 原生 Prompt）

```
目标：搭建统一的 Prompt 模板管理服务，展示 MCP 原生 Prompt 能力
产出：一个 MCP Server，使用 server.prompt() 注册模板 + Tool 辅助管理
```

具体任务：
- [x] 编写 Prompt 模板 YAML（客服模板、写作模板，含 user_profile 参数）
- [x] 实现 `server.py`：
  - 用 `@server.prompt()` 注册各业务 Prompt（MCP 原生能力）
  - 用 `@server.tool()` 注册 `list_prompt_templates` Tool（列出可用模板）
- [x] 模板支持参数渲染（context、history、question、user_profile 等占位符）

涉及大纲章节：第 11 章

MCP 原生 Prompt 设计：
```python
from mcp.server.fastmcp import FastMCP
from mcp.types import GetPromptResult, PromptMessage, TextContent

server = FastMCP("prompt-hub")

@server.prompt()
async def customer_service_qa(context: str, history: str, question: str) -> GetPromptResult:
    """客服问答 Prompt — 基于知识库和历史对话回答用户问题"""
    return GetPromptResult(
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=f"""你是一个专业的客服助手。

参考资料：
{context}

对话历史：
{history}

用户问题：{question}

请基于参考资料回答用户问题。如果资料中没有相关信息，请诚实告知。"""
                )
            )
        ]
    )

@server.prompt()
async def writing_generate(topic: str, references: str, style: str = "正式") -> GetPromptResult:
    """写作生成 Prompt — 基于主题和参考资料生成文章"""
    ...

@server.tool()
async def list_prompts() -> dict:
    """列出所有可用的 Prompt 模板及其参数说明"""
    ...
```

模板 YAML（供 server.py 读取渲染）：
```yaml
# templates/customer_service_qa.yaml
name: customer_service_qa
description: "客服问答 Prompt"
parameters:
  - name: context
    description: "检索到的参考资料"
    required: true
  - name: history
    description: "对话历史"
    required: true
  - name: question
    description: "用户当前问题"
    required: true
template: |
  你是一个专业的客服助手。
  
  参考资料：
  {context}
  
  对话历史：
  {history}
  
  用户问题：{question}
  
  请基于参考资料回答用户问题。如果资料中没有相关信息，请诚实告知。
```

---

### Step 7：HTTP 网关

```
目标：搭建 FastAPI 统一入口，内置 MCP Client 连接所有共享服务
产出：一个 HTTP 网关，提供认证、路由、日志、配额，并转发请求到 MCP 服务
```

具体任务：
- [x] 实现 `mcp_client_manager.py` — 管理到 4 个 MCP Server 的 Streamable HTTP 连接
- [x] 实现 `auth.py` — 项目级 API Key 认证中间件
- [x] 实现 `router.py` — HTTP 路由，提供以下端点：
  - `POST /api/tool/call` — 调用 MCP Tool
  - `POST /api/prompt/get` — 获取 MCP Prompt
  - `GET  /api/prompt/list` — 列出可用 Prompt
- [x] 实现 `logger.py` — 统一请求/响应日志（Trace ID）
- [x] 实现 `quota.py` — 按项目 Token 配额计量和限流
- [x] 实现 `main.py` — FastAPI 入口，组装中间件，启动时连接 MCP Server
- [x] 配置 `config.yaml` — 服务注册表 + 项目 API Key + 配额

涉及大纲章节：第 7 章、第 14 章、第 15 章、第 16 章

网关 API 设计：
```python
# POST /api/tool/call
{
    "service": "llm-gateway",           # 目标 MCP 服务名
    "tool": "chat_completion",          # Tool 名称
    "arguments": {                      # Tool 参数
        "messages": [{"role": "user", "content": "你好"}],
        "project_id": "customer-service",
        "model": "auto"
    }
}

# POST /api/prompt/get
{
    "service": "prompt-hub",            # 目标 MCP 服务名
    "prompt": "customer_service_qa",    # Prompt 名称
    "arguments": {                      # Prompt 参数
        "context": "...",
        "history": "...",
        "question": "..."
    }
}
```

网关配置示例：
```yaml
# gateway/config.yaml
services:
  llm-gateway:
    url: "http://localhost:9001/mcp"
  rag-service:
    url: "http://localhost:9002/mcp"
  memory-service:
    url: "http://localhost:9003/mcp"
  prompt-hub:
    url: "http://localhost:9004/mcp"

projects:
  customer-service:
    api_key: "cs-demo-key-001"
    quota:
      daily_tokens: 100000
  writing-assistant:
    api_key: "wa-demo-key-001"
    quota:
      daily_tokens: 100000
```

---

### Step 8：项目 A — 智能客服

```
目标：搭建客服项目，通过 HTTP 网关调用共享服务完成问答
产出：一个命令行客服对话程序
```

具体任务：
- [x] 实现 `gateway_client.py` — 封装网关 HTTP 调用（call_tool / get_prompt）
- [x] 实现 `agent.py` — 客服 Agent 编排逻辑：
  1. 调用 `recall_memory` 获取对话历史
  2. 调用 `recall_user_facts` 获取用户画像（过敏、偏好等）
  3. 调用 `search_knowledge` 检索知识
  4. 调用 `get_prompt("customer_service_qa")` 组装 Prompt（含用户画像上下文）
  5. 调用 `chat_completion` 生成回答
  6. 调用 `save_memory` 保存对话记忆
  7. 如果 AI 识别到新的用户事实 → 调用 `save_user_fact` 更新画像
- [x] 实现 `app.py` — 命令行交互入口
- [x] 实现 `init_knowledge.py` 上传产品知识库

涉及大纲章节：第 4 章

---

### Step 9：项目 B — AI 写作助手

```
目标：搭建写作项目，复用同一套共享服务
产出：一个命令行写作辅助程序
```

具体任务：
- [x] 实现 `gateway_client.py` — 复用同样的网关调用封装
- [x] 实现 `agent.py` — 写作 Agent 编排逻辑：
  1. 调用 `recall_user_facts` 获取用户画像（写作风格偏好等）
  2. 调用 `search_knowledge` 检索写作素材
  3. 调用 `get_prompt("writing_assistant")` 组装写作 Prompt（含用户偏好；多轮时配合 `recall_memory` 与模板中的 `history`）
  4. 调用 `chat_completion` 生成内容
  5. 调用 `save_memory` 记录对话上下文
- [x] 实现 `app.py` — 命令行交互入口
- [x] 使用 `init_knowledge.py` 上传写作素材

涉及大纲章节：第 4 章

---

### Step 10：联合演示 + 治理验证

```
目标：两个项目同时运行，验证共享架构的核心价值
产出：可演示的完整系统
```

演示场景：

- [ ] **场景 1：共享生效** — 两个项目同时对话，共用同一个 LLM 网关
- [ ] **场景 2：数据隔离** — 客服只能搜到产品知识，写作只能搜到写作素材
- [ ] **场景 3：跨项目用户画像** — 在客服项目说"我芒果过敏"，零食推荐项目自动规避芒果
- [ ] **场景 4：统一日志** — 在网关层查看两个项目的所有请求日志（Trace ID 串联）
- [ ] **场景 5：配额限流** — 项目 A 超出配额后被限流，项目 B 不受影响
- [ ] **场景 6：模型切换** — 修改 LLM 网关配置，两个项目无感切换模型

涉及大纲章节：第 5、6、7、10、14、15、16 章

---

## 进程启动一览

所有服务本地运行，通过 Streamable HTTP 传输通信。

```
进程                    端口       启动命令
─────────────────────────────────────────────────────────
LLM 网关 MCP Server     9001      python shared/llm_gateway/server.py
RAG 服务 MCP Server     9002      python shared/rag_service/server.py
记忆服务 MCP Server     9003      python shared/memory_service/server.py  (对话记忆+用户画像)
Prompt 中心 MCP Server  9004      python shared/prompt_hub/server.py
HTTP 网关 (FastAPI)     8000      uvicorn gateway.main:app --port 8000
─────────────────────────────────────────────────────────
客服项目 A              -         python projects/customer_service/app.py
写作项目 B              -         python projects/writing_assistant/app.py
```

一键启动脚本 `scripts/start_all.py` 按顺序拉起 4 个 MCP Server + 1 个网关。

---

## 实现顺序总览

```
Step 1   工程脚手架          ██████████  基础搭建         ✅
Step 2   LLM 网关           ██████████  第一个共享服务   ✅
Step 3   RAG 服务           ██████████  第二个共享服务   ✅
Step 4   记忆服务（对话）   ██████████  第三个共享服务   ✅
Step 5   记忆增强（画像）   ██████████  跨项目用户画像   ✅
Step 6   Prompt 中心        ██████████  第四个共享服务   ✅
Step 7   HTTP 网关          ██████████  治理层           ✅
Step 8   项目 A（客服）     ██████████  第一个业务项目   ✅
Step 9   项目 B（写作）     ██████████  第二个业务项目   ✅
Step 10  联合演示           ██████████  验证效果
```

---

## 大纲章节覆盖对照

| 大纲章节 | 演示项目中的对应 | Step |
|---|---|---|
| 第 1-3 章 基础认知 | Step 1 Hello World MCP Server | 1 |
| 第 4 章 典型 AI 项目 | Step 8/9 两个项目的完整实现 | 8, 9 |
| 第 5 章 单项目痛点 | 对比演示场景直接体现 | 10 |
| 第 6 章 识别通用服务 | 工程结构的 shared/ 划分 | 全程 |
| 第 7 章 整体架构 | Step 7 HTTP 网关 + 四层架构 | 7 |
| 第 8 章 LLM 网关 | Step 2 shared/llm_gateway | 2 |
| 第 9 章 RAG 服务 | Step 3 shared/rag_service | 3 |
| 第 10 章 记忆服务 | Step 4 对话记忆 + Step 5 用户画像 | 4, 5 |
| 第 11 章 Prompt 中心 | Step 6 shared/prompt_hub（原生 Prompt） | 6 |
| 第 12 章 语义缓存 | （可选扩展，在 LLM 网关中加） | - |
| 第 13 章 Tool 注册中心 | 网关的服务注册表简化实现 | 7 |
| 第 14 章 认证鉴权 | Step 7 网关 auth 模块 | 7 |
| 第 15 章 日志可观测 | Step 7 网关 logger 模块 | 7 |
| 第 16 章 成本配额 | Step 7 网关 quota 模块 | 7 |

---

> **下一步**：确认此方案后，从 Step 1 开始动手 —— 创建工程结构、配置 uv 依赖、跑通第一个 MCP Server。

