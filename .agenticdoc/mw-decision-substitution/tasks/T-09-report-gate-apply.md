# T-09 报告生成 + 签收门禁 + `dp apply` + 写守卫

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-008/009/010）+ design.md D-014、D-015、D-016、D-020 + plan.md §1

## 上下文

- 门禁引擎：`.agents/skills/agentic-task/core/scripts/advance_phase.py`（`GATES:69-95`、`check_gate:191-289`、`content_match:220-227`）。
- **已知陷阱**：`content_match` 对含 `*` 的路径恒 False（`is_file()`），故签收文件固定名 `sign-final.md`。
- `dp apply` 在 `PI_CODING_AGENT`/`AI_AGENT`/`PI_WORKER_TASK` 存在时 exit 2（`packages/coding-agent/src/cli.ts:21-22`、`launcher.py:693`）。
- 写守卫按 `xkey-gate-guard.ts` 模式（`tool_call` 全模式注册；fragment 匹配 `:133-155`；写动词正则族 `:170-186`）。

## 要求

1. 报告生成器：读 `decisions.jsonl` → `fold` → 生成 `evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`（概览/判据表/逐决策/分歧样例/`suggest:` 一行/无法关联项）；`N<5` 强制写"数据不足，不结论"。
2. 挂点：`advance_phase.py` 推进成功后检查"上一 phase 无报告"则生成（纯读触发，不阻塞推进）。
3. `GATES["done"]` 追加两条现成规则（`sign-final.md` + `glob_has_files`；`content_match` 正则），并在框架分发副本同步同一改动。
4. `mw decide dp apply <sign-file>`：全量校验（缺 conclusion / 错 dp id / P0 漏列 → exit 2）→ 单锁内原子写配置 → 追加 `kind=authority-change` 行。
5. 写守卫：`tool_call` 钩子拒绝 agent 写 `evidence/review/sign-final.md` 与 `.mw/decide-points.json`（fragment 匹配，含反斜杠/相对路径；bash 文本级 fail-closed）。
6. 测试：`test/suite/decision-signoff.test.ts`（守卫拦截）+ `packages/multi-workers/test_decide_report.py`（报告生成/数据不足规则）。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `.agents/skills/agentic-task/core/scripts/advance_phase.py:69-95`
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/xkey-gate-guard.ts:133-155`

## 写入允许面

- `packages/multi-workers/mw.py`（仅 `dp apply` 与报告生成 CLI 段）
- `packages/coding-agent/src/extensions/agent-team-loop/xkey-gate-guard.ts`
- `.agents/skills/agentic-task/core/scripts/advance_phase.py`（仅 GATES 追加与报告挂点）
- `packages/multi-workers/test_decide_report.py`（新建）
- `packages/coding-agent/test/suite/decision-signoff.test.ts`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decide_report.py -q
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts
```

## 改动历史

- 2026-10-20 创建
