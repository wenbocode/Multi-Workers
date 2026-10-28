# Spec: T22 生产写链路修复（capture filter 契约 + 结构化展示）

## 问题（已实证，2026-10-25）

`mw decide run` 写任何带 `task_before` 的 `record-start` 时崩溃：

```
packages/multi-workers/decision_wire.py:936 in _sanitize_metadata_key
    scrubbed, _scrubbed_flag = scope.redact.scrub_tail_prefix(clipped)
AttributeError: 'KnownSecretRedactor' object has no attribute 'scrub_tail_prefix'
```

异常被 transport 吞掉 → 账本静默零行。后果：`task_before`/`task_after` 在真实路径
从未落盘（新记录只能显示"未记录"），且 reload + 重新打包之后**所有 dp1 决策记录**
都写不进去（`.agenticdoc/_autopilot/` 5 个决策载体停在 `2026-10-25T02:12–02:16Z`，
07:00Z 的 `t22-live-verify` 与 `dpc-rq7/8/9` 均零行）。

根因两层：

1. `mw._decide_lifecycle_store` 注入 `decision.known_secret_redactor()`，该类按既有设计
   只是 book gate 的过滤器、**不是** capture filter（`test_decision_coverage_safety.py:569-580`
   明确要求拒绝它当 `scope.redact`）；`decision.py:1213 _capture_filter_contract_issue`
   就是这个契约，但注入点从未校验。
2. 换成 wire 兼容过滤器后，metadata **key** 的尾部清理按 `MIN_SCRUB_PREFIX = 1` 执行：
   实测 `observed_at → observed_a`、`completed → complete`，读侧
   `validate_task_state` 判为非法快照 → DAG 显示"无法确认"而不是"未记录"。

## 方案

A. `mw._decide_lifecycle_store` 改用 `decision.credential_redactor()`（wire 兼容
   `_CredentialRedactor`）。返回 `None`（wire 模块或凭证快照不可证）时**拒绝写入并报错**，
   不静默降级为不脱敏账本。保留 `KnownSecretRedactor` 作为 gate 过滤器的既有定位。

B. `decision_wire._sanitize_metadata_key`：键的尾部清理加 4 字符下限
   （`METADATA_KEY_MIN_SCRUB = decision._MIN_SECRET_LEN = _COVER_RESIDUAL_LEN`）。
   1–3 字符不是可用凭证片段，而清理它会改写固定 schema 字段名。值侧（`_sanitize_text`）
   语义不变；覆盖判据的下限本来就是 4 字符，不放松任何已证明的覆盖。

C. 回归测试：
   - 生产过滤器满足 `SecretRedactor` 契约；gate 形状仍被拒绝（不动 T05q 设计）。
   - 生产过滤器真实写出 `record-start`，且 `task_before` 六字段原样落盘。
   - 键的短尾巴不被清理（`observed_at` 保真），≥4 字符尾巴仍被清理。
   - `_scratch` 这类不可记录的 key 在创建事实处显式拒绝（不静默丢记录）。

D. 界面：`task_before` / `task_after` 结构化阅读友好——状态徽标 + 来源/记录时间一行
   + `已完成`/`待处理`/`阻塞` 分项列表（多点列表不再挤成一行），空列表 `无`、null
   `未记录`、非法 `无法确认` 三种语义保持不变。

## 不做

- 不回填历史记录（AC025 旧记录继续显示"未记录"）。
- 不把 `KnownSecretRedactor` 变成 capture filter（会推翻 T05q 的点设计）。
- 不改扩展 bundle（本轮无 TS 改动）；`_scratch` 在扩展侧的静默降级（`mw decide run`
  非零退出被映射成 `upstream-error`）另立条目。

## 验收

- `test_decision_task_state.py` 全绿（新增 4 条回归，其中 2 条在修复前 RED）。
- `test_decision_task_state_ui.py` 全绿（结构化展示不改变可读文本语义）。
- `test_decision_wire_store.py` 全绿；`test_decision_coverage_safety.py` /
  `test_decision_known_set_snapshot.py` 维持改动前的 10 条基线失败，不新增。
- 用既有 envelope 重跑 `mw decide run`：exit 0，账本出现六字段完整的 `task_before`。
- 浏览器（serve 重启后）行动反馈显示：决策前 → 实际处理 → 决策后，列表分项可读。

## 写面

`packages/multi-workers/{mw.py, decision_wire.py, decision_dashboard.js,
decision_dashboard.css, test_decision_task_state.py}` + 本 key 的 `evidence/`。
`decision.py` 不改（由 A 取代）。
