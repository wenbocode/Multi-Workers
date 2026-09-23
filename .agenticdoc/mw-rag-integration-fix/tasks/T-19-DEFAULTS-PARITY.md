# Task T-19: 默认解析收敛为单一解析器 + 跨语言一致（T-15 的收尾）

## 元信息
- Stage: 1（T-15 的补正，与 T-17 无文件冲突；**必须在 T-17 之前完成**，T-17 依赖最终 TS 源码重建 dist）
- 依赖: T-15（已完成）
- 风险等级: 低-中
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-101, AC-107]
- vc_refs: [VC-101, VC-102, VC-110, VC-111]
- pattern_refs: []

- `[VERIFY]` 行必须 `process.stdout.write`（TS）/ `print` + `pytest -s`（Python）（坑点 P-006）。

## 背景（T-15 上报的两处真实偏差，PM 已复核确认）

T-15 把 role/phase 默认接进了运行时，但留下两处**跨语言不一致**：

1. **server 优先级被 `default_server` 遮盖**（T-15 偏离说明 4）：
   `rag/tools.ts:458` 与 `rag/block.ts:80` 写的是 `roleRes?.server ?? phaseRes?.server ?? defaultServer`，
   而 `resolveForRole` 内部已经回落 `defaultServer` → 当「`default_server` 已设 + 角色 spec 没有 `server` + 阶段 spec 有 `server`」时，
   阶段声明的 server 被 default 遮盖。Python `_rag_resolve_defaults`（`mw_common.py:856`）是
   `role_spec.get("server") or phase_spec.get("server") or default_server`（**取声明值**），
   上位 design 的权威口径也是「角色声明 > 阶段声明 > `defaultServer` > 报错」。
2. **rewrite 兜底口径不一致**：TS `rewriteDefaults`（`rag/adapter.ts:247`）用「研究角色 **或** 研究阶段」，
   Python `_rag_resolve_defaults`（`mw_common.py:866`）用 `role in RAG_RESEARCH_ROLES`（**只看角色**）→ 仅阶段为 `design` 时，
   注入块写 `Rewrite: true`（TS）而 Python 侧的渲染与解析是 `false`。按 AC-006「调研类**角色/阶段**」的口径，TS 正确，Python 应对齐。

另外：`resolveForRole`/`resolveForPhase` 在 T-15 之后只被 `block.ts` 与 `tools.ts` 用来做**错误的** `??` 链，
本身没有独立价值 → 收敛成一个解析器，别留下第二个 P-005 死角。

设计：`design.md` D-102（修订）、D-104（修订）、D-109、VC-111。

## 必须实现

### 1) TS：新增单一解析器 `resolveDefaults`（`rag/config.ts`）

```ts
export function resolveDefaults(config: RagConfig, role: string, phase: string):
  { server: string | null; source: string | null; rewrite: boolean } {
  const roleSpec = role !== "" ? config.roles[role] : undefined;
  const phaseSpec = phase !== "" ? config.phases[phase] : undefined;
  const server = roleSpec?.server ?? phaseSpec?.server ?? config.defaultServer ?? null;
  const source = roleSpec?.source ?? phaseSpec?.source ?? null;
  const explicit = roleSpec?.rewrite ?? phaseSpec?.rewrite;
  const capabilityRewrite = server !== null && config.servers[server]?.capabilities.rewrite === true;
  return { server, source, rewrite: rewriteDefaults(role, phase, capabilityRewrite, explicit) };
}
```
（`rewriteDefaults` 保持为唯一的 rewrite 判定函数，不新增第二套；空 role/phase → 退化为 `defaultServer` / `null` / `false`，与 T-15 的「零介入」口径一致。）

- `rag/block.ts` 与 `rag/tools.ts` 的 `callRag` 都改用它（删掉各自的 `roleRes`/`phaseRes` 组合）。
- **删除** `resolveForRole` / `resolveForPhase`（含其导出与注释），把 `test/suite/rag-config.test.ts:300-312` 的断言改写到
  `resolveDefaults`（至少保留：research 角色 rewrite=true、coding 角色 false、阶段 design 命中、role 优先于 phase）。
- 行为不变的硬要求：`role=""`/`phase=""` 时 `resolveDefaults` 必须给出与 T-15 前完全相同的取值
  （`server = defaultServer`、`source = null`、`rewrite = false`），golden 与既有断言不受影响。

### 2) Python：rewrite 兜底对齐（`mw_common.py:866`）

`rewrite = bool(caps.rewrite) and role in RAG_RESEARCH_ROLES` → 改为「研究角色**或**研究阶段」
（`role in RAG_RESEARCH_ROLES or phase in RAG_RESEARCH_PHASES`；若没有 `RAG_RESEARCH_PHASES`，按 `RAG_RESEARCH_ROLES` 的形态新增一个
`{"spec", "design"}` 常量并与 `config.ts` 的 `isResearchPhase` 取值一致）。选中的 server 仍按第 1 步的声明值优先级。

### 3) 跨语言对照 fixture（VC-111）

新增 `packages/multi-workers/test/fixtures/rag/phase-only-target.yml`（**不要动 `target.yml` 与 golden 相关文件**）：

```yaml
rag:
  enabled: [A, B]
  default_server: B          # B 无 rewrite 能力
  roles:
    coding:
      require: true          # 故意不声明 server
  phases:
    design:
      server: A              # A 有 rewrite: true（复用 machine-servers.yml）
      source: docs
  budgets:
    chat_budget: 2
    time_budget_s: 900
```

- TS（`rag-parity.test.ts` 或新用例）：`resolveDefaults(config, "coding", "design")` → **`{server: "A", source: "docs", rewrite: true}`**；
  并断言 `resolveDefaults(config, "coding", "")` → `server: "B"`、`rewrite: false`（证明 default 仍在正确位置生效）。
- Python（`test_rag_config.py`）：同一 fixture 下 `render_rag_block(config, {"type": "coding", "phase": "design"})` 的
  三行必须分别是 `[mw] Default server: A`、`[mw] Default source: docs`、`[mw] Rewrite: true`。
- 两侧各打一行 `[VERIFY] VC-111`，字段含 `server=… source=… rewrite=…`（值为解析结果，不得写死期望常量当输出）。

## 验收

1. `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts test/suite/rag-role-defaults.test.ts test/suite/rag-parity.test.ts test/suite/rag-tools.test.ts test/suite/rag-required.test.ts test/suite/rag-adapter.test.ts` 全绿。
2. 十二套 `test/suite/rag-*.test.ts` 全绿（基线 `101 passed | 1 skipped`，允许 T-19 新增用例计数上升）。
3. **golden 不变**：`sha256(test/fixtures/rag-block.golden.md)` = `00f85e64…`，`[VERIFY] VC-027` 仍 `golden_byte_match=true fingerprint_match=true`。
4. Python：`python -m pytest test_rag_config.py test_rag_audit.py test_rag_phase.py test_rag_cli.py test_rag_launcher.py test_rag_research.py -q` 全绿；`python -m pytest -q` 无新增失败。
5. 仓根 `npm run check` exit 0。
6. `rg -n "resolveForRole|resolveForPhase" packages/coding-agent/src packages/coding-agent/test` **零命中**（证明没有留下第二个死角）；
   `rg -n "VC-111"` 在两侧测试里各命中一次。

## 禁止

- 不改 `mw.py` 的 role 回落（T-16 已对齐，保持 `coding`）；不改 `launcher.py`/README/env 文档（归 T-17）；
  不改 `test/fixtures/rag/target.yml`、`test/fixtures/rag-block.golden.md`、`machine-servers.yml`；
  不改文本层守护（`test_autopilot_l0.py`）；不 commit。
