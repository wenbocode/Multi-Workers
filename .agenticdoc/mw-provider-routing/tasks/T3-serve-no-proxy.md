# Task T3: serve AC-008 回归用例

- 状态: done
- ac_refs: AC-008
- 来源: plan.md T3

## 内容

`packages/multi-workers/test_serve_doctor.py`：新增用例——hermetic config 中仅无 port 路由（timi/zai-coding-cn）有凭证、带 port 路由（claude 等）无凭证时，`cmd_serve` 的 spawn 列表不含 proxy_multi.py。

## 测试点（VC-008）

- proxy_spawned=no

## 完成判据

- 用例 PASS（沿用现有 TestServeSupervision 的 fake Popen 模式与 ANTHROPIC_API_KEY autouse 清理）
