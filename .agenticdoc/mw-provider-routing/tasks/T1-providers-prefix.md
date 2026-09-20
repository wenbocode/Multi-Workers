# Task T1: providers.json + prefix map

- 状态: done
- ac_refs: AC-004
- 来源: plan.md T1

## 内容

1. `packages/multi-workers/providers.json`：
   - `credentials` 加 `zai-coding-cn`：sources = env `ZAI_CODING_CN_API_KEY` → file `~/.pi/agent/auth.json` field `zai-coding-cn.key`
   - `providers` 加 `zai-coding-cn`：`{"api_key_env": "ZAI_CODING_CN_API_KEY", "credential": "zai-coding-cn"}`（无 port）
2. `packages/multi-workers/mw_common.py`：`MODEL_PREFIX_TO_PI_PROVIDER` 加 `"zai": "zai-coding-cn"`

## 测试点（VC-004）

- test_common.py：route_precheck 输出含 `route=zai-coding-cn`；available 随凭证存在性翻转（缺失时 missing 为描述文本）

## 完成判据

- 上述用例 PASS；不改变现有任何路由的 precheck 输出（timi/claude/claude-cli/deepseek/codex-native 不变）
