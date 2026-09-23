# RAG 配置手册（Multi-Workers）

> **读者**：要给自己的项目接上 RAG/MCP 知识库的 mw 用户（PM 窗口或终端用户）。
> **一句话**：RAG 是**可选**能力；没配 `rag:` 段的项目零影响（不注册工具、不注入 task.md、不探活、不写文件）。
> **先看结论**：`python mw.py rag init --project <控制工作区>` 会按示例生成三个带注释的配置文件，你改字段即可；
> 本手册逐字段说明每个配置的含义、取值、默认与写错的后果，并给出四类可直接复制粘贴的完整示例。
> **权威性**：字段集合的真源是 `packages/multi-workers/mw_common.py` 的校验器（`_RAG_SERVER_FIELDS` /
> `_RAG_NESTED_FIELDS` / `_RAG_TARGET_KEYS` / `_RAG_ROLE_KEYS` / `_RAG_PHASE_KEYS` / `_RAG_BUDGET_KEYS`）与 TS 侧
> `packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts`；手册里三个模板块逐字取自
> `python mw.py rag init --print` 的实跑输出（`test_rag_docs.py` 做字节 parity 锁定，手改手册会变红）。

---

## 1. 3 分钟上手

```bash
# 1) 生成模板（零交互；默认写 <dir>/.mw/rag-servers.yml 与 <dir>/.agenticdoc/target.yml 的 rag: 段）
python mw.py rag init --project <控制工作区>

# 2) 编辑 <控制工作区>/.mw/rag-servers.yml：至少改 mcp.url 与 mcp.token_env（token_env 只填变量名）
#    默认会同时写出 .mw/rag-roots.json（engine: "." = 本项目根）并激活 path_roots_file；
#    不需要磁盘核对时用 --no-roots 跳过（此时 path_roots_file 保持注释）

# 3) 把服务名填进 target.yml 的 rag.enabled（空 = 全关）；也可以第 1 步直接用 --enable 一步写一致
python mw.py rag init --project <控制工作区> --enable --server overcode \
  --url http://localhost:8100/mcp/ --token-env OVERCODE_MCP_TOKEN

# 4) 验证（都在控制工作区根执行）
python mw.py rag list  --project <控制工作区>          # 合并后的 server 表 + 逐字段来源
python mw.py rag probe --project <控制工作区>          # 探活（诊断；不可达仍 exit 0）
python mw.py rag sync  --project <控制工作区>          # 把 skill 说明同步到 .pi/skills（可选）

# 5) 重启 mw serve，让新配置进入 worker 进程环境
```

改服务名时**不要只改服务表**：`target.yml` 的 `enabled` / `default_server` / `roles.*.server` / `phases.*.server`
都要同步改（见 §8）。一开始就用 `mw rag init --server <name> --enable` 生成可以避免漏改。

---

## 2. 三个文件的角色与优先级

| 文件 | 角色 | 谁写 | 优先级 |
|---|---|---|---|
| `~/.agents/rag-servers.yml`（可用 `MW_RAG_SERVERS_HOME` 改 HOME，或用 `MW_RAG_SERVERS_FILE` 直接指定文件） | **机器层**：本机所有 RAG 服务的连接信息，跨项目共享 | `mw rag init --machine` / `--only-machine`，或手工 | 低 |
| `<控制工作区>/.mw/rag-servers.yml` | **项目层**：本项目对机器层的覆盖 | `mw rag init`（默认写这层） | 中（同名字段覆盖机器层） |
| `<控制工作区>/.agenticdoc/target.yml` 的 `rag:` 段 | **选择与配置**：启用哪些服务、默认服务、角色/阶段要求与预算 | `mw rag init`（无 `rag:` 键时文本级追加），或手工 | 最高（决定 run 时行为） |

两层服务表形态都是 `{servers: {<name>: {...}}}`，**只有 `servers` 是合法顶层键**（多写别的顶层键会报
`unknown key(s)`）。合并是**逐字段**的：

- 项目层设置了某字段 → 用项目层值；否则用机器层值。
- 数组（`sources`）**整体替换**，不拼接。
- `null` 删除该字段（项目层 `skill: null` = 明确删掉机器层的 skill 块）。
- 每个字段的来源记在 `origin` 里，`mw rag list` 会打印 `[machine]` / `[project]`；`mw rag list --json` 是机器可读形态。

---

## 3. 逐字段参考（每字段 4 列：是什么 / 取值与默认 / 举例 / 写错的后果）

### 3.1 `rag-servers.yml` 服务表字段

| 字段 | 是什么 | 取值与默认 | 举例 | 写错的后果 |
|---|---|---|---|---|
| `transport` | 通信方式：走远程 MCP 还是本地 CLI | `mcp`（默认）/ `skill` / `both`；`both` = MCP 优先，仅**连接层**失败时只读工具降级 CLI | `transport: both` | 拼错（如 `mcps`）→ 配置整体不可用：`transport must be one of mcp, skill, both`，`rag list` exit 1 |
| `adapter` | 协议适配器 id（逻辑工具名 → 线上工具名的映射表） | 只能 `overcode-v1`（默认） | `adapter: overcode-v1` | 写成别的值 → `adapter must be 'overcode-v1'` |
| `path_roots_file` | `mw rag audit` 用来把引用落到本地磁盘的 JSON 映射文件（根角色 → 本地根） | 相对路径按项目根解析；`mw rag init` 默认写成 `.mw/rag-roots.json`（该文件同时写出，值 `engine: "."` = 本项目根）；`--no-roots` 时默认 `null`（不做磁盘核对，审计记为 `unverified`） | `.mw/rag-roots.json` | 指向不存在的文件 → 每条引用 `exists=false`、`local_path` 为空，审计全部 `unverified`；所以只有 `--no-roots`（没写文件）时该字段才保持注释，手工激活前先确认文件存在 |
| `sources` | 这个服务端有哪些可检索数据源；引用 `server:source:file_path:line` 的**第 2 段**就是它 | 非空字符串数组；默认 `[]` = 用服务端默认 | `sources: [code, docs]` | 写了服务端不存在的 source → 调用返回空结果或失败；含空串 → `sources must be a list of non-empty strings` |
| `capabilities.graph` | 是否支持引用图 / 相关文件查询（`rag_graph`、`rag_impact`） | 布尔；默认 `false` | `graph: true` | 服务端无此能力却写 `true` → 调用报能力错误（不计入熔断），工具白跑 |
| `capabilities.chat` | 是否支持自然语言问答（`rag_chat`，仅 `rag-research` 任务注册） | 布尔；默认 `false` | `chat: true` | 同上：报能力错误 |
| `capabilities.rewrite` | 是否支持检索前查询改写（角色/阶段 `rewrite: true` 生效的前提） | 布尔；默认 `false` | `rewrite: true` | 服务端无此能力却写 `true` 且角色开了 `rewrite` → 调用报能力错误 |
| `mcp.url` | MCP endpoint（streamable HTTP JSON-RPC） | 非空 URL；`transport` 为 `mcp`/`both` 时**必需** | `http://localhost:8100/mcp/` | 缺了 → `transport 'mcp' requires mcp.url`；写错端口/路径 → 会话开始探活失败，工具描述带 `[unreachable at session start]` |
| `mcp.token_env` | 持有令牌的**环境变量名**，不是令牌本身；值由 `mw serve` 自己的环境提供 | 变量名或 `null`；默认 `null`（不加认证头） | `OVERCODE_MCP_TOKEN` | 填了令牌值 → mw 会拿它当变量名去查环境，认证失败；且令牌值可能随配置文件泄漏 |
| `mcp.timeout_ms` | 单次 MCP 请求超时（毫秒） | 正整数；默认 `180000` | `180000` | 非正整数 → `mcp.timeout_ms must be a positive integer` |
| `skill.dir` | 本地 CLI 的工作目录（相对项目根） | 非空字符串；**TS 侧必填**（缺省或 `null` 报 `must be a non-empty string`），Python 侧接受 `null`/缺省 = 项目根；要项目根就写 `.`（见 §8 遗留） | `skills/overcode` | 只写 `skill: {cli_entry: ...}` 不给 `dir` → TS 侧报错；写错路径 → CLI 入口找不到 |
| `skill.cli_entry` | 运行本地 CLI 适配器的命令；`transport` 为 `skill`/`both` 时**必需** | 非空字符串 | `python overcode_cli.py` | 缺了 → `transport 'skill' requires skill.cli_entry` |
| `skill.timeout_ms` | 单次 CLI 调用超时（毫秒） | 正整数；默认 `180000` | `180000` | 非正整数 → `skill.timeout_ms must be a positive integer` |

### 3.2 `target.yml` 的 `rag:` 段字段

| 字段 | 是什么 | 取值与默认 | 举例 | 写错的后果 |
|---|---|---|---|---|
| `enabled` | 本项目的启用集；每个名字都必须在服务表里声明 | 非空字符串数组；**空或缺省 = 全关**（不是全开） | `enabled: [overcode]` | 引用未声明的名字 → `unknown rag server 'nope' in rag.enabled (available: ...)`，`rag list` exit 1；写空数组或删掉 = RAG 全关 |
| `default_server` | 角色/阶段没有指定 server 时的兜底 | 已声明的服务名或 `null`；默认 `null` | `default_server: overcode` | 未声明 → `unknown rag server 'x' in rag.default_server (available: ...)` |
| `roles` | 按**角色**覆盖（server/source/require/rewrite，另加 chat_budget/time_budget_s） | 映射；默认 `{}` | `roles: {review: {require: true}}` | 项内多写键 → `unknown key(s) ... (valid: ...)`；server 未声明 → `unknown rag server 'x' in rag.roles.review.server` |
| `phases` | 按**阶段**覆盖；键名**大小写敏感**，必须与 `pm-state.md` 的阶段值一致 | 映射；默认 `{}` | `phases: {design: {require: true}}` | 写成 `DESIGN` → 静默不生效（不报错，只是匹配不上） |
| `budgets.chat_budget` | 每个任务允许的 `rag_chat` 调用次数上限 | 正整数；默认 `2` | `chat_budget: 4` | 非正/非整数 → `target.yml rag.budgets.chat_budget must be a positive integer` |
| `budgets.time_budget_s` | 每个任务的 RAG 工具时间上限（秒） | 正整数；默认 `900` | `time_budget_s: 1200` | 非正/非整数 → `target.yml rag.budgets.time_budget_s must be a positive integer` |

### 3.3 `roles` / `phases` 项内字段

| 字段 | 是什么 | 取值与默认 | 举例 | 写错的后果 |
|---|---|---|---|---|
| `server` | 该角色/阶段默认用哪个服务（优先于 `default_server`） | 已声明的服务名 | `server: overcode` | 未声明 → `unknown rag server 'x' in rag.roles.review.server`（phases 同理） |
| `source` | 默认 source 段（引用第 2 段的兜底） | 字符串 | `source: docs` | 服务端没有该 source → 检索空结果；不影响配置解析 |
| `require` | 该角色/阶段是否必须有可核对引用；`required = role.require OR phase.require` | 布尔；默认 `false` | `require: true` | 写成字符串 `"true"` → `target.yml rag.roles.review.require must be a boolean` |
| `rewrite` | 是否允许查询改写（还需服务端 `capabilities.rewrite: true`） | 布尔；缺省时研究类角色/阶段 + 服务能力推导 | `rewrite: true` | 服务端无 rewrite 能力 → 改写被跳过或报能力错误 |
| `chat_budget` | 角色级 `rag_chat` 次数上限；**只有 `roles` 接受**，`phases` 不接受 | 正整数 | `roles: {research: {chat_budget: 8}}` | 写进 `phases` → `unknown key(s) chat_budget (valid: server, source, require, rewrite)` |
| `time_budget_s` | 角色级 RAG 时间上限（秒）；**只有 `roles` 接受** | 正整数 | `roles: {research: {time_budget_s: 1800}}` | 写进 `phases` → `unknown key(s) time_budget_s (valid: server, source, require, rewrite)` |

### 3.4 `rag-roots.json`

`path_roots_file` 指向的 JSON 对象，键 = 引用的**根角色名**，值 = 本地根（可以是相对项目根的路径，
`"."` 就是本项目）。`mw rag audit` 用它把
`server:source:file_path:line` 的 `file_path` 段解析成本地文件（填充 `local_path` / `exists`）。

- `file_path` 写成 `role::relative/path` 时 `role` 就是键；裸路径默认按 `engine` 解析。
- 以 `_` 开头的键被忽略，可以放说明文字（模板里的 `_README` 就是）。
- 文件缺失/不是 JSON/值不是非空字符串 → 审计把该服务下的引用记为 `unverified`（不崩溃）：
  `path_roots file is not valid JSON` / `path_roots entry 'x' must be a non-empty path string` /
  `path_roots file missing: <path>`。
- 键存在但引用指的角色不在其中、或文件在根下确实不存在 → 记为 **`missing`**（会让 `mw rag audit` exit 1）：
  `unknown role 'x' (available roles: ...)` / `file missing`（同时打印解析出的 `local_path`）。

`mw rag init` 默认写出的模板（`--no-roots` 则不写、且 `path_roots_file` 保持注释）：

<!-- mw-rag-init:print roots -->
```json
{
  "_README": [
    "role -> local root, used by `mw rag audit` to resolve citations on disk",
    "(it fills in local_path / exists). Keys starting with _ are ignored.",
    "A citation `server:source:<role>::<relative path>:<line>` is looked up",
    "under roots[role]; a citation with no <role>:: prefix uses 'engine'.",
    "Values may be relative to the project root, so '.' means this project.",
    "Change 'engine' when your RAG server indexes a DIFFERENT tree, and add a",
    "key per extra role (e.g. 'game': '../game'). A citation naming a role that",
    "is missing here is reported by the audit as missing.",
    "The file must stay one JSON object; delete the keys you do not need."
  ],
  "engine": "."
}
```

---

## 4. 四类可直接复制粘贴的示例

> 三份文件都从 `mw rag init` 生成的模板改；下面每类给「服务表片段 + `rag:` 段片段 + 场景说明」。
> `sources` 的顺序不重要，但每个值必须是服务端真实存在的 source。

### 4.1 (a) MCP-only（服务端是远程 MCP；OverCode 真实形态）

`<控制工作区>/.mw/rag-servers.yml`：

```yaml
servers:
  overcode:
    transport: mcp
    adapter: overcode-v1
    path_roots_file: .mw/rag-roots.json
    sources: [code, docs]
    capabilities: {graph: true, chat: true, rewrite: true}
    mcp:
      url: http://localhost:8100/mcp/
      token_env: OVERCODE_MCP_TOKEN
      timeout_ms: 180000
```

`<控制工作区>/.agenticdoc/target.yml`：

```yaml
rag:
  enabled: [overcode]
  default_server: overcode
  budgets: {chat_budget: 2, time_budget_s: 900}
```

说明：`token_env: OVERCODE_MCP_TOKEN` 只声明变量名，令牌值放在 `mw serve` 启动环境里（改完要重启 serve）。
`path_roots_file` 要指向**真实存在**的 `.mw/rag-roots.json`（`mw rag init` 默认会写出它；若用了 `--no-roots`
或删掉了文件，就注释掉该字段）——悬空引用会让每条引用都 `exists=false`，看起来像「RAG 没效果」。

### 4.2 (b) CLI/skill-only（没有 MCP，只有本地 CLI）

`rag-servers.yml`：

```yaml
servers:
  engine-cli:
    transport: skill
    adapter: overcode-v1
    sources: [code]
    capabilities: {graph: false, chat: false, rewrite: false}
    skill:
      dir: skills/engine
      cli_entry: python engine_cli.py
      timeout_ms: 180000
```

`target.yml`：

```yaml
rag:
  enabled: [engine-cli]
  default_server: engine-cli
```

说明：`skill` 形态没有网络依赖，适合本地索引/沙箱；`cli_entry` 必须能在 `skill.dir`（相对项目根）下执行，
输出约定与服务端 MCP 一致（stdout JSON）。`rag_chat` 只有在 `rag-research` 任务类型下才会注册请求。

### 4.3 (c) both（MCP 优先，连接层失败时只读工具降级 CLI）

`rag-servers.yml`：

```yaml
servers:
  overcode:
    transport: both
    adapter: overcode-v1
    path_roots_file: .mw/rag-roots.json
    sources: [code, docs]
    capabilities: {graph: true, chat: true, rewrite: true}
    mcp:
      url: http://localhost:8100/mcp/
      token_env: OVERCODE_MCP_TOKEN
      timeout_ms: 180000
    skill:
      dir: skills/overcode
      cli_entry: python overcode_cli.py
      timeout_ms: 180000
```

`target.yml`：

```yaml
rag:
  enabled: [overcode]
  default_server: overcode
  roles:
    research:
      server: overcode
      rewrite: true
  budgets: {chat_budget: 4, time_budget_s: 1200}
```

说明：**只有**连接层失败（`kind=connect`）才降级，且只对只读工具生效。**不会**降级的：
`rag_feedback`（写回）、`rag_chat`（问答，且只在 `rag-research` 注册）、任何**超时**（超时不算连接层失败）。
降级会在 trace 里留 `rag_fallback server=... tool=... via=cli reason=connect`。

### 4.4 (d) 双服务 + 角色/阶段要求

`rag-servers.yml`：

```yaml
servers:
  overcode:
    transport: mcp
    adapter: overcode-v1
    path_roots_file: .mw/rag-roots.json
    sources: [docs, code]
    capabilities: {graph: true, chat: true, rewrite: true}
    mcp:
      url: http://localhost:8100/mcp/
      token_env: OVERCODE_MCP_TOKEN
      timeout_ms: 180000
  engine-cli:
    transport: skill
    adapter: overcode-v1
    sources: [code]
    skill:
      dir: skills/engine
      cli_entry: python engine_cli.py
      timeout_ms: 180000
```

`target.yml`：

```yaml
rag:
  enabled: [overcode, engine-cli]
  default_server: overcode
  roles:
    review:
      server: overcode
      source: docs
      require: true
    coding:
      server: engine-cli
      source: code
  phases:
    design:
      server: overcode
      require: true
  budgets:
    chat_budget: 4
    time_budget_s: 1200
```

说明：`required = role.require OR phase.require`（并集，无例外）。`enabled` 里的两个服务都会注册/探活；
`coding` 角色用 `engine-cli`，`review` 角色与 `design` 阶段用 `overcode`。

---

## 5. 命令参考与退出码

五个子命令共同的必填参数是 `--project <dir>`（argparse `required=True`）。

| 命令 | 参数 | 作用 |
|---|---|---|
| `init` | `--project`（必填）、`--server NAME`、`--url URL`、`--token-env VAR`、`--transport {mcp,skill,both}`、`--enable`、`--machine`、`--only-machine`、`--no-roots`、`--force`、`--dry-run`、`--print` | 生成带注释的模板；零交互；默认写项目层三处（`rag-servers.yml` / `target.yml` 的 `rag:` / `rag-roots.json`） |
| `list` | `--project`、`--json` | 打印合并后的 server 表 + 逐字段来源 + 启用集 |
| `probe` | `--project`、`--json` | 对启用集探活（诊断；不可达仍 exit 0） |
| `audit` | `--project`、`--key KEY`、`--json`、`--out FILE` | 只读审计：`rag_call` / 可核对引用 / required-but-unused；`--out` 是唯一会写的文件 |
| `sync` | `--project` | 把 skill 说明同步到 `<project>/.pi/skills/mw-rag.md`（启用时安装，未启用时删除） |

`init` 的参数语义：

- `--server` / `--url` / `--token-env`：模板里用的示例值（默认 `example` / `http://localhost:8100/mcp/` / `EXAMPLE_MCP_TOKEN`）。
- `--transport`：哪一段模板保持激活（默认 `mcp`；`skill` / `both` 会把另一段整体注释掉并写明原因）。
- `--enable`：把 `enabled:` 直接写成 `[<server>]`，并把 `default_server` 也写成该服务（一步写一致）。
- `--machine`：**额外**写机器层 `~/.agents/rag-servers.yml`；`--only-machine`：只写机器层。
- `--no-roots`：不写 `<project>/.mw/rag-roots.json`，并把 `path_roots_file` 保持注释（默认相反：写文件并激活该字段）。
- `--force`：覆盖已存在的文件；`rag:` 段用文本级整段替换（不会 YAML round-trip 毁注释）。
- `--dry-run` / `--print`：只读，不改任何文件，exit 0。

退出码（以 `mw.py` 实现为准）：

| 命令 | 0 | 1 | 2 |
|---|---|---|---|
| `init` | 成功（含 `--dry-run` / `--print`） | 拒绝或失败：文件/`rag:` 段已存在且没给 `--force`、`--machine` 与 `--only-machine` 同用、`--server` 非法、`--enable` 的服务未声明、写盘失败 | argparse 用法错误 |
| `list` | 成功 | 配置错误（解析/校验失败） | argparse 用法错误 |
| `probe` | 成功（服务不可达也算成功） | 配置错误 | argparse 用法错误 |
| `sync` | 成功 | 配置错误，或框架 skill 源文件缺失 | argparse 用法错误 |
| `audit` | 干净 | 有 `missing` / `unverified` / `required_missing` | 用法错误或配置错误 |

---

## 6. 怎么判断成功：五层判据

逐层确认，**第 5 层才是验收判据**：

1. **配置层**：`mw rag list --project <dir>` exit 0，且 `enabled` 里有你的服务、字段来源正确（`[project]`/`[machine]`）。
2. **注入层**：派发出去的 task.md 里有 `<!-- mw-rag: v1 -->` 块（未启用时**不应有**该块）。
3. **注册层**：worker 的工具列表里有 `rag_search` / `rag_symbol` / `rag_graph` / `rag_impact` / `rag_sources` /
   `rag_feedback`，且工具描述**没有** `[unreachable at session start]`（`rag_chat` 只在 `rag-research` 出现）。
4. **调用层**：worker 的 `trace.log` 里有 `rag_call ... tool=... via=mcp|cli ms=<N> results=<N>` 证据行。
5. **验收层**：交付物里有**可核对的引用**（`server:source:file_path:line`，且本地路径存在），并且
   `mw rag audit --project <dir>` **exit 0**。只「调用过工具」不算——审计按产物里的引用判定。

---

## 7. 失败 signature 表

| signature | 看到什么 | 什么意思 | 怎么办 |
|---|---|---|---|
| `rag-unavailable` | `rag-unavailable server=S tool=T kind=connect\|timeout\|protocol\|tool\|capability\|circuit ms=N` | 本次调用没有任何可用传输：连接失败 / 超时 / 协议错，或熔断已打开 | 先 `mw rag probe --project <dir>` 看可达性；查 `mcp.url`、`token_env`（值是否在 serve 环境）、网络；需要本地兜底就改 `transport: skill`/`both`。`circuit` = 连续 3 次 connect/timeout/protocol 后打开（`tool`/`capability` 是工具面错误：无可用传输、服务端 `isError`、服务端不具备该能力——都**不计入**熔断），修复服务端或稍后重试 |
| `rag_fallback` | `rag_fallback server=S tool=T via=cli reason=connect` | `transport: both` 下 MCP 连接层失败，**只读工具**改走本地 CLI | 想彻底不降级就改 `transport: mcp`；想稳定降级就确认 `skill.cli_entry` 可用。`rag_feedback`/`rag_chat`/超时**不会**出这一行 |
| `rag-required-missing` | `rag-required-missing role=R phase=P server=S`（`output.md` 里还会有对应标记） | `require: true` 的角色/阶段结束时没有可核对引用 | 检查 RAG 是否可达、给 worker 更明确的检索指令，或调整 `require`/放宽该角色阶段；确认产物里带了可核对引用 |
| `rag-rewrite-degraded` | `rag-rewrite-degraded server=S tool=T` | 服务端响应 `meta.rewrite_degraded === true`：服务端**改写失败降级为普通检索**。它**不是**「开了多轮改写」的标记 | 服务端问题；检查服务端改写配置。本行不影响本次调用成功 |
| `rag-budget-exceeded` | `rag-budget-exceeded server=S tool=T reason=count\|cumulative\|wall used=N budget=N` | 触到 `chat_budget` / `time_budget_s` 上限，请求被拒且未发出 | 调大 `rag.budgets.*`、角色级 `chat_budget`/`time_budget_s`，或 `task.md` 的 `chat_budget:`/`time_budget_s:` 头 |

---

## 8. 已知坑

- **token 必须在 `mw serve` 环境里**：配置里只写 `token_env` 变量名；改完配置或改完令牌要**重启 `mw serve`**
  才会带进新 worker 进程。把令牌值写进 YAML 是错的（见 §3.1 的 `mcp.token_env`）。
- **改服务名要全套同步**：`target.yml` 的 `enabled`、`default_server`、`roles.*.server`、`phases.*.server`
  都要改成新名字，否则 `mw rag list` 报 `unknown rag server '...'`，派发时被拒。最省事的做法是
  一开始就用 `mw rag init --server <name> --enable` 一次写一致。
- **改配置后已派发的任务会被拒 spawn**：task.md 里记录了 RAG fingerprint，改完 `enabled`/字段/`path_roots_file`
  内容后，旧任务 spawn 时打印 `config torn (rag): task.md fingerprint=... != current ...`。**重派该任务**即可。
- **`phases:` 键大小写敏感**：`design` ≠ `DESIGN`；不匹配时**不报错**，只是该阶段覆盖静默失效。键必须与
  `pm-state.md` 的阶段值同大小写。
- **`rewrite: true` 还需要服务端 `capabilities.rewrite: true`**：角色/阶段开了 `rewrite` 但服务端没有该能力时，
  改写会被跳过或报能力错误。
- **`rag_chat` 只在 `rag-research` 任务类型下注册**：其它类型看不到这个工具，不是配置错误。
- **`skill.dir` 两侧行为不一致（遗留，未修）**：Python 接受 `null`/缺省（= 项目根），TS 侧要求非空字符串（`rag/config.ts:262` `requireString`）。跨语言统一前，写 `dir: .` 最稳。已记录待修（T-23 独立验证发现）。
- **没有 `rag:` 段的项目零影响**：不注册工具、不注入 task.md、不探活、不写文件；`enabled: []` 与「没有 `rag:` 段」等价。
- **`path_roots_file` 悬空引用是静默陷阱**：`mw rag init` 默认会写出 `.mw/rag-roots.json`（`engine: "."`）并激活
  该字段；只有用了 `--no-roots`（或手工删掉文件）它才保持注释。手工激活前先确认文件存在（见 §3.1、§3.4）。

---

## 9. FAQ

**Q：改完配置为什么不生效？**
按五层判据顺序查：`mw rag list`（配置是否解析、启用集对不对）→ `mw rag probe`（服务是否可达）→
看新派发任务 task.md 里有没有 `<!-- mw-rag: v1 -->` 块 → 看 worker `trace.log` 有没有 `rag_call` →
运行 `mw rag audit`。最常见原因是没重启 `mw serve`（token/新配置没进 worker 环境），或改完配置没重派旧任务
（`config torn (rag)`）。

**Q：两个服务同名怎么办？**
同名即同一逻辑服务：机器层与项目层会**逐字段合并**，项目层字段覆盖机器层。想让同一个名字在不同项目指向不同
端点，就在各项目层写自己的 `mcp.url`，机器层只放公共默认值。

**Q：想全局共享一份服务表怎么配？**
把公共连接信息放机器层 `~/.agents/rag-servers.yml`（`mw rag init --machine` 生成；或用 `MW_RAG_SERVERS_FILE`/
`MW_RAG_SERVERS_HOME` 指定），项目层 `.mw/rag-servers.yml` 只写覆盖字段（例如只改 `mcp.url` 或 `sources`）。
`target.yml` 的 `rag.enabled` 仍然按项目写。

---

## 附录：默认 `mw rag init --print` 模板（逐字）

<!-- mw-rag-init:print servers -->
```yaml
# RAG server table (rag-servers.yml).
#   machine layer: ~/.agents/rag-servers.yml  (shared by every project)
#   project layer: <project>/.mw/rag-servers.yml  (wins field-by-field)
#
# The two layers merge PER FIELD: a value set in the project layer
# replaces the machine value for that field only; an array (sources) is
# replaced wholesale, never concatenated; `null` deletes the field; and
# `mw rag list` prints the winning layer for every field as
# [machine] / [project].
#
# Nothing below is used until the server name appears in target.yml
# `rag.enabled` (see the target section printed by `mw rag init --print`).
servers:
  example:
    # transport — how mw talks to this server.
    # values: mcp | skill | both   default: mcp
    #   mcp   = remote MCP server over streamable HTTP
    #   skill = local CLI adapter
    #   both  = try MCP first; only on a CONNECTION-level failure do the
    #           read-only tools fall back to the CLI (rewrite/chat never do).
    # example: transport: both
    transport: mcp
    # adapter — protocol adapter id.
    # values: overcode-v1 (the only supported value)   default: overcode-v1
    adapter: overcode-v1
    # path_roots_file — JSON map (role -> local root) that `mw rag audit`
    # uses to resolve citations on disk (it fills in local_path / exists).
    # Relative values resolve against the project root.
    # values: path string or null   default: null (citations are then
    #         reported as unverified instead of checked on disk)
    # example: .mw/rag-roots.json (written by `mw rag init`)
    path_roots_file: .mw/rag-roots.json
    # sources — which data sources this server can query. The 2nd segment
    # of a citation `server:source:file_path:line` must be one of these.
    # values: list of non-empty strings   default: [] (server default)
    # example: [docs, code]
    sources:
      - docs
      - code
    # capabilities — what the server can do; each key turns on part of
    # the RAG surface (graph lookups / rag_chat / query rewriting).
    # values: boolean   default: false
    capabilities:
      # graph — citation-graph / related-file lookups
      graph: true
      # chat — natural-language q&a over the sources (rag_chat)
      chat: true
      # rewrite — query rewriting before retrieval
      rewrite: true
    mcp:
      # url — MCP endpoint (streamable HTTP JSON-RPC).
      # values: non-empty URL   required when transport is mcp or both
      # example: http://localhost:8100/mcp/
      url: http://localhost:8100/mcp/
      # token_env — NAME of the environment variable that holds the
      # token. Write the VARIABLE NAME ONLY, never the token value: mw
      # serve reads the value from its own environment and injects it
      # into spawned workers.
      # values: env var name or null   default: null (no auth header)
      # example: EXAMPLE_MCP_TOKEN
      token_env: EXAMPLE_MCP_TOKEN
      # timeout_ms — per-request timeout in milliseconds.
      # values: positive integer   default: 180000 (3 min)
      timeout_ms: 180000
    # NOTE: transport is 'mcp' — this CLI block is inactive. To use the local CLI set transport: skill (or both) and uncomment it.
#     skill:
#       # dir — working directory for the CLI, relative to the project root.
#       # values: path string or null   default: null (project root)
#       # example: skills/example
#       dir: skills/example
#       # cli_entry — command that runs the local CLI adapter.
#       # values: non-empty string   required when transport is skill or both
#       # example: python example_cli.py
#       cli_entry: python example_cli.py
#       # timeout_ms — per-invocation timeout in milliseconds.
#       # values: positive integer   default: 180000 (3 min)
#       timeout_ms: 180000
```

**`target.yml` 的 `rag:` 段：**

<!-- mw-rag-init:print target -->
```yaml
# RAG section for target.yml (appended by `mw rag init`, hand-edited after).
# Servers are declared in .mw/rag-servers.yml (project) or
# ~/.agents/rag-servers.yml (machine); this section selects and configures them.
rag:
  # enabled — server names active in this project (each must be declared
  # in rag-servers.yml). EMPTY or ABSENT means EVERYTHING IS OFF, not on.
  # example: enabled: [example] turns that server on; [] turns RAG off.
  enabled: []
  # default_server — server used by a role/phase that names none.
  # values: a declared server name, or null   default: null
  default_server: null
  # roles / phases — per-role and per-phase overrides. Each entry takes
  # server | source | require | rewrite (roles may also set chat_budget /
  # time_budget_s).
  roles:
    coding:
      # server — declared server name (default: default_server)
      server: example
      # source — default source segment of `server:source:file_path:line`
      source: docs
      # require — this role must get RAG: required = role.require OR phase.require
      require: false
      # rewrite — allow query rewriting (needs capabilities.rewrite: true)
      rewrite: false
  # phases — key names are CASE-SENSITIVE and must match the phase value in
  # pm-state.md (design != DESIGN).
  phases:
    design:
      server: example
      source: docs
      require: false
      rewrite: false
  # budgets — hard caps on RAG usage per task.
  # chat_budget — max rag_chat calls per task (default: 2).
  # time_budget_s — max seconds of RAG tool time per task (default: 900).
  budgets:
    chat_budget: 2
    time_budget_s: 900
```
