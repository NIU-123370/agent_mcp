# 第 11 章：共享服务四 — Prompt 管理中心

> 一句话：把 Prompt 当代码管理 —— 版本控制、参数化、A/B 测试、效果评估，通过 MCP Prompt 能力分发给所有项目。

---

## 11.1 Prompt 工程的协作痛点

```
现状：
  张三在笔记里存了一个"代码审查 Prompt v3"
  李四在飞书文档里存了"代码审查 Prompt v2"
  王五直接在代码里硬编码了"代码审查 Prompt v1"

结果：
  → 三个人用着三个版本，效果不一致
  → 谁的版本更好？没人知道
  → 新人来了不知道用哪个
  → 改了 Prompt 要去 N 个项目手动替换
```

---

## 11.2 架构设计

```
┌──────────────────────────────────────┐
│          Prompt 管理中心              │
│          (MCP Server)                │
│                                      │
│  ┌────────────────────────────────┐  │
│  │         Prompt 仓库            │  │
│  │                                │  │
│  │  code_review v3.2 (生产)      │  │
│  │  code_review v3.3 (灰度 20%) │  │
│  │  sql_optimizer v2.1 (生产)    │  │
│  │  translate v1.5 (生产)        │  │
│  │  customer_reply v4.0 (生产)   │  │
│  └────────────────────────────────┘  │
│                                      │
│  MCP Prompt: code_review             │
│  MCP Prompt: sql_optimizer           │
│  MCP Prompt: translate               │
│  MCP Tool:   create_prompt           │
│  MCP Tool:   update_prompt           │
│  MCP Tool:   get_prompt_metrics      │
└──────────────────────────────────────┘
```

---

## 11.3 版本控制

每个 Prompt 像代码一样管理版本：

```
code_review
  ├── v1.0  "请审查以下代码"          (已废弃)
  ├── v2.0  增加了输出格式要求         (已废弃)
  ├── v3.0  增加了严重程度分级         (已废弃)
  ├── v3.2  优化了安全审查维度     ←── 当前生产版本
  └── v3.3  试验新的评分体系       ←── 灰度测试中

发布流程：
  编写 → 内部测试 → 灰度(10%流量) → 全量发布
```

---

## 11.4 参数化与组合

Prompt 不是死模板，支持**参数注入**和**模板组合**：

```
基础模板：system_prompt
  "你是一位 {role}，擅长 {expertise}。请用 {language} 回答。"

组合模板：code_review = system_prompt + review_rules + output_format
  ┌─────────────────┐
  │ system_prompt    │  ← 通用人设
  │ (role=资深工程师) │
  ├─────────────────┤
  │ review_rules     │  ← 审查规则
  │ (focus=security) │
  ├─────────────────┤
  │ output_format    │  ← 输出格式
  │ (format=markdown)│
  └─────────────────┘

好处：修改 output_format 一处，所有使用它的组合模板都自动更新。
```

---

## 11.5 A/B 测试

```
code_review Prompt 有两个候选版本，如何选？

配置 A/B 测试：
  v3.2 → 80% 流量（基线）
  v3.3 → 20% 流量（实验）

收集指标：
  - 用户满意度评分
  - LLM 输出的平均长度
  - 任务完成率
  - Token 消耗

2 周后：
  v3.3 满意度 +8%，Token 消耗 -12%
  → 全量切换到 v3.3
```

---

## 11.6 跨项目复用

```
项目 A（客服）定制了一个很好的"友好回复"Prompt
  ↓ 沉淀到 Prompt 管理中心
  ↓ 标记为"公共可用"
  ↓
项目 B（销售）发现并复用了这个 Prompt
项目 C（知识问答）也复用了

Prompt 管理中心 = 团队的"Prompt 资产库"
```

---

[← 上一章](./第10章-共享服务-会话记忆服务.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第12章-共享服务-语义缓存.md)
