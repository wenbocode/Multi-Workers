# Task T2: launcher 直连分支

- 状态: done
- ac_refs: AC-001, AC-002, AC-003, AC-006
- 来源: plan.md T2

## 内容

1. `packages/multi-workers/launcher.py` `_build_env`：新增 `cli == "pi" and provider == "zai-coding-cn"` 分支（照 timi 模式，位于 timi 分支后）：
   - `resolve_credential`（env → auth.json）失败 → `RuntimeError`（消息含 `zai-coding-cn` 与 `describe_missing` 输出）
   - 成功 → `_stripped_env` + `env["ZAI_CODING_CN_API_KEY"] = value` + `PI_WORKER_TASK`；无 base_url 透传
2. `_build_command`：直连元组 `("anthropic", "openai-codex", "deepseek")` → 追加 `"zai-coding-cn"`（继承「必须显式 model」）

## 测试点（VC-001/002/003/006/009）

- test_launcher.py（hermetic config）：
  - VC-001: zai env 注入正确 + 无 localhost 值 + PI_WORKER_TASK；双源（env 源、auth.json file 源）各一例
  - VC-002: 双源皆缺 → RuntimeError 消息含 provider 名与缺失描述
  - VC-003: zai worker env 不含 ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN/DEEPSEEK_API_KEY/TIMI_API_KEY
  - VC-006: window-model timi/glm-5.3 且 task.md 无 model: → provider=timi、TIMI_API_KEY 存在、ZAI env 缺席
  - VC-009: zai 无 model → RuntimeError 要求显式 model；timi 无 model → `--model glm-5.3`（回归守护）

## 完成判据

- 上述用例全部 PASS；现有 launcher 用例零回归
