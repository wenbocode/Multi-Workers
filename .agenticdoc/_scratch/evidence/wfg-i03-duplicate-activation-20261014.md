# 事故取证：同一 task_key 被重复激活 12 次（wfg-i03，2026-10-14）

- 状态：**已取证、根因部分定案（机制层已定，触发者未定）、待修，未修复**
- 观察窗口：2026-10-14 03:06:18Z–03:40:29Z（本地 11:06–11:40）
- 涉及任务：`.agenticdoc/mw-write-face-guard/workers/wfg-i03-dispatch-refusal/`
- 记录者：PM（本窗口），取证方式：磁盘事实 + 代码锚点，**无一处依赖 worker 自述**
- 关联：P-028（假崩溃块家族）、P-033（spawn 阶段闸门）、`readback-push-scope-gap-20261014.md`（同源家族，不动）

## 0. 一句话结论

`wfg-i03` 的**真实实例从未崩溃**（pid 95260，03:06:18→03:40:27，34 分钟，exit 0，status=done）；
另有 **12 个进程以同一 `task_key` 重复进入了 Worker 模式**，各自写 `[START]`、覆盖 `run.json`、
并在退出时把自己那块"无产出即失败"的块写进**同一个 `output.md`**；这些副本在绑定模型之前就消失。
PM 当时看到的"崩溃块堆叠 + 长时间不落盘"全部来自这 12 个副本，不是真身卡住。

## 1. 现象（PM 最初看到的，含我自己的误判）

- `output.md` 末尾是 `status=failed` 的块，看起来像"worker 反复崩溃"。
- `trace.log` 有 26 行 `[START]`（= 13 次成对），远超一次派发应有的 2 行。
- `worker.log` 只有 `[worker] start`，长时间没有 `done`。
- `run.json` 长期停在 `status=running`，`pid` 却是 95260。
- PM 的误判（已作废）：把它读成"worker 崩溃重启循环 / 空转"，并据此怀疑 worker 质量。**错在只看 `output.md` 的尾部块，没有先读 `run.json`。**

## 2. 时间线（全部来自磁盘，可复核）

| 事件 | 证据 |
|---|---|
| 03:06:18.718Z 真身派发 | `run.json.run_id = wfg-i03-dispatch-refusal@2026-10-14T03:06:18.718Z`，`pid=95260` |
| 03:06:18.722Z 真身激活 | `trace.log`：`[START] pid=95260` / `[START] …03:06:18.722Z task=… type=coding phases=-`；随后 `[MODEL] 03:06:18.806Z` |
| 03:10:55.285Z **撕裂态**（见 §4） | 当时读到 `run.json`：`ended_at=03:10:55.285Z`、`exit=0`，但 `status=running`、`last_heartbeat_at=03:10:43.761Z` |
| 03:11:56–03:36:28 **12 次重复激活** | 12 对 `[START]` 行 + 12 个 `mw-run … status=failed` 块（见 §3 表） |
| 期间每 30s 心跳不断 | `trace.log` HEARTBEAT 序列在 03:11:18→03:36:18 连续，**只有真身在写**（副本没有心跳） |
| 03:40:19Z 最后心跳 / 03:40:27Z 真身正常收尾 | `run.json`：`last_heartbeat_at=03:40:19`、`ended_at=03:40:27`、`status=done`、`exit=0`，`artifacts=[output.md, progress.md]` |
| 03:40:29Z 队列行收敛 | 队列行 `wfg-i03-dispatch-refusal` → `done`，`updated_at=03:40:29` |

### 3. 13 次激活 + 13 个运行块（1 真 12 副本）

| # | pid | `[START]` 时间 | `output.md` 块 run_id | 块状态 |
|---|---|---|---|---|
| 1 | 95260 | 03:06:18.722Z | …@03:06:18.718Z | **done（真身）** |
| 2 | 141048 | 03:11:56.159Z | …@03:11:56.158Z | failed |
| 3 | 158052 | 03:14:38.144Z | …@03:14:38.143Z | failed |
| 4 | 170460 | 03:16:08.951Z | …@03:16:08.950Z | failed |
| 5 | 40472 | 03:16:12.548Z | …@03:16:12.547Z | failed |
| 6 | 23812 | 03:23:19.640Z | …@03:23:19.639Z | failed |
| 7 | 94608 | 03:26:14.821Z | …@03:26:14.820Z | failed |
| 8 | 150208 | 03:27:43.207Z | …@03:27:43.206Z | failed |
| 9 | 154380 | 03:27:47.324Z | …@03:27:47.323Z | failed |
| 10 | 156032 | 03:31:25.746Z | …@03:31:25.744Z | failed |
| 11 | 165788 | 03:34:18.236Z | …@03:34:18.233Z | failed |
| 12 | 6896 | 03:36:21.756Z | …@03:36:21.754Z | failed |
| 13 | 122904 | 03:36:28.555Z | …@03:36:28.553Z | failed |

**两条硬结论**（都来自上表的毫秒级对齐）：

1. 每个失败块的 `run_id` **恰好比同一次激活的 `[START]` 早 1 ms** ⇒ 块是**该进程自己**写的（它先覆盖 `run.json` 再写 START 行），**不是**外部崩溃检测器替它合成的。§5 之前的"检测器合成"猜测到此作废。
2. 副本**没有** `[MODEL]` 行、没有 `[TOOL]` 行、没有心跳 ⇒ 它们在"绑定模型"之前就退出，属于**激活后立即天折**，不是"跑了一段才崩"。

### 4. 撕裂态：`ended_at` 已写、`status` 仍是 `running`

03:10:55.285Z（**首次重复激活前 61 秒**）`run.json` 同时具备"结束记录"与"非终态状态"。
`ended_at`/`exit` 是结束路径才会写的字段，`status` 由 `writeRunState` 整体覆盖写入。
二者不一致说明至少有一个写入路径在**未把 status 落成终态**的前提下写了结束字段。
**这一条只做到"实测到该状态存在"，没有做到"定位到写入者"**，见 §6。

## 5. 排除表：这些都不是它干的（每条都有反证）

| 嫌疑 | 反证 |
|---|---|
| launcher 反复重派 | ① `worker.log` 由 `_spawn` 以 `"wb"` **截断写**（`launcher.py:1994`），文件里是成对的 `[worker] start` + `[worker] done exit=0 elapsed=34m tools=151` ⇒ 只发生过一次截断式 spawn；② 每次 spawn 后必调 `_update_status(..., "running")`（`launcher.py:2017`）→ `mw_common.update_status`（`mw_common.py:2175`）总会写新的 `updated_at`，而该行 `updated_at` 从 `03:06:16` 一直到 `03:40:29` 未变 ⇒ 期间无 spawn；③ `launcher.log` 里该任务只有一条 model 行 |
| conductor 孤儿重插 | 无 `_roadmap.md`；`timeline.jsonl` 中该任务事件数 0、orphan 事件 0，且 timeline 最后写入 10:59（早于窗口） |
| worker 自己的工具调用起了 `pi` | 151 条 `[TOOL]` 中无 `pi` / `pi-test` / `npx pi` / `cli.js` 调用 |
| 该任务新测试的子进程 | `test/test_write_face_dispatch.py:404` 起用 `sys.executable -c`（python），不加载 pi 扩展 |
| 普通子进程继承 env（通用路径） | 对照同形状任务：`woc-*` 11 个任务**全部 `starts=1`**；只有 wfg-i03 出现重复 |
| 12 个副本留下了 pi session | 全仓所有 `~/.pi/agent/sessions/*/` 目录在该窗口内只有本窗口 5 个任务 + 另一窗口 2 个任务的 session，**没有第 13 个** |
| PM 自己的 `pytest`（11:36 那轮） | 首次重复出现在 03:11:56，早于该轮 25 分钟 |

## 6. 机制层缺陷（这四条是代码可证的，也是真正的待修面）

1. **Worker 模式的激活只看一个继承来的环境变量，没有"同 task_key 是否已有活着的 run"守卫。**
   `worker-mode.ts:1891` 读 `process.env.PI_WORKER_TASK` → `:1909` 写 `[START] pid=` → `:1940` 覆盖 `run.json`。
   中间没有任何活性/唯一性判定。
2. **`PI_WORKER_TASK` 全仓只有 `launcher.py::_build_env` 会设置**（5 处，同一函数）。
   所以任何拿到该 env 的 pi 进程（**含继承来的**）都会被当成"同一任务的 worker run"。
3. **运行状态写入是无条件覆盖。** `writeRunState` 是 tmp+rename 的整对象覆盖，没有"该任务已有 active run 就不许覆盖"的判定；
   注释里声称的"终态任务不可重启"实际只由**派发侧**的 AC-022 门实现，**激活侧没有**。
   同理 `output.md` 的追加/覆盖也没有"别的 run 正活着"的检查 ⇒ 副本可以把失败块贴进真身的产物。
4. **三层都不报警。** launcher 的 `running_procs` 去重（`launcher.py:2009`）只是**本进程内存**，跨进程无效；
   崩溃/无产出兜底只看"本进程有没有写 output"，不校验该任务是否已有终态 run。
   于是"重复激活 → 覆盖 run.json → 追加失败块 → 无人拒绝"是**完全静默**的。

## 7. 未定论的一点 + 现场捕获器（定案所需）

**未定论：是哪个组件启动了这 12 个进程。** 已知约束：它们必须是 pi 进程（否则不会加载扩展、不会写 START 行），
且**不落 session 文件**（全 session 目录无第 13 个），并且不经 launcher（§5 三条反证）。
唯一"能拿到 `PI_WORKER_TASK`"的途径是**继承自真身进程**；但真身内部我只找到 3 类子进程
（`mw.py`、RAG bridge 的 python、bash 工具的 shell），**没有一处会起 pi**。
⇒ 要么 pi **core** 里还有一条"再起一个 pi"的路径（本轮只覆盖了 `process.execPath`/`spawn` 的主要点，未穷举），
要么存在一个我没想到的派发侧路径。**Windows pid 会被回收，所以事后查父进程已失效，必须现场抓。**

**现场捕获器（建议实现物，`mw-duplicate-activation` 修复卡的第一步）**：
轮询 `.agenticdoc/*/workers/*/trace.log`，一发现**新**的 `^\[START\] pid=(\d+)` 就立刻对该 pid 抓
`Win32_Process.ProcessId/ParentProcessId/CommandLine/CreationDate` + 其父进程的 `CommandLine` 落盘，
然后渲染成 `parent → child` 树。现象只在"跑到 30 分钟量级"的长任务上出现过，所以挂上它等下一次即可定案。

## 8. 待修项（编号给后续 key 用；本轮**未修任何一条**）

- **RF-1｜激活期唯一性闸（最重要）**：Worker 模式激活时，若该 task 的 `run.json` 显示**已有活着的 run**
  （或队列行已是终态/已 ack），必须**拒绝激活**并留一行机器可读拒绝原因，而不是覆盖状态与产物。
  要覆盖跨进程（launcher 的内存去重不够）。
- **RF-2｜`writeRunState` 加前置条件**：覆盖已有 active run 的 run.json 需要显式 takeover 语义；
  顺带修 §4 的撕裂态（`ended_at` 与 `status` 必须同一次写里保持一致）。
- **RF-3｜产物写入归属校验**：`output.md` 的失败/兜底块只能写进**该进程自己的 run**对应的产物段，
  不得把 `failed` 块贴到别的 run（尤其已终态的 run）的产物尾部。这条同时是 P-028 的正解。
- **RF-4｜重复激活的可见性**：同一 task_key 在一次派发周期内出现 ≥2 次激活时，应向 PM/conductor 发一条告警
  （当前完全静默，PM 只能靠数 START 行发现）。
- **关联但独立**：`readback-push-scope-gap-20261014.md`（终态回读不推送）——同一"回读/归属"家族，不并入本条。

## 9. 影响面（含对 PM 决策的污染）

- **产物污染**：`output.md` 尾部 12 个假 `failed` 块（4,470 B 里绝大半）；`run.json` 被 12 次覆盖（最后一次由真身修正回 done）。
- **误判成本**：PM 据假象判定"worker 崩溃重启循环、无法收敛"，并把该任务挂在"等用户决定是否终止"上，
  实际真身一直在正常工作、交付完整（25 个测试全绿、证据文件 `W-03-dispatch-refusal.md` 19,849 B 已写）。
- **不受影响**：该任务的代码交付与包级验收结果有效；`output.md` 是 `progress.md`/`run.json` 之外的展示面，
  真值应以 `run.json` 为准（与 P-028 同一条读法规则）。

## 10. 复核方式（任何人可重跑）

```powershell
cd H:/git/Multi-Workers/.agenticdoc/mw-write-face-guard/workers/wfg-i03-dispatch-refusal
# 1) 13 次激活（pid + 时间）
python -c "import re,pathlib; L=pathlib.Path('trace.log').read_text(encoding='utf-8',errors='replace').splitlines(); ..."
# 2) 13 个运行块（12 failed + 1 done）
Select-String -Path output.md -Pattern 'mw-run:' | ForEach-Object { $_.Line.Trim() }
# 3) 真身只 spawn 一次（成对 start/done + 单条 launcher model 行）
Get-Content worker.log;  Select-String -Path ../../../.mw/launcher.log -Pattern 'wfg-i03'
# 4) 对照：其它任务 starts=1
Get-ChildItem ../../../mw-worker-output-contract/workers -Directory | ForEach-Object { ... trace.log START 计数 ... }
```

辅助脚本（本轮新建，可复用）：`.agenticdoc/_scratch/evidence/start-context-20261014.py`（打印每次 START 的上下文）、
`.agenticdoc/_scratch/evidence/launcher-spawn-sites-20261014.py`（定位 `PI_WORKER_TASK` 全部写入点与唯一 spawn 点）。

## 追加实例 2（2026-10-14，key `mw-dynamic-concurrency`，任务 `mdc-m02-conductor-frontier`）

同一签名再现，佐证 RF-1..RF-4 是框架级缺陷而非 `wfg-i03` 的一次性偶发：

- 主激活完整写出 `output.md`（M-02 报告 + 证据落盘）；
- 之后在 **09:01:00 / 09:03:38 / 09:04:58 / 09:05:01** 出现 **4 条** `<!-- mw-run: … status=failed -->` 块，内容均为
  "worker exited before output.md was written (crash or unexpected exit)"（即"未写 output 就退出"的短命激活）；
- 另有 1 条 **08:26:50 `status=done`** 的块（"已追加 CKPT 40m"，`writes=none`）出现在文件**末尾**，与时间序不一致 ⇒ 说明这些块由**不同激活各自 append**，顺序即竞态顺序；
- 与 `wfg-i03` 一致：多次激活共享同一個 `output.md`，每个激活各自写自己的运行块；本任务的 `task_key` 全生命周期只 dispatch 过一次（PM 侧 `list_tasks` 单一 terminal 行）。
