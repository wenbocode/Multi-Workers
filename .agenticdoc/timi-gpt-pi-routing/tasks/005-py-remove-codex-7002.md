# Task 005: Remove codex port-7002 from all public surfaces

## 基本信息
- Stage: 2
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: TBD
- ac_refs: [AC-011]
- vc_refs: [VC-011]

## 描述
从以下六个公共接口面彻底移除 port-7002 Codex proxy：
- `providers.json`
- `launcher.py`（fallback defaults + `--codex-port` 参数）
- `proxy_multi.py`（codex proxy 构造 + `--codex-port`）
- `mw.py`（`--codex-port` 参数转发）
- `smoke_test.sh`（port 17002 检查）
- `dispatch-table.md`（Codex 行更新）

同时写 `test_proxy_service.py` 中的 VC-011 静态断言（grep 六个文件，确认零匹配 7002/codex-port）。

## 输入
- 依赖文件（全部修改）:
  - `packages/multi-workers/providers.json`
  - `packages/multi-workers/launcher.py`
  - `packages/multi-workers/proxy_multi.py`
  - `packages/multi-workers/mw.py`
  - `packages/multi-workers/smoke_test.sh`
  - `packages/multi-workers/dispatch-table.md`
- AC 约束:
  > AC-011: 六个公共接口面中，无任何代码启动、配置、接受 CLI 选项或记录 port-7002 Codex proxy 行为。

## 修改清单

### providers.json
删除 `"codex"` 条目，仅保留 claude/claude-cli/deepseek。

### launcher.py
1. 删除 fallback defaults 中的 `"codex": {...}` 行（约第 119 行）
2. 删除 `--codex-port` argument（约第 314 行）
3. 删除 `if args.codex_port is not None: port_overrides["codex"] = args.codex_port`
4. 删除 `port_overrides` 中的 codex 分支

### proxy_multi.py
1. 删除 `_OPENAI_UPSTREAM_*` 常量
2. 删除 `codex_proxy` 构造和加入 proxies 列表
3. `run()` 签名改为 `run(pi_port: int, claude_port: int, deepseek_port: int | None = None)`
4. 删除 `status_parts` 中的 `codex=` 部分
5. 删除 `--codex-port` argument parsing

### mw.py
1. 删除 `--codex-port` 参数（`_add_serve_args` 和相关函数）
2. 删除所有向 proxy_cmd 和 launcher_cmd 传递 `--codex-port` 的行
3. 删除 `cmd_start` 中的 codex-port 转发

### smoke_test.sh
1. 从两个 `mw serve` 命令移除 `--codex-port=17002`
2. 从 `for port in 17001 17002 17003` 改为 `for port in 17001 17003`（或等价检查）

### dispatch-table.md
1. Codex 行：provider=`codex`, port=`-`, credential=`Codex config`, note=`Uses Codex TiMiAIHub provider (user configuration)`
2. 新增 Pi/Timi 行：cli=`pi`, provider=`timi`, port=`-`, credential=`TIMI_API_KEY`, note=`Pi built-in mixed-protocol provider`

## 预期产出
- 修改上述六个文件
- 在 `packages/multi-workers/test_proxy_service.py` 中追加 VC-011 静态扫描断言：
  ```python
  def test_vc011_no_codex_proxy_7002():
      surfaces = [...six file paths...]
      for path in surfaces:
          content = Path(path).read_text()
          assert "7002" not in content, f"{path} still references 7002"
          assert "codex-port" not in content, f"{path} still references codex-port"
  ```
- 验证方式: `python -m pytest packages/multi-workers/test_proxy_service.py::test_vc011_no_codex_proxy_7002 -q`
- 验证等级: Level 0/1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本 | 状态 |
|----|------|---------|---------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
