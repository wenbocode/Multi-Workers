# T-W-I08 · PM 侧派发闸 + 卡渲染（TS，B1 的另一半）：同输入同输出 + 逐字同格式

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 核心交付是「一个常驻 mw 服务 + 让 Worker 并行开发同一个项目」，前提是"同文件多写者对 = 0"。PM 通道（本卡）与 conductor 通道（W-03 已完成）必须**同输入同输出**，否则同一个项目里两条派发路径的判定分叉，前提就只在一半路径上成立（AC-007）。
- **本卡是 B1 的另一半**：conductor 侧闸门已落地于 `packages/multi-workers/autopilot/dispatch.py`（`_card_write_face_entries` `:1022`、`render_write_face_line` `:1055`、`_write_face_verdict` `:1099`、拒绝码 `:1173/1198/1208`）。PM 侧目前**完全没有**：`pm/ui-bridge.ts:2030` 的 `mergeCardHeader` 只合并 `card_path` / `card_sha256` / envelope producer 三个字段，**不渲染 `write_face:`**；`pm/task-dispatcher.ts:288` 的 `dispatchTask` 只做 `injectWorkspaceProfile` + `store.upsert`，**没有重叠判定**。
- **定位锚点（写侧）**: `pm/ui-bridge.ts:2030`（`mergeCardHeader`）、`pm/ui-bridge.ts` 内已有的 `CardSections`（`{context, requirements, deliverables, extras: CardExtraSection[]}`，extras 已含每个未分类 `## ` 段的 `title` + `body`——**这是本卡渲染写面的唯一输入源，不要新写卡片解析器**）、`pm/ui-bridge.ts` 中 `mergeCardHeader` 的调用点。
- **定位锚点（判定侧）**: `pm/task-dispatcher.ts:288`（`dispatchTask`）、`shared/worker-store.ts:190`（`WorkerStore.upsert` 内部先 `acquireLock(this.lockPath)`，锁文件 = `.agenticdoc/../.mw/workers.lock`，见 `worker-store.ts:153`）、`shared/worker-store.ts:58`（`workerOwnerKey`）、`shared/worker-store.ts:65`（`workerBelongsToKey`）。
- **Python 侧参考语义（必须逐条镜像，AC-007「同输入同输出」）**：`dispatch.py:1022` `_card_write_face_entries` 的抽取规则——段标题 `title.startswith("写入允许面")` 才取；正文逐行 `strip()`，空行跳过，行首 `-`/`*`/`+` 去掉，然后**优先取第一个反引号 span**，否则按 `[\s（(]` 切取第一段；`item == "-"` 或空 ⇒ 跳过；**条目保持单 `/` 原样不动**（渲染器不得替解析器做归一化，否则同源锁断）。段缺失 ⇒ `None`（**不渲染** `write_face:`，D-003 未声明）；段存在但无条目 ⇒ `[]`（渲染 `write_face: -`，D-001/§3.3）。
- **两处站点助手（Python 已有，TS 无）**: `dispatch.py:1016` `write_face_base(project_root) -> str(project_root)`（即 `.agenticdoc` 的父目录，与 `mw_common.workers_path` 同锚）；`dispatch.py:1007` `write_face_case_insensitive() -> os.name == "nt"`。TS 侧对应物必须**同样在调用点**给出（base = `WorkerStore` 锚定的同一根，即 `path.resolve(agenticdocRoot, "..")`；大小写模式 = `process.platform === "win32"`），**不得**在算子内部推断（D-006/AC-007 明文要求"算子不自己推断平台"）。
- **裁定**: `design.md` D-113（渲染器契约 `parse(render(entries)) == entries`，含逗号条目必须走 §3.1 块列表载体）、D-001（头形态/空值语义）、D-003（未声明 ⇒ serial-only，不拒绝）、D-006（算子不自推平台）、D-111（先证冲突）；AC-001/002/003/008/011/014。
- **Python 侧已实测的形状（本卡要逐字段对齐的参照）**: 拒绝码 `write-face-overlap`、`overlap-with:<task_key>`、冲突样例路径；未声明走 `write-face-undeclared` 审计行 + serial-only。证据：`evidence/W-03-dispatch-refusal.md` + `evidence/PM-parity-differential-20261014.md`。
- **语料（只读）**: `packages/multi-workers/test/fixtures/write-face-corpus.json`（`counts={parse:23, overlap:59}`，LF 归一化 `sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`；本仓 Windows 磁盘为 CRLF ⇒ 20126 B）。TS 侧算子已在 W-02/W-05 交付并全绿。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`
- `packages/coding-agent/test/suite/agent-team-loop.test.ts`（仅限因新增 `write_face:` 头字段而必须同步的**期望值**）
- `packages/coding-agent/test/suite/write-face-pm-gate.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/**` 全只读（conductor 侧已交付，本卡是镜像它而不是改它；`dispatch.py` 含 W-03 的未提交改动）；`packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts` 只读（算子已达标，本卡只调用它）；`shared/dispatch-card.ts` 只读（卡片解析已够用，见上下文）；`worker/**` 只读（B2 的面）；`pm/pm-orchestrator.ts` 只读（改它会碰到别人正在写的大文件）；**禁止 `npm run check`**（全仓 `biome --write`，多会话下破坏性）；禁止跑不带文件参数的全量 vitest（本机 P-032：会挂死）。

## 要求

1. **渲染（写侧）**：让 `mergeCardHeader`（或它在 `ui-bridge.ts` 内的调用点）把卡片的 `写入允许面` 渲染成 task.md 头的一行 `write_face:`，**格式与 Python `render_write_face_line`（`dispatch.py:1055`）逐字一致**：单行 `write_face: a, b`；**任一条目含 `,` 时改为块列表形态** `write_face:\n  - <entry>`（D-113，Python 侧刚落地的形态，先例 `test_write_face.py:53`）。段缺失 ⇒ 不写该行；段存在为空 ⇒ `write_face: -`。
2. **抽取语义逐条镜像** `dispatch.py:1022`（见上文规则），包括"条目原样不归一化"与"第一个反引号 span 优先"。若 `CardSections.extras` 的 `body` 与 Python 侧拿到的 `extras.body` 形态有差异（例如是否含标题行），以**同一卡文件上两侧抽出的 entries 相等**为准，并把你实测的对照写进证据。
3. **判定（写侧之外的另一半）**：在 PM 派发路径上加入同族重叠判定，且必须落在**与 `WorkerStore.upsert` 同一把锁**的临界区内（Python 侧是"在已持的那一次 `acquireLock` 内完成判定 + 建 task.md + upsert"，`dispatch.py:1156`）。在飞集合必须**当场从队列重算**（`workerOwnerKey` + 单一终态集合；不得新增队列列）= AC-008。
4. **拒绝形状与 Python 逐字段相同**（AC-007）：同一 `code`（`write-face-overlap`）、同一 `overlap-with:<task_key>` 字段、同一冲突样例路径语义；**零副作用**（不写队列行、不建 taskDir/task.md）。未声明（段缺失、D-003）⇒ `write-face-undeclared` 审计行 + **serial-only**（存在同 key 在飞则不派发；**不是**拒绝）。
5. **站点助手**：按上文把 base 与大小写模式放在**调用点**（不在算子内推断）。
6. **测试**：
   - 新建 `test/suite/write-face-pm-gate.test.ts`：至少覆盖——含逗号条目卡的 render→parse 恒等（`parse(render(E)) == E`，含 `["a/{b,c}/**"]` 与 `["packages/x/**","a/{b,c}/**"]`）；段缺失不渲染；段存在为空渲染 `-`；重叠 ⇒ 拒绝且零副作用（目录/队列快照 diff）；未声明 ⇒ serial-only 且无拒绝（D-003）；同一卡上 PM 侧 entries 与 Python `dispatch.py` 抽出的 entries 逐条相等（可以用只读方式调用 Python 侧抽取函数，或把两侧输出落盘对照，**不得**改 Python 文件）。
   - `test/suite/agent-team-loop.test.ts`：其冻结断言是回归锚点；**只**同步因新增 `write_face:` 头行而变化的期望值，不得放宽或删除断言。
7. `git diff --stat` 收尾时只应出现上述允许面文件。

## 交付格式

`output.md` 必须包含框架要求的五段：`结论`、`证据`、`残留与未验证`、`上下文来源`、`改动清单`。`证据` 段要给**可直接复跑的原始命令与原始输出**（含 render 前后原文、两侧 entries 对照表、拒绝形状逐字段对照、vitest 条数），不要只写"已通过"。若出现 `## 路径形态（warn）` 之类的 warn 段，说明它来自 `worker/output-writer.ts` 的形态检查而**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-pm-gate.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts test/suite/agent-team-loop.test.ts
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/pm packages/coding-agent/test/suite
```

## 改动历史

- 2026-10-14 PM 实测现状：`mergeCardHeader`（`ui-bridge.ts:2030`）不含 `write_face:` 渲染；`dispatchTask`（`task-dispatcher.ts:288`）无重叠判定；TS 侧无 `writeFaceBase`/`write_face_case_insensitive` 对应物（全仓 grep 为空）。
- 2026-10-14 同日：conductor 侧同族能力已交付（W-03，`test/test_write_face_dispatch.py` 29 passed）；算子两侧已达标（V58 转绿、D-113 渲染器落地）。
- **热文件告警**：`ui-bridge.ts` 是本 key 之外也被改过的文件（本窗口刚在 `setWatchWidget` 一带做过时序修复，工作区里该文件带未提交改动）。开工前先 `git status --porcelain -- <该文件>` 看清未提交改动，**不要**回退或重写别人的行；若发现文件在你有动作期间被第三方改动，停下来在 `残留与未验证` 里报告。

## 硬约束

- 不跑 `npm run check`（AGENTS.md P-017）。不跑无文件参数的全量 vitest（P-032）。
- `packages/multi-workers/**` 全只读。不改算子 `shared/write-face.ts`。
- 只改本卡声明允许面的文件；发现别处也要改就写进 `残留与未验证` 并回报。
