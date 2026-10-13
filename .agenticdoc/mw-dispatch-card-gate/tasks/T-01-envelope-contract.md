# T-01 信封契约库（TS 叶子层）

- Key: mw-dispatch-card-gate｜Wave: 1｜依赖: 无｜type: coding

## 上下文
派发链上没有任何一层读取任务卡，投递物正文等于 PM 描述原文（`evidence/research/spec-dispatch-input-format-20261012.md` ③）。本卡建立**单一判据实现**，供工具层与服务层复用，避免两处判据漂移（`design.md` §4）。

## 要求
1. 新建叶子层 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`，仅 import `node:fs`、`node:path` 与 `./paths.ts`。
2. 实现并导出：
   - `ENVELOPE_SECTIONS = ["context","requirements","deliverables"] as const`
   - `readEnvelope(cardPath): { ok, missing[], type, detected{context,requirements,deliverables} }` —— 段非空判据用**宽档**：标题命中**或**段落语义命中（词表见 `evidence/research/spec-card-format-corpus-20261012.md` 的槽位词频表：描述/输入/目标/预期产出/交付物/状态与证据 等）；文件不存在或 `type:` 缺失 ⇒ `ok=false` 并把缺失项写入 `missing`。
   - `typeExtrasMissing(type, text): string[]` —— `coding` 缺「写入允许面/写入禁止面/验收命令/改动历史」、`research` 缺「唯一证据文件」、`review` 缺「审计目标/未覆盖面声明」时返回项名；未定义类型返回 `["unknown-type:"+type]`。
3. 只做判据，不做拦截（调用方决定动作）；不做内容质量评判。
4. 新增测试 `packages/coding-agent/test/suite/dispatch-card-envelope.test.ts`：≥12 个用例（含**字节金样本**：合规卡/缺各段/空段/coding 缺附加项/review 缺未覆盖面/文件不存在/CRLF 与 LF 等价）。

## 交付格式
- 写入允许面：上述 2 个新文件（`shared/dispatch-card.ts`、`test/suite/dispatch-card-envelope.test.ts`）。
- 写入禁止面：`pm/`、`worker/`、`packages/multi-workers/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录）。
- 交付物：两个文件的实现与测试；`report.md` 须含改动清单 + 上下文来源清单。
- 回收判据：
  - 验收命令（在 `packages/coding-agent` 下）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts` ⇒ 全绿；
  - 报告改动清单 ⊆ `trace.log` 写入事件；
  - 不得修改既有测试期望值来迁就实现。
