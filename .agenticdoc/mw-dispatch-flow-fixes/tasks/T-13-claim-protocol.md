# T-13: M4 框架对齐（update_index.py claim 协议）

- Stage: 5（评审修复轮）
- 代码状态: 代码完成
- 验证状态: 验证通过
- ac_refs: AC-001
- vc_refs: VC-017
- Error Fingerprint: 无

## 目标

消除 TS（agent-team-loop）与 Python（update_index.py）双写者在 `_index.parallel` 上的协议盲区（code-review-1 M4）：claim ID 互不认识 + 互斥机制不同 → 跨写者双活可复活。

## 变更（.agents/skills/agentic-task/scripts/update_index.py）

1. `now_claim_id()` → `host:pid`（与 TS windowClaimId 同格式；旧 `YYYYMMDD-HHMMSS-pid` 行两侧都按 stale 处理）
2. `claim_is_stale_local(claim_id)`：本地 host + pid 已死 → 视为 stale，claim 免 `--force` 接管（TS claimState "held-stale" 对位）；`_pid_is_gone` 在 Windows 用 OpenProcess+GetExitCodeProcess（实测 `os.kill(pid,0)` 对已终止 pid 仍成功，与 Node 侧 process.kill(pid,0) 行为不一致——已对齐）
3. `_index_lock(root)`：claim 等所有变更走 `.mw/index.lock`（O_CREAT|O_EXCL + 指数退避，与 TS acquireLock 同协议同参数）；`_write_index_atomic` 在锁内执行，mtime-CAS 保留为进程内防御
4. 删除失去调用方的 `TS_SEC_FMT` 常量

## 验证

- pytest `TestUpdateIndexClaim` ×3：claim id 格式、demote 其他 active 行 + 锁释放、stale-local 免 force / live 冲突 / legacy 冲突 → 15/15（全套 116）
- 手动四象限验证 claim_is_stale_local（本机死 pid=True、本机活 pid=False、异 host=False、legacy=False）

## 执行记录

| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 17:0x | 三项协议对齐 + Windows pid 探测修正 + 测试 | PASS |
| 2 | 2026-09-08 17:5x | 框架仓提交 0f4959b + 推送成功（d33e777..0f4959b master） | done |
