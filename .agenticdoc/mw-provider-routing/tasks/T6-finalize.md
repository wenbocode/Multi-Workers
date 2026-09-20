# Task T6: 收尾与提交

- 状态: blocked: pre-commit npm run check fails on the other session in-flight kimi-coding removal (packages/ai only); commit staged set once green
- ac_refs: AC-007
- 来源: plan.md T6

## 内容

1. 全量 pytest：`python -m pytest packages/multi-workers/`（期望 0 failed，deselect 8）
2. `npm run check`（T4 后复查）
3. CHANGELOG：multi-workers + coding-agent 两包 `[Unreleased]` 加条目
4. README Backlog：直连路由泛化项加「后续 key」指针（本 key 落地 C 后）
5. 脱敏确认：docs/zai_guider.md 保持 untracked；如需保留示例 key 文本则替换为占位符
6. 提交：src + 测试 + 重建后的 dist 同 commit（消息 `feat(multi-workers): add zai-coding-cn direct provider route`）

## 测试点（VC-007）

- failed=0 deselected=8

## 完成判据

- 全量绿 + CHANGELOG/README 更新 + 提交完成（含 dist）
