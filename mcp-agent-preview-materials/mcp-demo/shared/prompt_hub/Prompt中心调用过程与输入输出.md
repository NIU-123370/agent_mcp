# Prompt 中心调用过程与输入输出

用一个具体的业务场景，把 1 个 Tool 和 2 个 MCP 原生 Prompt 从头到尾走一遍。每一步列出：调了什么、传进去什么、返回什么。

---

## 场景设定

模拟两个项目使用 Prompt 中心的完整过程：

```
项目 A（智能客服）：用户问产品价格，Agent 获取客服 Prompt 模板来组装上下文
项目 B（写作助手）：用户要写一篇文章，Agent 获取写作 Prompt 模板来生成内容
```

MCP 服务地址：`http://127.0.0.1:9004/mcp`

---

## 第一部分：发现可用模板

### 第 ① 步：列出 MCP 原生 Prompt — list_prompts()

Agent 接入 Prompt 中心后，先调用 MCP 协议的 `list_prompts()` 了解有哪些模板可用。

**调用方式**（MCP 协议原生方法，不是 Tool）：

```python
prompts = await session.list_prompts()
```

**输出**：

```json
{
  "prompts": [
    {
      "name": "customer_service_qa",
      "description": "客服问答 — 基于知识库、用户画像和历史对话回答用户问题",
      "arguments": [
        {"name": "context", "required": true},
        {"name": "history", "required": true},
        {"name": "question", "required": true},
        {"name": "user_profile", "required": false}
      ]
    },
    {
      "name": "writing_assistant",
      "description": "写作生成 — 基于主题和参考资料生成文章",
      "arguments": [
        {"name": "topic", "required": true},
        {"name": "references", "required": true},
        {"name": "style", "required": false},
        {"name": "user_profile", "required": false}
      ]
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| name | Prompt 名称，调用 `get_prompt` 时用 |
| description | 模板描述 |
| arguments | 参数列表，标注了是否必填 |

**这是 MCP 协议的「自描述」能力**：Agent 不需要看文档，调一次就知道有什么模板、需要哪些参数。

---

### 第 ② 步：列出模板详情 — list_prompt_templates（Tool）

`list_prompts()` 返回的是 MCP 协议层面的信息。如果还想看 YAML 模板中定义的更详细的参数说明，可以调用 Tool。

**输入**（无参数）：

```json
{}
```

**输出**：

```json
{
  "count": 2,
  "templates": [
    {
      "name": "customer_service_qa",
      "description": "客服问答 — 基于知识库、用户画像和历史对话回答用户问题",
      "parameters": [
        {"name": "context", "description": "检索到的参考资料", "required": true},
        {"name": "user_profile", "description": "用户画像（过敏、偏好等），无则传空字符串", "required": false, "default": ""},
        {"name": "history", "description": "对话历史", "required": true},
        {"name": "question", "description": "用户当前问题", "required": true}
      ]
    },
    {
      "name": "writing_assistant",
      "description": "写作生成 — 基于主题和参考资料生成文章",
      "parameters": [
        {"name": "topic", "description": "写作主题", "required": true},
        {"name": "references", "description": "参考资料", "required": true},
        {"name": "style", "description": "写作风格（正式/轻松/学术/幽默）", "required": false, "default": "正式"},
        {"name": "user_profile", "description": "用户画像（写作偏好等），无则传空字符串", "required": false, "default": ""}
      ]
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| count | 模板总数 |
| templates[].parameters | 比 `list_prompts()` 更详细：含 description 和 default |

**两者的区别**：`list_prompts()` 是 MCP 协议级别的发现，返回精简信息；`list_prompt_templates` Tool 返回 YAML 中定义的完整参数说明，适合展示给人看。

---

## 第二部分：客服项目渲染 Prompt

### 第 ③ 步：获取客服问答 Prompt — get_prompt("customer_service_qa")

客服 Agent 处理用户提问前，已经通过其他服务拿到了：
- 对话历史（来自记忆服务）
- 用户画像（来自记忆服务）
- 检索结果（来自 RAG 服务）

现在调用 Prompt 中心，把这些素材渲染成最终的 LLM Prompt。

**调用方式**（MCP 协议原生方法）：

```python
result = await session.get_prompt("customer_service_qa", arguments={
    "context": "SmartAssist Pro：基础版 ¥99/月，专业版 ¥299/月，企业版 ¥999/月。专业版含高级分析。",
    "history": "用户: 我想了解专业版\nAI: 好的，专业版是我们的中端产品...",
    "question": "专业版多少钱？",
    "user_profile": "allergy: 芒果过敏, budget: 月预算 500 以内",
})
```

**参数说明**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| context | str | 是 | — | RAG 检索到的参考资料 |
| history | str | 是 | — | 对话历史（从记忆服务拿到） |
| question | str | 是 | — | 用户当前问题 |
| user_profile | str | 否 | `""` | 用户画像，无则传空或不传 |

**输出**：

```json
{
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "你是一个专业的客服助手。请严格根据提供的参考资料回答用户问题。\n如果参考资料中没有相关信息，请诚实地说\"抱歉，我没有找到相关信息\"。\n回答要简洁专业，使用中文。\n\n## 参考资料\nSmartAssist Pro：基础版 ¥99/月，专业版 ¥299/月，企业版 ¥999/月。专业版含高级分析。\n\n## 用户画像\nallergy: 芒果过敏, budget: 月预算 500 以内\n\n## 对话历史\n用户: 我想了解专业版\nAI: 好的，专业版是我们的中端产品...\n\n## 用户问题\n专业版多少钱？\n"
      }
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| messages | MCP Prompt 协议标准格式，包含 role 和 content |
| messages[0].content.text | 渲染完成的完整 Prompt，所有占位符已被替换为实际值 |

**内部机制**：`server.py` 中的 `customer_service_qa()` 函数读取 YAML 模板中的 `template` 字段，调用 Python 的 `str.format()` 填充参数，返回一条 `role=user` 的消息。

**不传 user_profile 时**：

```json
{
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "...（同上）\n\n## 用户画像\n(无)\n\n...（同上）"
      }
    }
  ]
}
```

`user_profile` 默认值为 `""`，代码中判断为空时填入 `"(无)"`。

---

### 第 ④ 步：Agent 使用渲染结果

拿到渲染后的 Prompt，客服 Agent 把它作为 messages 传给 LLM 网关：

```python
prompt_result = await session.get_prompt("customer_service_qa", arguments={...})
rendered_text = prompt_result.messages[0].content.text

llm_result = await llm_session.call_tool("chat_completion", {
    "messages": [{"role": "user", "content": rendered_text}],
    "project_id": "customer-service",
})
```

**Prompt 中心本身不调用 LLM**，它只负责组装模板。谁来调、怎么调，是业务项目的事。

---

## 第三部分：写作项目渲染 Prompt

### 第 ⑤ 步：获取写作 Prompt — get_prompt("writing_assistant")

写作 Agent 要生成一篇文章，同样先组装 Prompt。

**调用**：

```python
result = await session.get_prompt("writing_assistant", arguments={
    "topic": "AI 在教育领域的应用",
    "references": "研究表明 AI 辅导可使学习效率提升 30%。...",
    "style": "轻松幽默",
    "user_profile": "喜欢简洁幽默的文风",
})
```

**参数说明**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| topic | str | 是 | — | 写作主题 |
| references | str | 是 | — | RAG 检索到的参考资料 |
| style | str | 否 | `"正式"` | 写作风格 |
| user_profile | str | 否 | `""` | 用户画像（写作偏好） |

**输出**：

```json
{
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "你是一个专业的 AI 写作助手。请根据给定的主题和参考资料，生成一篇高质量的文章。\n\n## 写作要求\n- 主题：AI 在教育领域的应用\n- 风格：轻松幽默\n- 内容要结构清晰、逻辑连贯\n- 适当引用参考资料中的信息\n\n## 用户偏好\n喜欢简洁幽默的文风\n\n## 参考资料\n研究表明 AI 辅导可使学习效率提升 30%。...\n"
      }
    }
  ]
}
```

---

### 第 ⑥ 步：使用默认风格 — 省略 style 参数

如果用户没指定风格，不传 style 即可。

**调用**：

```python
result = await session.get_prompt("writing_assistant", arguments={
    "topic": "气候变化",
    "references": "全球温度自工业化前已上升 1.1°C。",
})
```

**输出**（style 字段自动填入默认值 `"正式"`）：

```json
{
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "...（同上）\n- 风格：正式\n...（同上）\n\n## 用户偏好\n(无)\n\n..."
      }
    }
  ]
}
```

---

## 完整场景时间线

```
时间轴 ─────────────────────────────────────────────────────→

10:00  启动 Prompt 中心                    模板加载完成
                                           customer_service_qa ✓
                                           writing_assistant ✓

10:15  项目A（客服 Agent）                  10:30  项目B（写作 Agent）

  用户："专业版多少钱？"                      用户："帮我写篇关于 AI 教育的文章"
    │                                         │
    ├─ recall_memory → 拿到对话历史            ├─ recall_user_facts → 拿到用户画像
    ├─ recall_user_facts → 拿到用户画像        ├─ search_knowledge → 拿到参考资料
    ├─ search_knowledge → 拿到参考资料         │
    │                                         │
    ├─ get_prompt("customer_service_qa")      ├─ get_prompt("writing_assistant")
    │   → 传入 context, history,              │   → 传入 topic, references,
    │     question, user_profile              │     style, user_profile
    │   → 得到渲染好的完整 Prompt              │   → 得到渲染好的完整 Prompt
    │                                         │
    ├─ chat_completion                         ├─ chat_completion
    │   → 把渲染后的 Prompt 发给 LLM           │   → 把渲染后的 Prompt 发给 LLM
    └─ "专业版每月 299 元。"                   └─ "AI 在教育领域的应用..."
```

---

## 总结：Prompt 中心能力速查表

### MCP 原生 Prompt（通过 get_prompt 调用）

| Prompt | 输入 | 输出 | 说明 |
|--------|------|------|------|
| `customer_service_qa` | `context` `history` `question` `user_profile`(可选) | `{messages: [{role, content}]}` | 渲染后可直接作为 LLM 输入 |
| `writing_assistant` | `topic` `references` `style`(可选,默认"正式") `user_profile`(可选) | `{messages: [{role, content}]}` | 渲染后可直接作为 LLM 输入 |

### Tool

| Tool | 输入 | 输出 | 说明 |
|------|------|------|------|
| `list_prompt_templates` | 无参数 | `{"templates":[...], "count":N}` | 返回所有模板及完整参数说明 |

### MCP 协议方法

| 方法 | 说明 |
|------|------|
| `list_prompts()` | MCP 原生发现机制，返回所有已注册 Prompt 的名称、描述和参数 |
| `get_prompt(name, arguments)` | MCP 原生方法，渲染指定 Prompt 模板 |
| `list_tools()` | MCP 原生方法，返回所有已注册 Tool |
| `call_tool(name, arguments)` | MCP 原生方法，调用指定 Tool |
