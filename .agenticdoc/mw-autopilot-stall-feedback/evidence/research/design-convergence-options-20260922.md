# 调研证据（design 阶段）：收敛机制与只读反馈的选型依据

- 时间：2026-09-22 23:55
- 关联 key：`mw-autopilot-stall-feedback`（design.md D-1..D-9 的出处）
- 代码库：`H:\git\Multi-Workers`（`packages/multi-workers` Python + `packages/coding-agent` 扩展 TS）

## 1. 现有机制盘点（可直接复用）

| 资产 | 位置 | 复用方式 |
|------|------|---------|
| `mark_stalled`（四件套：key-status / stalled 门禁 / achieved 遗留草稿 / `patterns/<key>/stall-lesson.md`） | `autopilot/conductor.py` | 停滞升级直接调用，不新增 kind |
| `_apply_stalled_rejections`（rejected → closed-legacy，并就地更新本次 tick 的 `status_of`） | 同上 | 设计对称的 `_apply_stalled_approvals` |
| `_budget_bonus` / `_budget_gate_rejected`（按 loop 标签在门禁里查额度状态） | 同上 | 额度恢复按 key 在**已批准 stalled 门禁**里查 |
| `rounds = state.used_rounds(...)`（按 task.md 的 loop+attempt 计数，无私有状态） | `autopilot/state.py` | 恢复额度直接加在预算上限上 |
| `gates.enumerate` 的 `Gate.kind/status/key/context_refs` | `autopilot/gates.py` | approve 恢复的判据（kind=stalled, status=approved, key 命中） |
| `timeline.query_events` / `_read_events` / `_tail_seq` | `autopilot/timeline.py` | 连击派生；尾部窗口读取沿用 `_tail_seq` 的「读文件尾 + 逐行容错」写法 |
| `autopilot/monitor.ts`（`MONITOR_WIDGET_ID`，只读，固定分节 + 110 列截断） | `packages/coding-agent/.../autopilot/` | 面板扩展点（不碰 `pm/ui-bridge.ts`，避免与并发 key 冲突） |
| `autopilot/status-model.ts`（`readConfig` / `readRoadmap` / `listGates` / `queryTimeline`） | 同上 | 新增派生函数的数据源 |

## 2. 被否决的方案

| 方案 | 否决原因 |
|------|---------|
| 新增 gate kind `advance-stuck` | `gates.py` 的 `GATE_KINDS` 与 TS 镜像必须同批次上线；旧解析器遇未知 kind 抛 `GateFormatError` → 整个 tick skip（比现状更坏）。`stalled` 语义已完全覆盖「无法推进」 |
| 在 framework 侧放宽 `advance_phase.py` 的 Phase 行解析（把 `EXECUTE（…）` 容错为 `execute`） | 跨仓（AgenticTask framework 是嵌套 clone，`.agents/skills/agentic-task`），属另一条根治路径；本 key 只做 mw 侧防呆与上报，是否改 framework 记 spec U-2 由用户另批 |
| 用内存计数器做连击判定 | 违反 GC-1（无私有状态）：conductor 重启即丢，且与「每 tick 从文件重派生」的既有契约（D-102）冲突 |
| 用固定次数的尝试上限（如最多 3 次）代替连击判定 | 会把「慢门禁」类临时失败也算进去，误伤正常推进；连击判定能被任何进展事件打断 |
| 停滞时直接 `closed-legacy` | 语义错误：无法推进 ≠ 遗留关闭；会绕过人工决策 |
| 自动探测恢复（冻结期间轮询重试） | 现场教训正是「静默空转」；恢复必须由人工 approve 触发（可审计） |
| 面板直接展示 `timeline.jsonl` 全文 / 新写状态文件 | 面板是只读视图；新写文件会产生第二事实源 |

## 3. 只读数据源与代价

- 连击派生需要 timeline 尾部（阈值 5 × 4s ≈ 20s，最多约 60 条事件即可覆盖）；用「读文件尾部 N 字节 + 逐行 JSON 容错」实现，避免每 tick 全量解析 4.14 MB / 21k 行（现状 `_consumed_gate_ids` 已是全量读，本 key 不加剧）。
- 面板侧（TS）同样只读：`config.json` / `_roadmap.md` / `gates/*.md` / `timeline.jsonl` / `_workers.parallel`，全部为既有读取器或尾部扫描。
- 现场观测：`beat` 事件频率 = `poll_interval_sec`（4s），60s 窗口 ≥12 跳（AC-019）；因此「tick 新鲜度」可由最近一条 beat 的 `seq` + `ts` 直接判定 STALE（面板阈值取 `max(30s, 5 × poll_interval)`）。

## 4. 现场修复与恢复路径（AC-001 / T-09 的证据）

1. `pm-state.md` Phase 行规范化为裸 token（bytes 级替换，其余字节不动，CRLF 保留）：21:35:32 写入；21:35:41 timeline 出现 `execute->verify exit=0`（此前 2242 次 exit=1）。
2. `.mw/dispatch.yml` 的 `review` 模型 id 修正为 `timi/gpt-5.6-sol`（1 token，字节级）：reviewer 不再启动即 403。
3. 剩余阻塞：L3 预算已耗尽 + `stalled` 门禁 approve 无实现 → 由本 key 的 AC-004/AC-013（恢复语义）正式解决，再驱动 K2 走完 VERIFY → done → K3 解锁。
