# RQ-4 证据：verify 命令的可移植性事实（占位符 / cwd / 机器级配置层）

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26 · 类型：spec 期只读调研
- 唯一写面：本文件。除本文件外未修改仓库任何文件。
- 取数环境：Windows 10.0.26100 / PowerShell 5.1；工作树 `H:\git\Multi-Workers`（HEAD 侧 `packages/multi-workers`）。
- 行号约定：全文行号以 `read`（offset）与 `Select-String` 为准。注意 `Get-Content` 在同一批文件上会因行尾差异少算 0–4 行，**不要用 `Get-Content` 行号对账**。

---

## 1. `target.yml` toolchain 占位模板：解析者、占位集合、未知占位、与 `mw ue-toolchain run` 的关系、E2 四个根

### 1.1 注释里的占位模板由谁生成

注释只是文档，真正的解析单点在 `mw_common`。

- partition 模式的模板注释由 `mw.py:_partition_template` 生成，占位说明写在 `mw.py:2632-2633`：
  `# command templates with {parent}/{partition}/{root name} placeholders, e.g.` / `# build: 'build.bat {partition} {sdk}'`。
- dual/legacy 模板注释由 `mw.py:_target_template` 生成，写在 `mw.py:576-592`（`{game}/{engine}/{uproject}`）。

### 1.2 解析/渲染的模块与函数（file:line）

- 单点：`mw_common.render_toolchain_command(command, config)`（`packages/multi-workers/mw_common.py:2866`）。
  - `mode == "partition"` → `_render_partition_command`（`mw_common.py:2894`）。
  - dual/single → 内联替换 `{game}` / `{engine}` / `{uproject}`（`mw_common.py:2875-2891`）。
- 占位形状：`_TOKEN_RE = re.compile(r"\{([A-Za-z0-9_-]+)\}")`（`mw_common.py:2415`）。
- 渲染结果的消费者（同一函数被四处复用）：
  - `mw target show`：`mw.py:795`
  - `mw ue-toolchain run`：`mw.py:980`
  - `mw partition show`：`mw.py:2906`
  - dispatch 的 workspace-profile 渲染：`mw_common.render_partition_profile_md`（`mw_common.py:2974`、调用在 `mw_common.py:3004`），经 `autopilot/dispatch.py:494` 注入 task.md。

### 1.3 支持的占位集合（逐字）

| mode | 支持 | 出处 |
|---|---|---|
| partition | `{parent}`, `{partition}`, 每个 `partition.roots.<name>` → `{<name>}` | `mw_common.py:2899`, `:2901`, `:2904-2907` |
| dual / single | `{game}`, `{engine}`, `{uproject}` | `mw_common.py:2875-2891` |

- `{engine}` 未配置 → `_tc_fail("missing-field", ...)`（`mw_common.py:2880-2885`）。
- `{uproject}` → `discover_uproject`（`mw_common.py:2843-2859`）。
- `{parent}` / `{partition}` 若 config 值为 `None`，不替换，落入残留检查。

### 1.4 未知占位怎么报错（重要不对称）

- **partition：fail-closed。** 替换完后 `_TOKEN_RE.search(out)` 若还有残留 → `_tc_fail("missing-field", "toolchain command references undefined placeholder '{x}' (partition mode defines: ...): <原命令>")`（`mw_common.py:2908-2914`），抛 `TargetConfigError(kind="missing-field")`。`{game}/{engine}/{uproject}` 在 partition 下也走这条（模块 docstring `mw_common.py:2868-2870` 明说）。
- **dual/single：没有残留检查。** `mw_common.py:2866-2891` 只做三个 `if "{token}" in out` 替换后直接 `return out`；`{sdk}` / `{python}` 这类未知占位会**原样透传**，最终交给 `shell`。同一个 `{sdk}` 在 partition 下报错、在 dual 下静默——这是既有怪癖，新实现不要照抄这条。

### 1.5 `mw ue-toolchain run` 与它的关系

调用链（`packages/multi-workers/mw.py`）：

1. `_toolchain_run(args)`（`mw.py:957`）
2. `_toolchain_load_config(project_dir)`（`mw.py:947`）→ `mw_common.load_target_config(project_dir)`（`mw.py:951`）→ 失败打印并 exit 1。
3. `template = toolchain.get(args.name)`，缺失 → 报 "no toolchain command named ..."（`mw.py:970-977`）。
4. `command = mw_common.render_toolchain_command(template, config)`（`mw.py:980`）；渲染失败也 exit 1（`mw.py:981-983`）。
5. `--args "..."` **原样字符串拼接**到 command 末尾（`mw.py:986-987`）。
6. 执行：`subprocess.run(command, shell=True, cwd=str(control_root))`（`mw.py:1009`）。

关键差异（决定 AC-007 不能直接复用）：
- `mw ue-toolchain run` 是 **字符串 + `shell=True` + cwd=控制根**；
- `xkey.run_verification` 是 **list argv + `shell=False` + cwd=控制根**（见第 2 节）。
`render_toolchain_command` 返回的是字符串，不能直接塞进 list argv。

### 1.6 E2 的四个根怎么算（`active: partition`）

E2 的 `H:\git\E2Feature\.agenticdoc\target.yml`（741 B，mtime 2026-09-19 17:07:08）实测内容：

```yaml
active: partition
partition:
  parent: 'E:\UEMigrator'
  partition: 'H:\git\E2Feature'
  toolchain:
  # command templates with {parent}/{partition}/{root name} placeholders, e.g.
  # build: 'build.bat {partition} {sdk}'
  ignore:
  contract:
```

四根定义与算法：

| 根 | 算法 | E2 取值 | 出处 |
|---|---|---|---|
| 控制根 control_root | 传给 `load_target_config` / conductor `--project` 的目录；归一化 `_tc_normalize_root(control_root, control_root)` | `H:\git\E2Feature` | `mw_common.py:2700`, `:2745`；`_tc_normalize_root` `mw_common.py:2321-2325` |
| partition 根 | 字段 `partition`（或 env `MW_PARTITION_ROOT`），相对时锚 control_root | `H:\git\E2Feature` | `mw_common.py:2627`, `:2612-2623` |
| parent 根 | 字段 `parent`（或 env `MW_PARTITION_PARENT`），相对时锚 control_root | `E:\UEMigrator` | `mw_common.py:2626`, `:2607-2623` |
| 项目根 project_root | conductor `pathlib.Path(args.project).resolve()` | `H:\git\E2Feature` | `autopilot/conductor.py:3939` |

- `_tc_normalize_root`：`str(pathlib.Path(os.path.normpath(os.path.join(control_root, raw))).resolve())`（`mw_common.py:2321-2325`）。`parent`/`partition` 是绝对路径，`os.path.join` 第二参数为绝对时直接取它。
- 约束只有一条：parent 与 partition 必须不同且不嵌套（`_tc_check_root_relation`，`mw_common.py:2578-2589`）。**control 与 partition 没有强制相等或不等**——`load_target_config` 只把 control 归一化，从不与 partition 比较。
- E2 实测：**partition 根 == 控制根 == 项目根**（三者同值），parent 是唯一不同的根。旁证：`H:\git\E2Feature\.mw\serve.meta` = `{"pid": 76584, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}`，`.mw/` 位于 `H:\git\E2Feature`。

---

## 2. `xkey.run_verification` 的 argv 语义 + conductor 的 cwd 来源 + partition 模式是否取错根

### 2.1 argv 语义（`packages/multi-workers/autopilot/xkey.py`）

- 签名 `run_verification(cmd, cwd, run_dir, timeout)`（`xkey.py:1272`），docstring 明写 `shell=False`（`xkey.py:1278`）。
- `cmd` 必须是非空 list，否则 `XKeyFormatError`（`xkey.py:1286-1288`）。
- **零展开**：`argv = [str(part) for part in cmd]`（`xkey.py:1289`）——只做 `str()`，不认识占位符、`~`、env 变量，也不做字符串分词。
- 执行：`subprocess.run(argv, shell=False, cwd=str(cwd), capture_output=True, timeout=timeout_value)`（`xkey.py:1301-1305`）。
- 失败语义：`FileNotFoundError` → `returncode = 127`（`xkey.py:1317-1320`）；超时 → rc 124 保留部分输出（`xkey.py:1307-1313`）。
- `cwd` 被原样 `str()`，**没有任何根解析**。

### 2.2 conductor 传入的 cwd 来源

`_xkey_run_verify`（`conductor.py:3448`）：

- `root = str(project_root)`（`conductor.py:3459`）
- `verify_cmd = [str(part) for part in (cfg.get("xkey_verify_cmd") or [])]`（`conductor.py:3460`）
- `timeout_s = _xkey_int(cfg.get("xkey_verify_timeout_s"), 1800)`（`conductor.py:3461`）
- 空命令：`if not verify_cmd:`（`conductor.py:3463`）→ `_xkey_verify_failed(..., "xkey_verify_cmd is empty (cannot prove green)")`（`conductor.py:3466`）
- 调用：`xkey.run_verification(verify_cmd, cwd=root, run_dir=str(applied["run_dir"]), timeout=timeout_s)`（`conductor.py:3470-3472`）

`root` 自始至终等于 `project_root`；而 `project_root = pathlib.Path(args.project).resolve()`（`conductor.py:3939`），即控制根/项目根。

`root = str(project_root)` 在 `conductor.py` 的出现位置（含义统一为控制根，**不是** `config["partition_root"]`）：
`2468, 2645, 2686, 2808, 3301, 3348, 3386, 3459, 3530, 3580, 3735`。

### 2.3 partition 模式下会不会取错根：会，当 control ≠ partition

正确语义（既有代码）：
- worker 的 cwd 是 **partition 根**：`launcher._worker_cwd`（`launcher.py:894`）在 partition 模式 `return pathlib.Path(cfg["partition_root"])`（`launcher.py:906`）；spawn 用 `"cwd": str(_worker_cwd(project_dir, target_config))`（`launcher.py:960`）。
- dispatch 的相对 read scope 也锚 partition 根：`anchor = pathlib.Path(config["game_root"] if mode == "dual" else config["partition_root"])`（`autopilot/dispatch.py:336`）。

verify 却固定用控制根（`conductor.py:3459`/`:3471`）。因此：
- **control == partition（E2 现状）**：cwd 恰好正确，问题被掩盖。
- **control ≠ partition（模型允许、未禁止）**：验证命令在协调仓（控制根）里执行，而不是代码所在的 partition 根 → 取错根，测试收集/依赖解析都指错目录。
- 同族问题：S3 apply 的目标文件也按控制根锚定：`target = pathlib.Path(project_root) / target_rel`（`conductor.py:3651`）。`frozen.file` 来自 worker（其 cwd 是 partition 根）的 handoff 记录，路径归一化只做斜杠/行号清理、不做根解析（`xkey._normalize_rel`，`xkey.py:226-233`）。

证据链一句话：`launcher.py:906`（worker cwd=partition）对比 `conductor.py:3470-3472`（verify cwd=project_root），而配置校验不要求两者相等（`mw_common.py:2578-2589` 只查 parent/partition）。

**结论（对 AC-007）**：E2 是 control==partition 的退化用例，"在 E2 上通过"不能证明 cwd 语义正确。AC-007 必须补一个 control≠partition 的 fixture。

---

## 3. RAG 两层配置的完整实现（`mw_common.py`）+ 可照抄骨架 + 坑

### 3.1 项目层路径函数

- `rag_servers_path(project_root)` → `<root>/.mw/rag-servers.yml`（`mw_common.py:373-375`）。

### 3.2 机器层路径选择顺序

`machine_rag_servers_path(env=None)`（`mw_common.py:378-396`）：

1. `MW_RAG_SERVERS_FILE`（`mw_common.py:368`）整文件硬覆盖：非空则 `Path(override)`，**存在才返回，缺失返回 None 且不回落到 HOME**（`mw_common.py:379-384`）。
2. 否则按序 `MW_RAG_SERVERS_HOME`（`:369`）→ `HOME` → `USERPROFILE`（`mw_common.py:385-395`），各自拼 `/.agents/rag-servers.yml`；存在才返回。
3. 全都不存在 → `None`（该层为空，不创建目录）。

写入目标的镜像（create 场景）：`mw.py:_rag_machine_write_path`（`mw.py:2017-2035`），同一 env 顺序，`MW_RAG_SERVERS_HOME` 优先于 HOME，保证测试钩子不会碰真实 HOME。

### 3.3 字段级 merge 与 origin 报告

- `load_rag_config(project_root)`（`mw_common.py:772-818`）：
  - machine 层：`mw_common.py:781-787`；project 层：`:788-793`；target.yml 的 `rag:` 段：`:794-796`。
  - server 名并集逐层 merge：`:796-806`（`_rag_merge_server`）。
  - 返回值 `{enabled, default_server, servers, roles, phases, budgets, fingerprint}`（`:807-817`）。
- `_rag_merge_server(name, machine_raw, project_raw)`（`mw_common.py:483-521`）：
  - 标量/数组：project 覆盖 machine；数组（`sources`）整体替换（`:516-520`）。
  - 嵌套对象（`mcp`/`skill`/`capabilities`，字段表 `_RAG_NESTED_FIELDS` `mw_common.py:357-361`）：逐 key 合并，project key 覆盖（`:499-514`）。
  - project 侧 `null` = 显式删除该字段（`:493-496`）；machine 侧 `null` 不删除任何东西（`:497-498`）。
  - `origins`：每个被求值字段路径记录 `machine`/`project`（`:486`, `:505`, `:512`, `:517`, `:520`），挂到 `entry["origin"]`（`_rag_finalize_server`，`mw_common.py:641`）。
- origin 展示：`mw.py:_rag_format_origins`（`mw.py:1210-1228`）把 entry 摊平成 `(field, value, origin)`；`mw rag list` 打印 `field = value [origin]`（`mw.py:1248-1249`）；`--json` 直接输出整个 config（含 origin，`mw.py:1240-1242`）。

### 3.4 单层损坏时的行为

- machine 层解析/校验错误 → `return {}, error`（`mw_common.py:782-786`）。
- project 层错误 → `return {}, error`（`:789-792`）。
- target.yml `rag:` 段错误 → `return {}, error`（`:794-796`）。
- 语义：`load_rag_config` **永不抛、永不阻塞派发**；但**任一层的错误会让整份配置作废**（project 层正确也一起丢）。
- 消费侧：`mw rag list` 打印错误并 exit 1（`mw.py:1234-1237`）；`mw doctor` 把错误放进 `section["error"]` 且**只作 informational**（`mw.py:_doctor_rag` `2248-2272`）；launcher 合并时忽略 RAG error（`launcher.py:935-940`）。

### 3.5 可照抄骨架（机器级默认层 + origin）

```python
ENV_FILE = "MW_<X>_FILE"      # 整文件硬覆盖/测试钩子，对齐 mw_common.py:368
ENV_HOME = "MW_<X>_HOME"      # 机器层 HOME 覆盖，对齐 mw_common.py:369

def machine_path(env=None) -> pathlib.Path | None:          # 对齐 mw_common.py:378-396
    env = os.environ if env is None else env
    override = (env.get(ENV_FILE) or "").strip()
    if override:
        p = pathlib.Path(override)
        return p if p.exists() else None                    # 缺失 = 层空，不回落 HOME
    for var in (ENV_HOME, "HOME", "USERPROFILE"):
        home = (env.get(var) or "").strip()
        if not home:
            continue
        p = pathlib.Path(home) / ".agents" / "<file>"
        if p.exists():
            return p
    return None

def merge(machine: dict, project: dict) -> tuple[dict, dict]:  # 对齐 mw_common.py:483-521
    merged: dict = {}
    origins: dict[str, str] = {}
    for field in FIELDS:
        in_m, in_p = field in machine, field in project
        if not in_m and not in_p:
            continue
        if in_p and project[field] is None:                  # project null = 删除
            merged[field] = None; origins[field] = "project"; continue
        if in_m and machine[field] is None and not in_p:     # machine null = 不删除
            continue
        merged[field] = project[field] if in_p else machine[field]
        origins[field] = "project" if in_p else "machine"
    return merged, origins

def load(root) -> tuple[dict, str | None]:                    # 对齐 mw_common.py:772-818
    m = machine_path()
    if m is not None:
        layer, err = read_layer(m, "machine")
        if err:
            return {}, err
    ...  # project 层；两层都失败即整份作废（fail-soft：返回错误串，不抛）
```

CLI `show` 的 origin 输出照抄 `mw.py:1248-1249`：`f"  {field} = {value if value is not None else '-'} [{origin}]"`。

### 3.6 照抄时必须注意的坑

1. **autopilot config 与 RAG 不同：不 merge 默认值。** `load_config` 返回原 dict（`autopilot/config.py:133`），`cached_load` 缓存原 dict（`config.py:168-170`）。RAG 是自己构造完整 merged 结构。新层若只写部分键，必须自己补默认值再 `validate_config`，否则下游 `cfg["poll_interval_sec"]` 这类直接下标会 KeyError。
2. **未知字段 fail-closed**（`validate_config` 的 `unknown = sorted(set(cfg) - set(DEFAULT_CONFIG))`，`config.py:90-92`）。机器层一个 typo 键会 poison 所有项目（RAG 的选择是整份作废）。要么同构，要么显式定义"机器层 typo 只警告"。
3. **缓存键**：`cached_load` 的 `_CACHE` 只按 `config.json` 路径键控（`config.py:150-170`），`save_config` 仅 `_CACHE.pop` 该路径（`config.py:146`）。若把机器层纳入 `cached_load`，缓存键必须包含机器层路径 + 其 mtime/size，否则机器层改动不生效（这是 P-015 同族的"重启/拾取"风险）。
4. **`MW_RAG_SERVERS_FILE` 语义**：设定但缺失 = 层空且**不回落 HOME**（`mw_common.py:379-384`）。这是测试隔离钩子，照抄时保留，否则测试会读真实 HOME。
5. **凭证**：机器层不得含凭证（spec §2.3）。RAG 机器层放连接信息 + `token_env`（变量**名**，非值）。
6. **原子写**：`save_config` 是 tmp+replace + UTF-8 + 尾换行（`config.py:136-148`）；新层写入必须同构，且不得放宽校验。
7. **Windows**：PowerShell 下 `HOME` 常不存在，必须保留 `USERPROFILE` 兜底（`mw_common.py:391`）。

---

## 4. 仓库既有 env 覆盖约定清单 + P-015 在代码里的体现

### 4.1 `MW_*` 变量

| 变量 | 定义/读取出处 | 谁读 | 备注 |
|---|---|---|---|
| `MW_TARGET_GAME` / `MW_TARGET_ENGINE` | 常量 `mw_common.py:2270-2271`；读 `mw_common.py:2722-2723` | `load_target_config` → target.yml 解析 | TS 镜像 `shared/target-config.ts:629-630`；互斥/冲突规则见 `_decide_active_mode` `mw_common.py:2441-2530` |
| `MW_PARTITION_PARENT` / `MW_PARTITION_ROOT` | 常量 `mw_common.py:2274-2275`；读 `mw_common.py:2724-2725` | `load_target_config`；partition env 家族检查 `mw.py:2323-2327`、`_partition_env_conflict` `mw.py:2665-2670` | TS 镜像 `target-config.ts:631-632`；纯 env 激活规则 `mw_common.py:2463-2530` |
| `MW_RAG_SERVERS_FILE` / `MW_RAG_SERVERS_HOME` | 常量 `mw_common.py:368-369`；读 `mw_common.py:379-396` | `machine_rag_servers_path`；写入镜像 `mw.py:2017-2035` | README:248-249；`FILE` 设定但缺失不回落到 HOME |
| `MW_RAG_PYTHON` | 读 `rag/cli-bridge.ts:33-36` | `resolveRagPython` → skill 形态 RAG 子进程 | 缺省 Windows `python` / 其它 `python3`；README:250 |
| `MW_PY` | 读 `shared/mw-runner.ts:30` | 扩展定位 `mw.py` 的路径覆盖 | README:246 |
| `MW_IMPL_GATE_ROOT` | 常量 `shared/implementation-gate.ts:62`；读 `:124` | `resolveGateRoot` | README:247，测试钩子，默认 cwd |
| `MW_UPSTREAM_HOST` / `MW_UPSTREAM_PORT` / `MW_UPSTREAM_BASE_PATH` | `proxy_multi.py:21-24` | 本地代理上游默认值 | 非文件配置 |
| `MW_SRC` / `MW_OUT` | 设 `mw.py:3536-3537`；读于内联 node 构建脚本 `mw.py:3485-3486` | esbuild 构建子进程 | 进程内传递，非用户配置 |
| `MW_E2E_*` / `MW_READCAP_BASELINE_DIR` / `MW_L3_STDOUT_ARCHIVE` | 测试文件 | 测试 | 仅测试钩子 |

### 4.2 `PI_*` 变量

| 变量 | 出处 | 谁读 | 备注 |
|---|---|---|---|
| `PI_WORKER_TASK` | 设 `launcher.py:248, 266, 275, 298, 323`（task.md 绝对路径） | `index.ts:61`（进入 Worker 模式的开关）、`worker/worker-mode.ts:603`、`shared/protected-config.ts:227`、`shared/xkey-gate-guard.ts:199` | README:242 |
| `PI_WORKER_TIMEOUT_MS` | 读 `worker/worker-mode.ts:742, 894` | `resolveBudgetMs`（`:155-160`） | `task.md` 的 `timeout:` 分钟头优先；README:243 |
| `PI_WORKER_IDLE_MS` | 读 `worker/worker-mode.ts:895` | `resolveIdleMs`（`:163-166`） | 默认 `DEFAULT_IDLE_MS = 10min`（`:148`）；README:244 |
| `PI_WORKER_ORPHAN_DEAD_MIN` | 常量 `mw_common.py:1858`；读 `orphan_dead_after` `:1915-1925` | launcher 静默规则 `launcher.py:588` | 默认 90min，非法值回落默认 |
| `PI_CODING_AGENT_DIR` | 常量 `mw_common.py:1146`；读 `:1640`、`agent_config_dir` `:1148-1158` | agent 目录解析 | TS：`shared/dispatch-models.ts:202`、`shared/mw-runner.ts:16`、`shared/protected-config.ts:95` |

（凭证类 env 如 `TIMI_API_KEY` / `ZAI_CODING_CN_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` 及其 `*_BASE_URL` 由 `_build_env` / `resolve_credential` 读取：`launcher.py:238-330`、`mw_common.py:193` 一带；与本次不是同一类"配置层"。）

### 4.3 P-015（env 不落盘）在代码里的体现

- `PI_WORKER_IDLE_MS` / `PI_WORKER_TIMEOUT_MS` **只存在于 serve 的进程 env**，由扩展在 worker 进程内 `process.env` 读取（`worker-mode.ts:742/894/895`）。
- launcher 给 worker 构造的 env 是 `_build_env`：`_stripped_env(config, rag_config)` + 凭证 env + `PI_WORKER_TASK`（`launcher.py:240-330`）。这两个墙钟变量**不会**被写入 task.md / config.json；`autopilot/config.py` 的字段集里也没有它们（`config.py:48-58`）。
- 因此重启时只继承"执行该命令的那个窗口"的 env：`/mw restart` 走 `mw.py:408` 的 `[sys.executable, mw.py, "serve"]`，`mw start` 继承启动进程 env；env 没设 → 回落默认 idle 10min（`worker-mode.ts:148/166`）→ 长任务被 idle 墙误杀。`UPDATE.md` A3 行把它写成"env 不落盘"。
- 对本 key 的直接结论：**机器级 verify 默认层必须是持久化文件**，命令行/env 只作覆盖（与 spec §1.1(3)/P-015 一致）。

---

## 5. `xkey_verify_cmd` 现网实况（FM / E2 / MW）

### 5.1 实测

**FM `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\config.json`**：存在，227 B，mtime 2026-09-24 11:06:45。

```json
{
  "enabled": true,
  "paused": false,
  "poll_interval_sec": 4,
  "max_parallel_keys": 2,
  "round_budget": 2,
  "worker_timeout_min": 30,
  "l2_read_file_cap": 60,
  "l2_read_byte_cap": 4194304,
  "advance_stall_ticks": 5
}
```

→ **不含任何 xkey 键**（无 `xkey_repair` / `xkey_verify_cmd` / `xkey_verify_timeout_s`）。

**E2 `H:\git\E2Feature\.agenticdoc\_autopilot\config.json`**：存在，200 B，mtime 2026-09-24 02:39:14。

```json
{
  "enabled": true,
  "paused": false,
  "poll_interval_sec": 4,
  "max_parallel_keys": 2,
  "round_budget": 2,
  "worker_timeout_min": 30,
  "l2_read_file_cap": 128,
  "l2_read_byte_cap": 4194304
}
```

→ **不含任何 xkey 键**（且缺 `advance_stall_ticks`）。

**MW `H:\git\Multi-Workers\.agenticdoc\_autopilot\config.json`**：**不存在**（`.agenticdoc/_autopilot/` 目录整体缺失）。

### 5.2 按代码路径的实际后果（不是猜测）

- **文件缺失（MW）**：`cached_load` 的 `path.stat()` 抛 `FileNotFoundError` → `return default_config()`（`autopilot/config.py:157-164`；`load_config` 同语义 `:126-127`）。默认 `enabled=False` → `mw serve` 的 `_conductor_decision` 不 spawn conductor（`mw.py:167-168`）。零足迹（`config.py` 模块 docstring `:8-11`）。
- **文件存在但缺 xkey 键（FM/E2）**：
  - `validate_config` 只校验"存在的字段"（`config.py:86-118`），缺键合法；`load_config` 返回**原 dict**（`config.py:133`）；`cached_load` 缓存原 dict（`:168-170`）。**没有"补默认值"这一步。**
  - conductor 读法：`if cfg.get("xkey_repair", False):`（`conductor.py:224`）→ 缺键 = `False` → `_xkey_aggregate` / `_xkey_proposal_stage` / `_xkey_apply_stage`（`conductor.py:224-234`）**整体不跑**。
  - **结论修正 spec 的假设**：FM/E2 现状**不是**"工单全部卡在验证失败"，而是 **xkey 通道整体关闭**。静默 fail-closed 只在有人显式写入 `xkey_repair: true` 而未配命令时才发生。
- **`xkey_repair: true` 且命令为空**：`_xkey_run_verify` 读 `cfg.get("xkey_verify_cmd") or []` → `[]`（`conductor.py:3460`），命中 `if not verify_cmd:`（`:3463`）→ `_xkey_verify_failed(..., "xkey_verify_cmd is empty (cannot prove green)")`（`:3466`）：字节回滚 + ledger 记录 + timeline `xkey-verify-failed`（`_xkey_verify_failed` `conductor.py:3334-3370`），ticket 永不 closed。
- **"静默"的确切含义**：`mw.py` / `mw_common.py` 中**零处** xkey（实测 grep 无命中），没有 doctor 检查项、没有启动自检；只有运行到 S4 才产生 `xkey-verify-failed`（`conductor.py:3364-3370`）与 escalation（`_xkey_escalation_write`，`:3334` 段内）。这就是 spec §1.1(5)/AC-008 要补的告警面。
- `xkey_verify_timeout_s` 缺省用 1800（`conductor.py:3461` 的 `_xkey_int(..., 1800)`）。

---

## 6. `{python}` 绑定 `sys.executable` 的实际后果 + 仓库"用哪个解释器"的既有约定

### 6.1 `{python}` 的现状

**`{python}` 不存在**于任何 token 集合（partition：`{parent}/{partition}/{<root name>}`；dual/single：`{game}/{engine}/{uproject}`，见 §1.3）。
- partition 模式下写 `{python}` → 被 `mw_common.py:2908-2914` 判 undefined，fail-closed。
- dual/single 模式下 → 被静默透传给 shell（§1.4）。

### 6.2 若绑定 `sys.executable` 会怎样

`sys.executable` 是启动 `mw.py serve` 的那个 Python 进程（conductor 由 `mw.py:169` 用 `sys.executable` spawn；conductor 内框架脚本也用 `sys.executable`，`conductor.py:1778`）。它由"用户在哪个 shell / venv / conda 里敲 `python mw.py serve`"决定，**不是**项目测试环境的解释器。后果：

1. **可移植性反而变差**：文件里看不出解释器是哪台机器的哪个 Python，行为随 serve 启动方式漂移。跨机器"同一份 config"跑出不同解释器。
2. **项目 venv 错配**：项目用 venv/uv/poetry 时，verify 会用 serve 的解释器 → import/依赖失败 → rc≠0，`_xkey_run_verify` 判 not green（`conductor.py:3476-3486`）→ 回滚，ticket 永远 `verify_failed`，且原因难诊断。
3. **Windows 不确定源**：`sys.executable` 可能是 Store alias、`py.exe` 拉起的 launcher、embedded python，或带 `-X utf8` 的同一 exe；不可审计。
4. **argv[0] 缺失仍是 fail-closed**：`run_verification` 是 `shell=False` + list argv（`xkey.py:1303`），argv[0] 不存在 → `returncode = 127`（`xkey.py:1317-1320`）。
5. **违背 origin 报告精神**：这个"值"既不在项目文件也不在命令行里，`show` 无法显示来源（与 AC-003 冲突）。

### 6.3 仓库既有"用哪个解释器跑项目命令"的约定

| 场景 | 约定 | 出处 |
|---|---|---|
| 框架自身脚本（install.py / update_index.py / conductor / mw serve 子进程） | `sys.executable` | `mw.py:169, 271, 311, 3679, 408`；`conductor.py:1778` |
| 项目命令（`mw ue-toolchain run`） | `shell=True` + 字符串 + cwd=控制根，解释器由命令自身 / PATH 决定 | `mw.py:1009` |
| RAG skill 子进程 | `MW_RAG_PYTHON` 显式覆盖，否则 Windows `python` / 其它 `python3` | `rag/cli-bridge.ts:33-36`；README:250 |
| 测试命令 | `python -m pytest -q`，假设 PATH 上有 `python` | README:352 |

**结论**：仓库唯一"可覆盖的项目解释器"约定是 `MW_RAG_PYTHON` 模式（env 覆盖 + 平台默认名），**不是** `sys.executable`。若 U-2 要提供 `{python}`，应照 `MW_RAG_PYTHON` 的形状定义（受 env 覆盖的常量名），并把解析结果纳入 `show` 的 origin 输出；不建议绑定 `sys.executable`。若不想引入这层复杂度，最稳的选择是不提供 `{python}`。

---

## 7. U-2 / U-3 / AC-007 定稿建议（可机械判定）

### 7.1 U-2 占位符集合：需钉死 5 件事

1. **token 集合（逐字）**：建议 `{control}` `{parent}` `{partition}` `{<root name>}`（与 `load_target_config` 已有字段一一对应）。**不含 `{python}`**；若要解释器覆盖，另立规则（见 §6.3），不与路径占位混在一起。
2. **展开域**：**list argv 逐元素、whole-token 展开**（不做 shell 引号/分词）。理由：`xkey_verify_cmd` 是 list（`config.py:61`）+ `shell=False`（`xkey.py:1303`），这是唯一不破坏安全边界的自洽选择。
3. **未定义占位**：fail-closed，错误文本照抄 `mw_common.py:2910-2912` 的形状（含 token 与原文），且**写入 CLI（`mw autopilot verify set`）与 conductor 消费两侧行为一致**。
4. **cwd 语义**：新增声明式键（如 `xkey_verify_cwd`），枚举 `control | partition | parent | <root name>`（或带同一占位集合的路径串）；**缺省应为 `partition`**（对齐 worker cwd `launcher.py:906`），替换当前硬编码的 `project_root`（`conductor.py:3459/3471`）。
5. **集成点**：解析结果必须是 `list[str]`；解析失败在写入时与消费时都要有明确错误。

### 7.2 U-3 dist 重建执行面

这是 RQ-3 的结论，RQ-4 侧只补两条约束：
- 改 verify 命令的解析/默认层是 **Python 侧**（`autopilot/config.py` + `conductor.py`），生效只需 `/mw restart`（serve 的 `code_dir` 见 E2/FM `.mw/serve.meta`；UPDATE.md A3），**与 dist 重建无关**；AC-009 的 dist 判据只覆盖 TS 侧 guard/kind。
- AC-010 的"新机器部署"文档必须把两条独立动作写清：Python 侧（serve restart）与 TS 侧（dist 重建）。否则"部署完成"无法机械验证。

### 7.3 AC-007 改写成可执行真值表

现措辞（"声明式可移植命令在 E2 的 partition 模式下解析出正确的实际路径，有测试"）不可机械判定。建议改为：

- **输入维度**：`mode ∈ {single, dual, partition}` × `(control 根, partition 根, parent 根, named roots)` × `cwd 声明（缺省 / 显式）` × `命令 argv（0 / 1 / 多个占位；含未知占位）`。
- **期望输出**：每个 argv 元素的**精确展开字符串** + **精确 cwd** + 未知占位时的**精确错误**（`TargetConfigError(kind="missing-field")` 或 CLI side 的等价错误）。
- **必须包含一个 `control ≠ partition ≠ parent` 的 fixture**：E2 是 `control == partition` 的退化用例，单用它不能证明 cwd 修复。
- **必须包含 E2 形状回归**：`active: partition`、`parent=E:\UEMigrator`、`partition=H:\git\E2Feature`；断言 partition 根 = `H:\git\E2Feature`、parent 根 = `E:\UEMigrator`，且 verify cwd 取 partition 根。**现状实现（`conductor.py:3459/3471` 用 project_root）在此断言下会红**——这正是该 AC 的价值。
- **必须含缺省分支**：`xkey_repair=true` 且有效命令为空 → 明确告警（与 AC-008 合流）。

### 7.4 新增未决项（超出 U-2/U-3，但会影响 AC-007 可判定性）

配置层目前**不强制** control 与 partition 的关系（不要求相等也不要求不等，`mw_common.py:2578-2589` 只约束 parent/partition）。若本 key 决定"verify cwd 默认取 partition"，需要同时定稿：当 `control ≠ partition` 时，`xkey` 的 target 文件路径（`conductor.py:3651` 的 `project_root / target_rel`）如何锚定。建议一并纳入 AC-007 或列为新的 U 项，否则同族根锚定问题只修一半。
