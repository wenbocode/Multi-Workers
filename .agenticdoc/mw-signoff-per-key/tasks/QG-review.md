# QG — mw-signoff-per-key（签收点按 key 通用 + 落授权表）

- type: review
- key: mw-signoff-per-key
- 上下文: `mini-spec.md`（本 key 的唯一规格）、`achieved.md`（PM 自述）。用户裁定：`dp25-signoff-conclusion` 必须对**任意 AgenticTask key** 通用，并且必须作为真实一行进 `.mw/decide-points.json`（唯一授权源）。
- 目标锚点: `H:/git/Multi-Workers/.agenticdoc/goal.md`（人只在事后 review；签收由决策模型完成）

## 上下文

改动面（都是小改，重点在"是否真的通用、是否真的只补缺行"）：

- `packages/multi-workers/decision_points.py:824-855`（dp25 定义：P2、description、q-conclusion instructions、回显 executor）
- `packages/multi-workers/decision_points.py:1184-1191`（dp25 的 `REQUIRED_STATE_FIELDS`，含 `key`）
- `packages/multi-workers/decide_signoff.py:285-330`（`collect(project_dir, key)`：按 key 过滤档案行）
- `packages/multi-workers/decide_signoff.py:380-430`（`auto_conclusion(project, key)`：state 里带 key）
- `packages/multi-workers/mw.py:2215-2264`（`_dp_refresh`：只 append 缺失行）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:364-378`（`TABLE_WRITE_CLI_RE` 去掉 `refresh`）
- `packages/coding-agent/test/suite/decision-signoff.test.ts:204-236`（blocked/allowed 清单）
- `packages/multi-workers/test_decide_sign_auto.py:642-683`（新增跨 key 用例 `test_dp25_signs_any_key_not_just_the_fixture_key`）
- `.mw/decide-points.json`（25 行，dp25 `{tier: P2, enabled: true, mode: auto}`，`updated_by: refresh`）

## 审计目标

1. **通用性**：dp25 的代码路径里不得出现任何硬编码 key（除测试夹具）；state 的 `key`、档案行过滤、`sign` 的 `--key/--project` 都由调用方决定。给出至少 2 条证据（源码行 + 新增测试行），并说明"另一个 key 的行会不会被算进来"。
## 要求（逐条给 PASS/FAIL + 证据 path:line，对应 AC-001..005）

2. **无越权**：`_dp_refresh` 不得改写已有行的 `enabled`/`mode`/`tier`/`note`，只能 append 缺失行；`TABLE_WRITE_CLI_RE` 仍必须拦 `on|off|set|apply`。用源码 + 测试行证明，并确认 `dp25` 的 P2 默认开不是被 `refresh` "打开"的（它本来就 P2）。
3. **表与注册表一致**：`dp check` / `dp list` / `dp show` 的口径（25 行、`source=config`、`layer=OK`、0 warning）。请自己跑一遍这三条命令（只读）。
4. **签收不受表更新影响**：说明 `rows_sha256`/`counted_rows` 是档案口径，改表不会让既有 `evidence/review/sign-final.md` 失效；并用一条只读命令验证（例如 `mw decide sign --key mw-decision-substitution --project . --dry-run`）。
5. **文档一致性**：`docs/decision-points.md`（授权来源 refresh 例外、dp25 通用段）、`flowcharts.md` §2.7 标题、两包 CHANGELOG 是否与实际行为一致；指出任何"文档说 A、代码做 B"的点。
6. **测试充分性**：新用例是否真的能抓住回归（把 dp25 改回 P1、或把 refresh 从放行表里拿掉、或把 collect 的 key 过滤去掉，测试会不会红）。给出你的判断，不需要真去改代码；如要验证，用临时副本，不要动工作树。

## 交付格式

- 写 `evidence/quality-gate-report-20261021.md`：首行 `Verdict: PASS|FAIL`，随后 `## 结论`、`## 逐条判定（1-6）`、`## 发现`（按 BLOCKER/MAJOR/MINOR 分级）、`## 未覆盖面`（明确声明你没查的部分）。
- 同时按 worker 通用格式写 `report.md`（≤50 行，含结论/证据/残留与未验证/上下文来源/改动清单）。

## 未覆盖面声明（必须保留并补充）

- 不做真实 jev 联网调用（本 key 无档案行，签收由 PM 单独做）。
- 不重建 `dist/**`、不跑 `npm run build`、不跑 `npm run check`（会碰他人未提交文件）。
- 不改任何源码/测试/配置；只读 + 写你自己的工作目录与上述 QG 报告文件。
