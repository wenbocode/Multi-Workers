# Spec-time research declaration (RQ0): mw-usage-monitor

- Date: 2026-10-19
- Status: declaration note (zero completed research at spec v0.1; 4 RQs dispatched immediately after)

## 为什么先有 spec 再有证据

dispatch gate 要求 key 先具备 spec.md（§0 Goal Alignment + 编号 AC）与至少一份 research note。
本文件是那份 note：声明 spec v0.1 的**事实基座**只有 PM 已实测的两条，其余全部交给并行 research，
回读后按证据修订 spec（不把推测写成需求）。

## PM 已实测的事实（可直接引用，不需要 research 复核）

- F-1 pi 会话 JSONL：`~/.pi/agent/sessions/<项目slug>/*.jsonl`，本机 4065 个；assistant 消息记录带
  `model` / `provider` / `usage{input,output,cacheRead,cacheWrite,totalTokens,cost,cacheWrite1h}` / `timestamp`。
  样本：`C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\2026-10-16T03-51-18-331Z_01a142d5-ec3b-747d-b5a8-25ec12206686.jsonl`
  第 6/9/12 行（assistant，`provider=timi`，`model=deepseek-v4.1-flash`）。
- F-2 pi CLI 提供 `--session` / `--session-id` / `--session-dir`（`packages/coding-agent/src/cli/args.ts:108,110,114`）
  与环境变量 `PI_CODING_AGENT_SESSION_DIR`（`packages/coding-agent/src/config.ts`，`ENV_SESSION_DIR`）；
  launcher 已用 `Popen` + `poll()` / `returncode` supervise worker（`packages/multi-workers/launcher.py:2317,2157,2162`）。
- F-3 仓库当前没有任何 `mw usage/stats/monitor` 命令（`packages/multi-workers/mw.py` argparse 子命令全表已核）。

## RQ 派发明细（互不重叠、唯一证据文件）

| RQ | 问题 | 唯一证据文件 | 阻塞的 spec 条目 |
| --- | --- | --- | --- |
| RQ1 | pi usage 全貌 + worker/PM 确定性归因 + 扫描成本 | `evidence/research/spec-rq1-pi-session-usage-20261019.md` | §2 口径、§3 采集、AC-002/AC-005 |
| RQ2 | 派发链路元数据与墙钟时间点、台账钩子 | `evidence/research/spec-rq2-dispatch-lifecycle-20261019.md` | §3 台账、AC-001/AC-004 |
| RQ3 | codex/claude CLI 日志可统计性与降级 | `evidence/research/spec-rq3-cli-worker-logs-20261019.md` | AC-007、范围边界 |
| RQ4 | `mw stats` 落位 / `/mw stats` 转发 / 机器级存储与并发写 | `evidence/research/spec-rq4-surface-storage-20261019.md` | §3 交付面、AC-003/AC-006/AC-009 |

## 回读后的处置规则

- 每条 spec 事实项必须能追到 RQ 证据的 `文件:行号` 或实测数值；追不到的降级为「待验证」而不是写成断言。
- 若 RQ 结论推翻 spec v0.1 的某条（例如 `--session-id` 无法固定、`~/.mw` 与既有约定冲突），修订 spec 并在
  pm-state 记录决策，不走 design 前的静默改口径。
