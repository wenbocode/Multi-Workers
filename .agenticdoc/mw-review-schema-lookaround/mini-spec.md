# Mini-Spec: mw-review-schema-lookaround

- Date: 2026-10-15
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop（write-surface / worker-file-tool）
- Origin: QG 后用户裁决（方案 B）；证据链 `mw-model-error-perception/workers/qg-review-mep/worker.log` 502 + 读码溯源

## Problem

review 角色默认模型 `gpt-6.1-sol`（timi→litellm→Azure 部署）对 `tools[].function.parameters` 的 JSON schema 做严格校验，**拒绝 ECMA lookaround**。`worker_file` 工具的 schema `file.pattern` 内嵌 `WORKER_FILE_PATH_RE.source`，其中 `WORKER_FILE_EVIDENCE_SEG`（write-surface.ts:64）含负向前瞻 `(?!\\.{1,2}(?:/|$))` → 该组合下 worker 首个 LLM 请求即 502，0 工具调用终止（qg-review-mep 实证）。影响面 = writeless 角色（review/verifier/reviewer/rag-research）× 严格校验通道。

## Root Cause（实证）

`WORKER_FILE_EVIDENCE_SEG = "(?!\\.{1,2}(?:/|$))[A-Za-z0-9._-]+"` 的 lookaround 仅用于拒绝 `.`/`..` 路径段。等价无 lookaround 构造：段内强制至少一个非点字符 → `[A-Za-z0-9._-]*[A-Za-z0-9_-][A-Za-z0-9._-]*`（全点串不可匹配，其余逐字符等价；空段两边都拒绝）。

## Change

1. `shared/write-surface.ts:64`：`WORKER_FILE_EVIDENCE_SEG` 改为无 lookaround 等价式（该常量同时供运行时校验与 schema pattern，一处改两生效）。
2. `test/extensions/agent-team-loop-worker-file-tool.test.ts`：schema 测试处补防回归断言——`file.pattern` 不含 `(?=`/`(?!`/`(?<=`/`(?<!`。
3. CHANGELOG（coding-agent [Unreleased] Fixed）：严格 schema 校验模型（Azure）下 writeless 角色无法启动的根因修复。

## Files（写入允许面）

- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts`
- `packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts`
- `packages/coding-agent/CHANGELOG.md`

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-1 | 新正则与旧正则路径白名单语义等价（合法路径全过、`.`/`..`/空段/`evidence/../x`/`evidence/./x` 全拒） | node 等价性探针（新旧正则对用例矩阵逐项比对） |
| AC-2 | `worker_file` schema `file.pattern` 不含 lookaround（防回归钉死） | 套件断言 + 套件全绿 |
| AC-3 | 既有行为无回归 | worker-file-tool 套件 + checkpoint-wiring + write-surface 相关套件全绿；biome 对两文件 clean |

## Out of Scope

- dispatch.yml 默认模型调整（用户配置项）；proxy 层 schema 清洗（跨项目）；`npm run build`（用户执行）。

## Outcome（2026-10-15 执行完毕）

- AC-1 ✅：等价性探针（真实模块常量）22/22 旧==新（2 条探针期望值笔误修正后归零：大写本在字符集、`.agenticdoc/../` 键段无点防护为旧正则既有属性）；附带修复 1 个潜在用例分歧（全点段 `evidence/...` 旧正则误放行，新正则正确拒绝——旧常量下该套件 3 failed，新常量 2 failed）。
- AC-2 ✅：套件断言 `file.pattern` 与 `WORKER_FILE_PATH_RE.source` 均不含 `(?=`/`(?!`/`(?<=`/`(?<!`。
- AC-3 ✅：agent-team-loop-worker-file-tool 9/9 全绿；write-surface 消费方 8 套件 196 passed + 1 既有失败（mwds-t02 语料回放：本会话新派发卡片致命中集漂移，A/B 证实与新旧常量无关）；biome 对两改动文件 clean。
- 附带 PM 直执：`snapshot()` 按 D-102 白名单过滤（他窗 progress-persist 提交 6e8ed174d 使 task 目录新增 trace.log，裸 readdir 快照被污染——同 VC-007 类基线适配，留痕本节）。
- CHANGELOG：coding-agent [Unreleased] Fixed 已落（mw-review-schema-lookaround）。
- 运行时生效同前：需 `npm run build` + `/mw restart`；在此之前 gpt-6.1-sol 的 review worker 仍会 502（或临时用 `mw model set review <非严格校验模型>` 顶替）。
