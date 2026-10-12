# T-15 — Python claim 收窄 + 大小写变体审计（`update_index.py` / `caseVariantOf`）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：`design.md` §4.4.5（key 身份定稿：豁免 14 名显式清单、新 key 判据 `findByKey === undefined`、`advance_phase`/`claim`/`/pm-key new`/`update_index.py` **共用同一 `keyNameRefusal`**）；`spec.md` AC-006；`evidence/research/spec-key-identity-20261011.md`（A5/A6/A7 实测）
- 证据: `.agenticdoc/mw-guard-form-hardening/workers/mwgf-t09-key-identity/report.md`（T-09 已交付 TS 侧并登记本缺口）；`evidence/research/design-role-key-identity-20261011.md` §4/§5
- **唯一允许改的路径**: `.agents/skills/agentic-task/scripts/update_index.py`；`packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-claim.ts`（仅用于 `caseVariantOf` 审计，若该类型实际位于别处，先报告定位再改）；对应 Python 测试（若 `update_index.py` 无测试，新增 `packages/multi-workers/test_update_index_key_refusal.py` 或就近放在已有 Python 测试目录）；外加自身目录 `report.md`
- 禁止: 运行全量 pytest / 全量 vitest / `npm run check` / `mw build`；修改 `shared/index-store.ts`（T-09 已定稿）、`pm/ui-bridge.ts`（T-04/T-09 已定稿）、TS 三解析器文件（T-07 持有）；改 `spec.md`/`design.md`/`plan.md`/其他卡片；git 操作

## 背景（PM 实测，勿再声称未验证）

- T-09 已完成 TS 侧：`shared/index-store.ts:17-36` 的 `RESERVED_INDEX_NAMES` 恰 **14** 名（`_scratch`/`.mw`/`_index.parallel`/`_index.md`/`_workers.parallel`/`_workers.stale.parallel`/`_workers.acked`/`_autopilot`/`_project_log.md`/`_arch_snapshot.md`/`_pitfalls.md`/`.agenticdoc`/`_impl_gate.log`/`_incidents`）；`foreignLiveClaimRefusal` 在 `ui-bridge.ts` 定义于 `:277`，调用行恰 **3** 处（`:1908`（无条件守卫）/`:2335`/`:2437`）；读侧归一在 `index-store.ts:169/212/275`。PM 复跑 `worker-crosskey-readonly` + `worker-dispatch-guard` 无失败。
- **缺口 1**：`update_index.py`（21,904 B）既**不含** `keyNameRefusal` 也**不含**任何保留名/形状检查 ⇒ Python 侧 claim 入口仍是旧语义（`/pm-key new` 与 `update_index.py` 未共用同一拒绝判据，AC-006 未闭合）。
- **缺口 2**：`caseVariantOf` 在**全仓零命中**（PM 用 `rglob('*.ts')` 全量搜索）⇒ design §4.4.5 要求的大小写变体**审计**没有落地（只有读侧归一，没有「检测到大小写变体并记录」的可观测面）。

## 必须实现

1. **`update_index.py` 接入同一判据**：把 key 名合法性/保留名判断改为与 TS 侧**同语义**（14 名保留清单、形状规则、路径逃逸、空名——与 `keyNameRefusal` 的稳定码一一对应）。Python 与 TS 无法共享函数 ⇒ 允许**同语义副本 + 一致性测试**（参照 T-08 的 golden/node 反向差分范式：同一组 key 名 fixture，两侧判定必须逐条相等）。
2. **一致性测试**：新增 fixture（建议 `packages/multi-workers/` 下 JSON 或内联表）覆盖：14 个保留名逐一、合法未占用名、大小写变体名、前缀名、含路径分隔符/`..`、空串、超长名。两侧逐条比对，**node 缺失即 fail**（不得 skip）。
3. **`caseVariantOf` 审计**：在 `claim` 成功但存储中已存在**仅大小写不同**的 key 时，产生可观测审计（沿用既有 `ClaimOutcome`/审计字段风格；若该类型不在 `pm-state-claim.ts`，先报告实际位置），**语义不放宽**（仍保首写大小写、不迁移存量、不追加重复行）。
4. **方向一致性**：`update_index.py` 与 TS `claim`/`advance_phase` 对同一 key 必须给出**同一结论**（合法未占用 ⇒ 都放行；保留名 ⇒ 都拒绝；`_scratch` ⇒ 守卫放行但不可 claim/advance）。
5. 先构造能失败的断言（红：保留名/大小写变体在 Python 侧当前被放行），再实现（绿），报告红→绿证据。
6. 不得改 `index-store.ts`/`ui-bridge.ts` 的既有行为；若发现必须改，**停下报告**。

## 验收命令（PM 执行）

- Python：`cd packages/multi-workers && python -X utf8 -m pytest <新增/命中测试文件> -q`
- TS 回归：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts test/suite/worker-dispatch-guard.test.ts`

## 交付

`report.md`：改动文件清单（逐文件 + 函数/行区间）、14 名保留名两侧判定对照表、大小写变体场景前后对照、`caseVariantOf` 审计的可观测证据、红→绿证据、未完成项与原因（若有）。
