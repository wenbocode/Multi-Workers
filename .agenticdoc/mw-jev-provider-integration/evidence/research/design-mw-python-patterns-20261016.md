# RQ-D2 设计调研：mw Python 侧既有模式盘点（CLI / 配置 / doctor / 证据行 / 测试 / 编码卫生）

- key: mw-jev-provider-integration / 卡: tasks/D2-mw-python-patterns.md / 相位: DESIGN 调研
- 日期: 2026-10-16 / 类型: research（只读调研，未改任何源码/配置）
- 所有结论均先读文件再下结论；行号基于当前工作区 `H:\git\Multi-Workers`。

---

## Q1 CLI 骨架：mw.py 子命令注册/派发

**结论：argparse + subparsers，处理器命名 `cmd_<name>` 返回 int，模块底部一个 dispatch 字典 + `sys.exit` 派发。**

- 解析器构造：`_parse_args()`，`argparse.ArgumentParser(description="Multi-Workers service manager")` + `parser.add_subparsers(dest="subcommand", required=True)` — packages/multi-workers/mw.py:6682-6684。
- 处理器命名约定：`def cmd_<subcommand>(args: argparse.Namespace) -> int`，例：`cmd_serve`(mw.py:260)、`cmd_doctor`(mw.py:606)、`cmd_target`(mw.py:1051)、`cmd_model`(mw.py:3495)、`cmd_autopilot`(mw.py:4004)、`cmd_rag`(mw.py:2375)。
- 派发：`if __name__ == "__main__":` 内先拦截隐藏子命令 `_run_supervisor`（不经 argparse，避免进 --help，mw.py:7138-7142），然后 `args = _parse_args()`，查 `dispatch = {"serve": cmd_serve, ..., "run-detached": console_run.cmd_run_detached}`（mw.py:7144-7165），最后 `sys.exit(dispatch[args.subcommand](args))`（mw.py:7166）。**新增子命令 = 写一个 `cmd_decide` + `_parse_args` 里 `sub.add_parser("decide", help=...)` + dispatch 字典加一行。**
- 参数解析风格：全 argparse。`--project` 几乎每个子命令都 `required=True`（mw.py:6673、6800、6817）；`choices=` 约束（mw.py:6803）、`metavar=` 美化（mw.py:6791-6794）、f-string 动态 help（mw.py:6805）、`type=int`（mw.py:6674-6678）、`action="store_true"`（mw.py:6819）。
- 嵌套动作子命令模式（`mw decide <action>` 该照抄）：`target_p = sub.add_parser("target", ...)` → `target_sub = target_p.add_subparsers(dest="target_action", required=True)` → 每个 action 一个 `add_parser`（mw.py:6711-6731）；`autopilot`（mw.py:6808-6812）、`model`（mw.py:6770-6806）、`rag`（mw.py:7063+）同构。
- 退出码约定：`cmd_*` 返回 int 透传给 `sys.exit`；0=成功/健康，1=有问题（`cmd_doctor` mw.py:662 `return 0 if report["summary"]["healthy"] else 1`；`cmd_status` mw.py:601）；argparse 参数错误自带退出码 2；`--json` 时输出机器可读 JSON 且消费方容忍 exit 1（mw.py:653-654 + 注释 641-643）。
- `mw` 入口：**没有 console-script shim**。真实入口是 `python mw.py <sub>`（mw.py:7137 `__main__`）；TS 侧用 `PYTHON_EXE`（win=`python`，else `python3`，shared/mw-runner.ts:12）spawn `mw.py`，路径可用 `MW_PY` env 覆盖（mw-runner.ts:23-30、62）。help 文本里的 `mw ...` 是 `python mw.py ...` 的简写（如 mw.py:4390；ui-bridge.ts:3407 "python mw.py rag <sub> --project <dir>"）。
- help 文本约定：每个 add_parser 都带一句话英文 `help=`（mw.py:6686-6693）；机器出口用 `--json` + "machine exit" 措辞（mw.py:6813-6820）。

### 最小可复用骨架：CLI 子命令（来源 mw.py:606-662、6682-6684、7144-7166）

```python
def cmd_decide(args: argparse.Namespace) -> int:
    """One-line English docstring (照 cmd_doctor mw.py:606-610)."""
    project_dir = pathlib.Path(args.project).resolve()      # mw.py:611
    ...
    return 0   # 0 = ok, 1 = issue；argparse 错参自动 exit 2

# _parse_args() 内（mw.py:6684 之后）：
decide_p = sub.add_parser("decide", help="Decision client subcommand")
decide_p.add_argument("--project", required=True, help="Project directory")
decide_sub = decide_p.add_subparsers(dest="decide_action", required=True)  # 嵌套 action 照 mw.py:6711-6731

# __main__ dispatch 字典（mw.py:7144-7165）加一行：
"decide": cmd_decide,
```

---

## Q2 配置读写：.mw/ 配置文件清单、格式与原子写（P-003）

**结论：`.mw/` 下配置=YAML/JSON/单行文本三类；读侧两种容错契约并存（fail-soft / fail-closed）；写侧统一「temp + os.replace」原子写；并发段用 O_CREAT|O_EXCL 锁。**

### .mw/ 下既有文件（谁读谁写）

| 文件 | 格式 | 路径函数/读写点 |
|---|---|---|
| `.mw/dispatch.yml` | YAML（PyYAML） | `dispatch_config_path` mw_common.py:216-217；读 `load_dispatch_config` mw_common.py:224-252；写 `_model_write`（**属另一 active key，只读参考**）mw.py:3464-3492 |
| `.mw/window-model` | 单行文本 `prefix/model-id`，首行生效 | `window_model_path` mw_common.py:220-221；读 `read_window_model`（OSError→`""`）mw_common.py:263-270 |
| `.mw/serve.meta` | JSON | 写 `_write_serve_meta`（原子）mw.py:164-182；读 mw_common.py:2265 |
| `.mw/mw.pid` / `.mw/mw.stop` | 单值文本 | mw.py:89-91（write_text 直写）、mw.py:101-108 |
| `.mw/workers.lock` | 锁文件 | `acquire_lock` 调用点 mw_common.py:1897；实现 2279-2291 |
| `.mw/proxy.log` / `.mw/launcher.log` | 日志 | doctor 取证 `_doctor_proxy_log` mw_common.py:2567-2590、`_doctor_launcher_log` mw_common.py:2593+ |
| `.mw/launcher-beat.<pid>` | 心跳 | `launcher_beat_write` mw_common.py:2717 |
| `.mw/toolchain.json`、`.mw/toolchain-runs/` | JSON / 目录 | mw_common.py:5405；mw.py:1073 |
| `.mw/rag-servers.yml`、`.mw/rag-roots.json` | YAML / JSON | mw_common.py:679；mw.py:2222 |
| `.agenticdoc/_autopilot/config.json` | JSON（在 .agenticdoc，非 .mw） | `config_path` autopilot/config.py:144-145；`load_config`/`save_config` autopilot/config.py:200-231 |
| `providers.json`（包根，非项目） | JSON | `load_providers` mw_common.py:182（doctor 默认源 mw.py:612-617） |

### 读工具与容错契约（新配置文件二选一对齐）

- YAML 通用工具：**没有封装**，各处函数内 `import yaml` + `yaml.safe_load(path.read_text(encoding="utf-8"))`（mw_common.py:240-243、mw.py:3451-3457、3477-3490）。PyYAML 是隐式依赖（注释 mw_common.py:240）。
- **fail-soft 参照**（model 默认值这类"便利配置"，绝不能阻塞主流程）：`load_dispatch_config` 缺文件→`({}, None)`；解析/校验错→`({}, "message")`，错误交给 doctor 展示（mw_common.py:224-252，docstring 明言 mw_common.py:225-231）。
- **fail-closed 参照**（错配置必须响亮失败）：`autopilot/config.py load_config` 缺文件→默认值零足迹；**在但坏→raise**（unknown keys/类型错/越界都 raise，部分文件只返回实际携带的 key，绝不满填充默认）autopilot/config.py:200-215、`validate_config` 153-158。
- 单行文本容错参照：`read_window_model` OSError→`""`（mw_common.py:263-270）。

### P-003 原子写：实现位置与调用方式

- **规范出处**：`console_run.py:32`「P-003: heartbeat/marker are written temp-file + os.replace (never in-place)」。
- **最小实现（推荐照抄）**：`_atomic_write_json` — packages/multi-workers/console_run.py:191-195：

```python
def _atomic_write_json(path: pathlib.Path, data: dict) -> None:
    """P-003: temp file + os.replace, never an in-place truncating write."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
```

- 其他同型实现：`_write_serve_meta`（temp + flush + `os.replace`，mw.py:164-182）；`_write_pi_settings`（mw_common.py:1546-1552）；byte-copy 版带 `fsync`（mw.py:1307-1319）；raw-lines 版保样 `_write_workers_file`（`Path.replace`，未解析行逐字保留，mw_common.py:2301-2314）。
- **并发锁（goal.md Key Constraint 对应实现）**：`acquire_lock(lock_file)` O_CREAT|O_EXCL + 指数退避 20 次，`release_lock` unlink（mw_common.py:2279-2298）；锁下读改写实例：`xkey.ledger_append`（autopilot/xkey.py:544-573+，坏账本拒绝写 raise `XKeyLedgerCorrupt`）。
- 新配置文件命名约定：`.mw/` 下 kebab-case（`dispatch.yml`、`window-model`、`serve.meta`）；JSON 写 `json.dumps(..., ensure_ascii=False, indent=2) + "\n"`、`encoding="utf-8"`、`newline="\n"`（console_run.py:194、autopilot/config.py:229-231、mw_common.py:2116）。

### 最小可复用骨架：新配置文件（读 fail-soft + 原子写）

```python
def decide_config_path(project_root: pathlib.Path) -> pathlib.Path:   # 照 mw_common.py:216-221
    return project_root / ".mw" / "decide.json"

def load_decide_config(project_root: pathlib.Path) -> tuple[dict, str | None]:  # 照 mw_common.py:224-252
    path = decide_config_path(project_root)
    if not path.exists():
        return {}, None                       # 缺失 = 未配置，不是错误
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"decide.json unreadable: {exc}"   # 坏文件 → 错误串，doctor 展示
    ...
    return data, None

def save_decide_config(path, data):           # 照 console_run.py:191-195（P-003）
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
```

---

## Q3 doctor 行：格式、字段渲染与新增一行要动哪里

**结论：`doctor_report` 组装 sections（dict）→ `format_doctor_text` 逐 section 渲染 `key: ...` 行；行是条件发射（zero-perturbation）；错误用 `ERROR`/`ISSUES:`/`FAIL:` 文本标记；`--json` 出整份报告，exit 0/1。**

- 组装：`doctor_report(project_dir, fix, config, stale_after_sec, worktree_scan_roots) -> dict`，把各 `_doctor_*` section 挂进 report（mw_common.py:4234-4287）；随后 `issues/suggestions` 由 `_doctor_issues(report)` 产出并写入 `report["summary"]`（mw_common.py:4285-4286）。
- 渲染：`format_doctor_text(report) -> str`，一行一发现，`lines.append(f"{section}: ...")`，最后 `"\n".join(lines)`（mw_common.py:4290-4518）。行样式实例：
  - `service: running (PID 123)` / `not running`（mw_common.py:4294-4296）
  - `dispatch: role=value images=...; window model X` / `dispatch: ERROR — <msg>`（mw_common.py:4473-4485）——**这是"一个 section 一行、存在才渲染"的最佳模板**（`_doctor_dispatch` mw_common.py:1558）
  - `dispatch_fallback: a=x,y b=z`，只在有配置时出现（mw_common.py:4486-4496）
- 新增一行要动的函数/常量（最小改动面）：
  1. 新 `_doctor_<section>(project_dir) -> dict`（参照 `_doctor_dispatch` mw_common.py:1558）；
  2. `doctor_report` 里 `report["<section>"] = _doctor_<section>(project_dir)`（mw_common.py:4253-4284 任一点）；
  3. `format_doctor_text` 里加条件渲染块（mw_common.py:4290-4518 内，建议紧跟 dispatch 块 4473-4496 之后）；
  4. 若属于"应翻转 healthy"的问题，进 `_doctor_issues`（mw_common.py:3838+）；**纯信息行绝不进 issues**（先例：conductor mw.py:631-633、write_face mw.py:637-640 注释明言"never flips the healthy verdict"）。
  - 替代路径（不动 mw_common）：在 `cmd_doctor` 里注入 section + 打印辅助行，先例 `_doctor_rag`/`_format_rag_doctor_line`、`_doctor_write_face`、serve code（mw.py:631-661）。
- 错误/警告标记的既有表达：`ERROR` 前缀（`dispatch: ERROR — ...` mw_common.py:4477、4490；`target: ERROR <kind>: <msg>` mw_common.py:4350）；块级标记 `REGISTRY-ERROR`/`MISSING`/`UNVERIFIABLE`/`MARKER-ABSENT`/`LEFTOVER`/`STALE-ENTRY`（mw_common.py:4433-4437、4450-4461、4423-4428）；toolchain 检查 `ok`/`FAIL: <detail>`（mw_common.py:4368-4371）；汇总行 `summary: healthy` / `summary: ISSUES: <; 列表>` + `suggest: <s>`（mw_common.py:4514-4517）。
- zero-perturbation 铁律（多处注释明示）：健康/未配置的项目输出必须与历史逐字节一致，新行只在条件成立时发射（mw_common.py:4330-4332、4383-4385、4392-4393、4463-4472）。
- 机器出口：`mw doctor --json` 打印整份 report JSON（mw.py:653-654）；TS 侧逐字复刻 doctor 文本行（先例：RAG 行由 ui-bridge 按 `mw.py:_format_rag_doctor_line` 逐字渲染，ui-bridge.ts:2990-3105）——**新 doctor 行要考虑 TS 面板同步渲染**。

### 最小可复用骨架：doctor 行（来源 mw_common.py:1558、4473-4485、mw.py:606-662）

```python
def _doctor_decide(project_dir: pathlib.Path) -> dict:      # 照 _doctor_dispatch mw_common.py:1558
    data, error = load_decide_config(project_dir)
    return {"exists": bool(data) or bool(error), "error": error, ...}

# doctor_report 内（mw_common.py:4265 附近）：
report["decide"] = _doctor_decide(project_dir)

# format_doctor_text 内（照 mw_common.py:4473-4485，条件发射）：
decide = report.get("decide")
if decide is not None and decide.get("exists"):
    if decide.get("error"):
        lines.append(f"decide: ERROR — {decide['error']}")
    else:
        lines.append(f"decide: <渲染字段>")
# _doctor_issues 内仅在真问题时 append(...)（mw_common.py:3838+）
```

---

## Q4 证据行与 PM 可见面：谁写、什么 API、格式约定、[XXX] 前缀全集

**结论：trace.log 的生命周期行由 TS worker 写、Python 只解析/追加；Python 侧自身写 `[LAUNCHER]`/`[MODEL_RETRY]`/`[MODEL_FALLBACK]`/`[ENVELOPE_FALLBACK]`（trace.log）与 `[conductor]`（stderr）+ timeline JSONL + ledger。**

- **trace.log 位置与追加 API（Python 侧）**：`launcher._record_trace_line(entry, line)` = `task_path.parent / "trace.log"` 以 `open("a", encoding="utf-8")` 追加一行，OSError 吞掉（best-effort）— launcher.py:2019-2032。时间戳 `mw_common.iso_now()` = UTC `isoformat(timespec="seconds")`（mw_common.py:171-172）。
- **trace.log 的行格式约定**：`[前缀] <iso> key=value ...`，单空格分隔；TS 写入侧统一 `new Date().toISOString()`（output-writer.ts:600 等）；Python 解析侧用锚定正则（`_HEARTBEAT_LINE_RE` mw_common.py:2606、`_END_LINE_RE` mw_common.py:2678，且注明"Mirrors END_LINE_RE in agent-team-loop/shared/heartbeat.ts" mw_common.py:2674-2677）。
- **[END] 解析**：`parse_end_exit` 只读尾部 64KB（`_TRACE_TAIL_BYTES` mw_common.py:2679，stat+tail 读法 mw_common.py:2690-2699），后写者胜（mw_common.py:2682-2689）。心跳同理 `_last_heartbeat` mw_common.py:2621-2633。
- **launcher 生命周期/预算行（Python 写）**：`[MODEL_RETRY] <iso> model=<m> attempt=<k>` launcher.py:831（格式约定注释 472-479）；`[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>` launcher.py:861（注释 442-459）；`[ENVELOPE_FALLBACK]` 常量 `_ENVELOPE_FALLBACK_AUDIT` launcher.py:1473（用于 trace 审计行 launcher.py:1643）；普通 launcher 叙事行 `[LAUNCHER] <iso> <text>`（launcher.py:1712、2048、2057、2109，且注明对 [START]/[END]/[HEARTBEAT] 解析器惰性 launcher.py:2024-2025）。
- **launcher.log 行（非 trace）**：小写 `[launcher] spawn failed (...)/envelope .../reconcile (...)` launcher.py:84、115、134。
- **autopilot**：
  - 时间线：`Timeline.append` 单一 JSONL `.agenticdoc/_autopilot/timeline.jsonl`，行 schema `{"ts","seq","ev","key","stage","detail"}`（autopilot/timeline.py:3-8、308-355；10MB 轮转 22-27；ts 用本地 `_iso_now` UTC 秒精度，132-133）；事件名集合 `EVENT_TYPES` frozenset 与 TS 镜像锁定（timeline.py:67-109）。
  - 告警：唯一双通道 `_emit_alarm` = stderr `[conductor] <detail>`（serve 重定向到 `.mw/conductor.log`）+ `st.timeline.append(ev, ...)`，**不得发明第二通道**（autopilot/conductor.py:3339-3359）。
  - ledger：`xkey.ledger_append` 锁下读改写、`dedup_key` 幂等、tmp+os.replace、坏账本拒绝写（autopilot/xkey.py:544-573；路径 `ledger_path` 153-154，文件名 `ledger.json` 98）。
- **TS 写、Python 读的 trace 生命周期行**（写入点）：`[START]`（output-writer.ts:595-600）、`[PHASE]`（613-623）、`[TOOL]`（626-633，target 截 80 字符）、`[TIMEOUT]`（646-652）、`[FLOW]`（appendTrace 包装器 572-577）、`[ERROR]`（718-723，首行截 160）、`[END]`（737-743）、`[MODEL]`（605-609；heartbeat.ts:84）、`[HEARTBEAT]`（shared/heartbeat.ts:61-79）、`[CHECKPOINT]`（heartbeat.ts:31、62；pm/pm-orchestrator.ts:1666）、`[GOAL_CHECK]`（heartbeat.ts:111）、`[MODEL_ERR]`（worker/worker-mode.ts:3835）、`[TOOL_ERR]`（pm/ui-bridge.ts:1700；shared/run-detached.ts:212；output-writer.ts:637、642）。
- **跨语言哨兵**：`[XKEY_GATE]` 由 TS 守卫打印（shared/xkey-gate-guard.ts:224），Python 以限定子串检测（`_GATE_GUARD_MARKERS` mw_common.py:5283-5286）——新增机器可读行若需跨语言检测，照此"限定串 + Python 检测常量"模式。

### 既有 `[XXX]` 前缀清单（新前缀避让表）

**Python 侧写入/解析（trace.log、launcher.log、stderr、CLI 输出）：**
`[LAUNCHER]`（launcher.py:1712,2048,2057,2109）、`[MODEL_RETRY]`（launcher.py:831）、`[MODEL_FALLBACK]`（launcher.py:861）、`[ENVELOPE_FALLBACK]`（launcher.py:1473,1643）、`[launcher]`（小写，launcher.py:84,115,134）、`[conductor]`（conductor.py:3358）、`[proxy_multi]`（proxy_multi.py:104,123）、`[mw status]`（mw.py:600）、`[mw rag sync]`（mw.py:1299,1305,1320）、`[XKEY_GATE]`（检测 mw_common.py:5286）、`[VERIFY]`（**非 trace 标记**：envelope 段提示词 launcher.py:979；测试 human-visible 打印约定 test_mw_serve_config_partial.py:39）。

**TS 侧写入 trace.log / PM 面板（worker 输出协议，新前缀同样避让）：**
`[START]`、`[PHASE]`、`[TOOL]`、`[TOOL_ERR]`、`[TIMEOUT]`、`[FLOW]`、`[ERROR]`、`[END]`、`[MODEL]`、`[MODEL_ERR]`、`[MODEL_RETRY]`、`[MODEL_FALLBACK]`（提及 worker-mode.ts:3786）、`[HEARTBEAT]`、`[CHECKPOINT]`、`[GOAL_CHECK]`、`[IDLE_KILL]`（worker-mode.ts:2439）、`[ESCAPE_HATCH]`（worker-mode.ts:2393）、`[READ_SCOPE]`（worker-mode.ts:861）、`[WRITE_FACE]`（worker-mode.ts:2178）、`[WRITE_SCOPE]`（pm-orchestrator.ts:645）、`[WRITE_SCOPE_SUMMARY]`（worker-mode.ts:2373）、`[WRITE_SURFACE]`（worker-mode.ts:2711）、`[WRITE_FILE]`（change-ledger.ts:111）、`[WRITE_UNRESOLVED]`（change-ledger.ts:146）、`[XKEY_GATE]`（xkey-gate-guard.ts:224）、`[WORKTREE_GUARD]`（worktree-junction-guard.ts:205）、`[PROTECTED_CONFIG]`（protected-config.ts:220）、`[ACTIVATION_FLAG]`（index.ts:30）、`[GATE]`（implementation-gate.ts:483）、`[ENVELOPE_FALLBACK]`/`[ENVELOPE_FALLBACK_MARKER]`（pm-orchestrator.ts:966,1026）。
（注：清单来自全源码字面扫描，含少量仅作常量名/提示词的 token；避让时按"整表避开"处理最安全。`[ENV_*]`/`[KEY]`/`[RUN]`/`[HEADER]` 等为 env 名或数组字面量，非协议标记。）

**timeline `ev` 事件名（另一套命名空间，同样要查重）**：`EVENT_TYPES` frozenset（autopilot/timeline.py:67-109，如 `beat`、`config`、`skip`，conductor.py:930、528）。

---

## Q5 测试骨架：组织、跑法、断言与环境隔离

**结论：pytest 直跑（根目录 `./test.sh` 只覆盖 TS 工作区；Python 套件独立），文件级 hermetic（tmp_path + monkeypatch），文件头 docstring 交代背景，`[VERIFY]` 人工可见断言行。**

- 组织与命名：`packages/multi-workers/test_*.py` 平铺约 111 个文件，无子目录分包；命名 `test_<主题>.py` / 回归 `test_<family>_tNN_<slug>.py`（如 test_mwds_t07_reap_productfirst.py）。rare 例外：rag 系列用 unittest（7 个 `unittest.main` 文件：test_rag_*.py），主流是纯 pytest 函数式（`__main__` 自跑仅 2 个）。
- 跑法：`cd packages/multi-workers && python -m pytest -q`（README.md:490-494「430+ 通过；e2e 默认 deselect」）；deselect 由 pytest.ini 实现：`addopts = -m "not e2e_real and not e2e_l2"` + marker 声明（pytest.ini:1-5）。根 `./test.sh` 只做 TS（`env -i ... npm test`，test.sh:98 末行）；multi-workers 无 package.json、不在 npm workspaces 测试链里——**Python 测试必须单独 pytest 直跑**。
- 文件头模式（照 test_mw_serve_config_partial.py:1-35）：模块 docstring 讲清 bug 背景/契约/T-xx 引用（1-19）；`sys.path.insert(0, str(pathlib.Path(__file__).parent))` 后 `import mw` + `# noqa: E402`（29-33）；`MW_PY = pathlib.Path(__file__).parent / "mw.py"`（35）。
- 环境隔离约定：autouse fixture `monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "..."))` + `monkeypatch.delenv(..., raising=False)`，保证真实 `~/.agents` 机器层永不泄漏（test_mw_serve_config_partial.py:42-46）；一切产物落 `tmp_path`（docstring 明言 "Everything is hermetic under tmp_path" 第 16-18 行）。
- 断言风格：裸 `assert` + 失败上下文（`assert result.returncode == 0, result.stderr` test_rag_cli.py:290）；假对象注入 `monkeypatch.setattr(mw.subprocess, "Popen", fake_popen)`（test_mw_serve_config_partial.py:89）；跨进程 CLI 冒烟用 `subprocess.run([sys.executable, str(MW_PY), "rag", "sync", f"--project={self.root}"], capture_output=True, ...)`（test_rag_cli.py:284-290）。
- 文件写编码注意：测试内所有 write/read 显式 `encoding="utf-8"`，配置写加 `newline="\n"`（test_mw_serve_config_partial.py:54-58；test_rag_cli.py:171,176,181）。
- 中文/编码注意点：源码与夹具含中文是常态（launcher.py:965-966、1474-1477），全部显式 utf-8；Windows 控制台 GBK 显示乱码不影响文件内容——**不要**为了控制台好看改动文件编码。
- human-visible 验证行约定：`_verify(tag, **kv)` → `print(f"[VERIFY] {tag}: k=v ...")`（test_mw_serve_config_partial.py:38-39），供人眼/PM 复核，不参与断言。

### 最小可复制测试骨架（来源 test_mw_serve_config_partial.py:1-58、test_rag_cli.py:284-290）

```python
"""test_mw_decide_cli.py — T-xx: <一句话契约背景>."""
import json, pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent))   # :29
import mw  # noqa: E402                                   # :31
from autopilot import config as _cfg                      # 参照 :32

MW_PY = pathlib.Path(__file__).parent / "mw.py"           # :35

@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))  # :45

def test_decide_writes_config_atomically(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"; project.mkdir()
    rc = ...  # 直接调 mw.cmd_decide(argparse.Namespace(project=str(project), ...))
    assert rc == 0
    data = json.loads((project / ".mw" / "decide.json").read_text(encoding="utf-8"))  # :54-58 风格
    assert data["models"] == {...}

def test_decide_cli_subprocess(tmp_path: pathlib.Path) -> None:  # 照 test_rag_cli.py:284-290
    import subprocess
    result = subprocess.run([sys.executable, str(MW_PY), "decide", f"--project={tmp_path}"],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
```

---

## Q6 编码与输出卫生硬规则在代码里的体现

- **显式 `encoding="utf-8"`**：所有 read_text/write_text 均带（抽查实锤：mw_common.py:243、267、1551、2116；mw.py:91、108、181、3490；launcher.py:2029；autopilot/config.py:215、231；测试侧 test_mw_serve_config_partial.py:54-58）。无一处依赖平台默认编码。
- **`newline="\n"`**：JSON/配置类写入统一加（mw_common.py:2116；console_run.py:194；autopilot/config.py:231；mw.py:1177），避免 Windows CRLF 漂移破坏字节级 parity。
- **容错读 `errors="replace"`**：可能撕裂/外源的日志与 trace 读用 `errors="replace"`（trace 心跳 mw_common.py:2626；[END] 尾读 mw_common.py:2696）——新证据行解析器照此。
- **TS 侧 spawn Python 带 `-X utf8`**（agent-team-loop/agentic-scripts.ts:67），解释了为何文件全 utf-8 也能在 Windows 正常交互；`PYTHON_EXE = python/python3`（shared/mw-runner.ts:12）。
- **避免 PowerShell 管线 / 控制台风暴**：代码层不写 shell 单行串，全部 argv 直传（`console_run.py` 的 run-detached 语义 "stored verbatim, no shell" mw.py:7131-7132）；后台子进程注入 `CREATE_NO_WINDOW` 守卫（mw_console_guard/mw_console_guard.py:20-30，explicit console 旗标永不改写 8-11 行契约）；长驻打印带 `flush=True`（proxy_multi.py:104,123；conductor.py:3358）。
- **stdout 行数约束**：Python 侧**没有**代码级 ≤30 行硬闸；等价物是"尾部截断"惯例——doctor 只打 issue 行 + 尾巴摘要（proxy tail 10 行 mw_common.py:2587；launcher tail 3 行 mw_common.py:4321；trace 尾读 64KB `_TRACE_TAIL_BYTES` mw_common.py:2679；`read_log_tail(log, 400)` mw_common.py:2575）。本卡"每条命令 stdout ≤30 行"是 worker 输出面纪律（卡片 envelope 层），实现新 CLI 时应自带 `--json` 机读出口 + 文本出口保持少量行（cmd_doctor 先例 mw.py:653-662）。
- **Windows 路径惯例**：全 pathlib（`pathlib.Path(__file__).parent / "providers.json"` mw.py:615；repo root `Path(__file__).resolve().parents[2]` mw_common.py:5294-5295）；junction/大小写 parity 用 `os.path.normpath` + `Path.resolve()`（mw_common.py:4580-4584 注释明言 "junction/case folding parity with the TS normalizeRoot"）；路径含空格是一等公民（smoke_test.sh 头部 "AC-015: path with space"；`f"--project={self.root}"` 直传 argv）。
- 锁/原子双保险：P-003 原子写（见 Q2）+ O_EXCL 锁（mw_common.py:2279-2298）是 goal.md Key Constraints 在代码里的直接对应，新配置文件/证据行写路径必须沿用。

---

## 残留与未验证

- `mw` 是否存在某台机器级 shim（如全局 alias）：仓库内无 console_scripts/bin 证据，TS 侧直 spawn `python mw.py`（mw-runner.ts:12,64）；按 `python mw.py` 设计即可。
- `[TOOL]`/`[TOOL_ERR]`/`[CHECKPOINT]` 等前缀清单来自字面扫描（含少量非协议 token），已在清单内标注；新增前缀按整表避让即可，无需逐条复核语义。
- `_doctor_issues`（mw_common.py:3838 起）只读到 3910 行附近；机制（往 issues/suggestions 追加字符串）已确认，完整 issue 清单未逐行盘点。
- 未实际运行 pytest（本任务只读约束）；跑法结论以 README.md:490-494 与 pytest.ini:1-5 文本为据。
- mw.py:3441-3492（`_dispatch_extra_keys`/`_model_write`/`cmd_model` 头部）属另一 active key 的改动段，本次仅按卡片要求做只读模式参考，未提任何改动建议。

## 上下文来源

- packages/multi-workers/mw.py（7166 行）：CLI 骨架 260/606/1051/3441-3492/4004/6660-6820/7060-7166
- packages/multi-workers/mw_common.py（5644 行）：配置 179-280、锁/原子 2279-2314、doctor 1558/2567-2633/2672-2699/3838+/4234-4518、xkey 哨兵 5283-5291
- packages/multi-workers/launcher.py（2541 行）：trace 追加 2019-2032、预算行 442-479/831/861、envelope 1470-1478/1643、log 行 84/115/134
- packages/multi-workers/console_run.py（191-195 P-003）、proxy_multi.py:104,123、mw_console_guard/mw_console_guard.py:1-30
- packages/multi-workers/autopilot/config.py:144-231、autopilot/timeline.py:1-133/308-355、autopilot/conductor.py:3339-3364、autopilot/xkey.py:98/153-154/544+
- packages/multi-workers/pytest.ini:1-5、README.md:490-494、smoke_test.sh、test.sh（根，TS 用）
- 测试样例：test_mw_serve_config_partial.py:1-58、89-127、test_rag_cli.py:171-290
- TS 侧（读参照）：worker/output-writer.ts:572-743、shared/heartbeat.ts:31-111、shared/mw-runner.ts:12-104、agentic-scripts.ts:67、pm/ui-bridge.ts:2990-3105/3407
