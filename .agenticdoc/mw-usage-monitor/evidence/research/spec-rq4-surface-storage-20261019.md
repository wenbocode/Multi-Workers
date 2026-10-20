# spec-rq4-surface-storage — `mw stats` CLI 落位 / `/mw stats` 转发链路 / 机器级存储约定（调研，2026-10-19）

type: research · key: mw-usage-monitor / um-rq4-surface-storage
行号基准：`mw.py` 7526 行、`ui-bridge.ts` 3866 行（当前工作树实测；任务卡起点坐标 `mw.py:5195`/`ui-bridge.ts:167` 已漂移，见 §3/§1）。

## 结论

1. `/mw` 是 `registerMwCommands`（ui-bridge.ts:3676）里 `pi.registerCommand("mw")`（:3684）的**if-链分发**（非表驱动），首个 token 决定子命令（:3687-3688）；参数用 `trimmed.slice(sub.length).trim()` 原样下传给薄包装函数（如 :3813 model）。stdout/stderr 在 `runMwCliRaw`（mw-runner.ts:508-528）合并为一段文本，全部经 `ctx.ui.notify(text, level)` 单通道回显（info/warning/error），无面板。新增 `/mw stats` 最小文件集 = 3 个源文件 + 测试：`mw.py`（子参数 + dispatch + `cmd_stats`）、`shared/mw-runner.ts`（`statsMw` 包装）、`pm/ui-bridge.ts`（`runMwStatsCommand` + 分支 + MW_COMMAND_DESCRIPTION:3514 + usage 尾行:3859）。
2. `mw stats` 的 argparse 落位：`_parse_args`（mw.py:7009-7493），建议插在 `("stop","status")` 循环（:7016-7018）之后、`doctor`（:7020）之前（同为只读报表族）；dispatch 字典（:7503-7524）加一行。**必须接受可选 `--project`**：TS 侧 `runMwCliRaw` 恒在 argv 尾部追加 `--project=<dir>`（mw-runner.ts:515-517），mw.py 不声明就会 argparse 报错。双输出先例 = doctor（`--json` 分支 mw.py:655-661）与 update-env（:6967-6971）；列宽唯一先例是 `_format_update_env_text` 的 f-string 定宽 `{c['id']:<18}`（mw.py:6933），仓库**没有**动态列宽表格渲染器。
3. 机器级路径先例共 4 处：`agent_config_dir`（mw_common.py:1453-1461，`~/.pi/agent`，protected）、`global_ext_dir`（mw_common.py:2582-2586，TS 镜像 mw-runner.ts:14-18）、`.mw-py-path`（mw.py:5255-5260，放在 global_ext_dir 内）、`~/.agents/rag-servers.yml`（`machine_rag_servers_path` mw_common.py:685-703，显式 `MW_RAG_SERVERS_FILE`→`MW_RAG_SERVERS_HOME`→`HOME`→`USERPROFILE` 解析序）。`~/.mw/usage/` 无硬冲突（`is_protected_agent_config` 只护 pi agent dir，mw_common.py:1464-1476），但 `.mw` 已是**项目级**运行期目录名（mw.py:267-268），机器级复用同名有范围歧义；Windows 下 `ntpath.expanduser` 实测（本机 CPython 3.15）优先 `USERPROFILE`、忽略 `HOME`——与 rag-servers 的显式 env 序先例不一致。建议：若保留 `~/.mw/usage/`，须按 `machine_rag_servers_path` 同款写成 `MW_USAGE_DIR`→`USERPROFILE` 显式解析助手；更贴现有约定的是 `~/.agents/mw/usage/`（复用已有的机器级 `.agents` 根）。二选一由 spec 定。
4. 并发写先例齐全：跨进程锁 = `O_CREAT|O_EXCL` + 指数退避（`acquire_lock` mw_common.py:2369-2382，TS 镜像 file-lock.ts:12-38 `wx`）；原子重写 = "P-003" temp+`os.replace`（`_decide_write_config` mw.py:772-790：锁→tmp→replace→解锁；console_run.py:192-195 marker 同款；`_write_pi_settings` mw_common.py:1548-1552）。JSONL 追加两个先例：`decision.py:941-970` `_append_evidence`（无锁、best-effort、单写者，`open("a", encoding="utf-8", newline="\n")` + `ensure_ascii=False`）与 `archive_stale_entries`（mw_common.py:2481-2503，**锁保护**的追加）。多 launcher 并发 append 同一 JSONL 的推荐写法照抄后者：`acquire_lock(<file>.lock)` → 每条 `open("a", encoding="utf-8", newline="\n")` 写一行 `json.dumps(..., ensure_ascii=False)+"\n"` → `release_lock`；Windows 三坑：`newline="\n"` 防 CRLF、显式 utf-8、`os.replace` 同卷原子（mw.py:167 docstring）。rollup `rollup-YYYY-MM-DD.json` 安全重写 = `_decide_write_config` 原样套用。
5. 汇总口径可复用的既有术语只有：`wall`（console_run marker `wall_sec`，console_run.py:29/214）、trace.log `[END] exit/elapsed/tools/phases`（heartbeat.ts:93，mw_common.py:2765）、pi 的 Usage 字段 `input/output/cacheRead/cacheWrite`（packages/ai/src/types.ts:365-371，台账建议落成 snake_case `in/out/cache_read/cache_write`）。**p50/p90 与任何分位数实现、任何 token 记账在 mw 仓库内均不存在**（见未找到清单）。最小列集建议：按 model / type / key / project 四个行组，各组列 = `calls, in, out, cache_read, cache_write, wall_p50, wall_p90, n`；`n<5` 时分位数显示 `-`。注意捕获面缺口：LLM 代理只覆盖 claude/claude-cli/deepseek 端口路由（mw.py:351-354），默认 worker 路由 timi **不经过**代理（直连，mw.py:368-370），且 `proxy_multi.py` 全文与 `timi_proxy_cli/proxy.py` 均无 usage/token 钩子——代理侧台账看不到主力流量，捕获点（另一 RQ）大概率要落在 TS 扩展侧（pi 窗口持有 Usage 对象 + `[START] task=<key>`/`[MODEL]` 行可绑定 key/type/model）。
6. 测试落位：pytest 平铺在 `packages/multi-workers/test_*.py`（114 个），CLI 子命令先例 = `test_rag_cli.py:207-247`（`_run` 重定向 stdout 直调 `mw._cmd_rag_list(Namespace)`）、`test_decide_cli.py:128-196`（直调 `mw.cmd_decide` 断言 rc）、`test_doctor_activation.py:73-79`（`mw_common.doctor_report` 断言 `report["<section>"]`）；新文件建议 `test_stats_cli.py`。vitest 侧现成可测入口：`test/suite/rag-window.test.ts:129-237`（纯 parse/format + 注入 runner + 断言 `MW_COMMAND_DESCRIPTION` 含子命令）与 `test/extensions/agent-team-loop.test.ts:3030/4965-5216`（fake pi 注册 + `runMwModelCommand` 注入 runner）。doctor 加 `usage` 段的注册点是 `cmd_doctor` 的 `report["conductor"/"rag"/"write_face"/"serve_code"]` 段（mw.py:627-643）+ TS `DoctorJson`（mw-runner.ts:379-459）+ `format_doctor_text`（mw_common.py:4381）；取舍：台账是机器级而 doctor 是项目级诊断，建议 v1 **不加**（stats 自身 `--json` 头部报台账文件健康即可），若加必须照 rag 段"纯信息、不进 issues、不翻转 healthy"（mw.py:629-631 注释）。

## 证据

### 1. `/mw` 子命令注册与转发全貌

**注册与分发结构（if-链，非表驱动）**
- `ui-bridge.ts:3676-3684`：`export function registerMwCommands(pi, projectDir, workerStore, ackStore, watch, agenticdocRoot)` → `pi.registerCommand("mw", { description: MW_COMMAND_DESCRIPTION, handler: async (_args, ctx) => {...} })`。
- `ui-bridge.ts:3687-3688`：`const trimmed = _args.trim(); const sub = trimmed.split(/\s+/)[0] ?? "status";` —— 子命令 = 首个空白分隔 token，缺省按 `status`。
- 分支一览（`if (sub === ...)` 行号）：build:3690、init:3701、doctor:3711、update:3722、status:3738、start:3754、stop:3768、restart:3779、target:3796、partition:3803、model:3810、rag:3818、run-detached:3826、ack:3834；兜底 usage `ctx.ui.notify("Usage: /mw build|init|...", "warning")` :3846-3862（文本 :3859）。共 14 个分支。

**参数透传**
- 薄包装族统一 `await runMwXxxCommand(ctx, projectDir, trimmed.slice(sub.length).trim())`（:3799 target / :3806 partition / :3813 model / :3821 rag / :3829 run-detached）——即"去掉首个 token 后的原始参数串"整体下传，TS 只做 usage-first 的最小解析，语义单源在 Python（每处分支注释均写明 "Python stays the single source of parsing and validation"）。
- 直连 runner 族不走参数解析：doctor 直接取第二个 token 判 `fix`（:3712-3713）；ack 取 `[1]` 为目标（:3836-3838）。

**mw.py 调用与 stdout/stderr 呈现（shared/mw-runner.ts）**
- `PYTHON_EXE`（:12）：win32 `python` 否则 `python3`。
- `findMwPy()`（:29-52）：`MW_PY` env → `<globalExtDir>/.mw-py-path` sidecar（:33-40）→ 扩展源码相对路径 `../../../../../multi-workers/mw.py`（:42-49）。
- `runMwCliRaw`（:508-528）：`spawnSync(PYTHON_EXE, [mwPy, sub, ...args, \`--project=${projectDir}\`], { encoding: "utf8", timeout })`；**stdout+stderr 合并**：`const output = \`${result.stdout ?? ""}${result.stderr ?? ""}\`.trim()`（:524-525），exit code 原样返回（为 rag 的 0/1/2 语义）。
- `runMwCli`（:530-536）：非 0 一律折叠成 `{ok:false, error: output}`；`targetMw`/`partitionMw`/`modelMw`（:538/543/549）皆一行转发；`ragMw`（:566-574）保留原始 code。
- 回显通道：一律 `ctx.ui.notify(text, "info"|"warning"|"error")`（如 model show 成功 `r.output || "mw model show: ok"` ui-bridge.ts:3431-3433；失败 `mw model show failed: ${r.error}`）。多行长文本直接进 notify（doctor 报表即如此，:3715）。rag 额外做层级映射与 30 行截断：`formatRagOutput`（:3547-3560，`RAG_OUTPUT_MAX_LINES=30` :3520，超长加 `RAG_FULL_OUTPUT_HINT` :3524）。
- doctor 是唯一的"结构化"特例：`doctorMw`（mw-runner.ts:468-487）spawn `doctor --project=<dir> --json`，stdout 必须是 JSON（空 stdout = 失败 :479-483），TS 侧 `formatDoctorReport`（ui-bridge.ts:3144）重新排版后 notify。

**可复制模板：`/mw model show` 完整调用链**
1. 用户输入 `/mw model show` → ui-bridge.ts:3684 handler，sub=`"model"`；
2. :3810-3815 → `runMwModelCommand(ctx, projectDir, "show")`（def :3427，runner 默认参数 `= modelMw` :3429）；
3. `runMwModelCommand` :3430-3434：action=`"show"` → `runner(projectDir, ["show"])` → `ctx.ui.notify(r.ok ? r.output || "mw model show: ok" : \`mw model show failed: ${r.error}\`, r.ok ? "info" : "error")`；
4. `modelMw`（mw-runner.ts:549-551）→ `runMwCli("model", projectDir, ["show"])` → `runMwCliRaw`（:508）→ `spawnSync(python, [mwPy, "model", "show", "--project=<dir>"])`；
5. Python：`_parse_args`（mw.py:7009）→ `model_p`（:7088）→ `model_show_p`（:7105-7106）→ dispatch `{"model": cmd_model}`（:7511）→ `cmd_model`（:3822）→ `# show` 块（:4011-4038）`print(f"{role}: {configured} images=...")`；
6. TS 拿合并文本 notify。runner 可注入（tests: agent-team-loop.test.ts:5125-5216 用假 runner 直测包装函数）。

**`/mw doctor` 调用链**：:3711-3718 → `doctorMw(projectDir, fix)`（mw-runner.ts:468，spawn `doctor --project --json [--fix]`，timeout 15s）→ `JSON.parse` 成 `DoctorJson`（:379-459，全字段 optional 以容忍旧 mw.py）→ `formatDoctorReport`（ui-bridge.ts:3144）→ `ctx.ui.notify(..., "info")`；spawn/解析失败 → `` `mw doctor 执行失败: ${r.error}` `` error notify（:3716-3717）。

**新增 `/mw stats` 最小文件集**
1. `packages/multi-workers/mw.py`：`stats_p = sub.add_parser("stats", ...)`（插 :7018 后）+ `cmd_stats()` + dispatch 表 :7503-7524 加 `"stats": cmd_stats`；
2. `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`：`export function statsMw(projectDir, args): MwCliResult { return runMwCli("stats", projectDir, args); }`（放 :538-551 一族旁；若 stats 用"exit 1 = 无数据"语义则照 ragMw :566 保留原始 code）；
3. `pm/ui-bridge.ts`：`runMwStatsCommand`（照 :3427 模板，runner 可注入）+ `if (sub === "stats")` 分支（插 :3817 附近）+ `MW_COMMAND_DESCRIPTION`（:3514）与兜底 usage（:3859）各加 `stats`；
4. 测试：`packages/multi-workers/test_stats_cli.py`（新）+ vitest（见 §6）。

### 2. `mw stats` 的 CLI 落位（argparse）

**结构**：`_parse_args`（mw.py:7009-7493）：`sub = parser.add_subparsers(dest="subcommand", required=True)`（:7012）→ serve/start（:7013-7014，`_add_serve_args` :7001-7008）→ `for name in ("stop","status")` 仅 `--project`（:7016-7018）→ doctor（:7020-7035，`--project/--providers/--json/--fix/--stale-after/--worktree-scan-roots`）→ target（:7038-7059，二级子命令）→ partition（:7061-7086）→ model（:7088-7133）→ autopilot（:7135-7228）→ init（:7229）→ pull/push-agentictask（:7239/:7249）→ setup（:7256）→ bootstrap（:7267）→ build（:7287）→ update-env（:7298）→ worktree（:7312）→ ue-toolchain（:7351）→ rag（:7385-7441）→ decide（:7442-7473）→ run-detached（:7474-7492）→ `return parser.parse_args()`（:7493）。`if __name__`（:7496-7502）→ dispatch 字典（:7503-7524，21 项）→ `sys.exit(dispatch[args.subcommand](args))`（:7526）。现状**没有** usage/stats/monitor 子命令（rg add_parser 全表核对）。

**建议落位**：插在 `("stop","status")` 循环之后（:7018 后、`doctor_p = ...` :7020 前）——stats 与 stop/status 同属"仅 --project 的只读报表"族；或与 model 平级放 :7133 后亦可，但紧邻 status 语义最顺。
**必带 `--project`（可选、default None）**：TS `runMwCliRaw` 恒追加 `--project=<dir>`（mw-runner.ts:515-517），mw.py 不声明该参数 argparse 直接 exit 2。stats 读机器级台账，`--project` 仅作"按项目过滤"的可选过滤器（不给 = 全机）。

**输出格式约定**：人读文本默认，`--json` 整体切换（不是行内混排）。双输出先例：
- doctor：`--json` 声明 :7025；`if args.json: print(json.dumps(report, indent=2, default=str)) else: print(mw_common.format_doctor_text(report))`（:655-661）；
- update-env：同构 `--json` 分支 :6967-6971 + `_format_update_env_text`（:6922-6947）。
- **列宽/对齐唯一先例**：`_format_update_env_text` :6933 `lines.append(f"  [{mark}] {c['id']:<18} {c['detail']}")` —— f-string 定宽左对齐，无动态测宽。`format_doctor_text`（mw_common.py:4381-4435）是"一发现一行"的 `key: value` 风格；`mw model show`（:4013-4038）同为 `key: value` 行。建议 stats 沿用「分组头行 + 定宽 f-string 列」，不要自造表格渲染器。

### 3. 机器级目录约定与 `~/.mw/usage/` 判断

**既有机器级路径常量/助手（逐项）**
| 路径 | 定义 | 行号 |
|---|---|---|
| `~/.pi/agent`（或 `$PI_CODING_AGENT_DIR`） | `agent_config_dir()`：`env.get("PI_CODING_AGENT_DIR")` expanduser，否则 `Path.home()/".pi"/"agent"`；`AGENT_DIR_ENV="PI_CODING_AGENT_DIR"` :1450 | mw_common.py:1450-1461；TS 镜像 mw-runner.ts:14-18 |
| 同上（protected） | `is_protected_agent_config`：对 effective dir + 默认 dir 双重判定 | mw_common.py:1464-1476 |
| `<agent_dir>/extensions` | `global_ext_dir()`：`$PI_CODING_AGENT_DIR/extensions` else `~/.pi/agent/extensions` | mw_common.py:2582-2586；mw.py `_global_ext_dir` :5550-5552（任务卡的 5195 已漂移）；TS `globalExtDir` mw-runner.ts:14-18 |
| `<ext_dir>/.mw-py-path` | `_mw_py_path_file()`：机器级 sidecar 记录 mw.py 绝对路径；`_write_mw_py_path` mkdir+write | mw.py:5255-5263；消费方 findMwPy mw-runner.ts:33-40 |
| `~/.agents/rag-servers.yml` | `machine_rag_servers_path()`：`MW_RAG_SERVERS_FILE` → `MW_RAG_SERVERS_HOME` → `HOME` → `USERPROFILE`，逐个探测存在性，"the directory is never created"；mw.py:2494-2504 有同逻辑镜像 | mw_common.py:685-703 |

**项目级对照**：`mw_dir = project_dir / ".mw"; mw_dir.mkdir(parents=True, exist_ok=True)`（mw.py:267-268）；运行期文件 mw.log/proxy.log 追加、launcher.log/conductor.log 每 serve 会话截断（:281-287）；`.mw/dispatch.yml`、`serve.meta`、`mw.pid`、`mw.stop` 皆项目级（mw_common.py pid_file、mw-runner.ts:79/162）。

**`~/.mw/usage/` 判断**
- 无硬冲突：仓库没有任何代码对 `~/.mw` 特殊处理；protected 检查只覆盖 pi agent dir（mw_common.py:1464-1476），不会挡写入。
- 范围歧义（软风险）：`.mw` 是既定的**项目运行期**目录名；`~/.mw` 把同名提到机器级。若用户 HOME 本身是个项目并跑过 `mw init/serve`，`<home>/.mw` 会同时承担两种身份（project runtime 文件与 usage 台账混在一层）。
- Windows 展开实证（只读验证）：本机 CPython `ntpath.expanduser` 源码顺序为 `USERPROFILE` → `HOMEPATH/HOMEDRIVE`，**不读 `HOME`**（本会话实测 HOME=None、USERPROFILE=C:\Users\wenbozhou，`python -c "import ntpath,inspect;print(inspect.getsource(ntpath.expanduser))"`）。而 rag-servers 先例（mw_common.py:695-699）显式按 `MW_RAG_SERVERS_HOME`→`HOME`→`USERPROFILE` 探测——两者序不同；直接 `expanduser("~/.mw/usage")` 会与仓库既有机器级解析先例不一致且不可注入测试。
- **建议**：二选一，spec 拍板——(a) 保留 `~/.mw/usage/`，但新建 `usage_dir()` 助手，照 `machine_rag_servers_path` 写成 `MW_USAGE_DIR`（测试注入）→ `USERPROFILE` 显式序；(b) 改 `~/.agents/mw/usage/`，复用 `.agents` 这个已被 rag-servers 建立的机器级根（当前唯一占用者：`~/.agents/rag-servers.yml`），`.mw` 名字保持纯项目级。(b) 语义最干净；(a) 改动最小。

### 4. 追加写与并发安全先例

**跨进程文件锁（协议单源）**
- Python：`acquire_lock(lock_file, retries=20, base_delay=0.05)` — `os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)` + `time.sleep(base_delay * 2**attempt)`；`release_lock` unlink 容忍 FileNotFoundError。docstring："Same protocol as the TS side."（mw_common.py:2369-2388）
- TS：`acquireLock` 用 `wx` flag 同语义，retries 默认 10（file-lock.ts:12-38）。

**原子重写（"P-003"）**
- `_decide_write_config`（mw.py:772-790）：锁（`<path>.lock`）→ `<path>.tmp` `write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")` → `os.replace(tmp, path)` → finally release。注释明说 read-modify-write 共享文件必须整程持锁。
- `_write_serve_meta`（mw.py:166-185）：tmp + `os.replace`，docstring "same volume"（Windows 同卷才原子）。
- `_write_pi_settings`（mw_common.py:1548-1552）：`tmp.write_text(json.dumps(...)+"\n")` + `os.replace`。
- `_write_workers_file`（mw_common.py:2390-2404）：按原始行重建、`tmp_path.write_text(..., newline="\n")` + `tmp_path.replace(path)`（T-18/AC-023：不丢 unparsable 行）。
- console_run marker（console_run.py:192-195）："P-003: temp file + os.replace, never an in-place truncating write"，`json.dumps(..., ensure_ascii=False, indent=2)` + `newline="\n"`。

**JSONL 追加**
- `decision.py:941-970` `_append_evidence`：best-effort 永不抛（`except Exception: return`）；`path.open("a", encoding="utf-8", newline="\n")` + `fh.write(json.dumps(record, ensure_ascii=False) + "\n")`；**无锁**——其安全前提是单项目单写者（PM 窗口）。字段集 `dict.fromkeys(_EVIDENCE_FIELDS)` 固定列。
- `archive_stale_entries`（mw_common.py:2481-2503）：**锁保护**的追加——`acquire_lock(lock)` → `with spath.open("a", encoding="utf-8") as fh: fh.write(f"{...} | {now} | {REASON}\n")` → `_write_workers_file` → finally release。这是仓库里唯一"多进程可能同时 append 同一文件"的先例。
- 长句柄日志追加：mw.py:281-282 serve 把 mw.log/proxy.log 以 `"a"` 打开交给子进程 stdout——单写者（serve 自己），不可外推到多进程。

**推荐写法（多 launcher 并发 append 同一 JSONL）**
```
lock = usage_dir() / "usage.jsonl.lock"
mw_common.acquire_lock(lock)          # O_CREAT|O_EXCL + 指数退避，跨进程
try:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")   # 每条一次打开-写-关闭
finally:
    mw_common.release_lock(lock)
```
Windows 三坑（全部有仓内先例可抄）：1) `newline="\n"` 防 CRLF（decision.py:967、console_run.py:194、mw_common.py:2402）；2) 显式 `encoding="utf-8"`（拒绝 locale 默认，decision.py:967）；3) 不复用长句柄、每条记录独立 open/close（mw.py:282 的长句柄模式只在单写者下成立）。
**rollup 安全重写**：`_decide_write_config`（mw.py:772-790）原样套用——`acquire_lock(rollup.lock)` → 写 `rollup-YYYY-MM-DD.json.tmp`（indent=2、ensure_ascii=False、结尾 `"\n"`、newline="\n"）→ `os.replace` → release。读侧容错照 `readServeMeta`（mw-runner.ts:222-248：全字段 optional、坏 JSON 返 null）。

### 5. 汇总口径与呈现建议

**既有数据形态（stats 的输入候选）**
- trace.log 行协议：`[START] <ts> task=<key> type=<t> phases=<spec>` / `[MODEL] <ts> model=<id>` / `[END] <ts> exit=<n> elapsed=<n>s tools=<n> phases=<n/m>` / `[CHECKPOINT] ... elapsed=<n>s reads= writes= risk=<low|mid|high>` / `[HEARTBEAT] <ts> task=`（TS 正则 heartbeat.ts:91-96；Python 镜像 mw_common.py:2696、:2765-2766）。`elapsed` 为墙钟秒。
- console_run marker.json：`{"schema":"mw-run/1","rc":...,"timed_out":...,"wall_sec":...,"pid":...,"argv":[...]}`（console_run.py:27-29，:214 `"wall_sec": round((ended_at_ms-started_at_ms)/1000.0, 3)`）。
- pi Usage 对象：`input/output/cacheRead/cacheWrite(+cacheWrite1h)`（packages/ai/src/types.ts:365-371）——仓库内唯一的 tokens in/out/cache 词汇来源；台账建议 snake_case：`in/out/cache_read/cache_write`。
- 维度词源：模型 id `prefix/model`（如 `timi/glm-5.3`，mw_common.KNOWN_MODEL_PREFIXES :138）；任务类型 `type:` → `TASK_TYPE_TO_ROLE` 桶（mw_common.py:144-160：coding/phase-writer/repair/roadmap-writer→coding，review/verifier/reviewer→review，research/rag-research→research…）；key = AgenticTask key（`_index.parallel`）；项目 = cwd。

**最小列集**（默认简报，`mw stats` 无参 = 当天；四行组，每组一表）
- 行组维度：`by model`（prefix/model 全称）、`by type`（任务类型原始 `type:` 值）、`by key`（AgenticTask key）、`by project`（项目根尾段或 --project 过滤值）。
- 每行列：`calls, in, out, cache_read, cache_write, wall_p50, wall_p90, n`。tokens 只求和不估钱（用户已定）；`wall` 复用 console_run 的 wall 术语；分位数建议 p50/p90（任务书给定；仓库内无任何分位先例，由 stats 模块自带小实现，不需引依赖）。
- 样本不足标注：`n < 5` 的行分位数显示 `-`，且每行都带 `n=` 列；无任何样本的维度组整组省略（照 doctor 的"零值不输出"习惯，format_doctor_text mw_common.py:4421-4435 仅在有 liveness 时打印 workers 行）。

**样例输出（纯文本示意，非实测；`mw stats` 默认当日简报）**
```
[mw stats] 2026-10-19 · ledger ~/.mw/usage/usage.jsonl (12,483 rows, 3 files)
— by model —
model                calls      in      out  cache_read  cache_write  wall_p50  wall_p90     n
timi/glm-5.3           214  1.21M   182.4K       8.90M        1.02M      41s       96s   214
timi/gpt-5.6-sol        63  402.1K    55.1K       2.10M      310.5K      58s      133s    63
claude/…                 7   88.0K    12.0K          -            -       -         -     7
— by type —
coding                 187  ...      ...         ...          ...        44s      101s   187
review                  52  ...      ...         ...          ...        37s       80s    52
research                45  ...      ...         ...          ...        52s      120s    45
— by key —
mw-usage-monitor        96  ...      ...         ...          ...        49s      110s    96
_scratch                63  ...      ...         ...          ...        39s       88s    63
— by project —
Multi-Workers          284  ...      ...         ...          ...        45s      104s   284
totals                 284  1.70M   249.5K      11.00M        1.33M        —         —
```
（`-` = 样本不足 n<5；`...` 为示意省略。）

**CLI 过滤形态建议**（对齐任务书 `--since/--key/--type/--model/--json`）：`--since` 接受 `YYYY-MM-DD` 或 `Nd`（如 `7d`）；`--key/--type/--model` 可重复（argparse `action="append"`，rag 的 `--root` 同款 mw.py:7076-7078）；`--json` 输出与文本同构的 `{window, groups:{model:[...],type:[...],key:[...],project:[...]}, totals}`。窗口简报 `/mw stats` 无参 → 打印当日默认简报；带参原样透传（rag 模式）。

**捕获面缺口（spec 必须显式决策的依赖）**：mw 的 LLM 代理仅服务 claude/claude-cli/deepseek 的端口路由（mw.py:351-354 注释；`proxy_routes` 过滤 `config.providers[route].port`），默认 worker 路由 timi/zai-coding-cn/codex-native **直连不过代理**（:368-370）；`proxy_multi.py` 全文（99 行）无任何 usage/token 记录点，上游 `timi_proxy_cli/proxy.py` 亦无（`rg -i "usage|token"` 零命中）。⇒ 若台账由代理写，主力流量（timi）不可见；现实捕获点应是 TS 扩展侧（pi 窗口在会话内持有 Usage 对象，且 trace.log `[START] task= type=`/`[MODEL]` 行可把 key/type/model 与 usage 关联；凭证隔离后每 worker 只见自己的 key，`by key` 归因天然成立）。此为 RQ4 范围外的接口约定，spec 引用本节即可。

### 6. 测试落位

**pytest**（全部平铺 `packages/multi-workers/test_*.py`，现 114 个）：
- `test_rag_cli.py:207-247`：class + `_run` 助手（:197-202 `contextlib.redirect_stdout(buf)` 直调 `mw._cmd_rag_list(argparse.Namespace(...))` 断言 `(code, out)`），text/JSON 双断言（:230-247）；`_ns` 助手 :194-196。
- `test_decide_cli.py:128-196`：直调 `mw.cmd_decide(_args(...))` 断言 rc（0/2 语义）；`_args` 组装 Namespace。
- `test_doctor_activation.py:73-79`：`mw_common.doctor_report(...)` 收集 report 后断言 `report["activation"]["..."]`——doctor 新段落测试的直接模板。
- ⇒ 新文件 `packages/multi-workers/test_stats_cli.py`：覆盖 `cmd_stats` 的分组聚合、`--json` 形状、`n<5` 分位数 `-`、空台账 exit 0 + 空 group、`MW_USAGE_DIR` 注入的 tmp 路径（照 test_rag_cli 的 `mock.patch.dict(os.environ, ...)` :59-66）。

**vitest**：
- `test/suite/rag-window.test.ts:129-237`：`runMwRagCommand(ctx, "/proj", raw, injectableRunner)` 的 spawn-free 测法 + `expect(MW_COMMAND_DESCRIPTION).toContain("rag")`（:236）——`/mw stats` 照抄成 usage-window.test.ts（或并入本文件）。
- `test/extensions/agent-team-loop.test.ts:3030`（`registerMwCommands(pi, root, store, ackStore, {key}, root)` fake pi 注册）+ :4965-5216（`runMwTargetCommand`/`runMwModelCommand` 注入 runner 断言 notify 文本与级别）——stats 分支与薄包装的现成测试容器。
- ⇒ TS 侧可测入口已齐备：解析/格式化做成纯函数 + runner 注入即可零 spawn 测试。

**doctor 加 `usage` 段？** 注册点：`cmd_doctor` 内 `report["conductor"] = ...`（mw.py:628-629）、`report["rag"] = _doctor_rag(project_dir)`（:631-632）、`report["write_face"]`（:635-637）、`report["serve_code"]`（:639-643）；文本面 `format_doctor_text`（mw_common.py:4381）+ doctor 专属追加行（mw.py:662-665）；TS 面 `DoctorJson` 加 optional 字段（mw-runner.ts:379-459，"all fields optional so an older mw.py renders nothing"）。**取舍**：加——`/mw doctor` 一站式暴露"台账目录不可写/JSONL 损坏行数/rollup 缺日"；不加——台账是机器级资产，doctor 是项目级诊断，坏台账不是本项目不健康；且 rag 段先例要求信息段"never flips the healthy verdict"（mw.py:629-631 注释）。**建议 v1 不加**，stats `--json` 顶部自带 `ledger: {dir, files, rows, corrupt_lines}` 承担该职责；若后续加段，必须按 rag/write_face 的纯信息段模式。

### 未找到清单

- `mw stats` / `usage` / `monitor` 子命令：未找到（`rg -n -m 100 "add_parser\(" mw.py` 全表 21 个 dispatch 项，无一相关）。
- p50/p90/percentile 实现：未找到（`rg -n "p50|p90|percentile" packages/multi-workers --glob "*.py"` 零输出）。
- 字面 `tokens in/out/cache` 记账：未找到；最近似为 pi `Usage` 字段 `input/output/cacheRead/cacheWrite`（packages/ai/src/types.ts:365-371）。
- 动态列宽表格渲染（ljust/rjust/测宽）：未找到（mw.py/mw_common.py 零命中；仅 mw.py:6933 `{:<18}` 定宽）。
- `fcntl`/`msvcrt`/`lockf`：未找到（mw.py/mw_common.py 零命中；锁协议统一为 O_CREAT|O_EXCL，mw_common.py:2369-2382）。
- 无锁跨进程 JSONL 并发追加先例：未找到（仅有锁内追加 archive_stale_entries mw_common.py:2481-2503 与单写者追加 decision.py:941-970）。
- 代理侧 usage 捕获点：未找到（proxy_multi.py 全文、E:\CLI_workspace\claude-hook\timi-proxy-cli\src\timi_proxy_cli\proxy.py 的 `rg -i "usage|token"` 均零命中）。
- 任务卡坐标 `mw.py:5195`（`_global_ext_dir`）与 `ui-bridge.ts:167`（/mw 转发面）：已漂移，现分别为 mw.py:5550-5552、ui-bridge.ts:3676-3684。

## 残留与未验证

**未覆盖面声明**：
1. 未运行任何测试/未运行 mw.py 任何子命令（只读边界）；样例输出为示意，列宽未实测渲染。
2. `ntpath.expanduser` 的 USERPROFILE 优先结论来自本机 CPython 3.15 的 inspect 源码 + 环境实测（HOME=None）；其它 Python 版本（尤其 <3.8 的 HOME 优先行为）未验证，spec 若依赖解析序应以显式 env 序（§3 建议 a）消除版本差。
3. `timi_proxy_cli` 是外部私有包（本机装于 E:\CLI_workspace\claude-hook\timi-proxy-cli）；其 proxy.py 只做了静态检索，未审计请求转发全路径——"代理侧无 usage 钩子"的结论对该包其它模块（如 logging_utils）未逐一排除。
4. 台账 schema/字段、按天切分粒度、`--since` 解析格式属捕获点 RQ 的决策面，本报告只给落位与兼容约束（`--project` 必须可选接受）。
5. 未检索 packages/coding-agent 主程序（非扩展）内是否有别的 usage 统计面；结论限定在 agent-team-loop + multi-workers 两个包。
6. `[MODEL_FALLBACK]` trace 行（mw_common.py:337 注释提及）未展开核对格式，若 stats 需要 fallback 归因需另行确认。

## 上下文来源

- 任务书：`.agenticdoc/mw-usage-monitor/tasks/T-RQ4-surface-storage.md`（card_sha256 bf42334a…；行号基准实测计数：mw.py 7526 行 / ui-bridge.ts 3866 行 / test_*.py 114 个）。
- 检索方式：rg 定向 + read 全文核对（ui-bridge.ts 3260-3866、mw-runner.ts 全文、mw.py argparse/dispatch/doctor/model/atomic-write 各段、mw_common.py 锁/路径/doctor-text 段、decision.py 证据追加、console_run.py marker、heartbeat.ts 行协议、packages/ai/src/types.ts Usage）；无任何仓库写入、无 pytest/vitest 执行、未启停 mw serve。
- 关键实证命令（复现用）：`rg -n -m 100 "add_parser\(|set_defaults\(func" mw.py`；`rg -n 'if \(sub === ' ui-bridge.ts`；`python -c "import ntpath,inspect;print(inspect.getsource(ntpath.expanduser))"`；`rg -i "usage|token" proxy_multi.py`（零命中）。

[VERIFY] dispatch_entries=21; mw_sub_branches=14; mw_py_lines=7526; ui_bridge_lines=3866; pytest_files=114; rag_subcommands=5 (list/probe/audit/sync/init); ts_precedents=2 (rag-window.test.ts:129-237, agent-team-loop.test.ts:4965-5216); atomic_write_precedents=5 (mw.py:772-790, mw.py:166-185, mw_common.py:1548-1552, mw_common.py:2390-2404, console_run.py:192-195); jsonl_append_precedents=2 (decision.py:941-970, mw_common.py:2481-2503); machine_path_helpers=4; usage_capture_hooks_found=0
