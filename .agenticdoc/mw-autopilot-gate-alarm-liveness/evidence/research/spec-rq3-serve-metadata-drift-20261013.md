# RQ-3 — serve/conductor 启动元数据与代码漂移检测的最小改动面

- Key: `mw-autopilot-gate-alarm-liveness`｜RQ: T-03｜日期: 2026-10-13｜阶段: SPEC｜只读取证
- 对应 AC: AC-005（`serve.meta` 记录 commit + 与工作区 HEAD 比对 + 漂移告警含期望/实际 commit + 修法 + serve 生命周期内限频）、AC-006（复用既有 stderr + timeline 通道）、AC-010（配置镜像一致）
- 唯一证据文件：本文件

## §0 结论先行

1. **`serve.meta` 今天只有三个字段，且没有 commit**：`{pid, started_at_ms, code_dir}`，由 `mw.py:122-131` 写、`cmd_serve` 在 `mw.py:273` 写一次、`mw.py:398` 退出时删。**这就是"我跑的是不是当前代码"的全部本地证据**——只有"启动时刻"和"源码目录"，没有任何代码身份。
2. **`code_dir` 是写而不读的死字段**：全仓只有 writer（`mw.py:126`）与断言它值的测试（`test_serve_meta.py:30/:78`）命中；4 个读取点全部只读 `started_at_ms`（TS `mw-runner.ts:207-216`、`monitor.ts:341-347`、Python `mw.py:5368-5379`）。⇒ 现在**没有任何一处**保证"检查者的代码树" == "serve 启动时的代码树"。
3. **serve/conductor 启动时没有任何代码身份可用**：不存在 `serve.version`、没有 bundle 哈希、没有 commit。唯一版本源 `_framework_version()`（`mw.py:4354`、`launcher.py:953`）读 `packages/coding-agent/package.json`（今天 `0.83.0`），只用于 bundle 注入与 envelope producer 基线，**从不落盘**。conductor 启动只写 `conductor.pid`（`conductor.py:7228-7230`）+ 一条 `goal-snapshot` timeline（`:7242`）。
4. **TS 侧 stale-serve 判据是纯 mtime**：`mwCodeNewestMtimeMs()`（`mw-runner.ts:224-256`）= mw 源码树最新 `*.py|*.json` mtime（跳过 `test_*`/`_*`/`__pycache__`/`dist`/`.tmp`） > `serve.meta.started_at_ms + 2000ms`（`:284`）。**Python 侧的等价物只有一个：`mw update-env` 的 A3 anchor（`mw.py:5362-5389`）**，判据同式（`_mw_code_newest_mtime()`，`mw.py:5120-5149`），但它不是 tick、不是告警、`mw doctor`（`mw_common.doctor_report`）与 `mw status`（`mw.py:486`）都**完全没有** serve 陈旧检查。
5. **真实现场（本卡最重要的实证）**：E2Feature 的 serve PID **140964** 起于 `2026-10-12T14:06:14Z`，而 `mw.py` mtime = `2026-10-13T02:26:03Z` ⇒ **此刻实测陈旧 +44389 s（12 h 20 m）**。同一项目的 `AUTOPILOT-HANDOFF.md` 在 `2026-10-12 14:11Z` 写下了 `mw update-env` 的"`serve = ok（PID 140964，代码新鲜）`"并注明"启动横幅那条 `/mw restart` 是过期信息，无需重启"——该结论在当时**确实正确**（当时最新 runtime mtime 是 `13:55:08Z`，早于 serve 启动），但 **+29m40s 后 `autopilot/config.py` 被改、+41m13s 后 `dispatch.py` 被改**，verdict 静默失效并作为"事实"留在文档里。⇒ 缺陷不是公式，而是：**判据的结论是时刻相关的，却以散文形式被缓存；`serve.meta` 没有代码身份可供复核。**
6. **只靠 commit 不够**：开发机常态是"改文件不提交"（dirty worktree），HEAD 不动而代码已变。⇒ AC-005 的正确形态是**三件事一起记**：`commit` + `dirty` + `code_mtime_ms`（把基线固化进 meta），而不是用 commit 取代 mtime。
7. **最小可靠采集 = 复用既有 `mw.py:_git_head_short()`（`:5187`）+ `_git_dirty()`（`:5175`），并且必须补 timeout**：`_git()`（`:4097`）今天 `subprocess.run(...)` 无 timeout、无 `CREATE_NO_WINDOW`，在 serve 启动路径上调用有挂死/弹窗风险。纯文件读 `.git/HEAD`（→ loose ref → `packed-refs`）可零依赖但需处理 worktree 的 `gitdir:` 与 packed ref；建议**只在启动时用 `git`（一次），在每 tick 的比对里只用文件读/stat**。
8. **比对必须用 `serve.meta.code_dir` 作为代码树，不能用检查者自己的树**：`findMwPy()`（`mw-runner.ts:29-55`：`MW_PY` env > 全局 `.mw-py-path` sidecar > 仓库相对）与 `_SCRIPT_DIR`（`mw.py:46`）都可能指向**另一棵树**。今天只有测试用例手工把两边对齐（`dual-root-worker.test.ts:239-245` 显式把 `code_dir: pkg` 与 `mwCodeNewestMtimeMs(pkg/mw.py)` 配对），产品代码没有这个保证。
9. **双重告警不需要"消掉一个"，需要分工**：Python（conductor tick）拥有**持久通道**（stderr→`conductor.log` + timeline `config`，`conductor.py:2603-2620` 形状）与 serve 生命周期级限频；TS 继续只拥有**交互恢复**（面板 STALE CODE `monitor.ts:782`、`/mw status` `ui-bridge.ts:3413`、`/autopilot enable` 自动重启 `console.ts:627-632`）。两侧都不得新增"周期性重复通知"，Python 侧不得自动重启（会与 TS 的 restart 抢）。
10. **`serve.meta` 的写入是非原子的**（`p.write_text(json.dumps(meta))`，`mw.py:128-131`）⇒ 加字段后读取端必须继续容忍半截 JSON（TS 已 `catch → null`，`mw-runner.ts:210-215`；Python 已 `except json.JSONDecodeError`，`mw.py:5371`），顺带用 `os.replace` 修掉这个竞态（1 行）。

---

## §1 `serve.meta` 真实现状

### 1.1 写入点 / 字段 / 路径

| 项 | 落点 | 原文/说明 |
|---|---|---|
| 路径 | `mw.py:114-119` `_serve_meta_path()` | `return project_dir / ".mw" / "serve.meta"` |
| 写入 | `mw.py:122-131` `_write_serve_meta()` | `meta = {"pid": os.getpid(), "started_at_ms": int(time.time()*1000), "code_dir": str(_SCRIPT_DIR)}` → `p.write_text(json.dumps(meta), encoding="utf-8")`（**非原子**） |
| 删除 | `mw.py:133-137` `_remove_serve_meta()` | `except FileNotFoundError: pass` |
| 唯一调用（写） | `mw.py:273`（`cmd_serve` 内，紧随 `:271 _write_pid(pid_path)`） | PID 与 meta 同一路径序，`wrote_pid` 同时决定二者清理 |
| 唯一调用（删） | `mw.py:398`（`finally` 块，紧随 `:397 _remove_pid`） | serve 正常/异常退出均删 |
| 谁定义 `_SCRIPT_DIR` | `mw.py:46` | `pathlib.Path(__file__).parent` = **本仓 `packages/multi-workers`**（源码目录，非安装副本） |
| 文档 | `mw.py:115-117` docstring | 明确写"extension-side staleness detection (stale-serve fix): the agent-team-loop extension compares started_at_ms against the mw source tree's newest mtime" |
| 更新锚点登记 | `UPDATE.md:40`（A3 行） | `<project>/.mw/serve.meta`（`started_at_ms`）；修法"该项目窗口 `/mw restart`（在飞 worker 由新 launcher orphan reconcile 收养）" |

**没有第二个 writer**：`grep 'serve\.meta'` 全仓（`packages/**` + `dist/` + docs）只命中上述 writer、TS 读者、`test_serve_meta.py`、`test_update_env.py`、`UPDATE.md`。

### 1.2 全部读取点

| 读者 | 落点 | 读什么 | 用途 |
|---|---|---|---|
| TS `readServeMeta` | `shared/mw-runner.ts:207-216` | `pid`, `started_at_ms`（**忽略 `code_dir`**） | `MwServeMeta{pid, startedAtMs}`；类型定义 `:198-201` |
| TS `serveStaleness` | `shared/mw-runner.ts:272-289` | 同上 + `codeMtimeMs` 参数或 `mwCodeNewestMtimeMs()` | `stale = codeMs > startedAtMs + 2000`；`detail` 为两个 ISO 时刻 |
| TS 面板 | `autopilot/monitor.ts:340-355`（`readMonitorState`） | `readServeMeta()?.startedAtMs ??` `mw.pid` mtime | 面板行 + `upMs`；渲染 `:782-789`（`STALE CODE ... -> /mw restart`） |
| TS `/mw status` | `pm/ui-bridge.ts:3413-3419` | `serveStaleness()` | notify warning |
| TS `/autopilot enable` 前置 | `autopilot/console.ts:622-633`（`defaultEnsureMwRunning`）+ `pm-orchestrator.ts:1776-1783` | `serveStaleness()` | 自动 `restartMw()` / 启动横幅提示 `/mw restart` |
| Python `mw update-env` A3 | `mw.py:5362-5390` | `started_at_ms`（回退 `serve.meta`/`mw.pid` mtime，`:5374-5379`） | anchor `serve` = ok/stale/info + `auto=True` 修法 |
| Python `mw doctor` | `mw_common.doctor_report()`（sections 列表） | **不读 serve.meta** | 无 serve 陈旧检查（只有 machine 层 `bundle`） |
| Python `mw status` | `mw.py:486-504` | **不读 serve.meta** | 只报 serve PID + conductor PID/水位 |

### 1.3 `mw_common` 里的 meta/心跳读写函数（结论：**没有 serve.meta helper**）

| 函数 | 落点 | 职责 |
|---|---|---|
| `pid_file(project_dir)` | `mw_common.py:2180-2181` | `<project>/.mw/mw.pid` |
| `check_pid(pid_path)` | `mw_common.py:2214+` | 读 PID + 存活（`_is_alive` `:2204`，win32 `:2184`） |
| `launcher_beat_write(project_dir, pid)` | `mw_common.py:2477-2481` | 覆写 `.mw/launcher-beat.<pid>`，单行 `ts=<iso UTC>`；调用点 `launcher.py:1717`（每 poll 第一件事） |
| `other_live_launcher(project_dir, self_pid)` | `mw_common.py:2485-2530` | 读全部 `launcher-beat.*`，`_BEAT_FRESH_SEC = 30`（`:2472`）+ pid 存活 ⇒ "另有活 launcher，本进程让路"；过期且 pid 死 ⇒ 顺手 unlink |
| `_parse_heartbeat_ts(hb)` | `mw_common.py:2369-2378` | 解析 TS 侧写的时间戳（含 `Z` 后缀归一） |
| `_last_heartbeat(task_dir)` / `worker_liveness(...)` | `mw_common.py:2381-2430` | worker 级存活裁决 `alive/stale/no-heartbeat`（worker 的 `[HEARTBEAT]` 行，非 serve） |
| `window_model_path` / 读 window-model | `mw_common.py:220-283` | `.mw/window-model`（非 worker 窗口上报的模型名）；消费点 `launcher.py:155` 的模型优先级链 |
| — | — | **serve.meta 的任何读/写/校验都不在 mw_common**；它只活在 `mw.py` 里，TS 侧各写一份镜像解析。⇒ AC-005 若要加字段，最省的落点是 `mw.py`（若要与 doctor/launcher 共享，才需要提升到 `mw_common`）。 |

### 1.4 `.mw/` 各文件角色（含本次实测的存在性）

| 文件 | 角色 | 写入者（落点） | 生命周期 |
|---|---|---|---|
| `mw.pid` | serve PID | `mw.py:96-102` → `:271` | 与 serve 进程同生共死（`:397`） |
| `serve.meta` | serve 启动戳 `{pid,started_at_ms,code_dir}` | `mw.py:122-131` → `:273` | 同上（`:398`） |
| `mw.stop` | 优雅停请求哨兵（文件即信号） | `mw.py:104-108`；TS `mw-runner.ts:331` 写、`mw.py:359-362` 消费 | 极短 |
| `mw.log` | serve 自身 stdout/stderr（**append**，跨会话累积） | `mw.py:223`（serve 内 `sys.stdout/stderr` 重定向） | 跨会话 |
| `proxy.log` | proxy 子进程日志（**append**） | `mw.py:224` | 跨会话 |
| `launcher.log` | launcher 子进程日志（**每 serve 会话 truncate**） | `mw.py:228`（注释说明：truncate 是为了不残留上一会话的 FATAL 假报） | 每会话 |
| `conductor.log` | conductor 子进程日志（**每 serve 会话 truncate**，会话内 respawn 共享句柄 ⇒ append） | `mw.py:231`；conductor 的 stderr 落在 `conductor.py:2589` 注释 | 每会话 |
| `conductor.pid` | conductor PID | `conductor.py:7228-7230`（**无 started_at / 无版本**） | 与 conductor 进程同生共死 |
| `launcher-beat.<pid>` | launcher 存活心跳（每个 launcher 一个文件，覆写式） | `mw_common.py:2477-2481` ← `launcher.py:1717` | 30 s 新鲜度；pid 死后被顺手清理，实测仍会残留多代（见 §5.3） |
| `workers.lock` | `_workers.parallel` 文件锁 | `mw_common.py:1731-1732` `lock_path()` | 短 |
| `window-model` | 最近一次非 worker pi 窗口的模型名 | `mw_common.py:220-283` | 跨会话 |
| `dispatch.yml` | 按 role 的模型映射 | 人工/`mw dispatch` | 跨会话 |
| `serve-console.log` | **孤儿**：实测 0 字节，当前树里零 writer（`grep 'serve-console'` 只命中 `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-capacity-constraints-20260926.md:131` 一处旧文档） | — | 历史遗留；AC-005 不得把它当成可用通道 |

### 1.5 真实片段（原样）

E2Feature（`H:\git\E2Feature\.mw\serve.meta`，mtime `2026-10-12 22:06:14 +08:00`）：

```json
{"pid": 140964, "started_at_ms": 1791813974011, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}
```

```
# H:\git\E2Feature\.mw\mw.pid            -> 140964
# H:\git\E2Feature\.mw\conductor.pid      -> 116216      (mtime 2026-10-12T14:06:14.539Z)
# H:\git\E2Feature\.mw\launcher-beat.88924 -> ts=2026-10-13T03:41:59+00:00
# H:\git\E2Feature\.mw\window-model       -> timi/deepseek-v4.1-flash
```

本仓（`H:\git\Multi-Workers\.mw\serve.meta`，当前活 serve）：

```json
{"pid": 168160, "started_at_ms": 1791860276020, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}
```

`mw.log`（serve 启动行**不含任何版本/commit**）：

```
[mw serve] route timi: available (file ~/.pi/agent/auth.json)
[mw serve] started (PID 168160) — proxy=disabled launcher=52140
```

`conductor.log`（既有 fail-loud 通道的真实输出形态，本 key AC-003/AC-006 的可复用形状）：

```
[conductor] gate reminders: roadmap unavailable, stage-terminal suppression disabled this tick: line 87 (stage 5): keys table row must have 3 columns ...
```

---

## §2 serve/conductor 启动时能拿到什么版本信息 + 最小可靠 commit 采集

### 2.1 现成可得

| 候选 | 落点 | 可得性 | 今天是否落盘 |
|---|---|---|---|
| git commit | `mw.py:5187 _git_head_short(repo)` → `git rev-parse --short HEAD`；`_git()` `:4097` | 有 git 时才可得；**无 timeout** | ❌ |
| worktree dirty | `mw.py:5175 _git_dirty(repo)` → `git status --porcelain` 计数 | 同上 | ❌ |
| 框架版本号 | `mw.py:4354 _framework_version()`（读 `packages/coding-agent/package.json` → `0.83.0`）；`launcher.py:953` 独立副本 | 纯文件读，最可靠 | ❌（只进 bundle 的 `MW_VERSION` env，`mw.py:4394`，与 `ENVELOPE_PRODUCER_BASELINE_SEMVER`，`launcher.py:963`） |
| bundle 哈希 | — | Python 侧**不存在**；TS bundle 侧有内容锚点前例：`mw_common.repo_bundle_anchor()`（GATE_KINDS + guard 标记）、`mw_common.sourcemap_drift()`（`sourcesContent` 比对） | ❌ |
| `.agentic-framework` 的 `commit=` | `mw.py:5218 _read_framework_manifest()` | 纯文件读，实测 `H:\git\E2Feature\.agentic-framework`：`framework=AgenticTask / repo=H:\git\Multi-Workers\.agents\skills\agentic-task / commit=d7004d0` | ✅ 但**是 AgenticTask 仓的 commit，不是 Multi-Workers 仓**；不可直接复用为 serve 身份 |
| 进程身份 | `pid`（serve.meta）、`conductor.pid` | 有 | ✅（但与代码无关） |
| envelope producer | `launcher.py:963` + 分派卡的 `agent-team-loop-pm@0.83.0` | 版本号，非 commit | 卡片里 |

> **`vcs:` 不是这个**：`mw.py:569/:637/:2750` 的 `vcs` 是 *target 项目* 的版本控制元信息（`git|p4|none`，用于 UE 双仓/分区），与 mw 自身代码身份无关，不要误用。

### 2.2 `code_dir` 指向什么，意味着什么

- 指向 **mw.py 所在的源码包目录**（`mw.py:46` = `packages/multi-workers`），不是安装副本、不是项目目录。Python 侧没有 "installed copy vs checkout" 二元性（与 TS 的全球 bundle 不同）。
- 因此 `serve.meta.code_dir` 天然是 **"该 serve 是从哪棵 checkout/worktree 启动的"** 的权威答复——但今天**没有读者**（§1.2）。
- 后果：多 worktree / `MW_PY` 覆盖 / 全局 `.mw-py-path` sidecar（本机实测 `C:\Users\wenbozhou\.pi\agent\extensions\.mw-py-path` = `H:\git\Multi-Workers\packages\multi-workers\mw.py`）下，"检查者看到的代码树"与"serve 当年启动的代码树"可以不同，而**没有任何一处会发现这个不一致**。

### 2.3 今天机器上并存的三个"代码树"概念

| 概念 | 落点 | 今天的值 |
|---|---|---|
| 运行中的 serve 用它 | `serve.meta.code_dir` | `H:\git\Multi-Workers\packages\multi-workers` |
| TS 检查者用它当基线 | `findMwPy()`（`mw-runner.ts:29-55`）→ 全局 sidecar | 同上（**巧合一致**） |
| Python `update-env` 检查者用它 | `_SCRIPT_DIR`（`mw.py:46`），测试里靠 monkeypatch 换（`test_update_env.py:203`） | 同上 |

⇒ **AC-005 必须把三者收敛到 `serve.meta.code_dir`**（读 meta 而不是读自己），并在 meta 里补 `commit/dirty/code_mtime_ms`，让"判据的输入"也变成落盘的事实。

### 2.4 最小可靠 commit 采集方式（Windows / dirty / 多 worktree）

推荐（**启动一次，不每 tick**）：

```
serve 启动时（mw.py:122-131 内）：
  commit        = _git_head_short(_SCRIPT_DIR)            # mw.py:5187，已有
  dirty         = _git_dirty(_SCRIPT_DIR)[0] > 0          # mw.py:5175，已有
  version       = _framework_version()                    # mw.py:4354，已有
  code_mtime_ms = int(_mw_code_newest_mtime() * 1000)     # mw.py:5131，已有（把基线固化）
```

必须同时做的加固（否则新字段会引入新的挂死面）：

- `_git()`（`mw.py:4097`）今天 `subprocess.run(cmd, capture_output=True, text=True)`：**无 `timeout=`**（git 缺凭证/慢盘/杀软扫描时可挂住 serve 启动）、无 `creationflags=CREATE_NO_WINDOW`（win32 上从无控制台的 serve 里 spawn 会闪窗；serve 自身对子进程是刻意加了这个 flag 的，`mw.py:277-278`）。⇒ 采集必须包 `timeout=5` + `except (OSError, subprocess.SubprocessError) → None`。
- git 缺失（Windows 无 git bash / PATH 无 git）：`subprocess.run(["git", ...])` 抛 `FileNotFoundError` ⇒ **必须有 None 降级**，且读端把 "commit 缺失" 视为 "不可判"，退回 mtime 判据（**不得因缺字段告警**，与 `config.py` 的 `DEFAULT_CONFIG` fail-open 传统一致）。
- 多 worktree：`git -C <code_dir> rev-parse` 给的是**该 worktree 的 HEAD**（正确语义）；另有 `.git` 是文件（`gitdir: ...`）的情形。
- dirty worktree：`commit` 不变 ≠ 代码不变 ⇒ **必须同时记 `dirty` 与 `code_mtime_ms`**，否则开发机（本仓今天就是 dirty：`git status --porcelain` 有 5 个改动 + 未跟踪目录）永远判 fresh。
- **纯文件读方案（不依赖 git 二进制）**：`<code_dir>/.git` 为目录 → 读 `.git/HEAD`；若 `ref: refs/heads/X` → 读 `.git/refs/heads/X`（本机实测存在，`cc9a46a1a...`）；否则在 `.git/packed-refs` 里找 `refs/heads/X`（本机 packed-refs 亦有）；`.git` 为文件 → 跟随 `gitdir:`。**代价**：还需处理逐级目录 ref、`HEAD` 直接是 40-hex（detached）。⇒ **建议只在"比对时"用纯文件读/stat，启动时用一次 `git`**；两者都返回 None 时 fail-open。

### 2.5 为什么不能只用 commit（AC-005 判据形态）

| 场景 | commit 变？ | mtime 变？ | 只有 commit | 只有 mtime |
|---|---|---|---|---|
| 别人 push 后你 `git pull` | ✅ | ✅（checkout 重写文件） | 抓到 | 抓到 |
| 开发机原地改 `mw.py` 不提交 | ❌ | ✅ | **漏** | 抓到 |
| `git checkout` 切分支后 mtime 反而变旧 | ✅ | 可能 ❌ | 抓到 | **漏** |
| 多 worktree 各跑一个 serve | 各树 HEAD 不同 | 各树 mtime 不同 | 需按 `code_dir` 分树 | 同 |
| 无 git（无 git bash） | 不可得 | ✅ | 不可判 → 必须 fail-open 退回 mtime | 抓到 |

⇒ **`commit`（强、可精确报期望/实际、去重键稳定）+ `code_mtime_ms`/`started_at_ms`（弱、兜 dirty 与无 git）并列为判据**，与 AC-005 文案"告警含期望/实际 commit + 修法"完全兼容：commit 可得时给二元组，不可得时给 mtime 对 + `commit=(unavailable)`。

---

## §3 TS stale-serve 判据 vs Python 侧等价物

### 3.1 TS 判据（逐字）

- `mwCodeNewestMtimeMs(mwPyOverride?)`（`mw-runner.ts:224-256`）：从 `findMwPy()`（或 override）目录**递归**取最新 `*.py|*.json` mtime（ms）；跳过目录名 `__pycache__|dist|.tmp`、文件名前缀 `test_|_`；`newest>0` 才返回。
- `serveStaleness(projectDir, codeMtimeMs?)`（`:272-289`）：`startedAtMs = readServeMeta()?.startedAtMs ?? fs.statSync(mw.pid).mtimeMs`（无 meta 且无 pid ⇒ `undefined` 不可判定）；`stale = codeMs > startedAtMs + 2000`（**2 s 松弛**：FS 时间戳粒度 vs 挂钟戳）；`detail = "serve started <ISO>, mw code changed <ISO>"`。
- **判据是 mtime，不是哈希、不是 commit**。源码注释明确这是有意选择（`:266-271`：false positive 的代价只是一次重启提示，且状态全在文件里，重启安全）。

### 3.2 Python 侧等价物：**唯一一处 = `mw update-env` A3**

`mw.py:5362-5389`：

```
started_ms  <- serve.meta.started_at_ms  (缺失则回退 serve.meta / mw.pid 的 mtime，:5374-5379)
code_mtime  <- _mw_code_newest_mtime()   (:5131 -> :5120-5149, 与 TS 同 skip 集 _UPDATE_ENV_SKIP_DIRS = ("__pycache__","dist",".tmp")，:5112)
stale iff code_mtime*1000 > started_ms + 2000
```

差异（逐条）：**同判据、同 2 s 松弛、同 skip 集**；差别在**触发方式**——A3 只在人敲 `mw update-env`（或 `/mw update-env`，`ui-bridge.ts:3394-3404`）时算一次，输出是 anchor 表里的一行 `status=stale/ok + auto=True`；**没有 tick、没有 stderr 告警、没有 timeline 事件、没有限频**。`mw doctor` 与 `mw status` 均无此项（§1.2）。

### 3.3 判据对照表

| 维度 | TS（`serveStaleness`） | Python（update-env A3） | Python（conductor tick） |
|---|---|---|---|
| 判据 | mtime > start+2s | mtime > start+2s | **不存在** |
| 基线树 | `findMwPy()`（**可能是别的树**） | `_SCRIPT_DIR`（**检查者自己**） | — |
| 触发 | 面板 4 s 轮询 / `/mw status` / enable / 启动横幅 | 人工敲命令 | — |
| 通道 | TUI notify + 面板行 | `mw.log` 里的 anchor 表 | — |
| 去重 | 无（每次调用/每次面板刷新都算；只有 enable 路径会真重启） | 无（一次性命令） | — |
| 覆盖"进程活着跑旧代码" | 面板开着时能看见 | 人敲时能看见 | **完全不可见** |

### 3.4 两者并存时如何避免双重告警（RQ-3 明确要求）

分工，而不是互相消音：

1. **Python conductor tick = 权威持久记录 + 生命周期级限频**：`stderr`（→ `.mw/conductor.log`，`mw.py:231`）+ timeline `config` 事件（唯一"可被 `/autopilot timeline` 回放、可被 PM 侧消费者看见"的通道，形状抄 `conductor.py:2603-2620`）。同一 `(code_dir, meta_commit, head_commit, serve_pid)` **只在 serve 生命周期内说一次**。
2. **TS = 交互恢复，不新增周期告警**：现有 4 个消费点语义保持不变；**不要**在 monitor 的 4 s 轮询里增发 notify（那会变成刷屏），面板行本身的 STALE CODE 常驻即是"状态面"，与 AC-001 的"状态面优先"同构。
3. **禁止互相触发**：Python 侧漂移告警**不得**执行 `/mw restart` 或重启自身（会与 `console.ts:627-632` 的 TS 自动重启互踩；且重启会清掉刚写下的 `conductor.log`，`mw.py:231` truncate）。
4. **一致化的最小交集**：让 TS 的 `readServeMeta` 也读 `commit`，`serveStaleness` 在 commit 可比时优先用 commit（mtime 作兜底），文案统一为 `期望 <meta_commit> / 实际 <head_commit>`；这样两侧不会因为"判据不同"给出互相矛盾的结论（今天已经发生过，见 §5.2）。

### 3.5 现判据的结构性缺陷（本卡实证，供 spec 引用）

- **缺陷 A：结论的时刻相关性被散文缓存**。`mw update-env` 在 `2026-10-12 14:11Z` 判 `serve=ok`（当时确实 fresh），41 分钟后即失效，而那条 verdict 以"`启动横幅那条 /mw restart 是过期信息，无需重启`"的形式固化进了 `AUTOPILOT-HANDOFF.md:454`，13 小时后成为**误导**（现场实测已 stale 12h20m）。⇒ 结论必须可随时**重算**（读 `serve.meta` 的 commit/mtime 即可复算），而不是靠人重跑命令。
- **缺陷 B：判据输入不落盘**。`serve.meta` 只有 start 时间与目录 ⇒ 每个观察者各自用**自己的**树重算基线（`findMwPy()` vs `_SCRIPT_DIR`），存在静默分歧面（§2.3）。
- **缺陷 C：`conductor.log` 每 serve 会话被 truncate（`mw.py:231`），timeline 只有 200 条尾窗（D-006 ≈20 分钟）**。⇒ 漂移告警"写过"不等于"还在"。**唯一可长期复算的载体就是 `serve.meta` 自身**——这正是 AC-005 要补 commit 的根本理由（与 P-02"状态面优先于事件面"一致）。

---

## §4 AC-005 最小改动面清单

### 4.1 改动面

| # | 类别 | 文件:落点 | 具体改动 | 是否被 P-04（要重启 serve 才生效）限制 |
|---|---|---|---|---|
| W1 | 写入点 | `packages/multi-workers/mw.py:122-131`（`_write_serve_meta`） | 追加 `commit`（`_git_head_short(_SCRIPT_DIR)`）、`commit_dirty`（`_git_dirty(...)[0]>0`）、`version`（`_framework_version()`）、`code_mtime_ms`（`_mw_code_newest_mtime()`）、`schema: 1`；保留既有 3 字段 | **是**：已运行的 serve 永远不会写新字段 |
| W2 | 写入加固 | `mw.py:4097` `_git()` 或 W1 内的局部调用 | 加 `timeout=5` + win32 `creationflags=CREATE_NO_WINDOW` + `except (OSError, subprocess.SubprocessError)` ⇒ None | 是（随 W1） |
| W3 | 写入原子性 | `mw.py:128-131` | `p.write_text(tmp)` + `os.replace(tmp, p)`（消除半截 JSON 竞态） | 是（随 W1） |
| W4 | 共享读 helper | `mw_common.py`（挨着 `pid_file` `:2180`） | `read_serve_meta(project_dir) -> dict`（容忍缺失/半截 JSON ⇒ `{}`）；可选 `resolve_head_commit(code_dir) -> str \| None`（纯文件读 `.git/HEAD`→loose→`packed-refs`→`gitdir:`） | 否（新函数立刻可用，但只有新进程会调用） |
| W5 | 比对点 P1（权威/tick） | `conductor.py:2880-2890`（`tick` 内，`:2887` beat 之后、`:2890` `enabled` 早退之前） | 新增 `_check_code_drift(project_root, st)`：读 `serve.meta` → 60 s 最小重检间隔（模块常量 `_CODE_DRIFT_CHECK_SEC = 60`）→ `meta.commit != resolve_head_commit(code_dir)` 或 `_mw_code_newest_mtime(code_dir)*1000 > started_at_ms+2000` ⇒ 漂移；`meta` 缺失/commit 不可判 ⇒ 静默（fail-open）；整体包在 `tick` 的 try 内（tick 永不抛，`:2883`） | **是**：旧 conductor 进程无此代码；首次上线必须 `/mw restart` |
| W6 | 告警点 | `conductor.py`（新增 `_emit_code_drift`，形状抄 `:2603-2620` `_emit_roadmap_failure`） | `print(f"[conductor] serve code drift: ...", file=sys.stderr, flush=True)` + `st.timeline.append("config", detail=...)`；文案固定含 `code_dir`、`期望 commit=<meta> / 实际 commit=<head>`（不可得时 `commit=(unavailable)`）、`mw code mtime vs serve start`、`fix: /mw restart` | 是（随 W5） |
| W7 | 限频键 | `conductor.py` 模块级（挨着 `:2594 _ROADMAP_ALARM_SEEN`） | `_CODE_DRIFT_SEEN: set[tuple[str,str,str,int]]`，键 `(code_dir, meta_commit, head_commit, serve_pid)` ⇒ "同一漂移每 serve 生命周期一次"；**不**合并进 `_ROADMAP_ALARM_SEEN`（键型不同、语义不同） | 是（随 W5） |
| W8 | 比对点 P2（新鲜进程，不受 serve 重启限制） | `mw.py:5362-5389`（A3） | detail 里补 `期望/实际 commit`；判据改为 `commit 不等 ⇒ stale`，`commit 不可比 ⇒ 退回现有 mtime 判据` | **否**（下次调用即生效） |
| W9 | 比对点 P2' | `mw.py:486-504`（`cmd_status`） | 加一行 `[mw status] serve: code <fresh|STALE (expected <c1>, actual <c2>)>` | **否** |
| W10 | 比对点 P2''（TS，不受 serve 重启限制） | `shared/mw-runner.ts:198-201 / 207-216 / 272-289` | `MwServeMeta` 增 `commit?: string`；`serveStaleness` 增 commit 分支（mtime 兜底），`detail` 含期望/实际 commit；**基线树改用 `readServeMeta()?.code_dir ?? findMwPy()`** | **否**（`/reload` 或新窗口即生效） |
| W11 | 面板可见性（可选，最小化） | `autopilot/monitor.ts:340-355 / 782-789` | 若希望面板直接显示 commit 对，则 `MonitorServe` 加字段；**不新增轮询、不新增 notify** | 否 |
| W12 | 文档 | `UPDATE.md:40`（A3 行） + `packages/multi-workers/CHANGELOG.md` | A3 行改为"`serve.meta` 含 commit；commit 漂移即 stale"；CHANGELOG 走 `[Unreleased]/Fixed` | 否 |
| — | **明确不做** | `autopilot/config.py` / `status-model.ts` / `autopilot-config-parity.test.ts` | **不新增 config 键**（20 键冻结 schema + TS 双镜像 + parity 测试的连带面）⇒ 重检间隔用模块常量，不用配置项。若 spec 坚持要可调，需在 AC-010 里同时改 `config.py`（`DEFAULT_CONFIG`/`_INT_RANGES`）与 `status-model.ts` 镜像表 | — |

**改动规模**：Python 2 文件（`mw.py` + `conductor.py`，可选 `mw_common.py` 加 2 个共享读函数）、TS 1-2 文件（`mw-runner.ts` 必需，`monitor.ts` 可选）；**无新文件、无新通道、无新 config 键**（满足 P-01 / AC-006）。

### 4.2 「各项目重启 serve 才生效」对每条改动的影响（P-04 标注）

| 生效时机 | 涉及改动 | 后果 |
|---|---|---|
| **必须 `/mw restart`（serve 重启）** | W1/W2/W3（新字段得等新 serve 写 meta）、W5/W6/W7（新 tick 检查得等新 conductor 起） | 老 serve 的 meta 永远缺 commit；老 conductor 永远不报漂移。⇒ **AC-005 的验收测试必须显式覆盖"meta 缺 commit 的存量现场"**：判据 fail-open（退回 mtime），不得报错、不得静默 |
| 立即（新进程即生效） | W4/W8/W9（`mw status`、`mw update-env` 都是新进程）、W10/W11（TS 侧 `/reload` 或新窗口） | 这是**首次上线后到第一次 `/mw restart` 之前**唯一能发现漂移的通道 ⇒ AC-005 的实现不应把检测只放在 conductor 里 |
| 需要 `build --install` + `/reload`（TS） | W10/W11 | 与既有 stale-serve 修复的部署路径一致（`UPDATE.md:40` 已写明） |
| **serve 自身不可自证** | 全部 | 跑旧代码的 serve 既不会写新字段、也不会自检 ⇒ **AC-005 的"每次比对"必须至少有一个新鲜进程侧入口**（TS 扩展 / `mw status` / `mw update-env`）。这一点建议写进 spec 的 P-04 与 AC-005 判据文字 |

### 4.3 要改的测试文件（AC-005 落地时）

| 侧 | 文件 | 改什么 |
|---|---|---|
| Python | `packages/multi-workers/test_serve_meta.py:21-31`（`test_write_serve_meta_shape`） | 断言新字段（commit/dirty/version/code_mtime_ms/schema）+ `code_dir` 语义不变 |
| Python | `packages/multi-workers/test_serve_meta.py`（新增用例） | 无 git 目录 ⇒ commit=null 且不抛（fail-open） |
| Python | `packages/multi-workers/test_update_env.py:77-79 / :287-294 / :374-389 / :440-460` | A3 fixture 加 commit；healthy/stale world 与 anchor 顺序/auto 集合断言同步 |
| Python | **新增** `packages/multi-workers/test_autopilot_serve_drift.py`（或并入 `test_autopilot_conductor.py`） | 纯判据表驱动：commit 不等 ⇒ 告警一次；相等 ⇒ 无告警；meta 缺 commit ⇒ 无告警且退回 mtime；mtime 漂移 ⇒ 告警；同 tick 重复调用 ⇒ 只 1 条（capsys stderr 1 行 + timeline `config` 1 事件） |
| Python | `packages/multi-workers/test_mwds_t25_version_semantics.py:234-273` | 若 `serve.meta.version` 走 `_framework_version()`，补一条"单源不变"断言 |
| TS | `packages/coding-agent/test/extensions/agent-team-loop.test.ts:958-1025` | `readServeMeta` 增 commit 解析；`serveStaleness` commit 优先 + mtime 兜底 + `code_dir` 优先于 `findMwPy()` |
| TS | `packages/coding-agent/test/suite/autopilot-monitor.test.ts:737-770` | `staleDetail` 文案若含 commit 对，更新期望串（`serve: PID 7 STALE CODE (...) -> /mw restart` 形态保持） |
| TS | `packages/coding-agent/test/suite/dual-root-worker.test.ts:228-250`（VC-016） | 补"`serve.meta.code_dir` ≠ `findMwPy()` 时以 `code_dir` 为准"的反例回归 |
| TS | `packages/coding-agent/test/suite/autopilot-console.test.ts:1291-1310` | enable ⇒ stale serve restarted 通知文案若变则同步 |

> 说明：本 RQ 未运行任何测试（只读卡）。上表的文件与行号来自通读测试源码，落地时以 design 阶段的实际改法为准。

---

## §5 真实证据（E2Feature 现场 + 本仓对照）

### 5.1 现场实测（命令与输出，2026-10-13T03:43Z 采集）

```
$ python -c "... 复算 _mw_code_newest_mtime 与 serve.started_at_ms 比对 ..."
serve.started_at_ms -> 2026-10-12T14:06:14.011000+00:00
STALE-DELTA    44389s 2026-10-13T02:26:03Z mw.py          <-- 最新 runtime 源
STALE-DELTA    44379s 2026-10-13T02:25:53Z launcher.py
STALE-DELTA    10454s 2026-10-12T17:00:27Z autopilot\roadmap.py
STALE-DELTA    10439s 2026-10-12T17:00:13Z autopilot\conductor.py
STALE-DELTA     2474s 2026-10-12T14:47:27Z autopilot\dispatch.py
STALE-DELTA     1780s 2026-10-12T14:35:54Z autopilot\config.py
STALE-DELTA     -665s 2026-10-12T13:55:08Z autopilot\card_audit.py   <-- 启动前最后一个改动
stale? True
```

⇒ **E2Feature 的 Py 侧此刻就在"进程活着 + 跑 12h20m 前的代码"，而 `.mw/serve.meta` 对此零信息**（无 commit）。这就是本 key 上游事故（2 天零派发）的静态指纹：**故障不需要崩溃，只需要没人重启。**

对照：本仓自己的 serve PID 168160 起于 `2026-10-13T02:57:56Z` > `mw.py` mtime `02:26:03Z` ⇒ fresh（说明同一判据在真数据上两侧都能过）。

### 5.2 「verdict 会过期」的逐分钟实证（`AUTOPILOT-HANDOFF.md`）

同一 serve（PID 140964）上，四个时刻四种真相：

| 时刻（Z） | 依据 | 判定 | 来源 |
|---|---|---|---|
| 2026-10-12 14:11 | 最新 runtime mtime = 13:55:08Z（**早于** serve 启动 14:06:14Z） | **fresh（正确）** | `AUTOPILOT-HANDOFF.md:454`：`mw update-env` 实测 `serve = ok（PID 140964，代码新鲜）`，并注明"启动横幅那条 `/mw restart` 是**过期信息，无需重启**" |
| 2026-10-12 14:35:54 | `autopilot/config.py` 被改（+29m40s） | 静默转 stale | 本卡 5.1 实测 mtime |
| 2026-10-12 14:47:27 | `autopilot/dispatch.py` 被改（+41m13s） | 仍 stale，仍无告警 | 同上 |
| 2026-10-13 03:43 | `mw.py`/`launcher.py` 被改（+12h20m） | **stale，唯一的"发现"是本 RQ** | 本卡 5.1 实测 |

同文档更早的同题实证（`AUTOPILOT-HANDOFF.md:356/:361/:392-393`）：`serve PID 102084 起于 2026-09-23T00:01:28，而 coding-agent dist 于 15:22:55 重建` ⇒ 当时只能以"**重启窗口后必须 `/mw restart`**"这种人工备注收场。

### 5.3 其它实测事实

- 本仓 `git status --porcelain` 有 5 个改动 + 未跟踪 `.agenticdoc/*` ⇒ **开发机常态 dirty** ⇒ 只记 commit 会漏（§2.5）。
- 本机 git 可用：`git version 2.53.0.windows.1`；`HEAD = ref: refs/heads/dev/AgentTeam`，loose ref `.git/refs/heads/dev/AgentTeam` 存在，`packed-refs` 也有 ⇒ 纯文件读方案两条路径在本机都成立。
- `.mw/launcher-beat.<pid>` 会残留多代死 launcher（本仓 `.mw/` 下 20+ 个，最老 `2026-09-11`；E2Feature 15 个）⇒ "`.mw/` 的文件名 = 身份"这套约定**没有自动回收**，AC-005 若依赖新文件名要自己收敛（本卡建议不新增文件）。
- 两仓现存 `serve-console.log` 均 0 字节且无 writer ⇒ 不是可用通道。
- 本机全局侧车 `C:\Users\wenbozhou\.pi\agent\extensions\.mw-py-path` = `H:\git\Multi-Workers\packages\multi-workers\mw.py`（与两仓 `serve.meta.code_dir` 相同，属巧合）；全局 bundle mtime `2026-10-13T02:35:35Z`。

---

## §6 上下文来源清单

| 来源 | 用途 |
|---|---|
| `packages/multi-workers/mw.py:5/:46/:49/:96-137/:204-231/:271-273/:352-398/:486-504/:4097/:5112/:5120-5149/:5175/:5187/:5218/:5362-5390` | serve 生命周期、serve.meta 写读删、`_git*`、update-env A3 |
| `packages/multi-workers/mw_common.py:220-283/:1716-1732/:2180-2226/:2369-2430/:2471-2530` + `doctor_report` | pid/beat/heartbeat/window-model、doctor 无 serve 检查 |
| `packages/multi-workers/launcher.py:155/:953-963/:1717` | window-model 消费、`_framework_version`、launcher beat 调用点 |
| `packages/multi-workers/autopilot/conductor.py:84/:183/:2594-2660/:2683-2735/:2880-2890/:7216-7250` | conductor pid/状态、alarm 双通道封装、tick 插入点 |
| `packages/multi-workers/autopilot/config.py:1-135`（20 键冻结 schema + `_INT_RANGES`） | 为什么不新增 config 键 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:29-55/:195-345` | TS stale-serve 判据 + restart 序列 + `findMwPy` |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/{monitor.ts:65,81-87,340-355,782-789},console.ts:43,611-633}` | 面板 STALE CODE 行、4 s 轮询、enable 自动重启 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/{ui-bridge.ts:3394-3419},pm-orchestrator.ts:1776-1783}` | `/mw status`、`/mw update-env`、启动横幅 |
| 测试：`test_serve_meta.py:21-79`、`test_update_env.py:77/:101-116/:287-294/:374-389/:440-460`、`test_mwds_t25_version_semantics.py:234-273`、`test/extensions/agent-team-loop.test.ts:958-1025`、`test/suite/autopilot-monitor.test.ts:737-770`、`test/suite/dual-root-worker.test.ts:228-250`、`test/suite/autopilot-console.test.ts:1291-1310` | 要改的测试面 |
| `UPDATE.md:21/:40/:138` | A3 更新锚点与部署路径（含 env 不落盘、须显式带 env 重启的 P-015 备注） |
| `H:\git\E2Feature\.mw\{serve.meta,mw.pid,conductor.pid,launcher-beat.88924,mw.log,conductor.log,window-model}` | 真实现场（§5.1） |
| `H:\git\E2Feature\.agentic-framework`（`commit=d7004d0`）、`H:\git\E2Feature\.agenticdoc\AUTOPILOT-HANDOFF.md:308/:356/:361/:392-393/:454` | commit 落盘前例 + verdict 过期实证 |
| `C:\Users\wenbozhou\.pi\agent\extensions\{agent-team-loop.js,.mw-py-path}` | TS 基线树与全局侧车实测 |
| 本卡、`spec.md` §1(E7)/§2(AC-005,AC-006,AC-010)/§3(P-01..P-06)/§4、`pm-state.md` | 需求与既有裁定 |

**本次使用的方法**：全仓只读（`read`/`grep`/`ls`/`git log`/`git status`/只读 Python 复算脚本），未运行任何写入型命令；`H:\git\E2Feature` 仅只读。

---

## §7 未覆盖面声明

1. **上游输入文件不可得**：`H:\git\E2Feature\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md`（`spec.md` §0 与 `spec-bootstrap-declaration-20261013.md` 引用的 P0×2/P1×2/P2 原文）在当前磁盘上**不存在**（已做递归 `*handoff*`、`*serve-drift*` 搜索与 `_autopilot/` 全目录列举）；本 RQ 改用 `AUTOPILOT-HANDOFF.md` 与 `.mw/` 现场取证。**P2 那条"独立文档项"的原文措辞未能核对**，其与 AC-005 自动化的对应关系只能按 `pm-state.md` 的转述理解。
2. **未验证进程级字节事实**：本 RQ 只能拿到"进程启动时刻 + 磁盘代码 mtime"，**没有** `140964` 这个 PID 内部实际加载的模块字节（没做 `sys.modules` 反查，也没取 `Get-Process` 的命令行快照），因此"它跑的是 12h20m 前的 mw.py"是**由 mtime 契约推出的**，不是直接的字节证据。若 spec 要求字节级自证，需要另一条路径（例如启动时记 `mw.py` 的 sha256）。
3. **未做多 worktree 复现**：`git worktree list` 本机只有一棵（`H:/git/Multi-Workers cc9a46a1a [dev/AgentTeam]`），"检查者树 ≠ 运行者树"的静默分歧面由代码路径与测试用法（`dual-root-worker.test.ts:239-245` 手工对齐）推出，**未构造过实际反例**。
4. **未评估 Windows 上 `git` 子进程的现实成本**：给了"每 tick 别 spawn git"的建议，但没有实测 `git rev-parse` 在杀软/Defender 下的 p50/p99 延迟，也没有实测 `CREATE_NO_WINDOW` 缺失时的弹窗行为（只确认了 serve 对子进程刻意加了该 flag，`mw.py:277-278`）。本卡建议的 60 s 重检间隔是工程判断，建议 design 阶段补一次实测。
5. **未覆盖 `mw build --install` / `pi-dist` 侧的代码漂移**：本 RQ 只处理 `serve.meta` 所代表的 **Python 侧**身份；TS bundle / coding-agent dist 的陈旧检测已在 `mw update-env` 的 A1/A1b/A2/A2b（`mw.py:5256-5311`）与 doctor bundle 段存在。**未评估** AC-005 的告警是否应把"Python 代码漂移"与"bundle 漂移"合并成一条（本卡倾向分开：判据、修法、重启成本都不同）。
6. **未定 spec 级取舍**：本卡给的是**最小改动面**，没有替 spec 决定 (a) 是否要做 gate 化/阻断、(b) 漂移是否应阻断 dispatch（本卡建议**不阻断**：老 conductor 的判断力可能仍然正确，阻断会把"部署漂移"升级成"停摆"，与 AC-011 的不回归原则相抵）、(c) 是否给 conductor 也写一份自己的 `commit`（本卡倾向**不写**新文件——conductor 的代码树 == serve 的代码树，`serve.meta` 一处即可）。
7. **未验证 `code_mtime_ms` 字段的跨平台语义**：`_mw_code_newest_mtime()` 用 `st_mtime`（浮点秒）；Windows FAT/exFAT 时间粒度与 NTFS 不同，2 s 松弛是否仍够用未实测（TS 侧注释把 2 s 解释为"FS 时间戳粒度 vs 挂钟戳"）。加 `code_mtime_ms` 后两侧单位必须一致（ms），属 design 阶段的接口约定。
