# T-12: 评审修复轮（code-review-1 M1/M2/M3/m1/m2/m3/m4/n2）

- Stage: 5（并入 S5 后的评审修复轮）
- 代码状态: 代码完成
- 验证状态: 验证通过
- ac_refs: AC-001, AC-004, AC-011
- vc_refs: VC-003, VC-006, VC-013, VC-015, VC-016, VC-017
- Error Fingerprint: 无

## 目标

处置 code-review-1（2026-09-08 评审 worker）的 M1/M2/M3/m1/m2/m3/m4/n2 共 8 项发现，全部收敛为代码修复 + 测试钉住。

## 变更

| 项 | 修复 | 文件 |
|----|------|------|
| M1 | `IndexStore.claim(key, self, heldLive, {force, demoteOthers, activate})`：单锁内 check→demote→upsert→写后磁盘复读验证；takeOverKey 改走该原语 | shared/index-store.ts, pm/ui-bridge.ts |
| M2 | restoreWatch 静默 re-claim 改走 claim({demoteOthers:false, activate:false})：保持行状态、不全局降级、竞争失败降级 watch-only 并告警 | pm/pm-orchestrator.ts |
| M3 | `_parse_heartbeat_ts`：`Z`→`+00:00` 归一后再 fromisoformat（Python 3.10 floor 上活性功能原先整体失效）；测试 `_hb_line` 改钉 TS 线格式 | mw_common.py, test_serve_doctor.py |
| m1 | gate 去重槽仅在真广播时消耗：onDocGate 契约改为必须返回 boolean（false=被抑制），suppressed 不进 warnedKeys | pm/pm-orchestrator.ts, pm/ui-bridge.ts |
| m2 | `/pm-key new` 改走 takeOverKey（自动建行 + 原子 demote），消除绕过单活纪律的路径 | pm/ui-bridge.ts |
| m3 | poll 句柄存储 + `session_shutdown` 清理（reload/会话替换后不再有僵尸 tick 打已释放的 ctx） | pm/pm-orchestrator.ts |
| m4 | 删除死代码 `activeKeys()`（零调用方） | shared/index-store.ts |
| n2 | 时长格式文档措辞对齐实际发射（formatHeartbeatAge 粗粒度桶 `(6m, ph 3/3)`，非 `7m32s`） | pm-orchestrator 注释, spec AC-013, design |

## 验证

- 新增 vitest：M1 原子 claim ×2（blocked/demote/force/quiet 语义）、m1 去重槽 ×1、m3 session_shutdown ×1、VC-019 断言更新为新消息格式 → **66/66**
- 新增 pytest：M3 Z 后缀解析 ×1 → test_serve_doctor 15/15、全套 116 passed
- `npm run check`：本 key 文件 0 错误（全仓 580 = HEAD 既有债务，与 T-10 基线完全一致，零新增）

## 执行记录

| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 16:3x-17:5x | 八项修复 + 6 个新测试 + 3 处既有断言更新；biome void-union 修正（契约改显式 boolean）；Windows 死 pid 探测改 OpenProcess+GetExitCodeProcess（os.kill(pid,0) 对已终止 pid 仍成功——与 Node 侧行为对齐） | PASS: 66/66 + 116 + check 零本 key 错误 |
