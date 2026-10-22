- type: coding
- key: mw-decision-substitution
- 目标锚点: `.agenticdoc/goal.md`（项目级目标：jev 替换中低风险决策，PM 并行管理 worker）；本卡对应其中"je**v 作为决策模型**"的可配置化与可审计化
- 上游: `spec.md` §14 AC-016、AC-020（per-dp 旋钮部分）、`design.md` §8 D-048..D-051、`decide_registry.json`（24 dp，schema 2）

## 上下文

阈值今天写死在 TS：`worker-mode.ts:4434 DP3_MIN_MATCH_SCORE=0.75`、`:4440 DP3_MIN_CONFIDENCE=0.7`、`:4444 DP3_ANSWERABLE_MIN=0.5`；dp2 的分拆门在 `pm-orchestrator.ts:2602` 一段（风险门 `risk=mid|high`）。per-dp 配置表 `.mw/decide-points.json` 的行 schema 在 `decision_points.py`（`_DP_ROW_KEYS` 附近）与 `mw.py:1482 _DP_ROW_KEYS` / `:1475 _DP_SET_SPEC`；TS 侧读同一文件的解析在 `pm/ui-bridge.ts`（`enabled`/`mode`）与 `worker-mode.ts` 的 dp3 settle 分支。用户裁定 A：只做 `min_confidence`/`max_questions`/`timeout_s` 三项，不做 per-dp `model`/`transport`。

## 要求

1) Python：`.mw/decide-points.json` 行接受 `min_confidence`（0..1 float）、`max_questions`（1..8 int）、`timeout_s`（1..300 int）三键；新增 `resolve_policy(dp_id, row, decide_cfg) -> {min_confidence, max_questions, timeout_s}`，顺序 per-dp > `.mw/decide.json` > 内置常量（dp1/dp2/dp3 的 0.7、全局 8、全局 20），非法值 fail-soft 回落 + 记 warning（复用现有 `issues`/warnings 机制，不要新抛异常）。
2) `mw decide dp check` 与 `mw decide dp show` 打印每行**生效值**（原始值非法时标注 fallback 原因）。
3) TS：新增 `resolveDecidePolicy(dpId, projectDir)`（放在 `pm/decision-tool.ts` 或 `shared/`，你选一处并说明理由），把 `worker-mode.ts:4434/4440/4444` 的常量与 dp2 门改为读生效值；不改判定结构与分支顺序（D-050）。
4) 档案：`decision_points.append_decide`/`decide_for` 的 `decide` 行新增 `policy` 字段（三个生效值），`_CHANGE_BY`/现有列不动；`mw decide show --json` 也带出 policy。
5) 测试：Python 新增 `test_decide_policy.py`（≥12 例：缺省、三层覆盖、越界回落、坏类型、dp show 生效值、档案回显、`decide-points.json` 行未知键仍被拒）；TS 在 `test/suite/dp3-answer.test.ts` 与 `dp2-narrow.test.ts` 各加 1-2 例（per-dp 阈值改变 acted/escalate 结果），并用一份共享 fixture 做 Python↔TS parity（同一配置 → 同一生效值）。
6) README（`packages/multi-workers/README.md` 的 dp 指令段）加三个键与 `dp check` 说明。

## 写入允许面

- packages/multi-workers/decision_points.py
- packages/multi-workers/mw.py
- packages/multi-workers/test_decide_policy.py
- packages/multi-workers/test_decide_dp_cli.py
- packages/multi-workers/README.md
- packages/coding-agent/src/extensions/agent-team-loop/shared/decide-policy.ts
- packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
- packages/coding-agent/test/suite/dp3-answer.test.ts
- packages/coding-agent/test/suite/dp2-narrow.test.ts

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（本卡不碰，W6/W7 也不会同时写）
- `packages/multi-workers/mw.py`（仅 W5-1 / W7 卡可写，见各卡；本卡按下面允许面执行）
- `.mw/decide-points.json`、`.mw/decide.json`（**运行时用户配置，严禁改**；测试只能写 tmp 目录）
- `.agenticdoc/**`（除你自己的 `workers/<task_key>/` 输出目录）、`docs/**`、`packages/ai/**`
- `decision.py`（W1 已定稿，本卡只读；需要改算法请在报告里提，不要动）
- git 写操作、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络调用（`--live`/`decide run`/`decide ask`）一律禁止

## 运行约束（上一轮 OOM 教训）

- **禁止整文件读大文件**：`mw.py` 超过 10000 行、`worker-mode.ts` 超过 5000 行。每次 read 只用 `offset`/`limit`，单次 ≤ 120 行，围绕卡片给的锚点。
- 单个命令的 stdout ≤ 30 行；长输出先落盘到 `workers/<task_key>/` 下再 `read` 尾部。
- write-first：先写实现，再跑验收；不要反复全量扫描仓库（`rg` 必须带 `-g` 限定目录）。
- 单次会话保持在 500 次工具调用内；超过 300 次仍未完成时，先在 `report.md` 写下当前进度与残留，再收尾。

## 验收命令

cd packages/multi-workers
python -m pytest -q test_decide_policy.py test_decision_points.py test_decide_dp_cli.py test_decide.py
python mw.py decide dp check --project H:/git/Multi-Workers
python mw.py decide dp show dp3-worker-clarify --project H:/git/Multi-Workers
cd ../coding-agent
npx tsgo --noEmit
npx vitest --run test/suite/dp3-answer.test.ts test/suite/dp2-narrow.test.ts

## 交付格式

`report.md` 五节：结论（含每项验收的命令原文与结果）/ 证据（文件:行）/ 残留与未验证 / 上下文来源（必须写 goal.md 的 mtime 与你读过的 `path:line`）/ 改动清单。每条验收命令必须贴 stdout 原文（≤30 行/条），不许写"已验证"。

## 改动历史

- 2026-10-21 创建（PM，用户裁定 A + 三条新需求）

