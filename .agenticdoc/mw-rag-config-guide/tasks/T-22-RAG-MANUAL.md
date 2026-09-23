# Task T-22: RAG 配置手册 + README 指向 + CHANGELOG

## 元信息
- Stage: 2
- 依赖: T-21（手册必须引用 `mw rag init --print` 的**真实输出**，不许手抄）
- 风险等级: 中（用户面向的文档，准确性 = 可执行性）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-204, AC-205, AC-206]
- vc_refs: [VC-205, VC-206, VC-209]
- 权威设计：`design.md` D-201（模板唯一来源）、D-207（章节骨架）

## 交付物

1. **新手册 `packages/multi-workers/docs/rag-config-guide.md`**（体例参照既有 `docs/dual-toolchain-practice-guide.md`）
2. `packages/multi-workers/README.md` 的 RAG 段加一行指向手册（不要大改 README）
3. `packages/multi-workers/CHANGELOG.md` 与 `packages/coding-agent/CHANGELOG.md` 的 `[Unreleased]` 追加条目
4. **新测试 `packages/multi-workers/test_rag_docs.py`**（手册-实现 parity）

## 手册必须包含（章节骨架固定，顺序照此）

① **3 分钟上手**：`rag init` → 改 `url`/`token_env` → 把服务名填进 `enabled` → `mw rag list`/`probe`/`sync` → 重启 `mw serve`。
② **三个文件的角色与优先级**：机器层 `~/.agents/rag-servers.yml`（或 `MW_RAG_SERVERS_HOME`）、项目层 `<control>/.mw/rag-servers.yml`、
   `<control>/.agenticdoc/target.yml` 的 `rag:` 段；说明**字段级合并**（同名字段项目层覆盖机器层，数组整体替换，`null` 删除该字段，
   `origin` 记录来源，可用 `mw rag list --json` 查）。
③ **逐字段表**（每字段 4 列：**是什么 / 取值与默认 / 举例 / 写错的后果**）：
   - 服务表 11 个字段：`transport`、`adapter`、`path_roots_file`、`sources`、`capabilities.graph`、`capabilities.chat`、
     `capabilities.rewrite`、`mcp.url`、`mcp.token_env`、`mcp.timeout_ms`、`skill.dir`、`skill.cli_entry`、`skill.timeout_ms`
   - `rag:` 段：`enabled`、`default_server`、`roles`、`phases`、`budgets.chat_budget`、`budgets.time_budget_s`
   - `roles.<name>` / `phases.<name>` 项内 4 键：`server`、`source`、`require`、`rewrite`
   - `rag-roots.json`：`<source 名> -> 绝对本地根`；`_` 前缀键被忽略
   注意：**`sources` 必须解释清楚用途**（服务端有哪些可检索数据源；引用 `server:source:file_path:line` 的第 2 段就是它；
   空 = 用服务端默认），`token_env` 必须写「只填变量名，不要填令牌值」（值由 `mw serve` 的环境提供）。
④ **四类可直接复制粘贴的完整示例**（每类都给「服务表片段 + `rag:` 段片段 + 该场景说明」）：
   (a) MCP-only（streamable-http + token_env）——**用 OverCode 的真实形态做例子**：
   `url: http://localhost:8100/mcp/`、`token_env: OVERCODE_MCP_TOKEN`、`sources: [code, docs]`、
   `capabilities: {graph: true, chat: true, rewrite: true}`、`path_roots_file: .mw/rag-roots.json`；
   (b) CLI/skill-only（`transport: skill` + `skill.cli_entry`）；
   (c) both（mcp 优先、连接级失败时只读工具降级 CLI，说明**哪些工具不会降级**：`rag_feedback`/`rag_chat`/超时）；
   (d) 双服务 + 角色/阶段要求（`roles.review.require: true`、`phases.design.require: true`，并说明 `required = role OR phase`）。
⑤ **命令参考**：`init`/`list`/`probe`/`audit`/`sync` 的完整参数（`--project` 必填、`--json`、`--key`、`--out`、
   `--print`/`--dry-run`/`--force`/`--machine`/`--only-machine`/`--with-roots`/`--server`/`--url`/`--token-env`/`--transport`/`--enable`）
   + **退出码表**（以 `mw.py` 实现为准，写之前先读代码/`--help` 核对）。
⑥ **怎么判断成功**：五层判据（配置 → task.md 注入块 → 工具注册且无 `[unreachable at session start]` → trace 里 `rag_call` →
   交付物里有**可核对引用** 且 `mw rag audit` exit 0），并强调第 5 层才是验收判据。
⑦ **失败 signature 表**：`rag-unavailable`（kind=connect/timeout/protocol）、`rag_fallback`、`rag-required-missing`、
   `rag-rewrite-degraded`（它是"服务端改写失败降级"，**不是**"开了多轮"的标记）各写「看到什么 / 什么意思 / 怎么办」。
⑧ **已知坑**：token 必须在 `mw serve` 环境里（改完重启）；改配置后已派发任务会 `config torn (rag)` 拒 spawn（重派即可）；
   `phases:` 键**大小写敏感**（`design` ≠ `DESIGN`，不匹配会静默不生效）；`rewrite: true` 还需服务端 `capabilities.rewrite: true`；
   `rag_chat` 只在 `rag-research` 任务类型下注册；没有 `rag:` 段的项目零影响。
⑨ **FAQ**：改完不生效怎么查（`list` → `probe` → 看 task.md 注入块 → 看 `trace.log` → `audit`）；两个服务同名怎么办；
   想全局共享一份服务表怎么配（机器层 + 项目层只写覆盖）。

## 模板引文规则（parity 契约，必须严格遵守）

手册中三个模板块必须**逐字**来自 `python mw.py rag init --print`（T-21 的格式：三段，分隔行 `# ===== file: <绝对路径> =====`）。
每个块前一行加上标签注释，便于测试定位：

```
<!-- mw-rag-init:print servers -->
```yaml
<第 1 段全文，不含分隔行>
```

<!-- mw-rag-init:print target -->
```yaml
<第 2 段全文>
```

<!-- mw-rag-init:print roots -->
```json
<第 3 段全文>
```
```

**唯一允许的差异**：分隔行不复制；`\r\n` → `\n`；行尾空白。除此之外任何字符差异都算失败。

## 测试 `test_rag_docs.py`（unittest）

- `VC-206`：按标签提取手册块，与 `mw.py rag init --print`（`subprocess` 真跑）分段结果做**字节比较**（上述归一则）；
  并断言 `[VERIFY] VC-206: sections=3 servers_bytes=<N> target_bytes=<N> roots_bytes=<N>`（字节数取自实测）。
- `VC-205`（文档侧）：手册字段表覆盖全部 11+6+4 字段/键名；反向：手册中出现的 YAML 键都必须能在字段表里找到；
  **并断言校验器确实接受这些字段**（构造一份含全字段的 `rag-servers.yml` 与 `target.yml`，`load_rag_config` 无 error）——
  防止"文档写了一个校验器不认的字段"。
- `VC-209`（诚实性）：手册「写错的后果」列引用的报错文本必须是实现里真实存在的（至少校验
  `unknown rag server`、`unknown-key`、`transport must be one of` 三类：从 `mw_common.py` 里读到原文并断言手册包含它）。
- 证据行用 `print`（`pytest -q -s`）。

## 验收

1. `cd packages/multi-workers && python -m pytest test_rag_docs.py -q -s` 全绿且 `[VERIFY]` 行可见。
2. 手册里的每条命令都被**真跑过**（在临时目录 + `MW_RAG_SERVERS_HOME` 指向临时目录），并在报告里贴关键输出。
3. `python -m pytest -q` 无新增失败；仓根 `npm run check` exit 0。
4. `rg -n "rag-config-guide" packages/multi-workers/README.md` 命中（指向手册）。
5. 两包 CHANGELOG 的 `[Unreleased]` 各有新增条目（只追加，不新建同名小节）。

## 禁止

- 不改 `mw.py` / `rag_templates.py` / `test_rag_init.py`（T-21 的产物；发现 T-21 有错就**在报告里写出来**，别顺手改）。
- 不改 `rag/*.ts`、既有 fixtures/golden、`test_autopilot_l0.py`、其它会话的未提交改动。
- 不 commit。
