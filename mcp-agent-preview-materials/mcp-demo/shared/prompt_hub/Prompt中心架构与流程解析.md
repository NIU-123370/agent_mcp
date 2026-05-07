# Prompt 中心架构与流程解析

## 这个服务解决什么问题

LLM 需要精心组织的 Prompt 才能稳定输出高质量回答。但 Prompt 散落在各业务项目中会带来三个问题：

```
没有 Prompt 中心：
  项目 A（客服）：Prompt 硬编码在 agent.py 里
  项目 B（写作）：Prompt 硬编码在 agent.py 里

  问题 1：想调整客服话术？得改代码、重新部署
  问题 2：两个项目都需要"用户画像"上下文，各自拼一遍
  问题 3：Prompt 没有版本管理，改坏了无法回退

有了 Prompt 中心：
  项目 A（客服）：get_prompt("customer_service_qa", {context, history, question, user_profile})
  项目 B（写作）：get_prompt("writing_assistant", {topic, references, style, user_profile})

  ✅ 模板集中管理，改 YAML 不改代码
  ✅ 参数化渲染，填入素材即可
  ✅ 模板自描述，Agent 可自动发现
```

简单说，Prompt 中心的职责是**把「怎么问 LLM」这件事从业务代码中抽出来，变成一个可管理的共享服务**。

---

## 它在多项目架构中的角色

```
                        四个共享 MCP 服务
                ┌────────────────────────────────────────┐
                │                                        │
项目 A ────→    │  ① LLM 网关    → 统一调用大模型          │
(智能客服)      │  ② RAG 服务    → 检索知识库              │
                │  ③ 记忆服务    → 对话记忆 + 用户画像      │
项目 B ────→    │  ④ Prompt 中心 → 管理提示词模板  ◀── 本文档│
(写作助手)      │                                        │
                └────────────────────────────────────────┘
```

### 客服项目处理一次提问——Prompt 中心在哪里被调用

```
用户："专业版多少钱？"
        │
┌─ 项目 A (agent.py) ─────────────────────────────────────────────┐
│                                                                  │
│  ① recall_memory → 记忆服务                                     │
│     拿回对话历史：["用户: 我要专业版", "AI: 好的，哪款..."]       │
│                                                                  │
│  ② recall_user_facts → 记忆服务                                 │
│     拿回用户画像：[allergy=芒果, budget=月预算500]                │
│                                                                  │
│  ③ search_knowledge → RAG 服务                                  │
│     拿回参考资料："专业版每月 299 元..."                          │
│                                                                  │
│  ④ get_prompt("customer_service_qa") → Prompt 中心  ◀── 本步骤  │
│     传入 context + history + question + user_profile             │
│     拿回渲染好的完整 Prompt                                      │
│                                                                  │
│  ⑤ chat_completion → LLM 网关                                   │
│     把渲染后的 Prompt 发给大模型                                  │
│     → "专业版每月 299 元，年付享 8 折。"                          │
│                                                                  │
│  ⑥ save_memory → 记忆服务（存本轮对话）                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**④ 是 Prompt 中心的核心价值**：业务项目只负责收集素材（对话历史、用户画像、检索结果），如何组织成 Prompt 交给 Prompt 中心。

### 两个项目共用同一套模板

```
项目 A（客服）：
  get_prompt("customer_service_qa", {
    context: "产品资料...",
    history: "对话历史...",
    question: "专业版多少钱？",
    user_profile: "芒果过敏, 月预算500"
  })
  → 渲染出客服专用 Prompt → 发给 LLM

项目 B（写作）：
  get_prompt("writing_assistant", {
    topic: "AI 在教育中的应用",
    references: "研究资料...",
    style: "轻松幽默",
    user_profile: "喜欢简洁文风"
  })
  → 渲染出写作专用 Prompt → 发给 LLM
```

---

## 一个源文件 + 一个模板目录，各管什么

```
prompt_hub/
├── server.py         # 入口：加载 YAML、注册 MCP Prompt + Tool
└── templates/        # 模板：每个 YAML 定义一个 Prompt 模板
    ├── customer_service_qa.yaml
    └── writing_assistant.yaml
```

### server.py（入口与渲染）

- 初始化 `FastMCP`（端口 9004）。
- 启动时遍历 `templates/` 下所有 `.yaml` 文件，用 `yaml.safe_load()` 加载到内存字典 `_templates`。
- 用 `@server.prompt()` 注册 2 个 MCP 原生 Prompt，每个函数读取对应模板的 `template` 字段，用 `str.format()` 渲染参数。
- 用 `@server.tool()` 注册 1 个 Tool `list_prompt_templates`，遍历 `_templates` 返回所有模板的名称、描述和参数说明。

### templates/（模板定义）

每个 YAML 文件定义一个模板，结构统一：

```yaml
name: customer_service_qa          # 模板名称，唯一标识
description: "客服问答 — ..."       # 模板描述
parameters:                         # 参数列表（带说明和默认值）
  - name: context
    description: "检索到的参考资料"
    required: true
  - name: user_profile
    description: "用户画像"
    required: false
    default: ""
  ...
template: |                         # 模板正文，用 {参数名} 做占位符
  你是一个专业的客服助手。
  ...
  {context}
  ...
  {question}
```

---

## 数据模型

### 与记忆服务的对比

Prompt 中心**没有数据库**，模板全部以 YAML 文件存储，启动时加载到内存。

| | Prompt 中心 | 记忆服务 |
|--|------------|---------|
| 存储 | YAML 文件（启动时加载） | SQLite（运行时读写） |
| 状态 | 无状态（不写入任何数据） | 有状态（持续读写数据库） |
| 更新方式 | 改 YAML + 重启服务 | 运行时通过 Tool 实时更新 |

### 内存中的模板结构

启动后，`_templates` 字典长这样：

```python
_templates = {
    "customer_service_qa": {
        "name": "customer_service_qa",
        "description": "客服问答 — 基于知识库、用户画像和历史对话回答用户问题",
        "parameters": [
            {"name": "context", "description": "检索到的参考资料", "required": True},
            {"name": "user_profile", "description": "用户画像（过敏、偏好等）...", "required": False, "default": ""},
            {"name": "history", "description": "对话历史", "required": True},
            {"name": "question", "description": "用户当前问题", "required": True},
        ],
        "template": "你是一个专业的客服助手。...\n{context}\n...\n{question}\n"
    },
    "writing_assistant": {
        "name": "writing_assistant",
        "description": "写作生成 — 基于主题和参考资料生成文章",
        "parameters": [...],
        "template": "你是一个专业的 AI 写作助手。...\n{topic}\n...\n{references}\n"
    }
}
```

---

## 两种能力的详细流程

### MCP 原生 Prompt：customer_service_qa

```
调用 get_prompt("customer_service_qa", {context, history, question, user_profile})
  │
  ① server.py 中的 customer_service_qa() 函数被调用
  ② 从 _templates["customer_service_qa"]["template"] 取出模板字符串
  ③ 对 user_profile 做空值处理：空字符串 → "(无)"
  ④ 调用 template.format(context=..., history=..., question=..., user_profile=...)
  │
返回 MCP PromptMessage: {role: "user", content: {type: "text", text: "渲染后的完整 Prompt"}}
```

### MCP 原生 Prompt：writing_assistant

```
调用 get_prompt("writing_assistant", {topic, references, style, user_profile})
  │
  ① server.py 中的 writing_assistant() 函数被调用
  ② 从 _templates["writing_assistant"]["template"] 取出模板字符串
  ③ 对可选参数做默认值处理：style 默认 "正式"，user_profile 默认 "(无)"
  ④ 调用 template.format(topic=..., references=..., style=..., user_profile=...)
  │
返回 MCP PromptMessage: {role: "user", content: {type: "text", text: "渲染后的完整 Prompt"}}
```

### Tool：list_prompt_templates

```
调用 call_tool("list_prompt_templates", {})
  │
  ① 遍历 _templates 字典
  ② 每个模板提取 name、description、parameters
  │
返回 {"templates": [...], "count": 2}
```

---

## MCP 原生 Prompt vs 普通 Tool

Prompt 中心同时使用了 MCP 的两种原语，它们的区别：

```
MCP 原生 Prompt（@server.prompt）          普通 Tool（@server.tool）
┌────────────────────────────────┐       ┌────────────────────────────────┐
│ 协议方法：get_prompt / list_prompts│     │ 协议方法：call_tool / list_tools│
│                                │       │                                │
│ 语义：这是一段「提示词模板」    │       │ 语义：这是一个「可调用的工具」  │
│ 返回：PromptMessage（role+text）│       │ 返回：任意 JSON                │
│                                │       │                                │
│ 适合：模板渲染、LLM 上下文组装  │       │ 适合：增删查改等通用操作       │
│ 本服务中：customer_service_qa   │       │ 本服务中：list_prompt_templates │
│            writing_assistant    │       │                                │
└────────────────────────────────┘       └────────────────────────────────┘
```

**为什么用 Prompt 而不是全用 Tool？**

1. **语义清晰**：`get_prompt` 的返回值天然就是 `{role, content}` 格式，可以直接拼进 LLM 的 messages 参数
2. **协议自描述**：`list_prompts()` 让 Agent 自动发现可用模板和参数，不需要人工配置
3. **MCP 设计理念**：协议本身就为模板管理设计了 Prompt 原语，作为教学项目应该展示这个能力

---

## 为什么选 YAML 存模板

| 考量 | YAML 文件 | 数据库 | 硬编码在代码里 |
|------|----------|--------|--------------|
| 可读性 | **极高**，非开发者也能编辑 | 需要工具查看 | 混在逻辑代码中 |
| 修改成本 | 改文件 + 重启 | 运行时 API 修改 | 改代码 + 重新部署 |
| 版本管理 | **Git 原生支持** | 需要额外机制 | 和代码混在一起 |
| 适用场景 | 模板相对稳定，人工维护 | 模板频繁动态变更 | 最简原型 |

对于本项目的演示场景，YAML 是最佳选择——直观、可 Git 管理、零依赖。

---

## 与其他共享服务的对比

| | Prompt 中心 | LLM 网关 | RAG 服务 | 记忆服务 |
|--|------------|---------|---------|---------|
| **一句话** | 组织提示词 | 统一调用大脑 | 查找参考资料 | 记住说过什么 + 用户是谁 |
| **存储** | YAML 文件 | 无状态 | ChromaDB | SQLite（两张表） |
| **有状态** | 否 | 否 | 是 | 是 |
| **MCP 能力** | Prompt + Tool | Tool | Tool | Tool |
| **端口** | 9004 | 9001 | 9002 | 9003 |

四个服务合在一起的协作链路：**组织语言（Prompt 中心）→ 记住上下文（记忆服务）→ 查找资料（RAG 服务）→ 调用大脑（LLM 网关）**，就是一个完整的 AI 对话能力底座。

---

## 启动方式

```bash
cd mcp-demo
uv run shared/prompt_hub/server.py
```
