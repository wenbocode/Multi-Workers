# Task 004: Python launcher Pi/timi + Codex native routing

## 基本信息
- Stage: 2
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: TBD
- ac_refs: [AC-008, AC-009, AC-010]
- vc_refs: [VC-008, VC-009, VC-010]

## 描述
当前 `launcher.py` 的 `_build_command` 和 `_build_env` 对所有 Pi 任务一律使用 port-7001 proxy 路径。需要在两个函数中分别处理：

1. **Pi + provider=timi**：命令为 `pi --provider timi --model gpt-5.6-sol -p <task>`；环境继承 `TIMI_API_KEY`（必须）和 `TIMI_BASE_URL`（可选），不注入 localhost URL 或其他 provider 凭证。
2. **Pi + empty provider**：维持原行为 `pi -p <task>` + `ANTHROPIC_BASE_URL=http://localhost:7001` + `ANTHROPIC_API_KEY`。
3. **Codex + empty/codex provider**：命令为 `codex exec -m gpt-5.6-sol <task>`；从环境移除 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`；其他 provider 值在 spawn 前抛 `RuntimeError`。

同时创建 `test_launcher.py` 覆盖以上三条路径。

## 输入
- 依赖文件: `packages/multi-workers/launcher.py`（_build_command, _build_env, _spawn, _dry_run）
- AC 约束:
  > AC-008: cli=pi, provider=timi → 命令 `pi --provider timi --model gpt-5.6-sol -p <task>`；继承 TIMI_API_KEY 和可选 TIMI_BASE_URL；不注入 localhost URL。
  > AC-009: cli=pi, empty provider → 命令 `pi -p <task>`；环境仅含 ANTHROPIC_BASE_URL=http://localhost:7001 + ANTHROPIC_API_KEY。
  > AC-010: Codex empty/codex → 命令 `codex exec -m gpt-5.6-sol <task>`；移除 OPENAI_BASE_URL/OPENAI_API_KEY；其他 provider 值 raise RuntimeError。

## 实现细节

### _build_command 改造
```python
def _build_command(entry: dict[str, str]) -> list[str]:
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()
    task_content = _read_task_content(entry["task_path"])
    if cli == "pi":
        if provider == "timi":
            return ["pi", "--provider", "timi", "--model", "gpt-5.6-sol", "-p", task_content]
        return ["pi", "-p", task_content]
    elif cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(f"Codex workers support only an empty provider or 'codex', got {provider!r}")
        return ["codex", "exec", "-m", "gpt-5.6-sol", task_content]
    elif cli == "claude":
        return ["claude", "-p", task_content]
    return [cli, task_content]
```

### _build_env 改造
在现有函数开头加 Pi/timi 特殊分支（在通用 port-based 路径之前）：
```python
if cli == "pi" and provider == "timi":
    env = dict(os.environ)
    # 移除所有已知 provider 的 base_url/api_key vars（防止泄漏）
    for p in providers.values():
        env.pop(p.get("base_url_env", ""), None)
        env.pop(p.get("api_key_env", ""), None)
    timi_key = os.environ.get("TIMI_API_KEY")
    if timi_key is None:
        raise RuntimeError("Required environment variable 'TIMI_API_KEY' is not set.")
    env["TIMI_API_KEY"] = timi_key
    if "TIMI_BASE_URL" in os.environ:
        env["TIMI_BASE_URL"] = os.environ["TIMI_BASE_URL"]
    if cli == "pi":
        env["PI_WORKER_TASK"] = str(pathlib.Path(entry["task_path"]).resolve())
    return env

if cli == "codex":
    if provider not in ("", "codex"):
        raise RuntimeError(f"Codex workers support only an empty provider or 'codex', got {provider!r}")
    env = dict(os.environ)
    env.pop("OPENAI_BASE_URL", None)
    env.pop("OPENAI_API_KEY", None)
    return env
```

## 预期产出
- 修改 `packages/multi-workers/launcher.py`（_build_command, _build_env）
- 新建 `packages/multi-workers/test_launcher.py`
  - VC-008: Pi/timi 命令 + 环境断言
  - VC-009: Pi/empty 命令 + 环境断言
  - VC-010: Codex empty/codex 命令 + 环境断言 + 其他 provider raise
- 验证方式: `python -m pytest packages/multi-workers/test_launcher.py -q`
- 验证等级: Level 1

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
