Verdict: PASS

QG 复核报告 — mw-signoff-per-key（worker psk-qg-review，2026-10-21）

## 结论

按卡片 `tasks/QG-review.md` 对 dp25-signoff-conclusion 通用性与 `dp refresh` 落表路径做独立复核，六项全部 PASS，对应 spec AC-001..AC-005：dp25 链路无硬编码 key、key 由调用方传入、只统计该 key 的档案行（新增跨 key 用例 + 生产档案 3 个 key 实证）；`_dp_refresh` 只按注册表默认值 append 缺失行、绝不改写已有行，`TABLE_WRITE_CLI_RE` 仍拦 `on|off|set|apply`，dp25 的 P2 默认开来自注册表而非 refresh；`.mw/decide-points.json` 25 行与注册表一致；既有 key 的签收（`rows_sha256`/`counted_rows` 档案口径）不受表更新影响；文档与行为一致（3 条 MINOR 陈旧文案/元数据）；三类回归场景均有测试会红。发现：0 BLOCKER / 0 MAJOR / 3 MINOR。

判定方法声明：本 worker 会话没有 shell 工具（工具面为 read/find/grep/ls/worker_file），卡片要求"自己跑一遍"的 `dp check/list/show`、`sign --dry-run`、pytest/vitest 均无法由本 worker 执行。第 3、4 条改为源码静态复核 + 表/档案逐行比对 + `pm-state.md` 验证台账交叉核对（记录值与静态推论一致）；执行性缺口见"未覆盖面"。

## 逐条判定（1-6）

### 1. 通用性 — PASS（AC-001/AC-002）

dp25 代码路径无硬编码 key，key 全程由调用方决定：

- `packages/multi-workers/decide_signoff.py:285` `collect(project_dir, key)` 显式收参；`:298-306` 只折叠 `kind=="decide"` 且 `_row_matches_key(row, key)` 且 `dp != dp25` 的行；`:221-228` `_row_matches_key` = key 列相等，或 `decision_id` 的 `:<key>` 后缀（既有 card 规则，兜底老格式行）。
- `decide_signoff.py:368` `signoff_state` 写 `"key": facts.key or (key or "")` — state 里的 key 来自调用方，非常量；`auto_conclusion(project_dir, key)`（`:380-430`）同签名透传。
- `packages/multi-workers/mw.py:10883-10884` `mw decide sign` 的 `--project`（默认 `.`）与 `--key`（默认取 `.agenticdoc/<key>` 目录名）都是 CLI 参数；epilog 示例即通用形式 `--project .agenticdoc/<key>`。
- `packages/multi-workers/decision_points.py:824-855` dp25 注册条目（description `:831`、q-conclusion instructions `:839-841`）通篇为"任意 key / 该 key"，无具体 key 字面量；全文件 grep 确认 `decide_signoff.py` 无任何 `mw-*` key 字面量（key 仅出现在测试夹具 `test_decide_sign_auto.py` 的 `KEY`/`k-any-other-key`）。
- 注册表镜像一致：`packages/multi-workers/decide_registry.json:915-926` dp25 `wiring_note` 明写 "on-demand CLI caller for ANY AgenticTask key … `mw decide sign --key <key>` (or `--project .agenticdoc/<key>`)"，required_state_fields 含 `key`（`:930-933`）。

**另一个 key 的行会不会被算进来？不会。** 测试与生产双重证据：

- 测试：`packages/multi-workers/test_decide_sign_auto.py:644-683` `test_dp25_signs_any_key_not_just_the_fixture_key` 以 `k-any-other-key` 建项目，同一档案放入 other 与夹具 key 各一行真引擎行，断言 `facts.key == other`、`len(facts.rows) == 1`（`:663`，"only the requested key's rows are counted"）、`state["key"] == other`、`auto_conclusion` 出 `continue`、签收文件 `key: other` / `counted_rows: 1`（`:677`）— 夹具 key 的行不串入。
- 生产：`.agenticdoc/_autopilot/decisions.jsonl` 中 dp25 已为至少 3 个不同 key 实答 — seq 34/40（`mw-decision-substitution`）、seq 36/37（`mw-usage-monitor`）、seq 41（`mw-signoff-per-key`）— 各 key `state_digest` 不同（`d57c52f0…` / `c3ae8193…` / `6b99064f…`），证明 state 确按 key 计算，且全部走 `kind=decide`、`available=true` 的同一链路。

### 2. 无越权 — PASS（AC-003）

- `_dp_refresh`（`packages/multi-workers/mw.py:2215-2250`）只做单向合并：已存在的行仅 `kept += 1`（`:2226-2227`），绝不改写其 `enabled`/`mode`/`tier`/`note`；缺行才 `points[point.id] = _dp_row_for(point)`（`:2228-2230`）；孤儿行保留不删（`:2231`，`:2257-2259` 打印 "row kept, not deleted"）；仅在 `added` 非空时写表并把 `updated_by` 置 `"refresh"`（`:2232-2233`）；每条新增行落一条 `by=refresh` 的 `authority-change` 审计行（`:2241-2249`）。没有任何独立设置 `enabled`/`mode` 的路径。
- `_dp_row_for`（`mw.py:1770-1776`）：新增行四值全部来自注册表默认（`tier`/`default_enabled`/`default_mode`/`note:""`）。
- 测试锁定：`packages/multi-workers/test_decide_dp_cli.py:453-484` `test_dp_refresh_adds_missing_rows_and_preserves_existing_ones` — 预置 dp4 行（`enabled=True, mode=suggest, note=trial`）与孤儿 dp99 刷新后原样保留，dp1 补为注册表默认、dp8（P0）补为 `enabled=False`，`updated_by=="refresh"`，每新增行一条 by=refresh 审计行；`:487-507` 幂等且无变化时零写入。
- 守卫：`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:380` `TABLE_WRITE_CLI_RE = /\bmw(?:\.py)?\b[^\n;&|]*\bdecide\s+dp\s+(?:on|off|set|apply)\b/i` — `refresh` 已移出；`:364-378` 注释写明放行理由（one-way merge、append-only、P0/P1 缺行补为关）；`DECISION_GUARD_EXPLANATION`（`:349-354`）同步改写为 "`on|off|set|apply` 写表行，`refresh` 只能补缺失的注册表行"。
- 测试锁定：`packages/coding-agent/test/suite/decision-signoff.test.ts:208-236` blocked 清单含 `mw decide dp off`（:217）、`dp apply`（:218）、`mw.py decide dp set enabled=true`（:219）、`dp on … --i-understand-p0`（:220，确认连 P0 确认旗也不放行）；allowed 清单含 `mw decide dp refresh --project .`（:237）与 `python packages/multi-workers/mw.py decide dp refresh`（:238）。
- **dp25 的 P2 默认开不是 refresh "打开"的**：`decision_points.py:825-828` 注册时即 `tier="P2"`（注释写明 P2 是让签收默认路径开箱即用，spec §15 AC-024/AC-027）；`_point` 工厂直接推导 `default_enabled=(tier == "P2")`（`:485`），`DecisionPoint.__post_init__` 铁律校验 `default_enabled is not (tier == "P2")` 即 import 期 fail-loud（`:378`）；`docs/decision-points.md:204` 记录是上一 key 的 W11 把 dp25 从 P1 改为 P2。反证两条：refresh 对 P0/P1 缺行补的是 `enabled=false`（`test_decide_dp_cli.py:479` 断言 dp8）；`test_decide_sign_auto.py:619-641` 证明**完全没有表行**时 dp25 靠注册表默认值即 `enabled=True`（`source=default`）且 jev 被问 — 默认开独立于 refresh 存在，refresh 只是把同一默认值物化为表行。

### 3. 表与注册表一致 — PASS（静态复核；三条命令未由本 worker 执行）

`.mw/decide-points.json` 逐行实测：

- 25 行（dp1..dp25），与 `DP_REGISTRY` 条目数一致（`test_decide_sign_auto.py:595` 锁定 `EXPECTED_DP_COUNT == 25`）；dp25 行 = `{tier: P2, enabled: true, mode: auto, note: ""}`；`updated_by: "refresh"`；`version: 1`。
- 25 行 tier 与注册表逐一相符（注册表 tier 定义 `decision_points.py:507-828`；比对规则 `_parse_row` `decision_points.py:1578-1681`：tier 不符 → L7、非法 tier → L4、enabled 非 bool → L5、mode 非法 → L3）— 当前表无一行触发任何 issue；无 policy 键 → 无 L8；无未知行键、无孤儿行 → 无 L2/L6。
- `version: 1` 为整数 → 无 version warning（`mw.py:2292-2330` `_dp_check_issues`）。
- enabled 计数 = 10（dp1/2/3/5/7/9/21/22/23/25），全 P2；P0/P1 全关 — 与"只有 P2 默认开"铁律一致。
- 行存在即 `source="config"`（`_parse_row` 成功路径固定返回 `source="config"`）；行干净即 `layer="OK"`（`decision_points.py:1476, :1588, :1766-1786`）。

推论与 PM 台账相符：`dp list` → `25 decision point(s), enabled=10, orphaned=0, layer=OK`（输出格式 `mw.py:1915-1943`）；`dp show dp25-signoff-conclusion` → `P2 enabled=true mode=auto source=config`；`dp check` → 0 error / 0 warning、rc=0。三者与 `pm-state.md:15,19` 的执行记录一致，且与 achieved.md 口径一致。本 worker 无 shell，未能亲自运行（见"未覆盖面"）。

### 4. 签收不受表更新影响 — PASS（静态复核；dry-run 未由本 worker 执行）

`rows_sha256`/`counted_rows` 是纯档案口径，授权表不进签名：

- sha 输入 `_ROW_FIELDS`（`decide_signoff.py:105-115`）= `seq/dp/available/acted/mode/escalated_reason/transport/model/confidence_source/ts` — 全部档案行字段；表仅在 `_p0_open`（`:268-284`）被读，其结果进 facts/state 但**不进** sha256。
- `collect` 只统计该 key 的 `kind=="decide"` 行，且排除 dp25 自身的行（`:298-306`，D-067：签收不能自证）。
- done 门禁（`.agents/skills/agentic-task/scripts/advance_phase.py:271-330`）重跑 `collect(key_dir.parent, key_dir.name)` 后只比对 `rows_sha256` 与 `counted_rows`（continue 再跑 verdict），不读授权表。

对既有 key `mw-decision-substitution` 的静态重算：

- 档案中该 key 满足计数条件的行只有 seq 25（dp3，available）与 seq 26（dp1，available）→ `counted_rows = 2`，与 `.agenticdoc/mw-decision-substitution/evidence/review/sign-final.md` 的 `counted_rows: 2`、按 dp 计数表（dp1×1 + dp3×1）、引擎表（true-engine×2）全部相符；档案 append-only，这两行未变 → sha 输入未变。
- 表更新引入的 `authority-change` 行（seq 1-24、39）`kind != "decide"` 不计数；表更新后新增的 dp25 decide 行（seq 34/40）被 `dp != SIGNOFF_DP_ID` 过滤；settle 行（seq 27-31）`kind != "decide"` 不计数 — 三类后续追加都不动 `rows_sha256`。
- 签收文件仍在且未过期：`conclusion: narrow`、`rows_sha256: eb447f1d44f68560…`、`signed_via: auto-decide`（ts 2026-10-21T15:40:33Z，晚于首次建表 03:39:33Z）。与 `pm-state.md:21` 的 dry-run 记录（2 rows、sha 与既有签收一致）相符。本 worker 未能亲自执行 dry-run（见"未覆盖面"）。

### 5. 文档一致性 — PASS（3 条 MINOR，均不影响行为）

一致的部分：

- `docs/decision-points.md:21`：授权来源一节明确"人写，机器禁写；唯一例外 `mw decide dp refresh` — 注册表→表单向合并，只补缺失行、永不改已有 `enabled`/`mode`"，并注明 dp25 例外 P2 默认开 — 与 `_dp_refresh` 实现和守卫新口径一致。
- `docs/decision-points.md:200,202,204-206`：dp25 行规格（P2/true/auto/wired）与"对任意 key 通用 + 已落表 source=config + 调用形式"段 — 与注册表/表/CLI 一致。
- `.agenticdoc/mw-decision-substitution/flowcharts.md:246` §2.7 标题 `签收链路（mw decide sign --key <任意 key>，W9/W11）`；`flowcharts.html:113,482` 同步（标题与锚点一致）。
- `packages/coding-agent/CHANGELOG.md:7`（refresh 放行 + `on|off|set|apply` 仍拦，mw-signoff-per-key）与 `packages/multi-workers/CHANGELOG.md` [Unreleased] 首条（任意 key 通用、key 由调用方携带、落表 source=config）— 与实际行为一致。

"文档说 A、代码做 B"的点（详见"发现" MINOR-1/2/3）：

- `decide_signoff.py:93-95` 注释仍称 dp25 "P1 … executor unwired"，实际 P2 + wired 回显 executor。
- `docs/decision-points.md:150-157` 必填字段表仍写"只有 3 个 dp"，实际 `REQUIRED_STATE_FIELDS` 有 4 条（含 dp25），且同文件 `:308` 已正确写 4 条 — 文档内部自相矛盾。
- `.mw/decide-points.json` 头部 `updated_at: 2026-10-21T03:39:33Z` 落后于 dp25 行实际追加时间（档案 seq 39，16:22:39Z）：`_dp_refresh` 只更新 `updated_by` 不更新 `updated_at`。

### 6. 测试充分性 — PASS（静态推演；未做变异验证）

三个回归场景都会红（判断，未实际改代码）：

1. **dp25 改回 P1**：`test_decide_sign_auto.py:594-613` `test_dp25_is_registered_with_the_contracted_shape` 直接断言 `point.tier == "P2"`（:598）、`default_enabled is True`、`REQUIRED_STATE_FIELDS` 五元组、executor `wired` → 红；`test_dp25_is_on_by_default_and_the_default_signoff_path_asks_jev`（:619-641）断言无表行时 `effective.enabled is True` 且 jev 被问 → P1 默认关，红；另外既有表行 `{tier: P2}` 会触发 L7 tier-drift → `dp check` 非零，`test_decide_dp_cli.py` 的 refreshed-table-clean 检查也红。
2. **refresh 放回 TABLE_WRITE_CLI_RE**：`decision-signoff.test.ts:237-238` 两条 allowed 断言（`refresh` 的两种拼写不得拒）→ 红；blocked 清单（:217-220）同时保证 `on|off|set|apply` 反向不放松。
3. **collect 的 key 过滤去掉**：`test_decide_sign_auto.py:663` `len(facts.rows) == 1`（档案里有 other + 夹具两行真引擎行）→ 红；`:677` 签收文件 `counted_rows == "1"` 机器行断言 → 红；`facts.key == other`（:659）与 `state["key"] == other`（:666）也会红。

覆盖面之外的既有锁定也在线：refresh 保留已有行/幂等零写入（`test_decide_dp_cli.py:453-507`）、无表行时 P2 默认开（`test_decide_sign_auto.py:619-641`）、answer 路径不执行 executor 且回显 executor 不落盘（`test_decide_sign_auto.py:686 起`）。结论：新增/既有用例对卡片点名的三类回归均有直接杀伤力。

## 发现

### BLOCKER

无。

### MAJOR

无。

### MINOR

1. **陈旧注释（文档说 A、代码做 B）**：`packages/multi-workers/decide_signoff.py:93-95` 对 `SIGNOFF_DP_ID` 的说明仍是 "P1, default_mode=auto, executor unwired"，而 dp25 实际注册为 P2（`decision_points.py:828`）且 executor 是 wired 的回显执行器（`:853`；`test_decide_sign_auto.py:603-604` 锁定 `_executor_kind == "wired"`）。行为无影响，但注释会误导后来者；同模块其余文案（模块 docstring、CHANGELOG、docs）均已按 P2 描述。
2. **陈旧文档表**：`docs/decision-points.md:150-157` "每个 dp 有固定格式吗"仍写"只有 3 个 dp 有强制的必填字段"并列 dp1/dp2/dp3 + "其余 21 个（无）"；实际 `REQUIRED_STATE_FIELDS` 有 4 条（`decision_points.py:1184-1191`，含 dp25 的 `key/rows_total/rows_available/chain_ok/p0_open`），且同文件 `:308` 已正确写"dp1/dp2/dp3/dp25"。文档内部前后矛盾，漏的是 dp25 行（疑似 dp25 补 REQUIRED_STATE_FIELDS 的上一 key 未回填此表）。
3. **表头时间戳失真（含既有模式）**：`_dp_refresh` 只把 `updated_by` 置 `"refresh"`（`mw.py:2233`），不更新 `updated_at`；`dp set/on/off` 同样不更新（全文件仅 `_dp_new_table` `mw.py:1767` 与 `dp apply` `mw.py:3087` 写 `updated_at`）。因此 `.mw/decide-points.json` 头部仍是首次建表时间 `2026-10-21T03:39:33Z`，而 dp25 行实际 16:22:39Z 追加（档案 `decisions.jsonl` seq 39 的 `authority-change` 行带真实时间与 `config_sha_after`）。审计不受损（权威轨迹在档案行），且无任何门禁消费 `updated_at`，但该字段语义（"最后更新时间"）对 refresh/set/on/off 均失真。

三条 MINOR 均不阻塞本 key 结案。建议后续顺手修：MINOR-1/2 改文案；MINOR-3 让 `_dp_refresh`/`_dp_set` 补写 `updated_at`（或在 docs 注明该字段只反映建表/apply 时间）。

## 未覆盖面

- **保留卡片"未覆盖面声明"原文**：不做真实 jev 联网调用（本 key 无档案行，签收由 PM 单独做）；不重建 `dist/**`、不跑 `npm run build`、不跑 `npm run check`（会碰他人未提交文件）；不改任何源码/测试/配置；只读 + 写自己的工作目录与本 QG 报告。
- **本 worker 会话无 shell/bash 工具**（工具面仅 read/find/grep/ls/worker_file）：卡片要求"自己跑一遍"的 `dp check`/`dp list`/`dp show`、`mw decide sign --key mw-decision-substitution --project . --dry-run`、受影响 pytest/vitest 套件、`gen_decide_registry_ts.py --check` 均未由本 worker 执行。第 3、4 条判定改为源码静态复核 + 表/档案逐行比对，并与 `pm-state.md:13-21` 的 PM 执行台账交叉核对（记录值与静态推论一致），但这不构成独立执行验证。
- **未做变异验证**：第 6 条三个回归场景为读断言反推的静态推演，没有改临时副本跑红/绿。
- **`_row_matches_key` 的 `decision_id` 后缀兜底**（老格式行无 key 列时按 `:<key>` 后缀匹配）的边界情形（如 trigger 含冒号造成伪后缀）未深入审计；该规则非本 key 引入，带 key 列的现代行不走该分支。
- **运行期 bundle**：`dist/**` 与 src 的同步状态未审计（已知遗留：guard 放行与 dp25 新文案需 rebuild + reload 才在 pi 会话内生效；命令行 `python mw.py …` 路径不受影响）。
- **档案 hash 链**：每一环 `prev_sha` 数值未逐行重算（需执行环境）；仅核验 seq 1..41 连续、签收时 `chain_ok: true`、后续均为 decide_archive 正常追加的行类（decide/settle/authority-change）。
