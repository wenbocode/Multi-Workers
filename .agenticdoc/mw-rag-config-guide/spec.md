# Spec: mw-rag-config-guide（RAG 配置手册 + `mw rag init` 模板命令）

- key: `mw-rag-config-guide`
- created: 2026-09-22
- 类型: 文档 + 一个 CLI 子命令（K1+K2 范围内）

## §0 Goal Alignment

- **对齐 goal.md**：goal 要求「Worker 执行过程中追踪 goal 一致性」「工具白名单按任务类型」「配置文件驱动协调」。RAG 是 coding/research
  角色的能力面，但**配置能力的可用性取决于文档**：现在要配好一个 RAG 服务，必须读 `mw_common.py` 的校验器才能知道有哪些字段。
- **GC 继承**：GC-2（不改 pi 核心：本 key 只动 `packages/multi-workers/*.py` 与 docs）；GC-5（allowlist parity 不变）；
  GC-1（不引入中心化调度器：init 只写配置文件，不落任何状态）；GC-6（看门狗）与 GC-7（goal.md 锚点）不涉及。
- **冲突**：无。与上位 `mw-rag-integration`（config 解析/注入/审计）不冲突：本 key **不新增配置语义**，只新增「生成模板」与「文档化既有语义」。
- **预期收益**：把「配 RAG」从「读源码 + 猜字段」变成「一条命令拿可改模板 + 一份逐字段手册」；并让字段集合与校验器由测试互相钉住
  （避免 F-5 那类「文档与实现脱节」复发）。

## 1. 背景

- 上位 key 交付了完整的两层配置 + `target.yml` `rag:` 段解析，README 只有 ~10 行示例（`enabled`/`default_server`/`roles`/`phases`/`budgets`）
  **完全没有服务表字段的示例**：`transport`/`adapter`/`sources`/`capabilities.*`/`mcp.*`/`skill.*`/`path_roots_file` 只能靠读
  `mw_common._rag_finalize_server` 反推。
- 用户明确要求：(1) 一份逐字段带注释、可直接复制粘贴修改即用的手册（每个配置文件都有示例，`sources` 这类字段要说明"是干什么的"）；
  (2) 一条**无交互输入**的命令，按示例生成模板让用户自己改。
- 已核实无既有文档缺陷遗留：README `enabled` 语义「空或缺省 = 全关」与两侧实现（`mw_common.py`、`rag/config.ts`）一致。

## 2. 范围

**做**：`mw rag init` 子命令（生成三个配置文件的模板）+ `packages/multi-workers/docs/rag-config-guide.md` 手册 +
README 指向手册 + 两包 CHANGELOG 条目 + `test_rag_init.py` 测试（含与手册的 parity 锁定）。

**不做**：任何真实 RAG 服务联调；K3 硬门禁；交互式问答（命令必须零提示）；修改 `rag/*.ts` 运行时语义；
改动既有 fixtures/golden/`target.yml` 语义/文本层守护。

## 3. 验收标准

| AC | 内容 |
|---|---|
| AC-201 | `python mw.py rag init --project <dir>` 在干净目录下创建 `<dir>/.mw/rag-servers.yml`、`<dir>/.mw/rag-roots.json`（`_README` + `"engine": "."`），并在 `<dir>/.agenticdoc/target.yml` 不存在时创建它、存在且**无** `rag:` 段时追加该段。两个产物必须能被 `mw rag list --project <dir>` **解析成功（exit 0）**；模板默认 `enabled: []` → `mw rag list` 显示 `enabled: (none)`，且该项目派发 worker 时 `rag_*` 工具注册数 0、task.md 注入块 0（init 不能把"零影响"变成"默认启用"） |
| AC-202 | 安全与幂等：已存在的 servers 文件 或 已存在 `rag:` 段 → **不覆盖**、打印提示与手工改法、exit 1；`--force` 才覆盖（`rag:` 段用**文本级**替换/定位，绝不 YAML round-trip 重写整个 target.yml）；`--dry-run` 与 `--print` **零文件写入**（调用前后目录树快照字节相等） |
| AC-203 | 零交互 + 可改模板：任意参数组合下不得调用 `input()` 或等待输入；缺省用示例值（服务名 `example`、url `http://localhost:8100/mcp/`、`token_env: EXAMPLE_MCP_TOKEN`）。`--machine` 同时（或配合 `--only-machine` 仅）写机器层 `~/.agents/rag-servers.yml`（存在则拒绝，除非 `--force`）；**默认**写 `<dir>/.mw/rag-roots.json` 模板并激活 `path_roots_file`，`--no-roots` 才跳过该文件并把 `path_roots_file` 写成注释行（`REVISED @ 2026-09-23`，原 `--with-roots` 已删，理由见 design D-210） |
| AC-204 | 手册逐字段：机器层服务表（`transport`/`adapter`/`path_roots_file`/`sources`/`capabilities.{graph,chat,rewrite}`/`mcp.{url,token_env,timeout_ms}`/`skill.{dir,cli_entry,timeout_ms}`）、项目层覆盖表（字段级合并语义：数组替换、`null` 删除、`origin`）、`target.yml` 的 `rag:` 段（`enabled`/`default_server`/`roles.{server,source,require,rewrite}`/`phases.*`/`budgets.{chat_budget,time_budget_s}`）、`rag-roots.json` —— **每个字段**都有「是什么 / 取值与默认 / 示例 / 写错的后果」；字段集合必须与校验器一致（漏写或多写都要有测试变红） |
| AC-205 | 手册含操作面：命令参考（`init`/`list`/`probe`/`audit`/`sync` + `--project/--json/--key/--out/--print/--dry-run/--force/--machine` + 退出码表）、"怎么判断成功"五层判据（配置 → 注入 → 注册 → 调用 → **可核对引用 + `mw rag audit` exit 0**）、失败 signature 表（`rag-unavailable`/`rag_fallback`/`rag-required-missing`/`rag-rewrite-degraded`）、已知坑（token 在 `mw serve` 环境、改配置后 fingerprint torn 拒 spawn、`phases:` 键大小写敏感、`rewrite` 需 `capabilities.rewrite`、`rag_chat` 仅 `rag-research`） |
| AC-206 | 文档-实现 parity 由测试锁定：手册里 fenced 的服务表模板块必须与 `mw rag init --print` 输出**字节一致**（换行归一后）；手册列出的字段名集合必须等于校验器接受集合 |
| AC-207 | 零回归：`python -m pytest -q` 无新增失败；`npm run check` exit 0；既有 fixtures/golden/`_workers.parallel` 测试与文本层守护零 diff；新增 `test_rag_init.py` 覆盖 AC-201/202/203/206 并打 `[VERIFY]` 实测行（`print` + `-s`） |

## 4. 可复用资产

- `mw_common.load_rag_config` / `rag_servers_path` / `machine_rag_servers_path` / `target_yml_path` / `RAG_FIELD_CAMEL`：
  校验与路径解析的唯一来源，**不要自己拼路径或另写校验**。
- `mw.py::_cmd_rag_sync`（"某文件唯一写入方"的既有模式）与 `_atomic_write_yml` / `_apply_bootstrap_line`（文本级、保注释写 YAML 的先例）。
- `mw.py::_cmd_rag_list` / `_cmd_rag_probe` 的输出格式（`--json` 可被测试直接断言）。
- `packages/multi-workers/docs/dual-toolchain-practice-guide.md`（本仓 `docs/` 手册的体例先例）。
- 上位 key 的文档纪律：`evidence/verify-run` 的「强/弱/装饰」证据口径、`[VERIFY]` 行必须带实测字段。

## 5. 需规避坑点

- **P-005（有实现没人用）**：init 写出的模板必须被 `load_rag_config` 真解析过（测试里跑 `mw rag list`），不能只断言"文件存在"。
- **P-006（日志通道关闭）**：`[VERIFY]` 一律 `print` + `pytest -q -s`；退出码不能作为唯一证据。
- **P-008（文档静默过期）**：字段表与模板块用 parity 测试钉住；校验器加字段时测试必须变红提醒改手册。
- **共享文件安全**：`target.yml` 被多会话共用 → 只在没有 `rag:` 段时**追加**，禁止 YAML round-trip 重写（会毁注释与其他段）。
- **模板必须"看起来能跑但默认不生效"**：`enabled: []` 是刻意的（占位 url 不应让每个 worker 都去打不通的服务）。
- **Windows**：写文件 `encoding="utf-8"` + `newline="\n"`；测试用 `pathlib` 比较字节，不用 shell 重定向。
