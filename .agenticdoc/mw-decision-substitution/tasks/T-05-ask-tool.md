# T-05 `ask_decision` 工具 + 注册接线 + 反重试

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-004/005/013/015）+ design.md D-017 + plan.md §1

## 上下文

- 工具注册：`pi.registerTool` + TypeBox；**失败必须 throw**（`packages/agent/src/types.ts:355-368` 的 `AgentToolResult` 无 `isError`）。
- 范例：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:130-152`。
- 注册范围：仅 worker 分支（`index.ts:72-75`），经 `activeToolsForType` 全角色追加，**不进 `TOOL_ALLOWLISTS`**。
- `tool_call` 钩子只做同步快判定；Python 往返只在 `execute` 内 async spawn + 20s 硬超时。
- 详细契约见 `evidence/research/design-ask-tool-hook-20261019.md` Q1..Q6。

## 要求

1. 新建 `pm/decision-tool.ts`：
   - 入参 `dp`（id 枚举，来自注册表常量）/`trigger`/可选 `question`/`note`。
   - 出参：单行 JSON `{available, decision_id, mode, acted, answers, confidence_source, latency_ms}`；失败为 `{available:false, unavailable:<frozen reason>, action:"blocked-ask-human"}` 并附固定"不要自行猜测"指令。
   - `execute` 内调 `mw decide run --dp <id> --request-file <tmp> --json`（async），超时 20s 杀进程。
2. 在 `index.ts` 注册（worker 分支）+ `activeToolsForType` 追加。
3. 反重试：同一 dp 同一轮内 block 计数，超阈值终止该工具循环；trace 留行。
4. 新建 `test/suite/decision-tool.test.ts`：成功/不可用/超时/非法 JSON/未注册 dp 五条路径，断言 `unavailable` 时返回体含"不要自行猜测"，且不抛未捕获异常。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/agent/src/types.ts:355-368`
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:130-152`

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`
- `packages/coding-agent/test/suite/decision-tool.test.ts`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-tool.test.ts
```

## 改动历史

- 2026-10-20 创建
