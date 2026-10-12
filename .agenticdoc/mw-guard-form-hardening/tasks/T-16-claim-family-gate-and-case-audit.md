# T-16 — claim/phase 命令族统一 gate + 大小写变体审计

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：`design.md` §4.4.5（key 身份定稿）；`spec.md` AC-006；`evidence/research/spec-key-identity-20261011.md`（A5/A6/A7 实测）
- 证据: `.agenticdoc/mw-guard-form-hardening/workers/mwgf-t15-python-claim/report.md`（T-15 已交付 claim 侧并登记本缺口）；`.agenticdoc/mw-guard-form-hardening/workers/mwgf-t09-key-identity/report.md`
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`；`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`；`.agents/skills/agentic-task/scripts/update_index.py`；`.agents/skills/agentic-task/scripts/test_update_index.py`；`packages/multi-workers/test_update_index_key_refusal.py`（仅追加）；外加自身目录 `report.md`
- 禁止: 运行 `npm run check` / 全量 vitest / 全量 pytest / `mw build`；修改 `worker/worker-mode.ts`、`pm/task-dispatcher.ts`、`autopilot/status-model.ts`、`shared/task-frontmatter.ts`、`shared/pm-state-claim.ts`、`spec.md`/`design.md`/`plan.md`/其他卡片；git 操作

## 背景（PM 实测，勿再声称未验证）

- T-15 已完成 Python claim 侧：`update_index.py` 有 14 名保留清单 + `normalize_key` + `key_name_refusal`（`:72-160`），`cmd_claim` 入口先过 gate（`:463-473`，拒绝即 rc=1 且零落盘）；新增 `packages/multi-workers/test_update_index_key_refusal.py`（66 条 golden 表，与真实 TS `keyNameRefusal` 经 node 逐条差分，node 缺失即 fail）；红→绿：实现前 `claim _tmp`/`_SCRATCH`/`_scratch`/`../x` 均 rc 0 并写行（`../x` 还逃出 `.agenticdoc`）、`claim _index.parallel` 抛未捕获 `FileExistsError`、`claim MW-KEY` 对存量 `mw-key` 追加重复行 ⇒ 9 failed / 3 passed ⇒ 现 12 passed。
- **缺口 1（T-15 按卡停下报告，成立）**：`caseVariantOf` 审计需要改 `index-store.ts` 的 `ClaimOutcome`（约 `:308-320`）与 `ui-bridge.ts` 的 `takeOverKey`（约 `:338-362`），而这两个文件在 T-15 卡的禁止面内。允许的 `pm-state-claim.ts` 只导出 `PmStateClaimSyncResult`/`syncPmStateClaimId`，加类型无 caller 不构成可观测审计。
- **缺口 2（T-15 登记）**：`update_index.py` 的 `set-phase` / `set-meta` / `release` / `get-claim` 仍用**精确匹配且不过 gate**（design §4.3 未点名它们）。

## 必须实现

1. **`caseVariantOf` 可观测审计**：在 `claim` 成功但存储中已存在**仅大小写不同**的 key 时产生可观测信号（`ClaimOutcome` 字段 + 调用点 `takeOverKey` 消费并落审计/告警；沿用既有审计风格，不新造通道）。语义**不得放宽**：保首写大小写、不迁移存量、不追加重复行。
2. **`update_index.py` 其余命令统一 gate**：`set-phase` / `set-meta` / `release` / `get-claim` 的 key 比较改为 `normalize_key`，并在会写入的命令（`set-phase`/`set-meta`/`release`）先过 `key_name_refusal`（拒绝即 rc=1、零落盘）；只读命令（`get-claim`）至少归一比较，行为与 TS 侧一致。
3. **两侧一致性测试扩充**：把 4 个命令的 key 形状/大小写/保留名场景加入 `test_update_index_key_refusal.py` 的 golden 表（同一 fixture 两侧逐条相等，node 缺失即 fail，不得 skip）；`test_update_index.py` 补对应回归。
4. **方向一致性**：同一 key 在 TS `claim`/`advance_phase` 与 Python 4 个命令上必须同结论（合法未占用 ⇒ 放行；保留名/非法形状/路径逃逸 ⇒ 拒绝；`_scratch` ⇒ guard 放行但不可 claim/advance）。
5. 先构造能失败的断言（红），再实现（绿），报告红→绿证据（含 `../x` 逃逸与 `MW-KEY` 重复行的前后对照）。
6. 不得回退 T-09/T-15 已交付的行为（14 名清单、读侧归一、`_index.md` 回退、无条件守卫的 3 个调用行、claim gate）；若发现必须改这些，**停下报告**。

## 验收命令（PM 执行）

- Python：`cd packages/multi-workers && python -X utf8 -m pytest test_update_index_key_refusal.py -q`；`cd .agents/skills/agentic-task/scripts && python -X utf8 -m pytest test_update_index.py -q`
- TS 回归：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts test/suite/worker-dispatch-guard.test.ts`

## 交付

`report.md`：改动文件清单（逐文件 + 符号名/行区间）、`caseVariantOf` 审计的可观测证据、4 个命令 gate 前后对照（含 `../x` 逃逸与 `MW-KEY` 重复行）、两侧一致性 fixture 行数、红→绿证据、未完成项与原因（若有）。
