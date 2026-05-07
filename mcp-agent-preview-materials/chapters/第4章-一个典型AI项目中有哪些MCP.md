# 第 4 章：一个典型 AI 项目中有哪些 MCP？

> 一句话：一个智能客服系统背后可能有 5-6 个 MCP Server 协同工作，这些 Server 的组合构成了项目的"AI 能力层"。

---

## 4.1 案例：智能客服系统的 MCP 全貌

以一个中等复杂度的智能客服系统为例，它需要这些能力：

```
用户提问 → 理解意图 → 检索知识库 → 查询订单 → 生成回答 → 记录日志 → 发送通知
```

每个能力背后都是一个 MCP Server：

```
┌──────────────────────────────────────────────────────────┐
│                    智能客服 Host                           │
│                                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│  │Client│ │Client│ │Client│ │Client│ │Client│ │Client│ │
│  │  A   │ │  B   │ │  C   │ │  D   │ │  E   │ │  F   │ │
│  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ │
└─────┼────────┼────────┼────────┼────────┼────────┼──────┘
      │        │        │        │        │        │
 ┌────┴───┐┌───┴───┐┌───┴───┐┌───┴───┐┌───┴───┐┌───┴───┐
 │  LLM   ││  RAG  ││数据库 ││ 文件  ││第三方 ││ 记忆  │
 │ 对话   ││ 知识库││ 查询  ││ 操作  ││ API  ││ 服务  │
 │ Server ││Server ││Server ││Server ││Server ││Server │
 └────────┘└───────┘└───────┘└───────┘└───────┘└───────┘
```

---

## 4.2 各 Server 的职责

### LLM 对话服务

```
职责：封装 LLM API 调用（OpenAI / Claude / 本地模型）
Tool：chat_completion, summarize, translate
价值：统一模型切换、管理 API Key、控制 Token 消耗
```

### 知识库检索（RAG）

```
职责：文档向量化 + 语义检索
Tool：search_knowledge, upload_document
Resource：knowledge://产品手册, knowledge://FAQ
价值：让 LLM 基于企业私有知识回答，而非纯靠训练数据
```

### 数据库查询

```
职责：安全地执行业务数据查询
Tool：query_orders, get_user_info, get_product_details
Resource：db://schema（表结构）
价值：LLM 获取实时业务数据（订单状态、用户信息等）
```

### 文件操作

```
职责：读写文件、生成报告、处理附件
Tool：read_file, write_file, generate_pdf
Resource：file://templates/{name}
价值：生成工单报告、处理用户上传的附件
```

### 第三方 API 集成

```
职责：对接外部系统（邮件、日历、CRM、企业微信等）
Tool：send_email, create_calendar_event, update_crm_record, send_wechat
价值：LLM 直接触发业务操作，不需要人工中转
```

### 会话记忆

```
职责：管理对话历史和用户偏好
Tool：save_memory, recall_memory
Resource：memory://user/{user_id}/recent
价值：跨会话的连续体验（"上次你说想退货，处理得怎样了？"）
```

---

## 4.3 协作关系

这些 Server 不是孤立运行的，一次用户请求可能**串联多个 Server**：

```
用户："我上周买的耳机还没到，帮我查一下"

  ① 记忆 Server → 召回用户历史（上次聊过什么）
  ② 数据库 Server → 查询订单状态（物流信息）
  ③ 知识库 Server → 检索退换货政策
  ④ LLM Server → 综合以上信息生成回答
  ⑤ 第三方 Server → 自动创建催单工单

                  LLM（大脑）
                 ╱   │    ╲
                ╱    │     ╲
           记忆   数据库   知识库    ← 获取信息
               ╲    │    ╱
                ╲   │   ╱
                 综合推理
                    │
                 第三方 API        ← 执行操作
                    │
                "已为您创建催单工单，
                 预计明天送达"
```

**关键观察**：LLM 是"大脑"，MCP Server 是"四肢和感官"。LLM 根据上下文自主决定调用哪些 Server、以什么顺序调用。

---

## 4.4 这个架构的特征

回看这个单项目架构，它有几个明显特征：

```
特征 1：每个能力独立成 Server
  → 清晰、解耦、可独立开发和测试

特征 2：所有 Server 只服务于这一个项目
  → 项目 A 有自己的 RAG Server，项目 B 也有自己的 RAG Server

特征 3：LLM 调用逻辑写在 Server 内部
  → 每个项目自己管理 API Key 和模型选择

特征 4：没有统一的日志和监控
  → 每个 Server 各自记录（或不记录）日志
```

看起来还好？等你公司有了 3 个、5 个、10 个 AI 项目，问题就爆发了。

> **下一章**：这些"看起来还好"的特征，如何变成架构噩梦。

---

[← 上一章](./第3章-动手搭建你的第一个MCP-Server.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第5章-单项目MCP架构的痛点.md)
