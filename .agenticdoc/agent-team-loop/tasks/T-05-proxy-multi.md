# Task T-05: proxy_multi.py（三端口 LLM 路由）

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-013]
- vc_refs: [VC-021]
- pattern_refs: []

## 描述
实现 `packages/multi-workers/proxy_multi.py`：
使用 `timi-proxy-cli` 的 `LocalProxyServer`、`StableRelay`、`ProxyWatchdog` 启动三个独立端口的 LLM proxy：
- Port 7001：pi provider（上游 ANTHROPIC_BASE_URL）
- Port 7002：codex provider（上游 OPENAI_BASE_URL）
- Port 7003：claude-cli provider（上游 ANTHROPIC_BASE_URL，ANTHROPIC_AUTH_TOKEN）

支持命令行参数 `--pi-port`、`--codex-port`、`--claude-port` 覆盖默认端口。
由 `mw serve`（T-06）作为子进程启动，不单独管理生命周期。

## 输入
- 依赖文件: timi-proxy-cli（已安装）
- 依赖 Task: 无（可独立实现）
- AC 约束:
  > AC-013: `proxy_multi.py --pi-port 7001 --codex-port 7002 --claude-port 7003` 启动后，Windows `netstat -an` 输出中三个端口均显示 `LISTENING` 状态

## 预期产出
- `packages/multi-workers/proxy_multi.py`
  - `--pi-port`、`--codex-port`、`--claude-port` 参数
  - 三个 `LocalProxyServer` 实例各自监听对应端口
  - 主循环阻塞，收到 SIGTERM/KeyboardInterrupt 时优雅停止
- 验证方式: VC-021（netstat 三端口 LISTENING，L2 E2E）
- 验证等级: Level 2

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: timi-proxy-cli API 不确定（LocalProxyServer 参数）
- 处置: 实现前用 `python -c "import timi_proxy_cli; help(timi_proxy_cli)"` 确认 API
