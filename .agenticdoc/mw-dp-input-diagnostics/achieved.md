# DP 输入诊断与显式证据引用交付

## 系统行为变化

- `ask_decision` 返回受限制的证据准备诊断，显示字段、错误码、修正提示和本地未发送事实。可公开的路径和有效行数随诊断返回。相同逻辑 ID 的 CLI 拒绝重放关联原阻塞记录。
- Prepared CLI、窗口工具和决策本支持显式 `evidence_refs`。存在该字段时仅按列表读取证据，空列表仅使用内联材料。历史请求沿用旧解析。显式选择器与原逻辑 ID 绑定。
- `/mw runtime` 显示扩展加载时的 SHA-256、当前 Python 入口及其能力。新扩展在旧 CLI 上拒绝发送显式协议请求并显示兼容诊断。
- 已安装 [独立发布包](../../.mw/releases/dual-independent-20261121-dp-input-diagnostics/release-manifest.json)。原全局文件已备份，发行基线的门控路由、Dual UBT 和 bearer 修复保留。

## 验收证据

- AC-001 到 AC-003 自验通过。44 项 TypeScript、195 项 Python 和 `npm run check` 通过。对 Bearing、Gaze、UEPerformanceFlow 使用脱敏请求回归测试。对候选执行 Pi 加载、受限证据失败和混合版本测试。见 [验收结果](evidence/codex-pm/self/1795191162917273800-mnau7msq/result.json)。
- AC-004 自验通过。新进程加载已安装全局扩展，确认哈希和 Python 能力，实际收到范围越界及未发送诊断。见 [安装验收](evidence/codex-pm/self/1795191233676253400-2ctfl8p2/result.json)。
- 被旧契约套件判为失败的 20 项 TypeScript 和 69 项 Python 用例与上一发布包完全相同。见 [基线对比](evidence/legacy-suite-comparison.json)。

## 遗留

实现位于独立发布目录，[基线补丁](evidence/implementation.patch) 可在协调共享文件后合入主工作树。运行中的历史窗口和后端未重启，也未重发任何历史决策。旧窗口在安全点 reload 后启用当前全局扩展。
