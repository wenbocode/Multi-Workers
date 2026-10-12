# T-18 — QG-B2 两条窄口径阻断修复 + `.exe` 包装器漏放实测

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：本卡 + `.agenticdoc/mw-guard-form-hardening/workers/mwgf-qgb2-evidence-recheck/report.md`（QG-B2 复审，FAIL，2 条阻断 + 1 条过程发现）+ `design.md` §4.6/§6
- **唯一允许改的路径**：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅当 A 段实测确认**）
  - `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`、`test/suite/worker-dispatch-guard.test.ts`、`test/extensions/agent-team-loop.test.ts`（**仅新增用例与 VC 标签**）
  - 自身 `report.md`
- **禁止**：改 `.agenticdoc/**` 的任何相位文档（`spec.md`/`design.md`/`plan.md`/`pm-state.md` 由 PM 负责——B-2' 的文档同步是 PM 的事，不是你的）；运行全量 vitest / 全量 pytest / `npm run check` / `npm run build`；改 `pm/ui-bridge.ts`、`shared/index-store.ts`、`shared/task-frontmatter.ts`、`pm/pm-orchestrator.ts`、`pm/task-dispatcher.ts`、`autopilot/status-model.ts`；git 操作

## A. `.exe` 包装器与 PowerShell 调用形态（**先实测再改码**）

QG-B2 报告（含原始输出）：在**当前源码**下，下列形态提取到的**候选数为 0** ⇒ 若真，属**漏放**（fail-open 旁路），因为它们确实会写入文件：
- `bash.exe -c "printf x > out.txt"`（以及 `cmd.exe /c …`、`powershell.exe -Command …`）
- PowerShell：`& "C:\…\bash.exe" -c "printf x > out.txt"`

**要求**：① 用真实提取器实测上述形态（给出 verdict/候选/rule 原始输出）；② 与对照比较（`bash -c "…"` 无 `.exe`、裸 `printf x > out.txt`）；③ **若确认漏放** ⇒ 修（`.exe` 后缀视为同一包装器并复用现有 unwrap 逻辑，注意 `MAX_UNWRAP_DEPTH` 语义），补 1 正例 + 1 条「不得误拦」反例（例如 `ls -la foo.exe`、`grep x file.exe` 这类**非包装器**用法不得被当成写入），断言等值；④ **若实测不成立** ⇒ 给出反证输出，**不要改码**，在报告中明确否决该发现。

## B. 同族误拦（QG-B2 附带发现）

QG-B2 另报：运行期守卫会从写命令的**内容**中误提取目标并拦截（false block），并与本 key 各卡要求的 `.tmp/` 落盘点冲突。**要求**：造最小复现（例如命令字符串中出现的路径被当作目标），实测确认后修（内容不得成为目标来源），补反例；若不成立同样给反证。

## C. VC 标签唯一性（AC-011 子判据，阻断 ①）

QG-B2 判定：`design.md` §6 的 **VC-036/037/038/041 在载体中无 `VC-NNN` 标签**，且 `VC-NNN` 编号在本仓其他套件里**已被复用**（如 `test_advance_phase.py` 的 VC-001…036）⇒ 「每个 VC 有唯一可解析载体」不成立。

**要求**（只动测试文件，不动设计文档）：在承载这 4 条（以及你认为缺失的）VC 的**测试用例名或显著注释**中加上**带 key 命名空间的标签** `VC-MWGF-0NN`（保持与 design §6 编号的对应关系，写在用例名或紧邻注释里），使每个 VC 都能被 grep 唯一解析：`rg -n "VC-MWGF-0NN"` 必须命中且命中数可解释。报告给出「VC 编号 → 标签 → 载体文件:行」对照表（**全部 VC-001…VC-046**：有载体的给载体，无载体的明确写「无载体」并说明理由）。

## D. 纪律

- A/B 段先实测后改码；每条给「红（改前实测失败/漏放原始输出）→ 绿（改后输出）」。
- 新增断言必须等值（`toEqual`/精确计数），不得 `>0`/`>=1`；不得依赖 `task.md` 语料条目总数。
- 不得回退既有验收：TS 基线 402（含 `mwds-t03` 42 / `worker-dispatch-guard` 20 / `agent-team-loop` 196+）、Python 143；改完复跑相关套件给前后计数。
- 若发现必须改卡外文件才能完成，**停下报告**，不要扩面。

## E. 验收命令（PM 执行）

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run --silent=false test/suite/mwds-t03-bash-write-scope.test.ts test/suite/worker-dispatch-guard.test.ts test/extensions/agent-team-loop.test.ts`（应仍见 `[FORMS] total=79 covered=79 missing=0` 与 `[ANCHORS] … unanchored_refs=0`）
- `rg -n "VC-MWGF-" packages/coding-agent/test` 可解析且计数可解释

## F. 交付

`report.md`：A/B 段实测命令 + 原始输出 + 判定 + 改动（或反证）；C 段 VC 对照表与 grep 证据；正反例清单；改前/改后套件计数；未完成项与原因。
