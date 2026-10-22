# T-07 — 快修 m1：B2 校验错误回喂重发（design D-002 对齐）

- key: mw-jev-provider-integration · type: coding · W7 · timeout: 30

## 上下文

goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」。W6 全量复审（`.agenticdoc/mw-jev-provider-integration/evidence/quality-gate-report-20261016-recheck.md`）给出 PASS（0 blockers / 0 majors），其中 **m1 = design D-002 要求"校验不合法 → 回喂校验错误重发 1 次"，实现未做**：当前 `LLMTransitionalBackend.decide()` 一次 POST 后，tool_use 解析/校验失败就直接走 text 回退，再失败即 `bad-response`（`packages/multi-workers/decision_backends.py:583-592`）。

为什么值得修（不是纯文档对齐）：
- B2 请求体 `temperature: 0`（`decision_backends.py:521`）——客户端对 `bad-response` 的重试会**确定性复现同一份非法输出**，等于没救；
- 回喂把"你上一轮哪一项不合法"告诉模型，才有纠错机会（design D-002 原话：校验不合法 → 回喂校验错误重发 1 次）。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/design.md:68`（D-002 解析与回退链的完整要求）
- `.agenticdoc/mw-jev-provider-integration/evidence/quality-gate-report-20261016-recheck.md`（m1 原文与 8 条 note）
- `packages/multi-workers/decision_backends.py:387`（`_validate_answers`）、`:437`（`_decode_text_fallback`）、`:500`（B2 请求模板与 `tools`/`tool_choice`）、`:521`（`temperature`）、`:583-592`（当前解析链）
- `packages/multi-workers/test_decide_backends.py:1`（现有 fake-HTTP 测试风格：monkeypatch `_http_post`）

## 要求

1. **实现回喂重发**（只在 `LLMTransitionalBackend`，且**仅**在"响应里存在 `tool_use` 块、但 `_validate_answers` 校验失败"时触发）：
   - 追加**一次** follow-up 请求：把上一轮的 assistant 响应（含 `tool_use`）与该 `tool_use` 的 `tool_result`（内容 = 校验错误文本，例如 `missing answer for triage_risk` / `choice out of enum for x: 'medium'`）送回，并重申要求（严格照 `submit_decision` 工具、逐题作答）；
   - **单个 `decide()` 调用内最多 2 次 HTTP POST**（1 次正常 + 1 次回喂）；不得循环重发；
   - 第二次仍不合法 → 继续走既有 text 回退（`_decode_text_fallback`）→ 仍失败 → `bad-response`（**不要**改这条尾部行为）；
   - 无 `tool_use` 块（模型只给 text）→ 保持现状：**不**触发回喂，直接 text 回退；
   - 不新增禁带字段（`response_format`/`state`/`questions`/`store` 仍禁）、不改 `temperature`、不改 `tools`/`tool_choice` 形状、不改 HTTP 错误分类。
   - 在模块 docstring 或该函数注释里写明这是"单次请求"约定的**唯一例外**，并引用 design D-002。
2. **测试**（`packages/multi-workers/test_decide_backends.py`，沿用现有 monkeypatch `_http_post` 风格，零真实网络）：
   - (a) 首次返回"存在 tool_use 但 choice 越界"→ 第二次返回合法 tool_use → `available=True`，且**恰好 2 次** `_http_post`，第二次请求 body 含校验错误文本与 `tool_result`；
   - (b) 两次都不合法 → `available=False`、`reason="bad-response"`、**恰好 2 次** `_http_post`（防死循环）；
   - (c) 首次返回**只有 text 无 tool_use** → **恰好 1 次** `_http_post`，且走 text 回退成功（证明回喂路径没被误触发）；
   - (d)（note 项，低成本）补 B1 `entry_probe=true` 路径的 hermetic 用例：断言它按配置探测并在失败时归一为 `entry-unavailable`，不得抛异常。
3. **不得**修改 `decision.py` / `mw.py` / `mw_common.py` / TS 侧任何文件；不改公开签名（`DecisionBackend` 协议与 `BackendOutcome` 字段不变）。

## 写入允许面

- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`

## 写入禁止面

- 其它一切文件（尤其 `decision.py`、`mw.py`、`mw_common.py`、TS 侧、README/CHANGELOG）；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
cd packages/multi-workers && python -m pytest -q test_decide_backends.py
cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py
```

## 改动历史

- 2026-10-16 W6 复审发现 m1（design D-002 漂移），本卡为快修。

## 交付格式

- 两个文件 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**前 10 次写调用内落出实现改动**（先改代码再补测试，不要长时间只读）。
