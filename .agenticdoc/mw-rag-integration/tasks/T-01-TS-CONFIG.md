# Task T-01-TS-CONFIG: RAG 配置层（两层合并 / 校验 / 默认与必需 / 指纹）

## 基本信息
- Stage: 1
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型，本仓 TS + vitest）
- ac_refs: [AC-002, AC-003]
- vc_refs: [VC-002, VC-024]
- pattern_refs: []

## 描述

### 源码

1. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts`（纯解析层：无网络、无写盘；只读文件）。形状照既有 `shared/target-config.ts`：模块级 `fail(kind, message): never` 抛 `RagConfigError extends Error { kind: RagConfigErrorKind }`，`requireString` / `optionalString` / `stringArray` 守卫，顶层键白名单校验（未知键报错，不静默忽略）。

导出（名字可微调，语义不可变）：

```ts
export type RagTransport = "mcp" | "skill" | "both";
export type RagConfigErrorKind =
	| "bad-yaml" | "invalid-shape" | "unknown-key" | "unknown-server"
	| "mcp-missing-url" | "skill-missing-cli" | "enabled-empty-entry";

export interface RagServerEntry {
	transport: RagTransport;
	mcp: { url: string; tokenEnv: string | null; timeoutMs: number } | null;
	skill: { dir: string; cliEntry: string; timeoutMs: number } | null;
	adapter: "overcode-v1";
	pathRootsFile: string | null;
	sources: string[];
	capabilities: { graph: boolean; chat: boolean; rewrite: boolean };
	origin: Record<string, "machine" | "project">;   // 逐字段来源（evaluated field path -> origin）
}
export interface RagRoleSpec { server?: string; source?: string; require?: boolean; rewrite?: boolean; chatBudget?: number; timeBudgetS?: number }
export interface RagPhaseSpec { server?: string; source?: string; require?: boolean; rewrite?: boolean }
export interface RagConfig {
	enabled: string[];
	defaultServer: string | null;
	servers: Record<string, RagServerEntry>;
	roles: Record<string, RagRoleSpec>;
	phases: Record<string, RagPhaseSpec>;
	fingerprint: string;
}

export function machineRagServersPath(env?: NodeJS.ProcessEnv): string;       // D-013 解析顺序
export function loadRagConfig(controlRoot: string): RagConfig;               // 无 config 时返回 enabled=[]
export function mergeServerEntry(machine: unknown, project: unknown, name: string): RagServerEntry;
export function resolveForRole(config: RagConfig, role: string): { server: string | null; source: string | null; rewrite: boolean };
export function resolveForPhase(config: RagConfig, phase: string): { server: string | null; source: string | null; rewrite: boolean };
export function requiredFor(config: RagConfig, role: string, phase: string): boolean;   // role.require OR phase.require
export function ragFingerprint(config: RagConfig, enabledOnly?: string[]): string;      // D-009 范围
```

实现要点：
- **机器级路径**：`MW_RAG_SERVERS_FILE`（整文件覆盖，测试钩子）→ `MW_RAG_SERVERS_HOME`（目录）→ `$HOME` → `%USERPROFILE%`；目标文件 `<home>/.agents/rag-servers.yml`。文件/目录不存在 = 该层为空（**不创建**，D-014）。
- **项目级**：`<controlRoot>/.mw/rag-servers.yml`；`target.yml` 的 `rag:` 段提供 `enabled` / `defaultServer` / `roles` / `phases` / `budgets`。读 target.yml 复用既有解析器：把 `target-config.ts` 内私有 `readTargetYml(controlRoot)` 导出为 `rawTargetYml(controlRoot): Record<string, unknown>`（**不要**新写第二个 target.yml 解析器，P-003 单一来源），本任务只加导出不改其语义。
- **逐字段合并（D-003）**：按 server 名对齐；标量/嵌套对象逐键合并（项目级给值即覆盖）；数组字段（`sources`）整体替换；`null` = 显式删除该字段（可删除机器级 `skill` 块）；`origin` 逐字段记录（形如 `mcp.url`、`mcp.tokenEnv`、`sources`、`skill`）。项目级未给 `transport` 时继承机器级。
- **校验**：`rag.enabled` 里出现未定义 server → `unknown-server`（消息含 server 名与可见 server 列表）；`transport` 含 mcp 但无 url → `mcp-missing-url`；含 skill 但无 `cliEntry` → `skill-missing-cli`；未知顶层键 → `unknown-key`。显式传入未定义 server 一律报错，不做静默回落。
- **默认解析**：`resolveForRole/Phase` 返回 `{server, source, rewrite}`，`rewrite` 默认 = `capabilities.rewrite && (role 属 spec/design/research 类)`；最终 server 取值优先级 角色 > 阶段 > `defaultServer` > null。
- **指纹（D-009）**：`node:crypto` `createHash("sha256")` over **规范化 JSON**：仅启用集内 server 的 `{name, transport, mcp.url, mcp.tokenEnv, mcp.timeoutMs, skill.dir, skill.cliEntry, pathRootsFile, pathRootsDigest(文件内容 sha256), sources, capabilities, adapter}` + 角色/阶段解析结果 + 预算值。**排除**探活/健康状态、session id、未启用 server 的任何字段。

### 与 Python 侧锁定的契约（T-06 已落地，必须对齐）

- 两层 YAML 文件形态 `{servers: {<name>: {...}}}`，**只有 `servers` 是合法顶层键**（否则 `unknown-key`）；`target.yml` 的 `rag:` 段接受 `enabled` / `default_server` / `roles` / `phases` / `budgets`。
- 文件字段为 snake_case（`token_env`/`timeout_ms`/`cli_entry`/`path_roots_file`/`default_server`/`chat_budget`/`time_budget_s`）；`mw_common.RAG_FIELD_CAMEL` 是权威映射表，TS 必须接受 snake_case 输入并在对外结构用 camelCase。
- `origin` 键为 snake_case 求值字段路径（`mcp.url`、`mcp.token_env`、`capabilities.graph`、`sources`、`skill`）。
- `MW_RAG_SERVERS_FILE` 硬覆盖：设定但文件缺失 → 机器层为空，**不回落 HOME**。
- 指纹 canonical JSON：键排序、`separators=(",",":")`、非 ASCII 不转义、整值浮点归一为 int；重算时忽略配置中的 `fingerprint` 键；`roles`/`phases` 整块参与，server 条目按启用集过滤；`path_roots_digest` 在 load 时算（相对路径按 project root 解析）。
- 共享输入 fixture：`packages/multi-workers/test/fixtures/rag/{machine-servers.yml,project-servers.yml,target.yml,rag-roots.json}`；rag 块字节契约：`packages/multi-workers/test/fixtures/rag-block.golden.md`（347 B，无尾换行）。
- 若你已开工且未按上述形态实现：**不要重写已完成的部分**，保持现有实现并把偏差写进 output.md（T-12 会以 Python/golden 为准统一修正）。

### 测试

新增 `packages/coding-agent/test/suite/rag-config.test.ts`（`vitest`，用 `fs.mkdtempSync` + 临时 controlRoot，`MW_RAG_SERVERS_FILE` 注入机器层）：

- **合并矩阵（VC-024）**：机器层 A 含全字段（mcp.url/tokenEnv/timeoutMs + skill + capabilities + sources + pathRootsFile）；项目层只覆盖 `A.mcp.url` → 断言 `url` = 项目值、`tokenEnv/timeoutMs/capabilities/sources` 继承机器层、`origin` 逐字段标注（`mcp.url` = project，其余 = machine）；`sources: []` → 清空（非继承）；`skill: null` → 删除且 origin 标注；机器层 B 不受任何影响。
- **加载与校验（VC-002/VC-003）**：`enabled` 引用未定义 server → 抛 `RagConfigError` 且 `kind === "unknown-server"`；skill 无 cliEntry → `skill-missing-cli`；mcp 无 url → `mcp-missing-url`；无 `rag` 段/无 `.mw/rag-servers.yml` → `enabled` 为空数组且不抛错。
- **必需并集**：`roles.review.require=true` → `requiredFor("review", <任意 phase>)` true；仅 `phases.design.require=true` → `requiredFor("coding","design")` true；两者皆 false → false。
- **指纹范围（VC-022 的一半）**：改 `mcp.url` → 指纹变；改 path_roots 文件**内容** → 指纹变；改未启用 server 的字段 → 指纹不变；改探活/健康字段 → 指纹不变。

### 注意

- Node strip-only 可擦除语法（AGENTS.md）：无 `enum`/`namespace`/参数属性；无 inline import；不使用 `any`（未知 YAML 输入用 `unknown` + 守卫收窄）。
- `yaml` 已是 `packages/coding-agent` 直接依赖（`package.json` `"yaml": "2.9.0"`，`target-config.ts:36` 已在用）——直接用，不新增依赖。
- 测试运行（coding-agent 包根）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts`。

## 完成判定

- `rag-config.test.ts` 全绿，且每条断言在输出中对应 `[VERIFY] VC-002` / `[VERIFY] VC-024`。
- `npm run check` 对本包 0 error / 0 warning / 0 info（TS 部分）。
- `target-config.ts` 的改动限于新增 `export`，其既有测试零修改通过。
