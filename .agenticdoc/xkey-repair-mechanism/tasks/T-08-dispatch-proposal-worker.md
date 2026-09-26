# T-08 追认后派发提案 worker（conductor.py 单写者）

key: `xkey-repair-mechanism` · 依赖: T-06 已落地（apply/verify/close 段在位） · 覆盖: AC-009 全链的"受限修复"生产侧 + D-005 的 (b) 路径完整性

## 背景（机制完整性缺口）

D-005 选 (b)：**worker 只产提案，conductor 前置校验后应用**；design §5 流程图也写明 `human approve -> dispatch proposal worker`。但当前实现里，工单到 `approved` 后**没有任何角色产出提案** ⇒ 真实项目开启后工单会永久停在 `approved`（T-06 的 apply 段只处理"提案已存在"的情形）。本卡补齐派发侧。

## 实现要求

1. **触发点**：ticket 状态为 `approved` **且**提案文件不存在（`.agenticdoc/_autopilot/xkey/evidence/<request_id>/proposal.md`）⇒ 派发**恰好一次**提案 worker。挂在 T-06 的 apply 段**之前**同一 `cfg["xkey_repair"]` 门控内（`conductor.py:229` 附近的调用链）。
2. **派发通道**：镜像既有修复派发 `conductor.py:1084-1088`：
   ```python
   dispatch.dispatch(project_root, key, stem, "phase-writer", prompt,
                     loop=loop, attempt=attempt, timeline=st.timeline)
   ```
   `key` 用 ticket 的 `source_key`（发货 key），`stem` 用 `f"xkey-{request_id}-proposal"`（task key 由 `dispatch.task_key_for` 生成，`ap-` 前缀）。
3. **prompt 契约**（新增 `_xkey_proposal_prompt(ticket)`，必须自包含，worker 只读 prompt + ticket 即可干活）：
   - 读工单文件（给绝对路径）；
   - 冻结块规格（`file` / `line_range` / `old_block_sha256` / `symbol`）与**允许改的行集合**；
   - `untouchable[]` 不可触碰清单（同文件其它常量 / 断言主体）；
   - **输出契约**：写 `evidence/<request_id>/proposal.md`，frontmatter 必含 `file` / `line_range` / `old_block_sha256`（逐字等于工单值），正文用围栏代码块承载**新冻结块内容**（逐字保留换行，D-012 字节精确）；
   - **明令禁止**：不得改任何其它文件、不得改断言逻辑（只更新冻结期望/常量块）；
   - 必须报告它实际改了哪些行。
4. **幂等/durable**：同一 `request_id` 只派发一次。守卫从盘重派生（例如把 `proposal_dispatch_at` + task key 写进工单 frontmatter（用 `xkey.ticket_write` 重写）或复用 `_row_exists`/in-flight 判据，见 `conductor.py:513-514`）；**禁止加内存游标**。提案 worker 在飞/已落盘都不得重复派发。
5. **失败有界**：派发被拒 ⇒ 记账本 history + escalation，工单留 `approved`；尝试次数有界（镜像 `:1082` 的 `used/attempt` 模式），超界后停止重派并升级，不无限循环。
6. **开关关闭零行为变化**（AC-008）。

## 验收（真实输出入报告）

`.tmp/` scratch fixture（跑完删）：approved 工单 + 无提案 ⇒ 连跑 N=3 tick 只产生 **1 条**派发记录（task key 唯一、无重复）；提案文件出现后 ⇒ 不再派发且 T-06 段接管；派发失败注入 ⇒ escalation + 留 `approved` + 有界重试。

- 焦点回归：`python -m pytest -q test_autopilot_xkey_registration.py test_autopilot_gates.py test_autopilot_fail_marker_forms.py test_autopilot_verdict_source_fallback.py` 无新增失败（外域先在红 1 条已归因）。
- 报告含：新函数 file:line、prompt 全文（逐字）、派发记录实物、幂等证据。

## 纪律

- **只写 `autopilot/conductor.py`**（+ 报告 + `.tmp/` scratch）。不改 `xkey.py` / `config.py` / 任何测试 / TS。
- `_parse_l3_output`/`_md_section` 区域禁改；4-tuple arity 保持；异常隔离（不得打断 tick）。
- 不跑全量套件；不 commit。
