# Prompt 中心测试指南

服务提供 2 个 MCP 原生 Prompt 和 1 个 Tool，分三组测试：列出能力（1 个）、渲染客服模板（1 个）、渲染写作模板（1 个）。

---

## 启动服务

```bash
cd mcp-demo
uv run shared/prompt_hub/server.py
```

看到这行就成功了：

```
Uvicorn running on http://127.0.0.1:9004 (Press CTRL+C to quit)
```

---

## 运行测试

```bash
uv run scripts/test_prompt_hub.py
```

---

## 预期输出

```
connecting to http://127.0.0.1:9004/mcp
connected!

available tools (1):
  - list_prompt_templates: 列出所有可用的 Prompt 模板及其参数说明。

=======================================================
TEST 1: list prompts (MCP native)
=======================================================
  registered prompts (2):
  - customer_service_qa: 客服问答 — 基于知识库、用户画像和历史对话回答用户问题...
    args: ['context', 'history', 'question', 'user_profile']
  - writing_assistant: 写作生成 — 基于主题和参考资料生成文章...
    args: ['topic', 'references', 'style', 'user_profile']

=======================================================
TEST 2: list_prompt_templates (Tool)
=======================================================
  template count: 2
  - customer_service_qa: 客服问答 — 基于知识库、用户画像和历史对话回答用户问题...
    params: ['context', 'user_profile', 'history', 'question']
  - writing_assistant: 写作生成 — 基于主题和参考资料生成文章...
    params: ['topic', 'references', 'style', 'user_profile']

=======================================================
TEST 3: get_prompt (customer_service_qa)
=======================================================
  messages count: 1
  [0] role=user
      preview: 你是一个专业的客服助手。请严格根据提供的参考资料回答用户问题。...
  
  -> PASS: all parameters rendered into prompt

=======================================================
TEST 4: get_prompt (writing_assistant)
=======================================================
  messages count: 1
  [0] role=user
      preview: 你是一个专业的 AI 写作助手。请根据给定的主题和参考资料，生成一篇高质量的文章。...
  
  -> PASS: all parameters rendered into prompt

=======================================================
TEST 5: get_prompt (writing_assistant, default style)
=======================================================
  preview: 你是一个专业的 AI 写作助手。请根据给定的主题和参考资料，生成一篇高质量的文章。...

  -> PASS: prompt rendered without explicit style parameter

=======================================================
ALL TESTS PASSED!
=======================================================
```

---

## 验证要点

| 测试 | 通过标准 |
|------|---------|
| TEST 1 | `list_prompts` 返回 2 个 MCP 原生 Prompt，各含参数列表 |
| TEST 2 | `list_prompt_templates` Tool 返回 2 个模板，含参数定义（来自 YAML） |
| TEST 3 | 客服模板渲染成功：context、user_profile、history、question 全部填充 |
| TEST 4 | 写作模板渲染成功：topic、style、references 全部填充 |
| TEST 5 | 不传 style 参数时模板仍能正常渲染（使用默认值） |

---

## 测试流程图解

```
test_prompt_hub.py             Prompt 中心 (:9004)         YAML 模板文件
   │                                │                        │
   │── list_tools() ──────────────→│                        │
   │←─ [list_prompt_templates] ───│                        │
   │                                │                        │
   │── list_prompts() ────────────→│                        │
   │←─ [customer_service_qa,      │                        │
   │    writing_assistant] ────────│                        │
   │                                │                        │
   │── call_tool                   │                        │
   │   ("list_prompt_templates")──→│── 遍历已加载模板 ────→│ *.yaml
   │←─ {templates:[...], count:2} │                        │
   │                                │                        │
   │── get_prompt                  │                        │
   │   ("customer_service_qa",     │                        │
   │    {context, history,         │── 读模板 + format() ─→│ customer_service_qa.yaml
   │     question, user_profile})─→│                        │
   │←─ 渲染后的完整 Prompt ───────│                        │
   │                                │                        │
   │── get_prompt                  │                        │
   │   ("writing_assistant",       │── 读模板 + format() ─→│ writing_assistant.yaml
   │    {topic, references, style})│                        │
   │←─ 渲染后的完整 Prompt ───────│                        │
   │                                │                        │
   │── get_prompt (省略 style) ──→│── format(style=默认) ─→│ writing_assistant.yaml
   │←─ 渲染后的完整 Prompt ───────│                        │
```

---

## 常见问题

### Q: 端口被占用？

```bash
# Windows
netstat -ano | findstr "9004"
# Mac/Linux
lsof -i :9004
```

杀掉旧进程后重启即可。

### Q: 加了新模板但 list_prompt_templates 没返回？

模板在服务启动时加载。新增或修改 YAML 文件后，需要**重启服务**才能生效。

### Q: get_prompt 返回的内容缺少某个参数？

检查 YAML 模板中的 `{占位符名}` 是否与 `@server.prompt()` 函数的参数名一致。不一致会导致 `format()` 时被跳过或报错。

### Q: 想新增一个模板？

1. 在 `templates/` 目录下新建 `xxx.yaml`，填写 name、description、parameters、template
2. 在 `server.py` 中新增 `@server.prompt()` 函数，参数与 YAML 中的 parameters 一一对应
3. 重启服务
