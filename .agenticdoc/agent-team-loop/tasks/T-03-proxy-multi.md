# T-03: proxy_multi.py（L1 timi-proxy 多端口）

type: code-gen/impl
cli: codex
deps: none
status: pending

## Description
为 timi-proxy-cli 写一个多端口扩展模块 `proxy_multi.py`，
让三种 CLI worker（pi/codex/claude）各自通过独立本地端口连接到同一个上游网关。

## Acceptance Criteria
- AC-1: `python proxy_multi.py --help` 无报错，显示 --pi-port/--codex-port/--claude-port/--upstream 选项
- AC-2: `MultiPortProxy` 类构造器可接受三个端口参数，启动后各端口独立监听
- AC-3: `build_pi_env(config, pi_port)` 返回 dict，包含 `ANTHROPIC_BASE_URL=http://localhost:{pi_port}`
- AC-4: `build_codex_env(config, codex_port)` 返回 dict，包含 `OPENAI_BASE_URL=http://localhost:{codex_port}`（带 ⚠ 版本注释）
- AC-5: `build_claude_env(config, claude_port)` 返回 dict，包含 `ANTHROPIC_BASE_URL=http://localhost:{claude_port}`
- AC-6: 启动时写 `proxy_multi.pid`，SIGTERM/SIGINT 优雅关闭

## Tool Constraints
allowed: [read, write, bash, glob]
denied: [network_fetch]

## Do NOT
- 不要修改 timi-proxy-cli 的核心文件
- 不要实现实际的 LLM 代理逻辑，只做端口绑定和 env builder
- 如果 `LocalProxyServer` 不支持多实例，用 mock class 占位并加 TODO 注释

## Expected Output
`agent-team-loop/proxy_multi.py`，包含 MultiPortProxy、MultiPortWatchdog、
三个 build_*_env 函数和 CLI 入口。
