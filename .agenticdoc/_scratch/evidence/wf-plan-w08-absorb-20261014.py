"""Record (a) plan.md section 7.3 = W-08 absorption + the two parity gaps the PM
found by reading, (b) design.md ruling D-114 (queue file single writer) and the
open decision for AC-003 on the PM channel."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")
DESIGN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\design.md")

PLAN_ADD = """
### 7.3 W-08 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-pm-gate.test.ts` = **19 passed**；`test/suite/write-face.test.ts` = **109 passed**；`npx tsgo --noEmit` 由 worker 报 0 错误（未复跑）。B1 两半（conductor `dispatch.py` + PM `pm/{ui-bridge,task-dispatcher}.ts`）现已同形。
- **PM 修掉了本 key 弄红的一条既有冻结断言**（W-08 报回的两处卡面缺陷，我认）：卡面把验收路径写成不存在的 `test/suite/agent-team-loop.test.ts`，而真正会因新增头行变红的是 `test/suite/dispatch-card-injection.test.ts`（byte-exact 头断言）。PM 自跑确认 `1 failed / 17 passed`（`+ write_face: 仅本任务目录。`），按 `write_face:` 头行把**期望值**同步为 `writeFaceLine` 常量 + prologue 数组一项（不动断言逻辑），复跑 **18 passed**。该文件不是任何活跃 worker 的写面（`git status` 干净、mtime 10-13 00:53）。
- **PM 读码对照出的两处真实分歧（测试未覆盖，非 W-08 越界）**：
  1. **拒绝分支 `reason` 丢算子 detail**。Python `_write_face_verdict`（`dispatch.py:1169`）：`reason = f"{parsed.code}: {parsed.detail}"`，而 `Refused.detail` 带 `entry '<raw>'` / `present-but-empty write_face head`（`write_face.py:654/668/674/685`）。TS 侧 `writeFaceVerdict`（`pm/task-dispatcher.ts` rejected 分支）只回 `code`，`detail` 退化为 `${taskKey}: ${code}` ⇒ 两通道对同一非法输入给出**不同的 reason 串**（`code` 相同）。根因：TS 算子 `WriteFaceParseResult` 的 `rejected` 变体只有 `code`（`shared/write-face.ts:134/514`），不带 raw entry。
  2. **PM 通道对任何拒绝都不留持久审计记录**（见 design 未决项）：Python 有 `_write_face_audit` → `.autopilot/timeline.jsonl`（事件 `write-face-rejected`/`-overlap`/`-undeclared`，`dispatch.py:1089/1164/1183/1230`）；TS 侧只有 timeline 的**读**入口（`autopilot/status-model.ts` 的路径/解析），W-08 把 PM 的审计出口定成 `DispatchOutcome` 返回值，但 `pm/pm-orchestrator.ts` 仍忽略该返回值（W-08 残留 2）⇒ **AC-003「拒绝/降级须写审计行」今日只在 conductor 通道成立**。
- **队列单写者偏离已裁定**：W-08 因写入面限制在 `task-dispatcher.ts` 内复制了 `WorkerStore.upsert` 的字节镜像（`upsertQueueRowLocked`，`task-dispatcher.ts:521`），并用结构化视图读 `WorkerStore` 私有 `filePath`/`lockPath`。裁定见 D-114；跟进卡 `wfg-i09-queue-single-writer` 已派。
- **计数偏乐观（未修，待 orchestrator 释放）**：`pm-orchestrator.ts` 的 `dispatchNewTasks` / `dispatchOrphanCandidates` 忽略 `DispatchOutcome`，被拒仍 `queued += 1`（下一轮扫描自愈，但计数误导）。该文件属另一 key 的读回投递话题范围，暂不派卡。
- **W-08 自报的既有红项**（T-17 anchor、worker-file-tool `trace.log`、mwds-t02 语料、mwds-t23 bundle sha）未由 PM 复跑，按"与写面路径无关"接受，不据此判分。
"""

DESIGN_ADD = """
## 追加裁定（2026-10-14，B1 收口后）

- **D-114（队列文件单写者）**：`.agenticdoc/_workers.parallel` 的任何写入**必须经由 `WorkerStore` 的同一实现**，包括在已持 `.mw/workers.lock` 时的写入路径。W-08 在 `pm/task-dispatcher.ts` 内复制了一份 `WorkerStore.upsert` 的字节镜像（`upsertQueueRowLocked`：9 列 ` | `、origin 末列、原地替换、`# mw-queue:v2`）以满足"判定与写行同一临界区"——判定与写行同临界区是**对的**（AC-008/AC-014），但复制写实现**违反 D-005 的精神**：行格式一旦在两侧漂移，队列文件就会出现两种合法形态，而解析器只有一份。**要求**：`shared/worker-store.ts` 暴露一个"已持锁时可用"的写入入口（命名如 `upsertWithinLock`，语义与 `upsert` 逐字节一致，只跳过取锁），`task-dispatcher.ts` 删掉镜像并改调该入口；不得以"结构化读私有字段"替代正式入口。跟进卡：`wfg-i09-queue-single-writer`。
- **未决（AC-003 在 PM 通道的落地方式，需用户/后续 key 定夺）**：PM 通道今日对拒绝**不留任何持久审计记录**（事实与证据见 `plan.md` §7.3）。候选：
  - (a) 由 `pm/pm-orchestrator.ts` 消费 `DispatchOutcome`，在 PM 可见面（watch/日志）落一条拒绝记录。**阻塞点**：该文件正处另一 key（读回投递 scope）话题范围内，需等其释放写权。
  - (b) 在 TS 侧补一个 conductor 同形的 timeline 写入口（`.autopilot/timeline.jsonl`，事件名逐字同 `write-face-rejected`/`-overlap`/`-undeclared`），PM 拒绝直接落同一条时间线；与 (a) 不互斥。
  - PM 倾向 (b) 直接消除通道差异，但 (b) 会新增"谁写 `.autopilot/**`"的写者（今日只有 Python conductor 写），需先确认不与 `.autopilot` 的既有所有权冲突。
"""

for path, add, marker in ((PLAN, PLAN_ADD, "### 7.3 W-08 终态吸收"), (DESIGN, DESIGN_ADD, "D-114（队列文件单写者）")):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n" + add, encoding="utf-8")
        print(f"{path.name}: appended")
    else:
        print(f"{path.name}: already recorded")
    print(f"  lines={len(text.splitlines())} bytes={len(text.encode('utf-8'))}")
