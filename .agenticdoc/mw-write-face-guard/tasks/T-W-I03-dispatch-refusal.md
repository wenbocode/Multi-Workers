# T-W-I03 · conductor 派发闸：写面判定进 `.mw/workers.lock` 临界区（Python，B1）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — 核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」。并行开发的前提是**同文件多写者对 = 0**；本卡交付该前提的**执行层**：把 B0 的词法算子接进真正派发 worker 的那一个咽喉点，让「重叠就不放行并行」从设计变成运行时事实。
- 写面**载体**已经落地（B0）：`packages/multi-workers/autopilot/write_face.py` 提供 `parse_write_face(text, *, base, case_insensitive)` 与 `globs_overlap(a, b, *, case_insensitive=False)`，冻结语料 `packages/multi-workers/test/fixtures/write-face-corpus.json`（`sha256=fb710b904cd4bbcb03ffa4f432ebc3b60c0234771b4c5f06c0d3a36a0186b09f`）parse 16 + overlap 49 全过（99 passed）。本卡把**判定接进 conductor 派发链**，即 AC-001/AC-002/AC-003/AC-008/AC-014 的落地卡。

当前 `autopilot/dispatch.py` 的派发顺序（实测）：

1. `render_task_md(...)` 渲染 task.md 内容（`dispatch.py:1119`）；
2. **先写盘**：`task_dir.mkdir(...)` + `task_md.write_text(...)`（`dispatch.py:1132-1135`）；
3. 取锁 `mw_common.acquire_lock(lock)`（`dispatch.py:1156`）；
4. 锁内 `mw_common.upsert_worker_row(wpath, row)`（`dispatch.py:1170`）；`dispatch.py:1183` `finally: release_lock`；
5. 读回校验"恰好 1 行且身份一致"（`dispatch.py:1186-1200`）。

由此产生的**检查-再行动窗口**（RQ-D3 实测，双进程对拍）：在飞判定若放在 `dispatch.py:1156` 之前，两个进程可同时通过判定 ⇒ 同 `task_key` 双写；`mw_common.upsert_worker_row` 的覆盖写把行数压成 1（`mw_common.py:2152`），读回只数行数（`dispatch.py:1185-1196`）⇒ **行数=1 但 timeline 有 2 条 `dispatch` 事件**，今天被覆盖写掩盖。

`.mw/workers.lock` 是**两条通道共用**的同一把锁（conductor 侧即本文件，PM 侧 `WorkerStore.upsert` 自带），因此**不需要**新增 per-key 锁；反过来说，`dispatch()` 已经在锁内，本卡不应再取第二次锁（嵌套取锁在 RQ-D3 实测里退避累计到 14.6h 后抛 `RuntimeError`）。

## 写入允许面

- `packages/multi-workers/autopilot/dispatch.py`（唯一写者）
- `packages/multi-workers/test/test_write_face_dispatch.py`（新建）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/autopilot/write_face.py`（B0 已冻结，只读；需要新算子行为就报回 PM）、`packages/multi-workers/test/fixtures/write-face-corpus.json`（冻结契约，只读）、`packages/multi-workers/autopilot/conductor.py`（属 `mw-dynamic-concurrency` M-02）、`packages/multi-workers/mw_common.py`（**其它 session 正在追加此文件**，本卡不得修改；需要它改变语义就报回 PM）、`packages/coding-agent/**`（属 W-04/W-05）。

## 要求

1. **判定必须在已持的那一次锁内**（AC-014）。把 `task.md` 的创建从 `dispatch.py:1132` 移到 `acquire_lock` 成功**之后**；锁内顺序 = 读队列 → 判重叠 → 建 taskDir/task.md → `upsert_worker_row`。锁内读队列用**无锁读取器**（`mw_common.parse_workers_file`），**不得**再调 `acquire_lock`/`mw_common` 里任何自带取锁的写入器（除 `upsert_worker_row`）。

2. **本任务的写面来源**：从已渲染的 `content` 文本头部解析（`parse_write_face(content, base=..., case_insensitive=...)`），不要另读文件。三态：缺头 → 未声明；有头但空 → 解析拒绝；非空 → 正常。

3. **在飞集合在判定时重算**（AC-008）：用锁内即时读到的 `_workers.parallel` 行，筛出**同 key**（`owner`）且**非终态**（沿用仓内既有终态集合的唯一定义，`rg` 定位并引用坐标；不要自造集合）且不与本次 `task_key` 同名的行。**不加队列列**（`WORKER_COLS_MAX=9` 保持）。

4. **拒绝条件分两档**：
   - **自身写面非法**（`write-face-empty` / `write-face-invalid-entry` / `write-face-escape` / `write-face-outside-base`）⇒ 无条件拒绝，零副作用。
   - **与在飞 worker 的可证重叠** ⇒ 只有**双方都已声明**时才拒绝：code `write-face-overlap`，附 `overlap-with:<task_key>` 与一个**冲突样例路径**（来自算子的 witness，必须是 glob-free 的字面路径）。任一侧未声明 ⇒ **不**按重叠拒绝（D-003）。
   - 算子的 `Unsupported` 保守回退（`§3.2` 清单）**按重叠处理**（D-006：任一侧命中即判重叠，不得静默判无交集）。

5. **未声明（D-003）= serial-only 且不拒绝派发**：写一条 `write-face-undeclared` 审计行（timeline），并在"存在同 key 非终态在飞行"时不放行本次并行（返回零副作用的未派发结果，**不得**把任务标成 rejected、不得写队列行）。**前置审计（必做）**：`rg` 枚举 `dispatch()` 的全部调用点，标出哪些属于"一次性、失败即中止、无重试"的内部派发（card-less：L3/repair/roadmap/phase-writer）。若这类路径存在，则对它们**不施加**未声明串行化（只写审计行、照常派发）——因为拒绝一个不被重试的派发等于制造永久失败。该判断必须在证据文件里带 `file:line` 坐标列出；若审计结论是"全部调用点都会在失败后重试"，则写明依据并实施串行化。

6. **refusal 必须零副作用**（D-008/AC-002）：不建 taskDir、不写 task.md、不写队列行。因此拒绝分支必须在 `task_dir.mkdir(...)` 之前返回。`DispatchResult` 的既有字段形状不变（`ok=False` + `reason`），`reason` 用稳定 code 前缀。**注意副作用面变化**：`task.md` 移入锁内后，`lock-unavailable` 分支（`dispatch.py:1157-1164`）返回的 `task_md` 变成"不会存在的路径"——保持字段类型不变，但要在证据文件里写明这一处语义变化（RQ-D3 §2 只影响 `DispatchResult.task_md` 与 `lock-unavailable`）。

7. **基准与大小写显式传入**：`base` = 与 `mw_common.workers_path(project_root)` 同一基准（即 `project_root`，`.agenticdoc` 的父目录）；**实测** conductor 调用点传入的是什么并写进证据。`case_insensitive` 由调用点显式传入（`os.name == "nt"` 的单一 helper），不用算子内部的平台默认。`\` 一律视为分隔符（由算子负责）。

8. **不得改变**：既有 `reject(...)` 族 code 的语义与优先级、`synthesized_card` 行为、渲染形状（除新增 `write_face:` 头行的渲染，见第 9 条）、读回校验、`origin` 语义、`mw_common` 的任何函数。

9. **渲染侧（同文件）**：卡 envelope 的「写入允许面」要渲染成 task.md 头的一行 `write_face: a, b`（单一 `/`、`,` 分隔、去掉条目首尾空格；`-` 表示未声明）。渲染与解析必须**同源**（渲染结果再过一遍 `parse_write_face` 必须得到与输入等价的集合，用测试锁住）。`## 写入允许面` 标题体本身**不**参与渲染。

10. **并发安全基线**（本卡的验收判据，不是"行数"）：今天"行数=1"恒成立、无判别力。要用**双进程对拍**：两个进程同时 `dispatch()` 同 `task_key` 同 key，合格判据 = `ok=True` 的个数恰为 1 **且** timeline 里 `dispatch` 事件恰为 1 条（RQ-D3 实测：改前 2 事件 / 1 行；锁内判定的形状原型 5 次运行全 `grants=1/refusals=1/rows=1`）。

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-write-face-guard/evidence/W-03-dispatch-refusal.md`（含 上文 §10 的双进程对拍原始输出、锁内临界区 before/after 行号、零副作用目录快照 diff、调用点审计表）
- 代码：`autopilot/dispatch.py` 的改动 + 新测试文件 `test/test_write_face_dispatch.py`
- 测试结论必须是**实跑原文**（命令 + 尾部计数），不许写推算值

## 验收命令

```bash
cd packages/multi-workers; python -m pytest -q
```

同时必须单独跑一次本卡的新文件确认它是真被执行（不是被跳过）：
```bash
cd packages/multi-workers; python -m pytest test/test_write_face_dispatch.py -q
```

## 改动历史

证据文件里必须给出 `## 改动历史`：每个改动点的 `file:line` before→after。`dispatch.py` 的改动是**在既有函数体内插桩 + 移动 task.md 创建**，必须逐处列出（不能写"见 diff"）。新测试文件写"新建"。

## 硬约束

- 只用顶层 import；不写内联动态 import。
- 不新增第三方依赖。
- `dispatch.py` 是跨 key 热文件：动手前先 `git diff --stat -- packages/multi-workers/autopilot/dispatch.py` 确认工作区没有其它 session 的未提交改动；若有，**停下报回 PM**，不要覆盖。
- 不跑仓库根 `npm run check`（多 session 下它会全仓 `biome --write`）；本卡是纯 Python，只跑 pytest。
- 测试不许 mock 掉锁：对拍必须是两个真实进程/两次真实 `dispatch()` 调用。
