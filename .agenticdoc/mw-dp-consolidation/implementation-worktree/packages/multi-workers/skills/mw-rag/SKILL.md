---
name: mw-rag
description: Use when a task may consult a RAG (retrieval) knowledge base through the mw rag_* tools - choosing between exact lookup and broad search, formatting citations, and writing the research document. Covers the six-section research-doc standard, the citation syntax server:source:file_path:line, and the degradation/anti-pattern rules.
---

# mw-rag - RAG 检索方法论

`rag_*` 工具是**可选**知识源；本地文件与可复现命令始终是事实源。本 skill 是方法论单一来源（框架仓 `packages/multi-workers/skills/mw-rag/SKILL.md`）；工具描述只重复其中 3 行调用纪律。

## 何时用

按任务类型选择工具；未列出的类型没有 RAG 工具：

| 任务类型 | 允许的 RAG 工具 |
| --- | --- |
| coding / review / verifier / research | `rag_search` `rag_symbol` `rag_graph` `rag_impact` `rag_sources` `rag_feedback` |
| rag-research | 上面六个 + `rag_chat` |

- `rag_symbol` / `rag_graph` / `rag_impact`：精确结构检索（符号定义、依赖边、影响面）。
- `rag_search`：全文/语义泛检索。
- `rag_sources`：列出服务端可用数据源/集合；`rag_feedback`：回写检索用法反馈。
- `rag_chat`：最慢、受次数与累计时间预算约束，**只在 `rag-research` 类型**、确需跨源推理时使用。

## 调用纪律

1. 先用 `rag_symbol` / `rag_graph` 精确定位符号与依赖，再按需用 `rag_search` 做泛检索；不要一上来就大范围语义搜索。
2. 引用必须使用工具返回的 `citation` 原文，不得自己拼接或改写路径。
3. “用了 RAG” = 结论已落盘且带可核对引用；只读结果不落盘不算。

## 引用格式

`server:source:file_path:line`

- `server`、`source` 不含 `:`；末段 `line` 是纯数字；中间剩余部分（含 `::`、Windows 反斜杠、空格）原样归 `file_path`。
- 每条结果附带本地核对三件套：`local_path`（本机路径）、`exists`（本地是否存在）、`line_hint`；`snapshot_warning` 表示索引快照可能过期（行号漂移）。
- `exists=false` 时不得把该结果当作已验证事实；`local_path` 与 `citation` 分开放置，不要混进引用字符串。

## 调研文档格式

`rag-research` 的产出物路径：`.agenticdoc/<key>/rag/<server>-<slug>.md`。固定六个小节，标题逐字如下：

```markdown
## 查询
## 结论
## 引用
## 未解决
## 快照
## 影响面
```

- `## 查询`：原始问题与拆解后的子问题。
- `## 结论`：可核对的结论；每条都能对应到 `## 引用` 中的 citation。
- `## 引用`：逐条 `server:source:file_path:line`，并标注本地核对状态（`exists` / `local_path`）。
- `## 未解决`：检索未能回答的问题与下一步。
- `## 快照`：索引快照时间、`snapshot_warning`、本地核对发生的时机。
- `## 影响面`：结论波及的模块/文件/后续任务。

## 降级与反模式

- 服务不可用只降级不阻断：记 `rag-unavailable` 证据行后改走本地检索；RAG 不可用不是任务失败。
- `rag_search` 的 `multi_rounds` / `auto_rewrite` 会让最终结果无法从证据重放；需要强验证的 review 结论只能用 `rag_graph` / `rag_impact`，其他场景注明结果经过改写。
- 不要凭记忆写文件路径或行号；一切以工具返回的 `citation` 与 `exists` / `local_path` 为准。
- 不要把 RAG 当作唯一事实源；本地文件与可复现命令优先。
