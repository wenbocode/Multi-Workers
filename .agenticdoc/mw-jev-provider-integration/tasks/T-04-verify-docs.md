# T-04 — 端到端验证 + 文档 + 变更记录

- key: mw-jev-provider-integration · type: coding · W4 · timeout: 55

## 上下文

goal.md 两条目标（① jev 跑通能用起来 ② 接口友好、决策被正确调用并有效反馈）的**证据收口**任务。W1/W2/W3 已交付代码；本任务产出可复核的验收证据与文档，不改动逻辑（除验证中发现的**明确缺陷**，且改动须在写入允许面内并在 report 单列）。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/spec.md`：§3 **AC-001..AC-012**（逐条要给证据）、§4 未决项 D-1..D-4、§2 业务约束（默认关闭、fail-soft 铁律）。
- `.agenticdoc/mw-jev-provider-integration/design.md`：D-005（反馈三层与降级呈现）、D-006（覆盖面 2/15）。
- `packages/multi-workers/README.md`（现有章节结构与测试说明 `README.md:490-494`）、`packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md`（`## [Unreleased]` 现有小节，**追加不重复**）。
- W1/W2/W3 产物：`decision.py`、`decision_backends.py`、`mw.py::cmd_decide`、`mw_common.py::_doctor_decide`、`pm/triage-client.ts`、`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`。

## 要求

1. **真实链路端到端（核心证据，允许 2–4 次真实调用）**：
   - 在临时项目目录（**不要**在本仓根目录）写 `.mw/decide.json`（`enabled=true, transport=llm-transitional, model=glm-5.3-flashx, timeout_s=20`），跑一次真实
     `python mw.py decide run --project <tmp> --dp dp1 --json`，请求含 `state`（一句派发场景描述）+ 两道题（`triage_type` choice、`triage_risk` score 或 choice）；
   - 记录：退出码、`available`、`reason`、`attempts`、`latency_ms`、`answers`、`confidence_source`（**禁打印凭据**）；
   - 再跑一次 `mw decide probe --json` 并把矩阵现状记入证据（这是 D-1 现状的可复现锚点）；
   - 若网络/凭据不可用：如实记录为"未跑通"并给出 doctor/probe 证据，**不要**伪造。
2. **验收证据文件** `evidence/runs/verify-mw-jev-provider-integration-20261016.md`：
   - 逐条 AC-001..AC-012：`结论 + 命令 + 关键输出（≤5 行）+ 证据文件:行`；
   - 专门记录**默认关闭等价性**（未配置项目：`mw decide show` → disabled；doctor 无 `triage:` 行；`git diff` 显示派发路径未变）；
   - 专门记录 **D-1 现状**（上游决策入口未暴露）与**缓解**（B2 承载同一契约）；
   - 单列"未覆盖/未验证"：conductor 的 13 个自动派发点、B1/B3 未实机、`box` 问题类型未跑、TS 面板未逐字同步 doctor 行。
3. **文档**：
   - `packages/multi-workers/README.md`：新增「决策服务（mw decide）」小节——配置样例、四个 action、fail-soft 语义（成功与 `available=false` 都 exit 0、参数非法 exit 2）、`confidence_source` 置信度硬规则、doctor 行说明、**默认关闭**声明；
   - `packages/multi-workers/CHANGELOG.md` 与 `packages/coding-agent/CHANGELOG.md`：在 `## [Unreleased]` 的 `### Added` 追加条目（先读全文，不重复小节、不改已发布段落）。
4. **回归**：
   - `cd packages/multi-workers && python -m pytest -q`（与既有 8 条环境失败基线对比，**零新增**才算过）；
   - `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts`；
   - 仓库根 `npm run check`（全量输出，修完所有 error/warning/info；**不跑** `npm run build`/`npm test`）。
5. 本任务原则上**只写文档与证据**；若 `npm run check` 暴露的是 W1–W3 代码缺陷，允许在当前写入允许面内修最小改动，并在 report 里单列"因 check 修复的改动"。
6. **并行噪声处置**：`npm run check` 可能报出**其它 key 在飞文件**的错（已知：`packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts`、`packages/multi-workers/goal.ts`、`mw.py` 的 `_goal_gate_install` 段）。这类错误**只记录、不修**（避免踩他窗写入面），在 report 里单列"他窗在飞、非本 key"清单；本 key 文件的 error/warning/info 必须清零。

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/runs/verify-mw-jev-provider-integration-20261016.md`（新建）
- `packages/multi-workers/README.md`
- `packages/multi-workers/CHANGELOG.md`
- `packages/coding-agent/CHANGELOG.md`
- （仅在必需时）W1–W3 产物文件的**最小修复**

## 写入禁止面

- 其它 key 目录；`packages/ai/src/models.generated.ts`；`packages/multi-workers/mw.py` 的 `_goal_gate_install`/`cmd_model` 段与 `ui-bridge.ts:3302-3391` 段（并行 key 写入面）
- 禁止 `git add`/`commit`；禁止 `npm run build`/`npm test`；禁止把任何凭据写入文件或输出

## 验收命令

```bash
cd packages/multi-workers && python -m pytest -q
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
cd H:/git/Multi-Workers && npm run check
```

## 改动历史

- 新建任务；文档/证据为主，代码改动仅限 W1–W3 缺陷的最小修复。

## 交付格式

- 证据文件 + 文档改动 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行（**例外**：`npm run check` 的全量输出按仓库规则完整保留，但 report 里只摘关键行）。
