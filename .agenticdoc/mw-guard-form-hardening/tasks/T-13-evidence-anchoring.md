# T-13 — 证据锚定与收口

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §`spec.md` AC-011｜`design.md` §4.1（落点表）+ §4.6（残余）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-011 + 下列证据文件
- 证据: 本 key 全部 `evidence/research/*` + `spec.md` AC-011 + `design.md` §4.1/§4.6（收口卡，PM 可直执或派 worker）
- **唯一允许改的路径**: `achieved.md`（尚未创建）；`evidence/runs/*`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-011｜VC: VC-038｜波 6｜链 S5
- 验收命令（PM 执行）: （无单测）证据核对脚本 + PM 复算；随后进入 verify 阶段派 2 张 QG 卡

## 必须实现
1. 逐条核对 spec 的 11 条 AC 与本 key 全部证据引用：每条引用的 `文件:行号` 必须在**最终工作树**可命中（`unanchored_refs == 0`），行号漂移须写勘误而非静默改数。
2. 汇总达成状态表：`AC-NNN → PASS/PARTIAL/FAIL + 实测证据路径 + 前值/后值`；PARTIAL 必须写残余去向。
3. 产出 `evidence/runs/summary-20261011.md`（验收命令与原始输出摘录）。
4. 不得修改 `spec.md` 的 AC 编号与文本（勘误只增不改，按 AC Lock 协议）。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。


## 追加（PM，23:55）：`update_index.py` 副本拓扑核实

T-15/T-16 只修了权威副本 `.agents/skills/agentic-task/scripts/update_index.py`（现有 `key_name_refusal` + `_key_name_error`，5 处 gate 调用）。PM 实测仓内另有 **5 份**副本，**全部无 gate**：

| 副本 | 字节 | 有 gate |
|---|---|---|
| `packages/multi-workers/.tmp/agentic-task/scripts/update_index.py` | 21,820 | 否 |
| `packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py` | 21,820 | 否 |
| `.claude/scripts/update_index.py` | 22,026 | 否 |
| `.agents/skills/agentic-task/core/scripts/update_index.py` | 22,492 | 否 |
| `.agents/skills/agentic-task/claude/scripts/update_index.py` | 22,492 | 否 |

**必须查清并写入报告**（本卡只做核实与登记，**不改这些副本**）：① 它们各自是**生成物**（有生成脚本/sync 脚本？）还是手工维护；② 运行时**实际被调用的是哪一份**（追 `mw.py`/`launcher.py`/skill 安装路径/`install.sh` 等调用链，给出文件:行）；③ 是否随安装或 npm 打包分发到用户环境（若是 ⇒ CLAUDE/其他 harness 用户仍会绕过 gate）；④ 结论与影响面写入 `achieved.md` 遗留账本（C-9 的处置）。若发现**活动副本未覆盖**，明确写「需后续 key」，不要在本 key 内扩面修改。


## 追加（PM，00:05）：`dist` 与 `src` 漂移核实（C-12，收口必办）

PM 实测 `git status` 显示 `packages/coding-agent/dist/extensions/agent-team-loop/**`（`ui-bridge.js`、`worker-mode.js`、`index-store.js` 等**被跟踪的构建产物**）**早于本 key 的全部源码改动**（T-04/T-07/T-09/T-16 都只改了 `src/**` 与测试）。后果：`mw serve` 装载的扩展仍是**旧守卫**（fail-open 判据未生效）。

**本卡必须完成**：① 列出 `dist` 与 `src` 的漂移范围与判据（至少：`ui-bridge`/`worker-mode`/`index-store`/`task-frontmatter` 在 `dist` 中是否存在、是否含新符号如 `judgeWriteTarget`、`readTaskType`、`RESERVED_INDEX_NAMES`、`caseVariantOf`）；② 明确「重建并安装」所需的命令与影响面（`npm run build` 等）；③ 把①②写入 `report.md` 与 `achieved.md` 遗留账本，并**明确标注：重建/安装需用户授权，PM 不得自行执行**。**不要**在本卡内执行构建命令。


## 追加（PM，00:20）：`[WRITE_SURFACE]` 审计行的端到端 emit 覆盖

T-12 补了消费端（`worker-mode.ts` 新增 `writeSurfaceMarkerState()` 整行匹配 `absent/ok/malformed` + 启动期对 `malformed` 落 1 条 `[WRITE_SURFACE]` trace 审计行，**审计-only、零 verdict 变化**），但**端到端 emit 无测试覆盖**（其卡白名单未含测试文件）。

**本卡补 1 正 1 反**：① 正例 = 合法 marker ⇒ 无 `[WRITE_SURFACE]` 审计行（或与 `absent` 可区分）；② 反例 = 悬空/重复/倒序 marker ⇒ 恰 1 条审计行且含可断言字段。断言要**等值**（精确计数，不用 `> 0`）；语料条目总数仍在增长 ⇒ 不得用计数上限断言。若测试文件在本卡写入面之外，**停下报告**并把该项列入「未覆盖」清单（不要扩面改卡外文件）。
