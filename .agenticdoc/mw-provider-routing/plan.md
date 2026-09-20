# Plan: mw-provider-routing

设计定稿：D-001=C（第 5 个硬编码直连分支，零触碰 timi 路径）。本计划将 design.md §3 模块表拆为可执行任务。

## 任务分解

| ID | 任务 | 涉及文件 | 依赖 | 测试点（VC） | 预估 |
|----|------|---------|------|--------------|------|
| T1 | providers.json 加 zai-coding-cn 路由与凭证链；mw_common prefix map 加 `zai` | providers.json, mw_common.py | — | VC-004（test_common：route_precheck 列出 + available 翻转） | 1h |
| T2 | launcher `_build_env` 新增 pi+zai-coding-cn 分支（凭证解析→注入 ZAI_CODING_CN_API_KEY + PI_WORKER_TASK，缺凭证 RuntimeError）；`_build_command` 直连元组加 zai-coding-cn | launcher.py | T1 | VC-001/002/003/006/009（test_launcher：hermetic config，env/auth.json 双源、隔离、timi 回归守护） | 2h |
| T3 | serve AC-008 回归用例：仅无 port 路由有凭证 → 不 spawn proxy | test_serve_doctor.py | T1 | VC-008 | 0.5h |
| T4 | dispatch-models.ts `PROVIDER_ID_TO_PREFIX` 加 `zai-coding-cn`；重建扩展 bundle + dist；`npm run check` | dispatch-models.ts, bundle, dist | T1（map 语义） | VC-010（vitest 侧 map 断言 + py 侧断言） | 1h |
| T5 | e2e 真实冒烟：以 `model: zai/glm-5.3`（预算 ≥1024）派发真实 worker，验证直连往返与退出码 | test_e2e_real.py（新用例） | T1+T2+T4 | VC-005（真实运行记录留底 evidence/） | 1h |
| T6 | 收尾：全量 pytest（VC-007）+ `npm run check` + CHANGELOG 两包条目 + README Backlog 泛化项指针 + 提交（含重建 dist） | CHANGELOG, README, git | 全部 | VC-007 | 1h |

## 顺序与关键路径

T1 → T2 → T3（串行，Python 侧）；T4 可与 T2 并行但依赖 T1 的 prefix 语义定稿；T5 在 T1+T2+T4 后；T6 最后。

## 风险与回滚

- 新代码仅在 `provider == "zai-coding-cn"` 时执行；timi/anthropic/deepseek/openai-codex 路径零触碰（D-001 裁定）
- 回滚：纯 Python 改动 `git revert` 即时生效；TS 侧单行 map 附加式，回滚同 commit 一并还原
- 凭证：e2e 用 env 源（ZAI_CODING_CN_API_KEY），不触 auth.json；真实 key 只存在于 docs/zai_guider.md（untracked，T6 脱敏确认）

## 明确不做（推迟到后续 key）

- pi_providers 数据驱动泛化、_stripped_env 收敛、route_precheck 双段遍历（README Backlog 已登记）
- 裸 `zai` 国际端点 provider
