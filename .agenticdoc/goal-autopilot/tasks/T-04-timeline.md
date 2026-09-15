# Task T-04: timeline.py（时间线追加/查询/轮转）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t04-timeline
- ac_refs: [AC-017]
- vc_refs: [VC-019, VC-021]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/timeline.py`（D-109）。

- 文件：`.agenticdoc/_autopilot/timeline.jsonl`，每行 `{"ts": iso8601, "seq": int, "ev": str, "key": str, "stage": int|null, "detail": str}`
- **seq 单调递增**：conductor 唯一写者；启动时从文件尾行恢复计数；同 ts 多事件靠 seq 去重排序
- **key 哨兵**：key 级事件填 key；stage 级/全局事件填 stage 编号或 `-`，**不为 null**（AC-017 erratum）
- 事件类型枚举：`beat|dispatch|worker-terminal|advance|gate-created|gate-answered|stalled|skip|stage-close|config|goal-halt|goal-snapshot|type-rejected|reconcile`
- **beat**：每 tick 一条（默认视图过滤）
- **轮转**：10MB 阈值保 2 代；轮转文件只追加不回写；重命名原子；当前文件只追加
- **查询/回放**：轮转文件（旧→新）→ 当前文件；过滤 `seq > watermark`；按 seq 升序；watermark 对应 seq 早于最旧保留行 → 返回 pruned 提示（「N events pruned（超 2 代轮转）」，不静默缺失）
- 追加失败（磁盘满等）不抛出到调用方主循环——记录 stderr，tick 继续（追加失败不中断 tick，§9）

注意：
- UTF-8 + newline 对称追加（open 'a' 模式 + 显式 encoding；勿引入 \r\n 双写）
- 查询接口供 console（TS 侧读同一文件，本模块只提供 Python 侧读取；TS 侧解析在 T-15）

## 输入
- 依赖文件: 无
- 依赖 Task: T-02（包结构）
- AC 约束:
  > AC-017: 在 conductor 发生状态转换（phase 推进 / worker 派发与完成 / gate 生成与回答 / stalled / skip）的条件下，事件时间线文件对每个事件追加 ≥1 行条目（含时间戳与 key 标识），条目追加与 console 是否打开无关
  > AC-019: 在 conductor 存活期间，以时间线/日志循环节拍度量：任意 60s 观测窗内 ≥ 12 个节拍事件（最大轮询间隔 ≤ 5s）
- 设计约束:
  > D-109: 单文件 + beat + 轮转 + seq/watermark 协议全文

## 预期产出
- `packages/multi-workers/autopilot/timeline.py`
- `packages/multi-workers/test_autopilot_timeline.py`：
  - 追加 + seq 恢复（重启后续号不回退、不重复）
  - key 字段非 null（哨兵 `-` / stage 编号）
  - 轮转：超阈值改名、回放顺序旧→新→当前、watermark 过滤、超代 pruned 提示
  - 追加失败注入 → 不抛出（tick 容错语义）
- 验证方式: `[VERIFY] VC-019: event_lines>=1 ... key_field_no_null=true`（转移矩阵全类型由 T-10 conductor 测试覆盖，本 task 验格式与轮转协议）
- 验证等级: Level 1（VC-021 60s 窗计时在 T-16）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 11:58 | 实现 `autopilot/timeline.py`（append/seq 尾行恢复/key 哨兵/10MB×2 代轮转/watermark 回放+pruned 提示/§9 追加容错）+ `test_autopilot_timeline.py` | 16/16 测试通过，[VERIFY] VC-019 ×16 行（event_lines=14 per_type=all, key_field_no_null=true, seq_monotonic=true, auto_threshold_rotate, pruned_notice 等）；转移矩阵全类型留待 T-10 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 测试期望错误 | test_autopilot_timeline.py:76 | `AssertionError: assert ['dispatch'] == ['dispatch', 'some-future-event']` — ev_filter 为 include-set 语义，枚举过滤集合同时滤除未知 ev，断言误期望未知类型保留 | 已修复：断言改为 include-set 语义（无过滤时未知 ev 保留，枚举过滤时滤除） |

### PM 验收备注（2026-09-10 13:30）
亲跡 16 passed + [VERIFY] ×16 复核；代码走查：seq 尾行恢复（增长窗口 + 撕裂行回退）、轮转链纯 rename 不回写、pruned 计数不静默（空链非零 watermark 给下界）、§9 容错（失败不抛出不耗 seq）、撕裂尾行补换行隔离——均超任务书基线要求。append 接口签名（Timeline.append(ev, key, stage, detail) -> int|None）确认为 T-06 消费契约。验收通过。

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
