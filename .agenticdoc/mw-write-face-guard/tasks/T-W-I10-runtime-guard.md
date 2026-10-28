# T-W-I10 · 运行期写面闸（TS，B2/D-007 IP-1b）：write/edit 分支 + bash 条件放宽 + 角色类别化写面

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— "同一时刻同 key 同文件多写者对 = 0"。派发期闸门（B1，已交付：conductor `dispatch.py` + PM `pm/task-dispatcher.ts`）只能拦**调度**层面的冲突；worker 跑起来之后**实际把文件写到哪**必须由运行期闸门兜住，否则"声明了写面"只是装饰（spec 风险 3）。
- **本卡是 D-007 的 IP-1b**（`design.md` 表格 D-007 行，逐字要求照办）：全可写角色（coding/repair/phase-writer/vision/fallback）= bash 写文件的 read-only 角色；插入点 = **IP-1b**（落在 `workerModeActivate` 闭包内：新增 `write`/`edit` 分支 + bash 分支条件由 `isShellRole && isWritelessRole` 放宽到 `isShellRole`，复用 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`；meta 已缓存，零额外 I/O）；**自建一份写面 lexer，不复用 `implementation-gate` 的 target lexer**（后者目标是"仓库代码路径"，自述漏 `python -c`/预写脚本/`find -delete`/tar/PowerShell cmdlets）；`worker_file` 的 basename 白名单保持不变；**默认面 / deny 面必须角色类别化**（把今天的 `packages/**` 绝对 deny + taskDir 默认面直接套到 coding 会误拦全部合法写）；`research` 行为**逐字保持**。
- **定位锚点（插入点，唯一）**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2195`（`// Bash write-surface guard (AC-005b / contract C3)` 起始的 `pi.on("tool_call")` 否决处理器）、`:2203`（`isShellRole(meta.type) && isWritelessRole(meta.type) ? {...} : undefined` —— 要放宽的那处条件）、`:2219`（`extractBashWriteCandidates(command)` 循环）、`:2220`（`checkBashWriteScopeTarget`）、`:2211`（`writeScopeCounts` 计数器，`recordEnd` 的 `[WRITE_SCOPE_SUMMARY]` 消费它）。
- **定位锚点（复用/不改）**: `worker-mode.ts:1554`（`extractBashWriteCandidates`）、`:1606`（`checkBashWriteScopeTarget`）、`:744`（`BashWriteScopeRule`）、`:747`（`BashWriteScopeConfig`）、`:729`（`BashWriteCandidate`）、`:151`（`isShellRole`）、`:158`（`isWritelessRole`）、`:1584`/`:1650`（`matchesWriteScopeEntry`）、`:364`（`parseTaskMd`）、`:434-441`（task.md `write_scope:` 解析）、`:2128`/`:2196`（`worker_file` 窄通道 / `writeScope` 取值）。
- **不得改动的相邻段**: `worker-mode.ts:2345+` 的 `tool_execution_start`/`tool_execution_end` **记账**分支（`READ_TOOLS`/`WRITE_TOOLS`/`bash` 计数、`[WRITE_FILE]` change-history 事件）——本卡是**否决**面，不是记账面；记账行为必须逐字不变（既有测试锁着）。
- **裁定与 AC**: `design.md` D-007（上引）、D-006（算子不自推平台）、D-003（未声明 ⇒ 不静默放行）；`spec.md` **AC-004/006/010/012/013**（AC-013 = 假阻反例族，含 `Write-Output a <term> --glob x` 家族 11 条，必须逐条判定入证）。
- **跨 key 热文件告警（plan §3 串行点 1）**: `worker/worker-mode.ts` 是跨 key 热文件（含 `[WRITE_SCOPE]` 相邻段）。PM 派发前实测：该文件 `git status` 干净、mtime 2026-10-12 22:02，当前无活跃写者。**开工后若发现文件被第三方改动（例如你已在编辑的区段被别人重写），立刻停下并在 `残留与未验证` 报告，不要回退别人的改动。**

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/write-face-runtime.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/output-writer.ts`、`worker/read-scope.ts`、`shared/implementation-gate.ts`、`shared/write-face.ts`、`pm/**`、`autopilot/**`、`packages/multi-workers/**` 全部只读；**不得**改动 `worker-mode.ts:2345+` 的记账分支行为；**不得**改 `worker_file` basename 白名单；其它 test/suite 文件只读。**禁止 `npm run check`**（全仓 `biome --write`，多会话破坏性）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **IP-1b 插入点唯一**：把 `write`/`edit`（以 `event.toolName` 判定，读取 `event.input` 里的目标路径）也纳入 `:2195` 那个 `pi.on("tool_call")` 否决处理器；bash 的配置条件由 `isShellRole && isWritelessRole` 放宽为 `isShellRole`。**不要**把闸门放进 `tool_execution_start/end` 记账分支。
2. **写面 lexer 自建，不复用 `implementation-gate` 的 target lexer**（D-007 明文）。`extractBashWriteCandidates` / `checkBashWriteScopeTarget` / `matchesWriteScopeEntry` 复用（meta 已缓存，零额外 I/O）。
3. **角色类别化的默认面与 deny 面**（D-007 明文，本卡最容易做错的一处）：今天的"默认面 = 自己的 taskDir + `<key>/evidence/**`、`packages/**` 绝对 deny"是为 `research` 这种 writeless 角色设计的；直接套到全可写角色会误拦**全部**合法写。必须给出**按角色类别**的面表（至少区分：writeless 角色 / 全可写角色），并把该表与理由写进证据；若某类角色的面在 meta 里无法确定，按 D-003 的方向处理（**不静默放行**：记审计并把处置写清），不要猜一个面出来。
4. **`research` 行为逐字保持**：`research` 的窄 `worker_file` 通道、bash 分类结果、`[WRITE_SCOPE_SUMMARY]` 计数、审计行都必须字节级不变；用**现有测试**证明，而不是新增豁免分支（若为保住 `research` 而要在代码里写 `if (type === "research")`，说明设计错了，改回去）。
5. **AC-013 假阻反例族**：把 11 条 `Write-Output a <term> --glob x` 家族（及你自己补的同族）逐条过一遍，**判定结果入证**（放行/拦截 + 依据），要求"真写拦、假写不拦"。
6. **测试**（新建 `test/suite/write-face-runtime.test.ts`）：
   - `write`/`edit` 目标在声明写面内 → 放行；在写面外 → 拦截（含跨 key、`..` 逃逸、绝对路径）。
   - 全可写角色（无 `write_scope:` 声明）→ **不误拦**其合法写（这是本卡的核心反例：旧条件放宽后最容易在此翻车）。
   - bash 分支：`isShellRole` 放宽后的新覆盖（例：coding 角色用 `python -c "open(...,'w')"` / 重定向 / `find -delete` 家族写面外文件 → 拦截；纯读命令与无法静态判定的命令仍**不拦**且记 `allow-unknown` 审计）。
   - `research` 无回归（跑现有套件）。
   - 对每条断言给出理由注释（对应哪条 AC/D 编号）。
7. `git diff --stat` 收尾时只应含允许面两个文件（工作区其它 session 的改动不算本卡）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：新测试条数、11 条 AC-013 向量的逐条判定表、角色类别化面表（含理由）、`research` 无回归的现有测试名单与条数、以及"全可写角色合法写不被误拦"那条的原始输出。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-runtime.test.ts
node ../../node_modules/vitest/dist/cli.js --run <现有 research/bash 写面相关套件，逐个文件参数>
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/worker packages/coding-agent/test/suite
```

（现有相关套件请先用 `rg -l "WRITE_SCOPE_SUMMARY|write_scope|writeScope" test/` 定位，然后**逐文件**跑并在证据里列出名单与条数；已知 `test/extensions/agent-team-loop-worker-file-tool.test.ts` 有 2 条与本卡无关的既有失败（trace.log 污染），遇到时报出基线即可，不要去修。）

## 改动历史

- 2026-10-14 B1 收口：派发期闸门两通道已同形（`dispatch.py` + `pm/task-dispatcher.ts`，`design.md` D-114 队列单写者亦已收敛）；运行期闸门尚未开始 —— 今日只有 `research` 角色经 bash 写面闸被拦（`worker-mode.ts:2195-2243`）。
- 2026-10-14 PM 实测 `worker/worker-mode.ts` 无活跃写者（`git status` 干净、mtime 10-12 22:02），故本卡可派；同 key 无其它在跑卡（W-09 已 done）。

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 不复用 `implementation-gate` 的 target lexer；不改记账面行为；不改 `worker_file` 白名单。
- 发现别处也要改（例如 `shared/implementation-gate.ts`），写进 `残留与未验证` 回报，不要越面修改。
- `worker-mode.ts` 若在你工作期间被第三方改动，停下报告，不要覆盖别人的行。
