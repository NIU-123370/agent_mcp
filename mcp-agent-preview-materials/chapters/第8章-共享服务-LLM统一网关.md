# 第 8 章：共享服务一 — LLM 统一网关

> 一句话：所有项目通过一个网关调用 LLM，统一管理模型接入、路由策略、Key 轮换、流式输出和故障降级。

---

## 8.1 为什么是第一优先级？

LLM 网关解决的是第 5 章中**最痛的三个问题**：

```
痛点 ② API Key 散落      → 网关统一管理所有 Key
痛点 ④ 模型切换改 N 个项目 → 网关路由，项目无感知
痛点 ⑤ Token 成本失控     → 网关统一计量和限流
```

一个服务解决三个痛点，所以它排第一。

---

## 8.2 架构设计

```
项目 A ──┐                ┌── OpenAI (GPT-4o / GPT-4o-mini)
项目 B ──┼── LLM 网关 ────┼── Anthropic (Claude 3.5 Sonnet)
项目 C ──┘   (MCP Server) ├── Google (Gemini Pro)
                          ├── 本地模型 (Ollama / vLLM)
                          └── Azure OpenAI (合规需求)
```

网关的 Tool 接口：

```
Tool: chat_completion
  输入：messages, model_hint(可选), temperature, max_tokens
  输出：LLM 的回答

Tool: embedding
  输入：text, model_hint(可选)
  输出：向量

Tool: summarize
  输入：text, max_length
  输出：摘要
```

项目只需要调用 `chat_completion`，**不需要知道背后用的是哪个模型、哪个 Key**。

---

## 8.3 模型路由策略

```
请求到达 → 路由引擎决策 → 选择最优模型

路由规则（按优先级）：
  1. 项目指定：项目 A 要求只用 Claude → 走 Claude
  2. 任务类型：简单查询 → GPT-4o-mini（便宜）
               复杂推理 → GPT-4o（强）
               代码生成 → Claude 3.5 Sonnet（擅长）
  3. 成本优先：优先选便宜的，超时或失败再升级
  4. 负载均衡：同一模型多个 Key 轮询，避免单 Key 限流
```

路由配置示例：

```yaml
routes:
  - match: { project: "customer-service", task: "simple_qa" }
    model: gpt-4o-mini
    fallback: gpt-4o

  - match: { task: "code_generation" }
    model: claude-3.5-sonnet
    fallback: gpt-4o

  - match: { task: "translation" }
    model: gpt-4o-mini

  - default:
    model: gpt-4o
    fallback: claude-3.5-sonnet
```

---

## 8.4 Fallback 与重试

```
请求 → 主模型
         │
       成功？──是──► 返回结果
         │
        否（超时/限流/错误）
         │
         ▼
       Fallback 模型
         │
       成功？──是──► 返回结果
         │
        否
         │
         ▼
       返回错误 + 告警
```

关键策略：

| 策略 | 说明 |
|---|---|
| **超时控制** | 流式首字节 5s，非流式 30s，超时切 Fallback |
| **Key 轮换** | 单 Key 限流时自动切换到备用 Key |
| **模型降级** | GPT-4o 不可用时降级到 GPT-4o-mini |
| **跨厂商切换** | OpenAI 全线故障时切到 Claude |
| **重试策略** | 指数退避，最多 2 次重试，幂等请求才重试 |

---

## 8.5 流式输出的统一处理

不同模型厂商的流式格式不同，网关需要**统一化**：

```
OpenAI 流格式：       Claude 流格式：       统一输出格式：
data: {"choices":     event: content_block   data: {"text": "你好",
[{"delta":{"content": _delta                        "model": "gpt-4o",
"你好"}}]}            data: {"delta":                "usage": {...}}
                      {"text": "你好"}}
         │                    │
         └────────┬───────────┘
                  │
           网关统一转换
                  │
                  ▼
         标准化的 SSE 流
```

项目端不需要关心背后是 OpenAI 还是 Claude，接收到的流格式始终一致。

---

## 8.6 多模态支持

```
网关不仅处理文本，还统一封装多模态能力：

Tool: generate_image     → DALL-E / Midjourney API
Tool: understand_image   → GPT-4o Vision / Claude Vision
Tool: text_to_speech     → OpenAI TTS / Azure TTS
Tool: speech_to_text     → Whisper / Azure STT
```

每种模态的调用方式统一，模型选择和 Key 管理由网关负责。

---

## 8.7 开源方案参考

| 方案 | 特点 | 适合 |
|---|---|---|
| **LiteLLM** | Python，100+ 模型支持，OpenAI 兼容格式 | 快速落地 |
| **OneAPI** | Go，中文社区活跃，Web 管理界面 | 国内团队 |
| **自研** | 完全定制 | 有特殊需求的大团队 |

> **务实建议**：用 LiteLLM 或 OneAPI 快速搭建，在上面包一层 MCP Server 接口。不要从零造轮子。

---

[← 上一章](./第7章-共享MCP服务的整体架构设计.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第9章-共享服务-RAG即服务.md)
