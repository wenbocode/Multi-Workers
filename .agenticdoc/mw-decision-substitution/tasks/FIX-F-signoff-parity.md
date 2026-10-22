# FIX-F：签收守卫两通道落位对齐 + doc §3 采纳条件补全（QG-2B 残留 4/5）

- type: coding
- owner key: mw-decision-substitution
- 来源：`evidence/quality-gate-report-20261020b.md`「残留与未验证」第 4、5 条（一轮 6 条发现已全关闭，本卡只收这两条措辞/对称性残留）
- 规模：两处小改 + 2 个用例。

## 背景

`shared/xkey-gate-guard.ts` 里有两个判定函数，各自覆盖的落位不一致：

- `isDecisionSignoffEvidenceTarget`（`worker_file` 通道，`:373`）按「首个 `evidence` 段 + 其后只有 `[]` 或 `["review"]`」判定，覆盖两个落位；
- `isDecisionSignoffPath`（write、edit、bash 三通道，`:353`）只做 `DECISION_SIGNOFF_FRAGMENT`（`evidence/review/sign-final.md`）后缀匹配，
  **不覆盖 evidence 根落位** `evidence/sign-final.md`。

结论：写通道存在纵深远近不对称——同一个固定文件名，`worker_file` 会拒、`write` 会放行。
done 门禁只读 review 落位，所以**不存在门禁绕过**，但两个通道对同一路径给出相反判定是自相矛盾的守卫。

## 改动 1：让 `isDecisionSignoffPath` 复用落位判定

把 `isDecisionSignoffPath` 改成：先判 `.mw/decide-points.json`（`DECISION_POINTS_FRAGMENT` 后缀）与已有的
`DECISION_SIGNOFF_FRAGMENT` 后缀，**再**对 basename 为 `sign-final.md` 的路径委派给
`isDecisionSignoffEvidenceTarget(rawPath)`，由同一份落位规则（首个 `evidence` 段 + 其后 `[]` 或 `["review"]`）裁决。

这样：

- `<key>/evidence/sign-final.md` → write、edit、bash、`worker_file` **四通道一致拒**；
- `<key>/evidence/review/sign-final.md` → 四通道一致拒；
- `<key>/evidence/research/sign-final.md` → 放行（tail 长度 1 但不是 `review`）；
- `<key>/evidence/research/evidence/sign-final.md` → **放行**（FIX-E 刚修的误拒，不能再被这次改动带回来）；
- `.mw/decide-points.json` 的判定保持原样。

注意顺序：不要用「以 `evidence/sign-final.md` 结尾」这种后缀规则，它会把
`evidence/research/evidence/sign-final.md` 又误判回拒（这正是 FIX-E 修的那条），必须走段位判定。

同时在 `DECISION_SIGNOFF_FRAGMENT` 附近的注释里写明「write/edit/bash 与 worker_file 共用同一落位判定，
两落位一致拒」，避免下次再分叉。

## 改动 2：doc §3 的 dp1 采纳条件补全

`docs/decision-substitution.md` 讲 dp1 时现在写的是「`mode=auto` 且带 `decision_id` 才算采纳」，
这只写了必要条件。补上充分条件里的分歧闸：**建议类型必须等于实际派发类型**（`triage_type === 实际 type`）；
不一致时即使 `auto` 也不采纳、不写 `decision:` 头行（QG MINOR-1 的修复点，`pm/ui-bridge.ts:282`）。

一行话，写清「必要不充分」，并指向 `ui-bridge.ts` 的分歧闸。

## 必做用例

`packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts` 追加一例（或并入已有 describe）：

1. `write`、`edit`、`bash` 三通道对 `<key>/evidence/sign-final.md` → 拒（bash 用一条重定向写法即可）；
2. 同一批通道对 `<key>/evidence/research/evidence/sign-final.md` → 放行（回归 FIX-E）；
3. `<key>/evidence/research/sign-final.md` → 放行。

`packages/coding-agent/test/suite/decision-signoff.test.ts` 现有用例不得减少（现 11 例）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`
- `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`
- `packages/coding-agent/test/suite/decision-signoff.test.ts`
- `docs/decision-substitution.md`
- `packages/coding-agent/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/**` 一切文件
- `pm/decision-tool.ts`、`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`pm/triage-client.ts`、`worker/worker-mode.ts`
- `spec.md`、`design.md`、`plan.md`、`pm-state.md`、`achieved.md`、`tasks/**`
- `.agenticdoc/**` 下除上述四个测试/文档路径与 CHANGELOG 之外的任何路径
- 禁止 `git` 任何写操作；禁止 `npm run check`（含 `biome check --write .`）；禁止全量 pytest、禁止全量 test.sh
- 禁止 `Set-Content`（会经 cp936 往返丢字节），一律用 `edit` 或 `write` 工具

## 验收命令

```bash
npx tsgo --noEmit
node ../../node_modules/vitest/dist/cli.js --run test/suite/xkey-gate-guard-coverage.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-tool.test.ts
npx biome check src/extensions/agent-team-loop/shared/xkey-gate-guard.ts test/suite/xkey-gate-guard-coverage.test.ts test/suite/decision-signoff.test.ts
```

例数只许增：`xkey-gate-guard-coverage` 现 12、`decision-signoff` 现 11、`decision-tool` 现 23。
`npx tsgo --noEmit` 必须 rc=0。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待改点 1：`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:353`（`isDecisionSignoffPath`）、`:373`（`isDecisionSignoffEvidenceTarget`）、`:335`（`DECISION_SIGNOFF_FRAGMENT`）
- 待改点 2：`docs/decision-substitution.md` 讲 dp1 采纳条件的那一段（搜 `decision_id` 与 `auto`）
- 契约：`design.md` 的 D-014（固定名）、D-015（写守卫）、D-012（`decision:` 仅 acted=true）
- 分歧闸实现：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:282`
- 用例参照：`test/suite/xkey-gate-guard-coverage.test.ts:391`（FIX-E 的深路径放行例）、
  `test/suite/decision-signoff.test.ts`（两落位拒绝例）
- 上一轮证据：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020b.md`

## 上下文纪律

单文件读取一律带 offset / limit，单次 ≤ 200 行；`xkey-gate-guard.ts` 约 500 行，只读点名行段。

## 改动历史

- 2026-10-20 建卡：来自 `ds-qg-review-2` 的残留 4/5（写通道落位不对称、doc §3 采纳条件表述不完整）。
