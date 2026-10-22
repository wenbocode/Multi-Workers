# spec — mw-signoff-per-key

## §0 Goal Alignment

项目目标（`goal.md`）：PM Agent 管理多个 Worker 并行开发，人只在事后 review；中低风险决策由 jev 决策模型完成，而不是阻塞在人身上。

本 key 服务该目标的两处缺口：

- **预期收益 1**：签收不再隐含"只对发起该功能的 key 有效"——任何 AgenticTask key 收尾都能用同一条 `mw decide sign --key <key>` 让决策模型出 `continue|narrow|revoke`，人只在事后看记录。
- **预期收益 2**：签收点成为授权表里可审计的真实一行（`.mw/decide-points.json`），而不是只以注册表默认值"隐身生效"；表的唯一授权源地位保持不变（机器只能做 append-only 的注册表→表同步，翻开关仍要人）。

## §1 问题

1. `dp25-signoff-conclusion` 的文案（`decision_points.py` 的 `description`/`instructions`、注册表 `wiring_note`、`docs/decision-points.md`）读起来像"某个 key 的专属签收"，没有说明 key 由调用方传入、对任意 key 通用。
2. `.mw/decide-points.json` 只有 24 行；dp25 靠注册表默认值（P2）生效，`dp show` 报 `source=default`，授权表不是唯一可审计源。
3. 把缺行补进表的唯一合规手段 `mw decide dp refresh` 被 `xkey-gate-guard` 当成"机器写授权表"直接拦死（`TABLE_WRITE_CLI_RE` 含 `refresh`）。

## §2 验收标准

- **AC-001**：`dp25` 的注册表文案与文档明确"任意 AgenticTask key 收尾通用"，且说明调用形式（`--key` 或 `--project .agenticdoc/<key>`）。
- **AC-002**：`dp25` 链路中不出现硬编码 key；`decide_signoff.collect(project, key)` 只折叠该 key 的档案行；`signoff_state(...)["key"]` 等于调用方传入的 key。
- **AC-003**：`xkey-gate-guard` 放行 `mw decide dp refresh`（注册表→表单向合并），仍拦 `mw decide dp on|off|set|apply`；放行后 `mw._dp_refresh` 只 append 缺失行，绝不改写已有行的 `enabled`/`mode`/`tier`/`note`。
- **AC-004**：执行一次同步后 `.mw/decide-points.json` 含 25 行，`dp25-signoff-conclusion = {tier: P2, enabled: true, mode: auto}`，`dp show` 报 `source=config`、`layer=OK`、`dp check` 0 error/0 warning。
- **AC-005**：既有 key（`mw-decision-substitution`）的签收不因表更新失效（`rows_sha256`/`counted_rows` 为档案口径，`check_gate("done")` 仍为 True）。

## §3 非目标

- 不放开 `dp on|off|set|apply`（翻开关仍需人签或人操作）。
- 不改 `signoff=auto|disable` 语义、不改 dp25 判据、不改"只有 P2 默认开"的注册表铁律。
- 不重建 `dist/**`（运行期生效需 rebuild + reload，由用户放话）。
- 不处理上一 key 的待裁定项（D-044、21 个未接线 dp 的 `REQUIRED_STATE_FIELDS`、`narrow` 是否据此收窄）。

## §4 证据要求

- 代码：`decision_points.py`、`decide_signoff.py`、`mw.py`、`xkey-gate-guard.ts` 的改动行 + 测试行。
- 运行：受影响 pytest/vitest 套件、`dp list/show/check`、`dp export --write`、`gen_decide_registry_ts.py --check`、`sign --dry-run`（既有 key）。
- 表：`.mw/decide-points.json` 的 25 行与 `updated_by=refresh`、追加的 `authority-change` 行。
