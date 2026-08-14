# Task T-04: launcher.py 进阶（providers.json + dry-run + max-workers）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-007, AC-009, AC-024, AC-025]
- vc_refs: [VC-012, VC-014, VC-015, VC-033, VC-034]
- pattern_refs: []

## 描述
在 T-03 基础上补充三个能力：

**providers.json 路由**（AC-024）：
创建 `packages/multi-workers/providers.json`，包含 `claude`、`codex`、`claude-cli`、`deepseek` 四个 provider 配置（port、base_url_env、api_key_env）。
`_build_env()` 从 providers.json 查找 `Provider` 列对应配置，注入正确 env var（如 deepseek 用 `DEEPSEEK_BASE_URL`，不使用 `ANTHROPIC_BASE_URL`）。

**--max-workers**（AC-007）：
超出 max_workers 时，新 pending task 进入等待队列，不立即 spawn。
有 worker 退出后从队列取下一个 spawn。

**--dry-run**（AC-009）：
不创建任何子进程，stdout 输出所有 pending task 的 CLI 命令 + task.md 路径 + env var 列表（含 provider 对应 env），exit 0。

## 输入
- 依赖文件: `launcher.py`（T-03）
- 依赖 Task: T-03
- AC 约束:
  > AC-007: 已有 N 个活跃 worker（N=max）时，新 pending 进入队列，不立即 spawn
  > AC-009: --dry-run 输出命令和路径，exit 0，不创建子进程
  > AC-024: task.md 含 Provider 字段时，从 providers.json 查端口 + env var 名称
  > AC-025: --dry-run 且 Provider=deepseek 时，输出含 DEEPSEEK_BASE_URL，不含 ANTHROPIC_BASE_URL

## 预期产出
- `packages/multi-workers/providers.json`
  ```json
  {
    "claude": {"port": 7001, "base_url_env": "ANTHROPIC_BASE_URL", "api_key_env": "ANTHROPIC_API_KEY"},
    "codex": {"port": 7002, "base_url_env": "OPENAI_BASE_URL", "api_key_env": "OPENAI_API_KEY"},
    "claude-cli": {"port": 7003, "base_url_env": "ANTHROPIC_BASE_URL", "api_key_env": "ANTHROPIC_AUTH_TOKEN"},
    "deepseek": {"port": 7004, "base_url_env": "DEEPSEEK_BASE_URL", "api_key_env": "DEEPSEEK_API_KEY"}
  }
  ```
- `launcher.py` 更新（max-workers 队列逻辑 + dry-run 模式）
- 验证方式: VC-012（max-workers 单元测试）、VC-014/015（dry-run）、VC-033/034（provider env）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-11 | providers.json + max-workers + dry-run 已在 T-03 实现 | 验证 VC-012/014/015/033/034 全 PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
