"""Record plan.md section 7.4 = W-09 absorption (queue single writer, D-114)."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADD = """
### 7.4 W-09 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/worker-store.test.ts` + `test/suite/write-face-pm-gate.test.ts` = **38 passed**（19 + 19）；相邻 `write-face` / `dispatch-card-injection` / `mwds-t21-write-intent-soundness` = **140 passed**；`rg 'join(" | ")|upsertQueueRowLocked|serializeWorkerEntry' pm/task-dispatcher.ts` **无命中** ⇒ 第二份行拼接实现确已删净。
- **PM 补做了一项测试抓不到的核对（base 语义）**：`dispatchTask` 现在是 `writeFaceBase(path.dirname(store.queuePath))`，而 `store.queuePath` = `worker-store.ts:152` 的 `path.join(agenticdocRoot, "_workers.parallel")` ⇒ `writeFaceBase` = `resolve(agenticdocRoot, "..")` = **仓库根**，与 Python `write_face_base(project_root) = str(project_root)`（`dispatch.py:1016`，调用点 `:1452` 传 `project_root`）**同根**。这条必须用代码锚点核对：base 若错成 `.agenticdoc`，条目仍是原样字符串、往返/条目对照测试全都照样绿，但 `write-face-escape` / `write-face-outside-base` 的判定会与 conductor 分叉。
- **临界区形状保持**：`task-dispatcher.ts` 仍是 `acquireLock(store.lockFilePath)` → `writeFaceVerdict` → `injectWorkspaceProfile` → `store.upsertWithinLock(full)`，与 D-005/AC-014 一致；`WorkerStore.upsert`（`:208`）改为取锁 + 调 `upsertWithinLock`（`:225`，不取锁，docstring 写前置条件），D-114 落地。
- **残留（已记，未开卡）**：`upsertWithinLock` 是 public 方法，误用（非持锁调用）只靠 docstring + 测试约束；`pm-orchestrator.ts` 仍忽略 `DispatchOutcome`（被拒仍 `queued += 1`），与 §7.3 同题，等该文件写权释放。
- **B2 已派**：`wfg-i10-runtime-guard`（T-W-I10，D-007 IP-1b 运行期写面闸）。派发前实测 `worker/worker-mode.ts` 无活跃写者（`git status` 干净、mtime 2026-10-12 22:02），满足 plan §3 串行点 1 的前置检查。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.4 W-09 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.4")
else:
    print("plan: already has 7.4")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
