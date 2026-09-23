# 现场恢复证据（AC-001 / AC-004 / AC-011）

- key: mw-autopilot-stall-feedback · T-09
- 现场: `H:\git\E2Feature`（control workspace）
- 采集: 2026-09-23 00:01–00:15（本地）

## 0. 恢复前的状态（承接 spec 证据链）

| 项 | 值 |
|----|----|
| key | `feature-params-service`（K2） |
| `_index.parallel` phase | `VERIFY` |
| roadmap key-status | `stalled`（21:43:24 起） |
| 门禁 | `gate-0002` kind=`stalled` status=`pending` |
| 停摆时长 | 约 2h18m（21:43 → 00:01）只有 heartbeat |
| 前置止损 | T-01：Phase 行规范化（21:35:41 `execute->verify exit=0`）+ `dispatch.yml` review 模型 id 修正 |

## 1. serve 重启（加载本 key 的 conductor 改动）

```
[mw stop] stopped PID 97648
[mw start] background PID: 102084
serve.meta: {"pid": 102084, "started_at_ms": 1790092888945, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}
conductor.pid: 102960 -> 109732
timeline: 16:01:29Z ev=goal-snapshot detail="startup baseline mtime_ns=1790046982584464900"
timeline: 16:01:37Z ev=beat seq=23619        # 心跳恢复
```

重启前确认：E2Feature 无 in-flight worker（`_workers.parallel` 无 `running` 行）；
被 import 的并发 key 脏文件（`mw.py` / `mw_common.py` / `launcher.py` / `autopilot/dispatch.py`）
先经 `python -m py_compile` 通过，且 packages/multi-workers 全包测试 818 passed。

## 2. 人工 approve `gate-0002`（不变量：不改任何配置，只回答门禁）

改写脚本：`workers/t9-live-recovery/approve_gate.py`（字节级，只动 4 个 frontmatter 标量，678 → 760 B）：

```
status: approved
answered_at: 2026-09-22T16:01:56+00:00
answered_by: human-pm-window
note: approved - resume with one extra round
```

## 3. 下一个 tick 的行为（正式恢复路径，零配置改动）

```
16:01:57Z seq=23625 ev=gate-answered key=feature-params-service detail="gate-0002 approved → feature-params-service running"
16:01:57Z seq=23626 ev=resume        key=feature-params-service detail="feature-params-service resumed by gate-0002 (one extra round granted)"
16:01:57Z seq=23627 ev=dispatch      key=feature-params-service detail="ap-feature-params-service-repair-a2-a2 type=repair loop=repair:feature-params-service attempt=2"
roadmap: > key-status: feature-viewer-mvp=done, feature-params-service=running, ...
```

要点：

1. `gate-answered` 的措辞与 `resume` 事件都是本 key 新增代码的产物（改动前 approve 是 no-op）；
2. roadmap 从 `stalled` 回到 `running`，即 `_apply_stalled_approvals` 的复位生效；
3. 额度的效果可见：L3 预算为 `round_budget(2) + credits(1) = 3`，因此 used=2 时不再立即 `mark_stalled`，
   而是继续该回路的修复/复评（本 tick 派出 `repair-a2-a2`，对应 L3 第 2 轮的修复动作）；
4. 该 tick 之后 key 处于 `running` + in-flight worker，后续由 conductor 继续推进 VERIFY 回路。

## 4. 运行中的状态（采集时刻 00:10:45）

| 项 | 值 |
|----|----|
| in-flight | `ap-feature-params-service-repair-a2-a2`（running，trace.log 持续增长，正在重跑 verify_params.py 取证） |
| timeline | 无新的 advance 失败（本轮不再空转） |
| 已知偏差 | E2Feature 运行的是 16:01:29Z 代码快照，`_l3_round_verdict` 的「worker 状态优先」修正（16:05 落地）未加载，故本轮 L3 第 2 轮按「占位 output.md → below」走了 repair 分支；下一次 serve 重启即生效 |

## 5. 同期旁证：AC-012 在真实 worker 上再次发生（本 key 自己的复核 worker）

派给本 key 的只读复核 worker `mw-stall-feedback-l3-review` 也落在了同一个坑里：

```
worker.log: [worker] start task=mw-stall-feedback-l3-review type=review
            [worker] done exit=0 elapsed=8m tools=77
            stream closed before response.completed        <- provider 流提前结束
output.md : 264 B，内容是 harness 占位模板（"Task completed. Tools used: find, grep, read (77 calls)."）
_workers.parallel: mw-stall-feedback-l3-review | failed
```

即：worker 进程 exit=0、但**从未产出结论**，harness 仍写了 `output.md`。
若按「文件存在即裁决」的旧规则，这一轮会被读成 verdict（无 FAIL 小节 → `below`），于是派 repair 去修一份空报告；
本 key 的 `_l3_round_verdict` 以队列表状态优先，判为 `no-verdict` + `L3 无裁决（worker failed: …）`。
处置：ack 后在收窄范围下重派 `mw-stall-feedback-l3-review-a2`（只读、≤12 个片段、不跑测试）。

## 6. 结论

- AC-004（approve → 复位 + 恢复一轮）在真实现场**成立**（事件 + roadmap + 额度三处证据）。
- AC-011（并发边界留痕）：本恢复过程未修改 E2Feature 的任何配置（仅回答门禁），也未触碰 Multi-Workers 中并发 key 的文件；`dist/` 重建仍待对方提交。
- AC-001（K2 走完 VERIFY → done → K3 解锁）在本文件中标记为**进行中**：剩余路径 = repair → `l3-a3`(reviewer，模型已修正) → meets → done 事务 → K3 派发；若 `l3-a3` 再崩，新代码会以 `L3 无裁决（worker <status>: <task_key>）` 明确升级而不是报 `below`。
