# Task T-05: launcher 凭证走 mw_common + 单测密封化

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-009, AC-016]
- vc_refs: [VC-010, VC-017]
- pattern_refs: []

## 描述
1. `launcher.py` 的 `_load_providers` / `_build_env` 改走 `mw_common.load_providers` / `resolve_credential` / `credential_env_names`：
   - 删除 `_read_timi_api_key_from_config` 硬编码（timi 的 config.toml 兜底由 providers.json file 源声明取代）
   - strip 集合 = `credential_env_names()` ∪ `_EXTRA_CREDENTIAL_VARS`
   - `_build_env` 的 timi 直连 / codex / 代理三分支保留，仅凭证取值与 strip 集合来源变化
2. 密封化修复 `test_launcher.py` 两个失败用例（2026-08-28 实测 FAIL）：
   - `test_env_missing_timi_key_raises`：fixture 注入 tmp providers.json（timi 仅 env 源），monkeypatch 清 TIMI_API_KEY → _build_env 抛 RuntimeError（不再读真实 home 的 config.toml）
   - `test_missing_timi_key_raises_fatal_launcher_error`：按 T-03 新语义改写（隔离 failed，无真实 pi 子进程副作用）
3. 全量用例在本机（真实 `~/.timi-anthropic-proxy/config.toml` 存在）通过

## 输入
- 依赖文件: launcher.py、mw_common.py（T-01）、providers.json（新 schema）
- 依赖 Task: T-01, T-03
- AC 约束:
  > AC-009: 在存在真实 `~/.timi-anthropic-proxy/config.toml` 的机器上运行 `python -m pytest test_launcher.py test_integration.py` 的条件下，全部用例通过，且无任何用例发起真实 LLM 请求或 spawn 真实 pi/claude/codex 子进程
  > AC-016: 在 providers 配置中为某路由声明配置文件凭证来源的条件下，launcher 从该文件读取凭证并完成该路由预检与 worker env 注入，无需设置对应 env var

## 预期产出
- launcher.py 改造（凭证走 mw_common）
- test_launcher.py 密封化（33+2 用例全绿）
- 验证方式: VC-010（本机实测全绿）、VC-017
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 18:11 | 实现并通过单测（见下） | PASS: 相关 pytest 用例全绿 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
