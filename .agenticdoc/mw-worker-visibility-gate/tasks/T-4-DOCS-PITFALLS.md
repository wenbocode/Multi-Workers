# Task T-4: 文档与记忆登记（PM 直执）

## 元信息
- Stage: 2（与 T-3 同波，文件面不相交）
- 依赖: 无（内容由 design 锁定；措辞在 T-3 完成后校准）
- 风险: 低
- Agent: PM 直执（不派 worker）
- ac_refs: [AC-013]
- vc_refs: [VC-013]
- 文件面：`packages/coding-agent/CHANGELOG.md`、`packages/multi-workers/CHANGELOG.md`（仅在需要时）、`.agenticdoc/_pitfalls.md`

## 交付物

1. `packages/coding-agent/CHANGELOG.md` → `## [Unreleased]` → `### Added` / `### Fixed`（按语义二选一或各一条）：
   - 派发门禁按 owner key 相位分层：SPEC 相位只校验 spec 侧四项，DESIGN 起追加 design.md 与 design 证据（不再要求新 key 先有 design 才能派调研 worker）。
   - 底栏面板新增跨 key 聚合提示行（`~ N elsewhere: <owner>(<counts>; risk=high:K)`），本窗口派发到他键的任务（如 `_scratch`）不再静默不可见。
   - TS claim/takeover 后同步 `pm-state.md` 的 `- Claim-Id:`（单行原地替换，索引行为权威；同步失败只回 warning）。
2. `.agenticdoc/_pitfalls.md` → 新增 P-011（**VC-013**）：claim 身份双写分叉。正文必须同时含三处口径：
   - "索引行"（`_index.parallel` 的 Claim 列）是权威；
   - 两处必须**同值**（python claim 与 TS takeover 都要写）；
   - "liveness" 只能在索引行判定（pm-state 的 `- Claim-Id:` 是镜像，短命 python pid 天然已死，按它判活会误判 stale）。
   并写明日期与来源 key（2026-09-23，mw-worker-visibility-gate）。
3. 若 `_index.parallel` / `_project_log.md` 的相位行需与本 key 同步，由 `advance_phase` 负责，不手改。

## 约束

- 追加式编辑，保留文件既有换行风格（本仓 `.md` 记忆文档为 CRLF；CHANGELOG 按既有行尾）。
- 不动 `## [0.x.y]` 已发布小节；新条目一律进 `## [Unreleased]`。
- 不用 Python 文本模式整文件重写（P-010）；用 `edit` 工具做定点替换。

## 验收命令

```
cd H:/git/Multi-Workers
python -X utf8 -c "import pathlib;t=pathlib.Path('.agenticdoc/_pitfalls.md').read_text(encoding='utf-8');i=t.find('P-011');print(t[i:i+80])"
git diff --stat -- .agenticdoc/_pitfalls.md packages/coding-agent/CHANGELOG.md
```

## 报告要求

给出：新增条目首行、三处口径的实际句子、CHANGELOG 小节落点。
