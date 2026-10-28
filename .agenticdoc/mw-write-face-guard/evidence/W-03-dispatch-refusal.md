# 证据 W-03 · conductor 派发闸：写面判定进 `.mw/workers.lock` 临界区

- Key: `mw-write-face-guard`
- Card: `.agenticdoc/mw-write-face-guard/tasks/T-W-I03-dispatch-refusal.md`
  （`sha256=f25e62b4441ae500a45dd89cd96efc35c6e6fa55a7d6485b36c64833429aa1e8`）
- 状态: **DONE**（AC-001/002/003/008/014 落地）
- 交付:
  - `packages/multi-workers/autopilot/dispatch.py`（改动，唯一写者）
  - `packages/multi-workers/test/test_write_face_dispatch.py`（新建，25 tests）
- 上游冻结契约（只读）：`autopilot/write_face.py`、`test/fixtures/write-face-corpus.json`
  在本卡中**未被修改**（`git status` 无 diff）。
- 本文件是卡「交付格式」指定的**唯一证据文件**（卡 `写入允许面` 只列了两个代码路径，
  未重复列证据文件；按派发门禁的强制交付项写入，代码写入面未越界）。

## §0 目标对齐

- `.agenticdoc/goal.md`：并行开发的前提是「同文件多写者对 = 0」；本卡把 B0 的词法算子
  接进真正派发 worker 的咽喉点，让「重叠就不放行并行」成为运行期事实（`.agenticdoc/goal.md`
  核心交付第 2 条 + Key Constraints「不引入中心化调度器：协调通过文件系统」）。
- 判定位置 = `dispatch.dispatch()` 内、`_workers.parallel` 的同一把 `.mw/workers.lock`
  （design.md D-005/D-008；spec.md AC-014）。
- 不新增队列列（`WORKER_COLS_MAX=9`）、不新增 per-key 锁、不二次取锁（RQ-D3），
  不修改 `mw_common.py` / `conductor.py` / `write_face.py`。

## §1 锁内临界区：before / after（行号）

原顺序（HEAD，实测）——**判定所需的状态在锁外读取，task.md 在锁外写**：

```
dispatch.py:1114  envelope_card = dispatch_card(...)          # 渲染前
dispatch.py:1130  task_dir.mkdir(...)                          # [锁外] side effect
dispatch.py:1131  task_md = task_dir / "task.md"
dispatch.py:1132  task_md.write_text(content, ...)             # [锁外] side effect
dispatch.py:1138  wpath = mw_common.workers_path(project_root)
dispatch.py:1156  mw_common.acquire_lock(lock)                  # <<< 锁始
dispatch.py:1174  mw_common.upsert_worker_row(wpath, row)
dispatch.py:1184  mw_common.release_lock(lock)                  # <<< 锁终
dispatch.py:1186  # 3. read-back verification
```

改后（worktree）——**读队列 → 判定 → 建 taskDir/task.md → upsert 全在同一临界区**：

```
dispatch.py:1375  card_backed = dispatch_card(project_root, owner, stem)
dispatch.py:1376  envelope_card = (card_backed if ... else synthesized_card(...))
dispatch.py:1399  task_md = task_dir / "task.md"               # 只算路径，不建文件
dispatch.py:1416  mw_common.acquire_lock(lock)                  # <<< 锁始
dispatch.py:1433  refusal = _write_face_verdict(...)           # 锁内读队列 + 判定
dispatch.py:1442  task_dir.mkdir(parents=True, exist_ok=True)  # 过闸后才落盘
dispatch.py:1443  task_md.write_text(content, ...)
dispatch.py:1459  mw_common.upsert_worker_row(wpath, row)
dispatch.py:1469  mw_common.release_lock(lock)                  # <<< 锁终
dispatch.py:1471  # 3. read-back verification
```

锁内只使用**无锁读取器** `mw_common.parse_workers_file`（`dispatch.py:1131`
`_write_face_verdict` 内）；锁内**没有**第二次 `acquire_lock`（RQ-D3：嵌套取锁退避累计
14.6h 后 `RuntimeError`）。

## §2 改动历史（逐处 `file:line` before→after）

`packages/multi-workers/autopilot/dispatch.py`（HEAD → worktree）：

| # | 位置 | before | after |
|---|---|---|---|
| 1 | 模块 docstring「Dispatch transaction (D-102)」段 | `:16` 原段（task.md 先写、再取锁） | `:16-25` 改为「锁内：判定 + task.md + row」；新增 `:27-31`「Write-face gate (D-001/D-003/D-008)」段 |
| 2 | import 块 | `:49` `from autopilot import timeline as timeline_mod` | `:62` 后新增 `from autopilot import write_face as write_face_mod`（顶层 import） |
| 3 | `render_task_md` docstring | `:824` `comparisons hold.` 结尾 | `:837` 后新增 `write_face:` 渲染说明段（`:839-848`） |
| 4 | `render_task_md` 入口 | `:830` `card = card if isinstance(...)` | `:852` 同句；`:853` 新增 `write_face_entries = _card_write_face_entries(card)` |
| 5 | `render_task_md` 头渲染 | `:864-866` `deny_globs` 块后直接进 `---` | `:887-894` 新增 `write_face: a, b`（空 section → `write_face: -`）行 |
| 6 | `dispatch()` 之前 | `:964` `def dispatch(` | `:992-1217` 新增写面 gate 辅助块（`WRITE_FACE_CARD_SECTION`、`write_face_case_insensitive`、`write_face_base`、`_card_write_face_entries`、`render_write_face_line`、`_write_face_audit`、`_parse_inflight_write_face`、`_write_face_verdict`）；`:1219` `def dispatch(` |
| 7 | `dispatch()` docstring | `:978` 仅写 task.md/row | `:1233` 起补写面 gate 的零副作用/临界区条款 |
| 8 | card 解析 | `:1114` `envelope_card = dispatch_card(...)` + `if envelope_card is None:` | `:1375` `card_backed = dispatch_card(...)`；`:1376-1379` `envelope_card = (card_backed if ... else synthesized_card(...))`（新增 `card_backed` 判别，渲染形状不变） |
| 9 | 队列字段/路径 | `:1130-1132` mkdir+write task.md（锁外）；`:1131` `task_md = task_dir / "task.md"` | `:1399` `task_md = task_dir / "task.md"`（只算路径）；`:1442-1443` mkdir+write 移入锁内 |
| 10 | 取锁 | `:1156` `acquire_lock` | `:1416`（前移：判定与 task.md 都在其后） |
| 11 | 锁内新增 gate | —（无） | `:1433-1438` `refusal = _write_face_verdict(...)`；`if refusal is not None: return refusal`（在 `task_dir.mkdir` 之前） |
| 12 | `lock-unavailable` 分支 | `:1157-1164` 返回 `task_md=<将被写出的路径>` | `:1418-1427` 同字段形状；`:1420-1423` 注释写明 task_md 现在是「从未创建的路径」（RQ-D3 §2 语义变化，见 §8） |
| 13 | upsert / release / 读回 | `:1174` upsert、`:1184` release、`:1186` 读回 | `:1459`、`:1469`、`:1471`（逻辑逐字不变） |

`packages/multi-workers/test/test_write_face_dispatch.py`：**新建**（25 tests）。

## §3 `dispatch()` 调用点审计（`rg -n "dispatch\.dispatch\(" autopilot/conductor.py`）

实测输出（唯一调用文件 = `autopilot/conductor.py`，共 **13** 处）：
`1196 / 1605 / 1643 / 1679 / 1788 / 2369 / 2419 / 2454 / 2486 / 2526 / 2571 / 2579 / 5098`。

判定「是否有任务卡」= `dispatch_card()`（`dispatch.py:583` `card_path = f"tasks/{stem}.md"`）
在该 stem 下能否读到文件。判定「失败后是否重试」= 看该调用点的 `result.ok` 分支。

| # | file:line | 调用者 | type | owner | 有卡? | 失败后处置（坐标） | 本卡处置 |
|---|---|---|---|---|---|---|---|
| 1 | `conductor.py:1196` | `_dispatch_roadmap_writer` (`:1168`) | roadmap-writer | `_scratch` | 无 | 仅写 `config` 审计行（`:1204-1207`），`used_rounds` 未增 → 下 tick 重入 | 豁免 |
| 2 | `:1605` | `_advance_key` (`:1577`) | phase-writer（artifact 缺失） | key | 无 | `return result.ok`（`:1610`）；artifact 仍缺 → 下 tick 重入 | 豁免 |
| 3 | `:1643` | `_advance_key` | phase-writer（l2-fix） | key | 无 | `return result.ok`（`:1648`）；fix_key 仍无行 → 下 tick 重入 | 豁免 |
| 4 | `:1679` | `_advance_key` | verifier（L2） | key | 无 | `mark_stalled`（`:1687-1692`）→ 需人 approve | 豁免 |
| 5 | `:1788` | `execute_loop` (`:1737`) | phase-writer（EXECUTE task） | coding key | **有**（`tasks/<stem>.md`） | `mark_stalled`（`:1794-1799`） | **不豁免**（D-003 serial-only 生效） |
| 6 | `:2369` | `_verify_loop` (`:2330`) | reviewer（L3 round 0） | key | 无 | `return result.ok`（`:2376`） | 豁免 |
| 7 | `:2419` | `_verify_loop` | reviewer（l3-abort reroll） | key | 无 | `return result.ok`（`:2426`） | 豁免 |
| 8 | `:2454` | `_verify_loop` | reviewer（no-verdict re-review） | key | 无 | `return result.ok`（`:2461`） | 豁免 |
| 9 | `:2486` | `_verify_loop` | reviewer（source-suspect） | key | 无 | `return result.ok`（`:2493`） | 豁免 |
| 10 | `:2526` | `_verify_loop` | reviewer（done-gate reprompt） | key | 无 | `return result.ok`（`:2535`） | 豁免 |
| 11 | `:2571` | `_verify_loop` | repair | key | 无 | `return result.ok`（`:2577`） | 豁免 |
| 12 | `:2579` | `_verify_loop` | reviewer（下一轮） | key | 无 | `return result.ok`（`:2586`） | 豁免 |
| 13 | `:5098` | `_xkey_proposal_one` (`:5050`) | phase-writer | `ticket["source_key"]` | 无 | `_xkey_proposal_escalate`（`:5113`）+ ticket `proposal_attempts` 记账 → 有界重入（`_XKEY_PROPOSAL_MAX_ATTEMPTS`） | 豁免 |

**审计结论**：13 个调用点里 **12 个是 card-less 内部派发**（roadmap / 生成 phase-writer /
l2-fix / verifier / L3 reviewer / repair / xkey proposal），**1 个是卡片派发**（`execute_loop`
的首个 attempt）。两者的语义差别不是「重试与否」（#4/#5 都 `mark_stalled`，#1/#2/#3 都会
重入），而是**是否存在可宣告载体**：

- card-less 派发没有 `tasks/<stem>.md`，作者**无处**写 `## 写入允许面`，D-003 的补救路径
  不存在 ⇒ 一次「未声明 serial-only」拒绝要么制造永久失败（#4/#5 型），要么在同一状态
  下无限复发（card-less 永远未声明）。故卡要求 5 的豁免按 **card-less** 施加：
  **只写审计行、照常派发**。
- `execute_loop` 首个 attempt 有可编辑的卡 ⇒ `card_backed=True` ⇒ 未声明时 D-003
  serial-only 生效（零副作用不派发）。重试 attempt 的 stem 是 `<stem>-aN`，`tasks/<stem>-aN.md`
  不存在 ⇒ card-less ⇒ 豁免（与 #5 同类）。
- `orchestrate` 对同 key 在飞直接跳过（`conductor.py:742` `if key in in_flight_keys: continue`），
  所以 card-backed 的 serial-only 是**安全网**，不是常规路径上的阻塞。

## §4 `base` / `case_insensitive` 实测

- `base`：conductor 的 13 处调用全部以 `dispatch.dispatch(project_root, ...)` 传入
  `project_root`（例：`conductor.py:1605-1606` `dispatch.dispatch(project_root, key, ...)`；
  `:1788-1789` 同），`dispatch()` 首行 `project_root = pathlib.Path(project_root)`
  （`dispatch.py:1252`），`mw_common.workers_path(project_root) = project_root/.agenticdoc/
  _workers.parallel`（`mw_common.py:1716-1717`）⇒ base = `.agenticdoc` 的父目录，即
  `project_root`。实现取 `write_face_base(project_root) = str(project_root)`。
- `case_insensitive`：调用点显式经单一 helper `write_face_case_insensitive()`
  （`dispatch.py:1007-1013`，`return os.name == "nt"`）传入，不使用算子内部平台默认。
  本机 win32 ⇒ 实测为 `True`；算子自身对 `base` 不同的比较返回 `Unsupported`
  （保守按重叠），不会被平台默认绕过。
- `\` 由算子 `_norm_sep` 统一视为分隔符（`write_face.py:182`），dispatch 侧不做任何
  路径预处理。

## §5 零副作用快照 diff（原始输出）

命令：临时脚本（已在收尾时删除）——先真实派发一个 `packages/x/**` 的在飞 worker，
写第二个 `packages/x/file.ts` 的卡，对项目目录做「前快照 → 冲突派发 → 后快照」。
原始输出：

```
in-flight dispatch: True 
refused dispatch: {"ok": false, "reason": "write-face-overlap: overlap-with:ap-probe-keep sample=packages/x/file.ts"}
task_dir_exists: False
queue_rows: ['ap-probe-keep']
events: [('dispatch', 'ap-probe-keep type=phase-writer loop=exec:probe:keep attempt=1'), ('write-face-overlap', 'ap-probe-new: overlap with ap-probe-keep at packages/x/file.ts (packages/x/file.ts vs packages/x/**)')]
diff before->after:
  + .agenticdoc/_autopilot/timeline.jsonl (390B)
RAW_BEFORE {".agenticdoc": "DIR", ".agenticdoc/_autopilot": "DIR", ".agenticdoc/_autopilot/timeline.jsonl": "171B", ".agenticdoc/_workers.parallel": "215B", ".agenticdoc/probe": "DIR", ".agenticdoc/probe/tasks": "DIR", ".agenticdoc/probe/tasks/keep.md": "120B", ".agenticdoc/probe/tasks/new.md": "125B", ".agenticdoc/probe/workers": "DIR", ".agenticdoc/probe/workers/ap-probe-keep": "DIR", ".agenticdoc/probe/workers/ap-probe-keep/task.md": "418B", ".mw": "DIR"}
RAW_AFTER {".agenticdoc": "DIR", ".agenticdoc/_autopilot": "DIR", ".agenticdoc/_autopilot/timeline.jsonl": "390B", ".agenticdoc/_workers.parallel": "215B", ".agenticdoc/probe": "DIR", ".agenticdoc/probe/tasks": "DIR", ".agenticdoc/probe/tasks/keep.md": "120B", ".agenticdoc/probe/tasks/new.md": "125B", ".agenticdoc/probe/workers": "DIR", ".agenticdoc/probe/workers/ap-probe-keep": "DIR", ".agenticdoc/probe/workers/ap-probe-keep/task.md": "418B", ".mw": "DIR"}
```

结论：拒绝路径的**唯一**目录变化是被 D-008 要求的审计事件
（`.agenticdoc/_autopilot/timeline.jsonl` 增长）；`ap-probe-new/`（taskDir）、
`task.md`、`_workers.parallel` 行数/字节**均未变化**。`.mw/` 目录由锁协议
（`acquire_lock` 建 `.mw/workers.lock`）产生，锁文件本身在 `release_lock` 后已删除。

## §6 双进程对拍原始输出（`ok=True` 恰 1 + `dispatch` 事件恰 1）

命令：临时脚本（收尾时删除）——两个真实 Python 进程，经文件屏障同时进入
`dispatch()`；同 owner、两个不同 task_key、写面分别 `packages/x/**` 与
`packages/x/file.ts`（可证重叠）。原始输出（5 轮）：

```
run 1: grants=1 refusals=1 rows=1 dispatch_events=1 overlap_events=1 results=[{"stem": "a1", "ok": false, "reason": "write-face-overlap: overlap-with:ap-race-a2 sample=packages/x/file.ts"}, {"stem": "a2", "ok": true, "reason": ""}]
run 2: grants=1 refusals=1 rows=1 dispatch_events=1 overlap_events=1 results=[{"stem": "a1", "ok": true, "reason": ""}, {"stem": "a2", "ok": false, "reason": "write-face-overlap: overlap-with:ap-race-a1 sample=packages/x/file.ts"}]
run 3: grants=1 refusals=1 rows=1 dispatch_events=1 overlap_events=1 results=[{"stem": "a1", "ok": false, "reason": "write-face-overlap: overlap-with:ap-race-a2 sample=packages/x/file.ts"}, {"stem": "a2", "ok": true, "reason": ""}]
run 4: grants=1 refusals=1 rows=1 dispatch_events=1 overlap_events=1 results=[{"stem": "a1", "ok": false, "reason": "write-face-overlap: overlap-with:ap-race-a2 sample=packages/x/file.ts"}, {"stem": "a2", "ok": true, "reason": ""}]
run 5: grants=1 refusals=1 rows=1 dispatch_events=1 overlap_events=1 results=[{"stem": "a1", "ok": false, "reason": "write-face-overlap: overlap-with:ap-race-a2 sample=packages/x/file.ts"}, {"stem": "a2", "ok": true, "reason": ""}]
```

5 轮全为 `grants=1 / refusals=1 / rows=1 / dispatch_events=1`（与 RQ-D3 形状原型一致）。
同一对拍也固化为真测试：
`test/test_write_face_dispatch.py::test_race_distinct_task_keys_overlapping_faces_exactly_one_grant`
（两个真实 `subprocess` 进程，锁未 mock）。

**关于「同 task_key」**：requirement 3 明确把本次 `task_key` 自身的行排除出在飞集合
（幂等重排不得自拒），所以两个进程派发**同一个** `task_key` 时判据是
`grants=2 / rows=1`（第二次是 upsert 覆盖），而不是 `grants=1`；该形状固化为
`test_race_same_task_key_is_an_idempotent_requeue`。§10 的「`ok=True` 恰 1 + `dispatch`
事件恰 1」由**同 owner / 不同 task_key / 可证重叠**这一真正会产生「同文件多写者」的
对拍满足（也是 RQ-D3 `grants=1/refusals=1` 唯一可达的形状）。

## §7 测试实跑原文

新文件单独跑（确认被执行、未被跳过）：

```
$ cd packages/multi-workers; python -m pytest test/test_write_face_dispatch.py -q
.........................                                                [100%]
25 passed in 0.51s
```

（`-v` 实跑 25 个具名用例全 PASSED，含两个真实进程对拍；无 skip。）

全包回归：

```
$ cd packages/multi-workers; python -m pytest -q
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_task_type_parity.py::test_bom_historical_books - AssertionError: ...
6 failed, 2178 passed, 10 deselected, 2 warnings in 396.75s (0:06:36)
```

改动前同一窗口的基线（工作区 `dispatch.py` 尚未改动时实跑）：

```
6 failed, 2124 passed, 10 deselected, 2 warnings in 327.49s (0:05:27)
```

两轮的 **6 个失败完全相同（逐名一致，全部是 BOM/编码与 TS-parity 的环境性失败，
无一涉及 write_face/dispatch 路径）**。通过数 +54 = 本卡新增 25 + 另一 session 的
W-01 r2 在 `test_write_face.py` 追加测试（卡记录 W-01 r1 为 99 passed；本窗口
`pytest --collect-only` 实测该文件为 128 tests，且其 `LastWriteTime=11:17:56` 落在两轮
运行之间）；无本卡引入的回归。

未跑仓库根 `npm run check`（跨语言热文件，多 session 下会全仓 `biome --write`；本卡纯 Python）。

## §8 语义变化 / 残留风险

1. **`lock-unavailable` 的 `task_md` 语义变化（requirement 6，必记）**：task.md 移入锁内后，
   取锁失败分支（`dispatch.py:1418-1427`）返回的 `task_md` 指向一个**从未被创建**的路径。
   `DispatchResult` 字段形状与类型不变（`pathlib.Path | None`，仍非 None），不改既有
   `reject()` 族 code；只影响「ok=False ⇒ 一定有 task_md 落盘」这一旧隐含保证——现在
   `ok=False` 恒等于「未写盘」。无既有测试依赖该分支。
2. **未声明审计的发射条件（对 requirement 5 的收窄）**：card-backed 的未声明**总**写
   `write-face-undeclared`；card-less 的未声明仅在有同 owner 在飞行时才写审计行（无争用时
   与改前逐字节一致）。收窄是必要的：`test_autopilot_dispatch.py:181` 断言一次无争用
   card-less 派发的 timeline 恰为 `["dispatch"]`，而该文件不在本卡写入允许面内、不得修改；
   且无争用场景下 D-003 的 serial-only 判定根本不存在。
3. **未声明在飞行不再证明重叠（D-003 方向性）**：本次声明 + 在飞行未声明 ⇒ 不按重叠拒绝
   （requirement 4 明示）。存量在飞行（本卡合入前派发、写面未声明的 419 份旧卡）不受
   serial-only 保护；这是 D-003 的既定方向，不是本卡缺陷。W-08 迁移后消失。
4. **旧 task.md 正文若含行首 `write_face:`**：算子 `_find_head` 取**首个**匹配行
   （`write_face.py:229-250`）。新渲染把 `write_face:` 放在 frontmatter（正文之前），所以
   自身派发永远命中头部；但读取「在飞行」task.md 时，若某个旧文件正文首行恰好是
   `write_face:`，会被当作已声明。风险面极窄（需正文行首裸写该 ASCII 头），且方向是
   「更保守地判重叠」，交 PM 记录。
5. **不改动项**：既有 `reject(...)` 族 code 及优先级、`synthesized_card`、`origin`、
   读回校验、`mw_common` 任何函数、既有渲染形状（除新增 `write_face:` 头行）——均已由
   全包回归（6 个既有环境性失败之外全绿）与本卡测试锁定。
6. **终态集合的引用**：gate 用 `mw_common._TERMINAL_STATUSES`（`mw_common.py:168`；
   与 `mw_common.py:2342` 的 doctor 段同名常量、以及 `RUN_TERMINAL_STATUSES:1876`
   逐字同内容），与 conductor 侧唯一在飞谓词 `_is_in_flight`（`conductor.py:3539-3540`，
   同样引用该常量）一致；**未自造任何集合**，也未采取原集合的 “复制一份到 dispatch.py”。
