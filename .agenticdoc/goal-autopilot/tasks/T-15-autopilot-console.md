# Task T-15: /autopilot console（status-model / gate-writer / 命令集）

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t15-console
- ac_refs: [AC-015, AC-016, AC-018]
- vc_refs: [VC-017, VC-018, VC-020]
- pattern_refs: []

## 描述
新目录 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/`（console.ts / status-model.ts / gate-writer.ts）+ 改 `pm/pm-orchestrator.ts`（pmActivate 注册）。console 无状态，一切从文件推导（D-005）。

**status-model.ts**：
- 输入：_roadmap.md + gates 目录 + timeline.jsonl + _workers.parallel → 视图模型
- `/autopilot status --json` schema（版本化 `autopilot-status/1`，D-109 N8）：
  ```json
  {
    "schema": "autopilot-status/1",
    "stage": {"current": N, "status": "...", "keys": [
      {"key": "...", "phase": "...", "state": "running",
       "rounds": {"l2": {"used": 1, "max": 2}, "l3": {...}, "retry": {...}}}]},
    "gates": [{"id": "gate-0007", "kind": "stage-confirm", "status": "pending"}],
    "timeline": {"seq": 1234, "ts": "..."},
    "config": {"enabled": true, "poll_interval_sec": 4, "round_budget": 2,
               "max_parallel_keys": 2}
  }
  ```
- rounds used 从 task 目录 loop 标签推导（与 Python state.py 同源同推导规则——两侧各自实现同一文件推导，VC-020 parity 锁定）、max 从 config
- 人读视图与 --json 同一推导函数产出（view parity）

**gate-writer.ts**：
- `/autopilot gate <id> approve|reject [--note <text>]`：`.mw/gates.lock`（O_CREAT|O_EXCL）下重写 gate frontmatter `status / answered_at / answered_by（窗口 claimId）/ note`

**console.ts 命令集**：
- `/autopilot status [--json]`（AC-015/018）
- `/autopilot gates`（未决列表）
- `/autopilot gate <id> approve|reject [--note]`（AC-016）
- `/autopilot timeline [--since <iso>] [--all]`（默认 last-seen 水位，beat 过滤；轮转旧→新回放；超代提示「N events pruned」）
- `/autopilot enable|disable`（写 config；enable 时若 mw 未运行则启动，AC-025）
- `/autopilot pause|resume`（写 config paused，进程存活暂停派发）
- `/autopilot roadmap`（摘要视图）
- 水位持久化：session entry `agent-team-loop:autopilot-seen`（与 WATCH_ENTRY_TYPE 同机制；新会话默认 0 或 --since）
- pmActivate 注册全部命令

## 输入
- 依赖文件: shared/paths.ts / index-store.ts / worker-store.ts / file-lock.ts；autopilot/_autopilot/ 文件族（roadmap/gates/timeline，S1/S2 产物）
- 依赖 Task: T-03~T-07（文件 schema 定型）、T-14（pm-orchestrator 增量先合入）
- AC 约束:
  > AC-015: 在 console 进程关闭后重新打开的条件下，console 在 10s 内仅凭文件（roadmap / 索引 / gate 队列 / 时间线）重建 stage 进度视图与未决 gate 队列，并按 last-seen 时间戳过滤回放离线期间事件；`/autopilot status --json` 输出同一状态集（stage 进度 / gate 队列 / 时间线水位），作为可机械校验面
  > AC-016: 在人工通过 `/autopilot gate <id> approve` 回答门禁的条件下，回答文件落盘后 conductor 在 1 个轮询间隔（≤5s）内读取并推进对应流程
  > AC-018: 在 console stage 视图打开的条件下，每个 key 显示其各回路（L1↔L2 / L3 / retry）已用轮数与剩余预算，数值与 `/autopilot status --json` 暴露的回合计数一致（持久化位置由 design 定义，--json 为唯一校验面）
- 设计约束:
  > D-005: console 无状态；断点重开 = 正常重开；离线事件按 last-seen 回放
  > D-109: seq/watermark/轮转协议；F10 覆盖点

## 预期产出
- `autopilot/console.ts` / `autopilot/status-model.ts` / `autopilot/gate-writer.ts`
- `pm/pm-orchestrator.ts` 改（注册）
- `packages/coding-agent/test/suite/autopilot-console.test.ts`（vitest，测试名含 VC 编号）：
  - --json 三字段（stage/gates/timeline）+ schema 版本串 + rounds 结构（VC-017）
  - 仅凭 fixture 文件重建视图（推导函数纯文件输入）+ 重建耗时 <10s
  - view parity：人读视图数值 == --json（VC-017）
  - rounds parity：TS 推导 == fixture 标注的 Python 侧推导结果（VC-020，同 task 目录双实现对照）
  - gate-writer：approve/reject 重写 frontmatter 四字段；锁互斥
  - timeline 回放：水位过滤、beat 过滤、--all、超代提示
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1（VC-018 消费时延在 T-16）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 | 实现 status-model.ts / gate-writer.ts / console.ts + pm-orchestrator 注册 + autopilot-console.test.ts（30 用例） | 定向 vitest 20/30 过，暴露 fixture ts 双秒号笔误、gates 列表断言、pruned 期望值错（均测试侧）与 gate-writer 空值丢冒号（实现侧）|
| 2 | 2026-09-10 | 修复 gate-writer 空值渲染为裸 `field:` 行；修正测试 fixture/期望；gates 列表 scope 同时展示 stage+key | 定向 vitest 30/30 全绿；Python 交叉验证：gates.py enumerate() 接受 TS 写入的 approve/reject 四字段（含 Z 形态 answered_at），timeline.py query_events 语义一致 |
| 3 | 2026-09-10 | npm run check：修复 readConfig 联合键赋值 TS2322（改为显式 boolOf/intOf 构造） | biome/pinned-deps/ts-imports/shrinkwrap/install-lock 全过，tsgo 仅剩 packages/ai 存量噪音（非本任务文件）|
| 4 | 2026-09-10 | 回归：autopilot-protocol + autopilot-read-scope + agent-team-loop 三套 | 29 + 90 全绿；定向 30 全绿 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| T15-E1 | 实现 bug | autopilot/gate-writer.ts (rewriteAnswerFields) | expect(after).toMatch(/^note:$/m) 失败：空 note 重写后丢失冒号（`note` 而非 `note:`）| 已修复：空值渲染为裸 `field:` 行，与 gates.py create() 形态一致 |
| T15-E2 | 类型错误 | autopilot/status-model.ts:165 (readConfig 合并循环) | error TS2322: Type 'number | boolean' is not assignable to type 'never'（联合键索引赋值）| 已修复：改为显式 boolOf/intOf 逐字段构造 |
| T15-E3 | 存量噪音 | packages/ai/**（test + providers） | tsgo --noEmit 存量错误（ModelId 字面量过期 / erasableSyntaxOnly / ProviderStreams 键），共 28 条 | 非本任务文件，按任务书如实报告不修 |

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —

### PM 验收备注（2026-09-10 17:50）
- 亲跑定向三套件 59/59（console 30 / protocol 10 / read-scope 19）；agent-team-loop 回归 90/90；npm run check 零新增（shrinkwrap/install-lock up to date，错误全为 packages/ai 存量 tsgo 噪音）
- 走查：pmActivate 顶层 import 注册 /autopilot（无 inline import）；命令集 status〔--json〕/gates/gate approve|reject --note/timeline〔--all|--since〕/enable/disable/pause/resume/roadmap 全落地；watermark 会话条目（AUTOPILOT_SEEN_ENTRY_TYPE，D-109 seq 协议）；gate-writer 四字段改写逐字节保留（含 CR）/gates.lock/renderScalar 镜像 _PLAIN_SCALAR_RE+AMBIGUOUS_SCALARS；usedRounds = loop 内 distinct attempt（与 state.py 同口径，D-111），VC-020 Python 探针结果已固化为测试标注
- git status 核对：仅预期文件（autopilot/ 3 新 + pm-orchestrator〔T-14+T-15 双任务〕+ 测试）；worker-mode.ts/read-scope.ts 未被本任务触碰（时间戳属 T-14/T-13）
- 中途检查点 risk=mid（30m）裁决继续等待：trace 尾部为 edit→test→fix 收敛循环，uniq_targets=6 与契约文件集精确吻合——事后确认任务在检查点后 8m 内收敛，判断正确

**结论：T-15 验收通过，S3（TS 侧）三任务全部收口。**
