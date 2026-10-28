# T-W15 — 对抗性审计：G6 三条新 AC（AC-014/015/016）与部署宣告

- type: review
- key: mw-worktree-junction-guard
- 角色约束: 只读审计 + 只读命令复算；**不写**任何代码/夹具（writeless 角色）；禁破坏性 git/文件命令、禁 `npm install|ci`、禁跑 `mw build`/`mw start|stop`

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` 的 INV-1（含 reparse point 的 worktree 没有任何执行通道能连目标一起删）与 INV-4（同类事故可被机器发现）。G6 是本 key 的第三批交付（`spec.md` §2 G6、§7 D-13/D-14/D-15）。
- **前两次审计的方法边界**（你必须换一种方法，不要重复它们）：
  - `evidence/quality-gate-report-20261013.md`（QG）= **引用闭包**：逐条检查 AC 声明与证据坐标是否对得上，13/13 ✅。它**没有**做负空间枚举，也**没有**攻击结论本身。
  - `evidence/negative-space-audit-20261013.md`（W-12）= **负空间/危害面**：先做工件清单（该有而没有 / 有而无人引用）+ 29 条危害面三态，产出 N-01…N-06。
- **本卡的方法 = 对抗性（攻击者视角）**：默认"G6 的实现与被引用的证据链都可能是错的/可被绕过的"，目标是**证伪**下列 5 条结论，而不是复述它们。找不到反例时必须给出"我试了哪几条路径、为什么它们打不穿"。
- **被审对象（改后坐标，行号会漂，符号为准）**：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:217`（`pi.on("user_bash")`，与 `:202` 的 `pi.on("tool_call")` 并列，同在 `registerWorktreeJunctionGuard` 内）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:78`（`decideWorktreeRemove`）、`:291`（`decideDeletePenetration`）、`:453`（`expandToken`）、`:506`（`parseDeleteInvocation`）、`:539`（`notRemove`）、`:544`（`reparsePointVerdict`）
  - `packages/multi-workers/mw_common.py`：AC-015 消费（`_doctor_issues` 的 `registry_error` 块）+ AC-016 段（`ACTIVATION_MARKER`/`_activation_bundle_paths`/`_activation_scan`/`_doctor_activation`）+ `format_doctor_text` 的 `REGISTRY-ERROR`/`activation:` 行
  - `packages/multi-workers/worktree_doctor.py`（`registry_error` 镜像）
  - 证据：`evidence/T-W14-user-bash-guard-20261013.md`、`evidence/T-W13-doctor-visibility-activation-20261013.md`
  - 部署事实（PM 实测，可复算）：两份 `agent-team-loop.js` 各 **1,136,103 B**、`'reparse-point'`=1、`worktree`=25、`"user_bash"`=2

## 审计目标

1. **证伪 AC-014**：`user_bash` 挂钩是否**真的**零副作用拦截、且**不误拦**？具体攻击面：
   - 短路语义：返回 `{result: …}` 是否确实使命令体**不被 spawn**（去 `node_modules` 的 `dist` 里找真实消费者代码核验；注意区分"tool_call 的 `{block:true}` 语义"与"user_bash 的 `{result}` 语义"，前者用在后者上会怎样？）——**这是本卡最想被证伪的一条**。
   - 覆盖缺口：多段/换行/管道/分号拼接、`--force` 变体位置、`-C`/`cd`/`Set-Location` 基准、插值变量、`git -c`/`--git-dir`、大小写与 PowerShell 别名（`ri`/`rm -r -fo`）、多目标 `git worktree rm a b`、`&&`/`;` 续行。逐条给"拦/放"结论并标注哪些**必须**拦（否则 INV-1 在那条通道上仍不成立）。
   - 反向：干净命令是否可能被误拦（尤其 `event.cwd` 语义与 bash 工具不同时）。
2. **证伪 AC-015**：`registry_error` 的消费与文本行是否**只在坏文件时**出现、且**一定**影响 rc？攻击面：空文件/只有空白/JSON 合法但结构错（顶层是数组、缺 `entries`）/权限不可读/路径是目录/符号链接指向目录。逐条给"issue+rc / 静默"实测结论；找出**任何一种坏文件形态仍然静默**的情形，那就是 AC-015 未达成。
3. **证伪 AC-016**：激活自检是否可能**假绿**与**假红**？
   - 假红：非本仓项目会不会被误报；bundle 路径判断（`global_ext_dir()` 受 `PI_CODING_AGENT_DIR` 影响）在"用户自定义扩展目录"时是否稳定；
   - 假绿（更重要）：标记 `reparse-point` 是否可能**在能力缺失的情况下仍然出现**（它是否只是字符串字面量而可能与能力解耦？例如标记出现在某个未被调用的分支、或某天有人保留字符串却删掉判定逻辑）？若存在这种解耦路径，AC-016 的"能力在"判据就只是"字符串在"，请给反例或明确说"找不到"。
   - `has_marker=None`（不可读）是否可能被当作"OK"从而假绿（读 `_doctor_issues`/`format_doctor_text` 的三态处理 + 测试断言）。
4. **证伪部署宣告**：`mw doctor` 在 bundle 部署后 `guard-not-deployed` 归零，被你接受为"G1+AC-014 已进入 pi 实际加载的产物"。请独立核验：① 两份 bundle 的字节与计数；② **全局**那份是否就是 pi 运行时会加载的那份（查 pi 的扩展发现路径与优先级，注意 `packages/coding-agent/dist` 与 `~/.pi/agent/extensions/` 的关系）；③ 有没有第三个位置（其它 profile/目录）也会被加载而未被检查。
5. **复核证据可信度（不是重跑）**：读 `evidence/T-W13-*.md` 与 `evidence/T-W14-*.md`，逐条判定"该断言是否可能假绿"：测试用的是真链路还是自证（`emitUserBash` 是真实 runner 路径吗？断言的是"执行记录为空"还是只断言返回值？阴性对照是否真的非空转）。列出你认为**证据强度不足**的具体断言。

## 要求

- 只用只读命令复算（`git grep --untracked`、`read`、python 只读脚本、`node -e` 只读读取、跑既有测试文件）；**不新建夹具、不写文件**（writeless）。允许运行既有测试（`vitest --run <具体文件>`、`python -m pytest <具体文件>`）——跑测试会产生 pytest 缓存等副作用，若你判断不允许，则改为纯读码并如实声明。
- 每条结论给 `file:line` 或命令原文 + 实测输出片段；找不到反例要写"试了 N 条路径，均被拦，理由 X"。
- **禁止**把"我没找到反例"写成"不存在反例"；禁止复述前两次审计的结论当自己的结论。

## 交付格式

- 唯一产物：**本任务目录**内的 `report-delta-adversarial-audit-20261013.md`（PM 会原样提升到 `.agenticdoc/mw-worktree-junction-guard/evidence/`）。
- 报告结构：`## 结论`（逐条：AC-014/AC-015/AC-016/部署宣告/证据可信度 → 站稳 / 有裂缝 / 被证伪，各附最强反例或最强攻击尝试）、`## 证据`、`## 未覆盖面声明`（**必须**分列两层：① 工具边界：writeless 不建夹具、未做执行型反例；② 方法边界：本审计只做对抗性证伪，未做全量危害面清单与引用闭包逐条核对）、`## 上下文来源`。
- 末行固定格式：`ADVERSARIAL: AC-014=<站稳|有裂缝|被证伪> AC-015=… AC-016=… 部署=… 证据强度不足=N 条 | 攻击尝试=N 条`.

## 写入允许面

- 仅 `.agenticdoc/mw-worktree-junction-guard/workers/wjg-w15-delta-adversarial/report-delta-adversarial-audit-20261013.md` 与同目录 `progress.md`。

## 写入禁止面

- 一切源码、测试、证据、`spec.md`/`design.md`/`achieved.md`、其它 worker 目录、`%TEMP%` 夹具、任何 `.agenticdoc/_*` 台账。
- 禁 `mw build`/`mw start|stop`/`npm install|ci`/`git worktree *`/`rm`。

## 验收命令（只读）

```
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts
cd ../multi-workers
python -m pytest test_doctor_activation.py -q
python mw.py doctor --project H:/git/Multi-Workers
```

## 改动历史

报告内逐条列 `file:line`（你引用/复算的坐标）+ 你实际执行过的命令清单（含未产出结论的尝试）。
