# Task T-21: `mw rag init`（零交互模板生成）

## 元信息
- Stage: 1
- 依赖: 无
- 风险等级: 中（写用户配置文件，必须安全）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-201, AC-202, AC-203, AC-204（模板侧）]
- vc_refs: [VC-201, VC-202, VC-203, VC-204, VC-205, VC-207, VC-208]
- 权威设计：`design.md` D-201~D-208（尤其 D-204 写入纪律、D-205 退出码、D-206 零交互）

## 背景

上位 key 交付了完整的两层配置解析，但**没有**生成器：用户配 RAG 只能读 `mw_common.py` 的校验器反推字段。
本任务交付 `mw rag init`：**零交互**，按示例写出可直接编辑的模板。手册（T-22）稍后引用 `--print` 的输出。

## 必须实现

### 1) 新模块 `packages/multi-workers/rag_templates.py`

纯数据 + 渲染函数，**不写盘、不读配置文件**：

- `render_servers_template(server: str, url: str, token_env: str, transport: str, skill_dir: str, skill_cli_entry: str) -> str`
  生成服务表文件全文（`{servers: {...}}` 形态）。要求：
  - 文件首行注释说明「这个文件是什么、位置、两层合并语义（字段级：数组整体替换、`null` 删字段、origin 记录来源）」；
  - **每个字段都有行内注释**，注释必须写清「是什么 / 取值 / 默认 / 举例」四要素。必须覆盖全部 11 个字段：
    `transport`、`adapter`、`path_roots_file`、`sources`、`capabilities.graph`、`capabilities.chat`、`capabilities.rewrite`、
    `mcp.url`、`mcp.token_env`、`mcp.timeout_ms`、`skill.dir`、`skill.cli_entry`、`skill.timeout_ms`
    （即 `capabilities` 的 3 个与 `mcp` 的 3 个、`skill` 的 3 个都要注释到）；
  - `sources` 的注释必须解释用途（"这个服务能查哪些数据源；引用语法 `server:source:file_path:line` 里的 `source` 段就取自这里；
    取空 = 服务端默认"）；
  - `token_env` 的注释必须写明「**只写环境变量名，不要写令牌值**；值由 `mw serve` 进程环境提供，spawn worker 时注入」；
  - `transport` 的注释必须写明三值语义与 `both` 的降级条件（mcp 优先，**连接级**失败时仅只读工具降级到 CLI）；
  - 按 `transport` 决定哪块生效：非选中块**整体注释掉**并提示「改用 X 时把这块取消注释」；
  - 生成的文本必须能被 `yaml.safe_load` 解析且通过 `mw_common.load_rag_config` 校验。
- `render_target_rag_template(server: str, enabled: bool, with_default_server: bool) -> str`
  生成 `target.yml` 的 `rag:` 段（含注释），覆盖 `enabled` / `default_server` / `roles` / `phases` / `budgets` 全部键与
  `roles`·`phases` 项内 4 个键（`server`/`source`/`require`/`rewrite`）。要求：
  - `enabled` 注释必须写明「**空或缺省 = 全关**（不是全开）」与写法举例；
  - `require` 注释写明「`required = role.require OR phase.require`（并集）」；`rewrite` 注释写明「需要该服务 `capabilities.rewrite: true`」；
  - `phases.<phase>` 的注释写明「phase 名**大小写敏感**，要与 `pm-state.md` 的阶段值一致（`design` ≠ `DESIGN`）」；
  - `budgets` 注释写明默认值（`chat_budget: 2`、`time_budget_s: 900`）与作用；
  - `enabled=False`（默认）时写 `enabled: []`；`enabled=True` 时写 `enabled: [<server>]`。
- `ROOTS_TEMPLATE`：`rag-roots.json` 模板全文（JSON 无注释 → 用 `_README` 键说明，与 `test/fixtures/rag/rag-roots.json` 同风格）。

### 2) `mw.py`：`mw rag init`

```
python mw.py rag init --project <dir>
    [--server NAME] [--url URL] [--token-env VAR] [--transport {mcp,skill,both}]
    [--enable] [--machine | --only-machine] [--with-roots] [--force] [--dry-run] [--print]
```

行为（严格按 D-202~D-206）：

1. 读一次 `mw_common.load_rag_config(project)`：**配置坏了不要紧**（init 是用来修配置的）——只要不是"读不到文件"就继续；
   但 `--project` 必须存在，否则 exit 1 并给清晰错误。
2. 目标文件：
   - 项目层服务表 `<dir>/.mw/rag-servers.yml`（不存在才写）
   - `target.yml`：不存在 → 创建并写入 `rag:` 段；存在且**无**顶层 `rag:` 键 → **文本级追加**（前置一个空行）；存在且**有** `rag:` 键 → 拒绝（除非 `--force`；`--force` 时只替换该段，**不动其它段**）
   - `--machine`：额外写 `~/.agents/rag-servers.yml`（用 `mw_common.machine_rag_servers_path()` 解析路径；已存在 → 拒绝除非 `--force`）
   - `--only-machine`：只写机器层，不碰项目层；`--machine` 与 `--only-machine` 同时给 → exit 1（组合非法）
   - `--with-roots`：写 `<dir>/.mw/rag-roots.json`（同上，存在则拒绝除非 `--force`）
3. `--dry-run`：只打印"将要写哪些文件、是否跳过、为什么"，**零写入**，exit 0。`--print`：把模板全文打到 stdout，**零写入**，exit 0。
   `--print` 的输出格式是**手册 parity 测试的契约**，必须严格是：

   ```
   # ===== file: <项目层服务表绝对路径> =====
   <servers 模板全文>
   # ===== file: <target.yml 绝对路径> =====
   <rag: 段全文>
   # ===== file: <rag-roots.json 绝对路径> =====
   <roots 模板全文>
   ```

   三段顺序固定（servers → target → roots），分隔行逐字就是 `# ===== file: <path> =====`（行首 `# `，路径为绝对路径）。
4. 成功时打印 next steps（3 步：改 `url`/`token_env` → 把服务名放进 `enabled` → `mw rag list` / `mw rag probe` / `mw rag sync`，并提示重启 `mw serve`）。
5. 退出码：0 = 达成；1 = 拒绝/失败（已存在且无 `--force`、参数组合非法、OSError）；2 = argparse 用法错。
6. 写盘：`utf-8`、`newline="\n"`、临时文件 + `os.replace` 原子替换（沿用既有 `_atomic_write_yml` 风格）。
7. **不得**出现 `input()` / `sys.stdin` 读取（`rg` 必须零命中）；不得写 `.pi/`、`_workers.parallel`、`_index.parallel`、`goal.md`。

### 3) 测试 `packages/multi-workers/test_rag_init.py`

用 `unittest`（与本仓 `test_rag_*.py` 一致）+ `tempfile`，全程用 `MW_RAG_SERVERS_HOME` 指向临时目录（**绝不动用户真实 HOME**）。
至少覆盖 `[VERIFY]`（`print` + `pytest -q -s`）：

- `VC-201`：干净目录 → 两产物存在；`mw rag list --project DIR` exit 0 且 stdout 含 `enabled: (none)`；
  `load_rag_config(DIR)` 无 error 且 `servers` 含模板服务名。证据行字段取自实测（如 `created=2 list_exit=0 enabled=(none) servers=1`）。
- `VC-202`：重跑 → exit 1 + 两文件 sha256 不变；`--force` → exit 0 + sha256 改变。
- `VC-203`：`--dry-run` / `--print` 前后目录树快照（相对路径 + sha256 全表）相等；`--print` 输出含 `servers:` 与 `rag:` 段。
- `VC-204`：`subprocess.run([...], stdin=subprocess.DEVNULL)` 跑真进程 exit 0；源码里 `input(`/`sys.stdin` 零命中。
- `VC-205`：模板文本包含 11 个字段名全集；`transport` 非选中块被注释（对 `--transport skill` 与 `both` 各断言一次）。
- `VC-207`：`--machine` 写机器层到临时 `MW_RAG_SERVERS_HOME`，再次运行 exit 1。
- `VC-208`：`--with-roots` 后 `load_rag_config` 的该 server `path_roots_digest` 非空（需模板里 `path_roots_file` 指向它——若默认注释掉，则测试先取消注释或用 `--with-roots` 时自动启用该字段）。

## 验收

1. `cd packages/multi-workers && python -m pytest test_rag_init.py -q -s` 全绿且 `[VERIFY]` 行可见。
2. `python -m pytest -q` 无新增失败（基线 805 passed / 9 deselected）。
3. `python mw.py rag init --print` 的 stdout 能被切分成 3 段（按 `# ===== file: ` 前缀），且每段内容能被 `yaml.safe_load` 解析（`rag:` 段需补缩进上下文后再解析）。
4. `rg -n "input\(" packages/multi-workers/rag_templates.py packages/multi-workers/mw.py`（在 `_cmd_rag_init` 范围内）零命中。
5. 仓根 `npm run check` exit 0。
6. 手工真跑一次：在临时目录 `python mw.py rag init --project <tmp>` → `python mw.py rag list --project <tmp>` 输出形如
   `[mw rag] enabled: (none)`；再次 init → exit 1。

## 禁止

- 不改 `mw_common.py` 的解析/校验语义，不改 `rag/*.ts`，不改既有 fixtures/golden，不改 `test_autopilot_l0.py`。
- 不写 `docs/`（手册归 T-22）、不改 `README.md`/`CHANGELOG.md`（归 T-22）。
- 不 commit。
