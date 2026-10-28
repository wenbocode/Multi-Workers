# Key Decisions: mw-monitor-auto-restart

## A（架构）
User confirmed proposed design D001–005 including strict process exit and dashboard fingerprint extension in this turn.
- D001 互斥替换: 选启动锁内opt-in，否独立stop/open（避免重复启动）。
- D002 退出确认: 选旧进程身份消失，否仅端口关闭（不弱化退出边界）。
- D003 兼容性: 选源码和页面资产指纹，否module-only（覆盖缓存旧页面）。
- D004 并发: 选既有锁冲突，否新增等待重试（最小安全范围）。
- D005 停止契约: 选替换路径严格校验，否修改公共stop（保持显式stop语义）。

## Authority
No live user's monitor/shared service/browser/provider/decision API/build/install/commit/config/framework operations. PM serial source edits and isolated synthetic unit/private-loopback tests only. No worker redispatch.
