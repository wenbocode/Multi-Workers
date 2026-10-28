# T-W-I11 · 载体收敛：运行期接入权威 `write_face:` + 旧口径改写（AC-011/AC-004 收口）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— "同一时刻同 key 同文件多写者对 = 0"，前提是"声明了写面就必须真的拦"。现在这个前提只在 writeless 角色上成立。
- **本卡要修的集成漏洞（W-10 残留 R1，PM 复核确认）**：B1 的权威载体是 **task.md 头的 `write_face:`**（PM 侧 `pm/ui-bridge.ts` 渲染：`mergeCardHeader` 在 `:2092`、调用点 `:2273`；conductor 侧 `dispatch.py::render_write_face_line`），而 B2 的运行期闸门（W-10）仍只读 `meta.writeScope`（来自 `write_scope:`）。⇒ **真实 writable 卡只有 `write_face:` 时，运行期拿不到声明面，落入"工作树根"默认面，越出 `write_face:` 的写不会被拦**。AC-004 目前只对 `write_scope:` 承载的卡成立。
- **裁定 (必读，逐条照办)**: `design.md` **D-115**（载体收敛，AC-011）+ D-007（IP-1b 面表）+ D-006（fail-closed 与算子不自推平台）+ D-001（头形态）/D-003（未声明不静默放行）。要点：
  1. `write_face:` 是**唯一权威 allow 载体**。
  2. `write_scope:` 只对 **writeless 角色**（research）仍作声明面，行为**逐字保持**；writable 角色存在 `write_face:` 时以它为准。
  3. 两者**同时存在且不等** ⇒ 取**交集**（fail-closed）**并写一条审计行**（legacy 载体只能收窄、不能放宽，且不得无痕）。
  4. writable 角色**无** `write_face:` ⇒ 回落 `write_scope:`（只读兼容存量卡）。
  5. **不得新增第五个载体**；W2 gate v2 `write_scope`（异语义 `blast_radius`）与 W4 `mw-write-surface` marker 各自保持现状（在代码注释里标注"异语义/仅标记，不参与 allow 判定"即可，不改行为）。
  6. **安装条件补洞**：守卫必须覆盖"**有 `write`/`edit` 工具**"的角色（`hasWriteTools(type) || isShellRole(type)`），而非只覆盖 shell 角色——`roadmap-writer` 这类 writable 无 bash 的角色今天**完全没有运行期闸门**；bash 子判定仍只在角色确有 bash 时启用。
  7. `mwds-t03` 的 4 条旧口径断言按新语义**重写**（见要求 4），不得删除或放宽。
- **定位锚点（改）**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:364`（`parseTaskMd`，产出 `meta.writeScope`）、`:434-441`（`write_scope:` 头解析）、`:723`/`:756`/`:786`（写面相关类型/常量）、`:2195`（`pi.on("tool_call")` 否决处理器）、`:2203`（`isShellRole(meta.type) ? {...}` —— 安装条件与面表装配处）、`:2211`（`writeScopeCounts`）、`:2196`/`:2128`（`writeScope` 取值 / `worker_file` 窄通道）、`:1584`/`:1650`（`matchesWriteScopeEntry`）、`:151`/`:158`（`isShellRole`/`isWritelessRole`）、`:145`（`activeToolsForType`，可用于 `hasWriteTools`）。
- **权威解析器（优先复用，避免第二套语义）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts` 的 `parseWriteFace`（`:616`，语料锁定的算子，D-009/AC-007）。若 `worker/**` 的分层不允许 import `shared/**`，**不要**另写一个头部解析器——在 `残留与未验证` 报告并停在"复用现有 `matchesWriteScopeEntry` 做包含判定"的最小可行路径上。
- **测试锚点**: `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`（当前 **4 failed / 59 passed**，4 条红全部是旧口径：3× `VC-024: <coding|repair|vision> registers no write-scope guard and its bash commands pass`、1× `the summary is written once at recordEnd and only for the writeless guard role`）、`packages/coding-agent/test/suite/write-face-runtime.test.ts`（W-10 新建，9 passed）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`
- `packages/coding-agent/test/suite/write-face-runtime.test.ts`

## 写入禁止面

其余一切路径。特别地：`pm/**`、`autopilot/**`、`shared/write-face.ts`（**只读**，本卡不改算子）、`worker/output-writer.ts`、`worker/read-scope.ts`、`packages/multi-workers/**` 全部只读；**不得**改 `tool_execution_start/end` 记账分支行为；**不得**改 `worker_file` basename 白名单；其它 test/suite 文件只读。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **运行期读权威载体**：`parseTaskMd` 解析 task.md 头的 `write_face:`（含 D-113 的块列表形态：`write_face:\n  - <entry>`），按 D-115 的优先级/交集规则得到"声明面"；解析语义（分隔符、`*` 是否跨 `/`、大小写模式 = `process.platform === "win32"`，D-006）必须与 B1 侧同源；若必须自建包含判定，用**测试**把 `*`/`**`/`{a,b}`/大小写/`..` 逃逸逐个钉住，并在证据里给出与算子归一化的对照（两侧不得静默分叉）。
2. **两条载体同时存在且不等 ⇒ 交集 + 审计行**（D-115 第 3 条）：写出审计（沿用现有 `appendBashWriteScopeTraceLine` 家族或等价既有通道），并把"不等"的事实与两侧条目写进审计 detail。
3. **writeless 角色逐字不变**：research 的 `write_scope:` 语义、deny 面、`[WRITE_SCOPE_SUMMARY]` 计数、审计行全部字节级不变；用**现有** `mwds-t03` 的 research 相关用例 + `write-face-runtime.test.ts` 的 research 用例证明。
4. **旧口径断言重写（不得放宽）**：`mwds-t03` 的 4 条红按新语义重写——VC-024 三条从"不装闸"改为"**装了闸但合法写不被误拦**"（保留原有"合法 bash 命令必须通过"的实质断言，并新增一条"面外写被拦"的正向断言）；summary 那条从"只给 writeless"改为"**每个 shell 角色各一行**"。改完 `mwds-t03` 必须 **63 passed / 0 failed**。
5. **安装条件补洞（D-115 第 6 条）**：守卫装配条件改为 `hasWriteTools(type) || isShellRole(type)`；`roadmap-writer` 这类角色必须能装上 `write`/`edit` 分支（bash 分支不装，因为它没有 bash）。给该角色加一条测试。
6. **端到端集成用例（本卡的关键验收）**：在 `write-face-runtime.test.ts` 里构造"**只有 `write_face:`（无 `write_scope:`）的 writable 卡**"（含单行与 D-113 块列表两种形态，条目含逗号的那种），断言：面内写放行、面外写（跨 key / `..` 逃逸 / 绝对路径）**拦截**。这条就是 W-10 残留 R1 的反例，必须由真实 task.md 文本 + 解析路径走通，不能只调纯函数。
7. `git diff --stat` 收尾时只应含允许面三个文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：`mwds-t03` 由 4 failed 变 0 failed 的条数、`write-face-runtime` 新条数、端到端用例的原始判定输出（task.md 原文片段 + 判定）、两条载体不等的交集+审计行样例、`roadmap-writer` 角色装闸的原始输出、以及 writeless 无回归的用例名单。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-runtime.test.ts test/suite/mwds-t03-bash-write-scope.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/mwds-t12-regression.test.ts test/suite/mwds-t21-write-intent-soundness.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/worker packages/coding-agent/test/suite
```

（已知与本卡无关的既有红：`test/extensions/agent-team-loop-worker-file-tool.test.ts` 2 条 `trace.log` 污染；`test/suite/mwds-t02-write-intent.test.ts` 1 条别 key task book 引起的语料漂移。遇到时报基线，不要修。）

## 改动历史

- 2026-10-14 B1 收口：PM 与 conductor 两通道同形渲染 `write_face:`（D-113 逗号回退在内）；运行期闸门在 W-10 之前只覆盖 writeless 角色的 bash 通道。
- 2026-10-14 W-10（B2）落地 IP-1b：`write`/`edit` 分支 + bash 条件放宽 + 角色类别化面表 + AC-013 假阻族修复；自报残留 R1（运行期未接 `write_face:`）、R2（`mwds-t03` 4 条旧口径断言）、R3（writable 无 bash 角色零闸门）。
- 2026-10-14 PM 复核确认 R1/R3 并裁定 D-115（载体收敛 + 安装条件补洞 + 旧口径改写），本卡即该收口。

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 不改算子 `shared/write-face.ts`；不改记账面；不改 `worker_file` 白名单。
- 旧口径断言只许按新语义**重写**，不得删除、跳过（`skip`/`todo`）或放宽。
- `worker-mode.ts` 若在你工作期间被第三方改动，停下并在 `残留与未验证` 报告，不要覆盖别人的行。
