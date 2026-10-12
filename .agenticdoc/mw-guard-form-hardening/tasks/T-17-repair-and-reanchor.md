# T-17 — QG 阻断项修复 + 全量锚点重锚（verify 阶段修复卡）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：本卡 + `design.md`（§3 AC→落地→VC 映射、§4.1 landing 表、§4.6 残余账本）+ 两份 QG 报告：
  - `.agenticdoc/mw-guard-form-hardening/workers/mwgf-qga-code-adversarial/report.md`（对抗审查，**注意：该 worker 无 bash，全部结论为静态推演，须由本卡以实测判定**）
  - `.agenticdoc/mw-guard-form-hardening/workers/mwgf-qgb-evidence-chain/report.md`（证据链审查，FAIL，7 项阻断）
- **唯一允许改的路径**：
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（F-6）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（F-1/F-2，**仅当实测确认**）
  - `packages/multi-workers/autopilot/state.py`（F-5，**仅当实测确认分歧**）
  - `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`、`test/suite/mwds-t02-write-intent.test.ts`、`test/suite/worker-dispatch-guard.test.ts`、`test/extensions/agent-team-loop.test.ts`（新增用例）
  - `.agenticdoc/mw-guard-form-hardening/spec.md`、`design.md`（**仅限锚点重锚与度量现值**，不得改判据口径——口径已由 PM 以 `[REVISED @ date]` 落笔）
  - `.agenticdoc/mw-guard-form-hardening/evidence/runs/t17-forms-baseline-20261012.md`（新建，度量输出）
  - 自身 `report.md`
- **禁止**：运行全量 vitest / 全量 pytest / `npm run check` / `npm run build` / `mw build`；修改上述以外的 `src/**`（尤其 `ui-bridge.ts`、`index-store.ts`、`shared/task-frontmatter.ts`、`pm/task-dispatcher.ts`、`autopilot/status-model.ts` 的既有判据）；改 `plan.md`、其他卡片、其他 key；git 操作

## A. 实测裁决（先跑，再决定改不改）

### A1（F-6，**已由 PM 读源确认，必修**）
`pm-orchestrator.ts:346 pickWorkerRoute(taskContent)`，`:351` = `/^type:\s*codex/im.test(taskContent)`（**`m` 多行标志**，调用点 `:740`）⇒ **正文里一行 `type: codex` 可把派发 CLI 翻转**。这是第 7 个 `type:` 读取器，T-07 未覆盖。
**要求**：改走共享单源（`shared/task-frontmatter.ts` 的 `extractTaskHeader`/`readTaskType`），**正文行不得改变路由**。新增用例：① 仅正文 `type: codex` ⇒ 路由**不变**；② 头部 `type: codex` ⇒ 路由为 codex（正例，防误改）；③ 头部 `type: review` + 正文 `type: codex` ⇒ review。

### A2（F-2，先实测）
假设：`[[ "$ts" > "2026-01-01" ]]` 与 `(( x > 5 ))` 的右操作数被当重定向目标 ⇒ deny（而 shell 语义是比较、不建文件）。
**要求**：用真实提取器跑这两条与 2 条对照命令（`printf x > f.txt` 应 deny、`echo ok` 应 allow），给出 verdict/rule/risk 原始输出。若确认为误拦 ⇒ 修（比较上下文不产候选）并补 1 正例 + 1「不得误拦」反例；若实测证明无问题 ⇒ 在报告中给出反证输出，不改码。

### A3（F-1，先实测）
假设：`tar -czf $OUT.tar ...` 因 `add`（`:1155`：字符串源默认 `verbatim=true`）被判 deny，而 AC-001 契约要求非静态可判 ⇒ `allow-unknown` + `detail=target-not-statically-determinable`。
**要求**：实测该命令与对照（`dd of=$OUT`、`curl -o $OUT`）。若 tar 族为 deny ⇒ 修至契约形态并补用例（含 1 条「不得误拦」反例）。

### A4（F-5，先实测）
假设：`packages/multi-workers/autopilot/state.py::parse_task_labels` 未复用共享头区 ⇒ unclosed-fence / BOM / 重复 `type:` 时 TS 与 Python 的**标签**语义分歧。
**要求**：造 3 个最小 fixture（未闭合围栏、UTF-8 BOM、头部 `type: coding` + 正文 `type: review`）逐条比对两侧输出；确认分歧 ⇒ 改为同语义（可复用 `mw_common.py` 的既有 `read_task_header_region`）并补一致性用例；无分歧 ⇒ 给反证。

## B. 证据链修复（QG-B）

- **B-1（AC-011，阻断）**：程序化重锚 `spec.md`/`design.md` 中**全部** `` `文件:行号` `` 引用到**最终工作树**。要求：① 多根解析（仓库根 / `packages/coding-agent` / `packages/multi-workers` / `.agents/skills/agentic-task/scripts`）；② 不只看越界，**逐条核对被引行的内容**是否符合声称（PM 实测反例：`spec.md` 引 `worker-mode.ts:667/959`，实际是 `): void {` 与 `if (value === "--") {`，且被引符号 `gapLen` 在全文件已 0 命中）；③ 输出引用总数 / 不可解析 / 越界 / 内容不符 四类计数与逐条映射表，写入 `report.md`，并把 `unanchored_refs` 修到 **0**（不可解析的按真实位置改写，内容不符的改引到真实现位置）。
- **B-6（AC-002 量化口径）**：给出 `forms_total` / `forms_covered` / `forms_missing` 的**机器可读现值**。要求：写一个可重复运行的度量脚本（放 `packages/coding-agent/test/suite/` 内或以测试形式实现，输出 `[FORMS] total=… covered=… missing=…` 行），把原始输出落盘 `evidence/runs/t17-forms-baseline-20261012.md`，并在 `spec.md` §4 度量表对应格填入现值与命令。禁止只写「按口径计」。
- **B-5 + C-13（消费端载体）**：给 `[WRITE_SURFACE]` 审计行补 **1 正 1 反** 用例（正：合法 marker ⇒ 无该审计行；反：悬空/重复/倒序 ⇒ 恰 1 条且字段可断言；等值断言、不得用 `>0`）。
- **B-2 / B-3 / B-4 / C-2**：不属本卡改动范围，**只需在报告确认状态**（B-2 AC-008 已由 PM `[REVISED]`；B-3 C-9 交后续 key；B-4 = C-12 cutover 项；C-2 载体由本卡 B-5 覆盖或明确登记）。

## C. 纪律

- 先实测（A2/A3/A4）再改码；每条要给**原始命令输出**，不得以「应该是」代替。
- 新增断言必须等值（`toEqual`/精确计数），不得 `>0`/`>=1`；不得依赖 `task.md` 语料条目总数（语料仍在增长）。
- 不得回退既有 402 项 TS 验收与 143 项 Python 验收；改完必须复跑相关套件并给前后计数。
- 卡片自带状态：每条修复给「红（改前实测失败输出）→ 绿（改后通过输出）」。

## D. 验收命令（PM 执行）

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts test/suite/mwds-t02-write-intent.test.ts test/suite/worker-dispatch-guard.test.ts test/extensions/agent-team-loop.test.ts`
- `cd packages/multi-workers && python -X utf8 -m pytest test_update_index_key_refusal.py test_launcher.py -q`
- 锚点脚本：由本卡落盘的脚本（给出路径）在仓库根可重复运行，输出 `unanchored_refs=0`

## E. 交付

`report.md`：A1–A4 逐条的实测命令 + 原始输出 + 判定 + 改动（若有）；B 项逐条的落盘物与计数；四类锚点计数与映射表；`forms` 度量现值与脚本路径；正反例清单；改前/改后套件计数；未完成项与原因。
