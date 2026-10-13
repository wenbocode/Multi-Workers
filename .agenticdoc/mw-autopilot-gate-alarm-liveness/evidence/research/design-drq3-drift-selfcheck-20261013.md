# DRQ-3 — 漂移自检设计：serve 身份字段 / 比对与告警 / 新鲜进程侧入口 / 边界反例

- Key: `mw-autopilot-gate-alarm-liveness`｜RQ: DRQ-3（执行卡 T-07）｜阶段: DESIGN｜日期: 2026-10-13｜只读取证
- 唯一证据文件: 本文件（`.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq3-drift-selfcheck-20261013.md`）
- 对应 AC: AC-005（身份字段 + 每 tick 比对 + 漂移告警含期望/实际 + 漂移时长 + 修法 + 新鲜进程侧入口 + 重启后复核 pending 门禁）、AC-006（复用 stderr + timeline `config`，与 TS 侧分工不重复）、AC-011（不新增 config 键）、AC-012（不回归）
- 上游原文（已核实存在）: `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md` P0-①（serve 漂移自检，含告警文案范例 `capability drift: serve started …, modules HEAD=ab546bb64 (+3 commits)`）与 P2（"合并新增守护的提交后必须重启长驻 serve，并在重启后复核 pending 门禁未被新自动裁决意外改写"）
- 种子: 同 key SPEC 阶段 RQ-3 证据（`spec-rq3-serve-metadata-drift-20261013.md`，40,704 B）。本卡**不复述**其全部结论，只做（a）设计决策、（b）增量实测、（c）与种子的差异声明
- 本卡实测的现场: `E:\CLI_workspace\FeatureMigrator`（serve PID 116368）+ `H:\git\Multi-Workers`（serve PID 168160），两份 `.mw/serve.meta` 均只有 `{pid, started_at_ms, code_dir}` 三字段

## 结论

- **C1（判据换轴：内容摘要是权威，commit 是命名，mtime 是时间戳）**。种子建议"`commit` + `dirty` + `code_mtime_ms` 三件事一起记"是对的，但**只靠 commit 与 mtime 都有确定性漏洞**：(a) mtime 看不见**删除/重命名**（删掉一个 runtime `.py`，剩余文件 mtime 不变、HEAD 不变 ⇒ 判 fresh，实为 drift）；(b) commit 看不见 dirty 内容，且**"把 dirty 文件提交掉"会让 HEAD 前进而字节零变化 ⇒ 假漂移**。因此新增第三个身份字段 `code_digest`（runtime 文件集的 sha256 内容摘要），作为**唯一权威判据**：内容变了才算"进程跑的代码不是磁盘上的代码"。实测代价极低：本仓 runtime 集 71 文件 / 1,305,650 B，摘要 7.6 ms（§5.6）。
- **C2（基线必须同域）**。今天 TS/Python 两侧都是"**wall-clock 启动戳** vs **FS mtime**"跨域比较，那 2 s 松弛就是为跨域准备的。把**启动时刻的 runtime 最新 mtime** `code_mtime_ms` 固化进 meta 后，判据变成 **FS mtime vs FS mtime**，同一时间域，既去掉时钟跳变类误判，也把"进程 import 之后、写 meta 之前"的窗口算准。旧 meta（无此字段）回退 `started_at_ms + 2000ms`，语义与今天一致。
- **C3（字段集固定为 6 个新增键，全部 fail-open）**：`schema`(int) / `commit`(full 40-hex | null) / `dirty_tracked`(int|null) / `dirty_untracked`(int|null) / `code_mtime_ms`(int|null) / `code_digest`("sha256:…"|null)，外加 `version`(str) 与 `written_at_ms`(int)。**任何字段缺失/为 null 一律降级为"该判据不可用"，永不因此告警**（沿 `config.py` 的 fail-open 传统）。
- **C4（写 commit 必须用 full OID，不能用 `_git_head_short`）**。实测同一棵树上 `git rev-parse --short HEAD` = `cc9a46a1a`（9 位，长度随对象库自动伸缩），而"纯文件读 `.git`"得到的是 40 位 OID；**两者字面永不相等 ⇒ 每 tick 假漂移**。种子原文（"复用 `_git_head_short`"）直接照做会踩这个坑。写入与比对统一用 full OID，显示时才截断。
- **C5（比对环节零 spawn 是可达的，且必须如此）**：`commit` / `code_digest` / `code_mtime_ms` 三者都能由纯文件读得到（`.git/HEAD` → `gitdir:` → loose ref → `packed-refs`，含 `commondir`），**比对时不需要 git 二进制**；只有启动期一次性取 `dirty` 需要 git，且必须 `timeout=3` + `CREATE_NO_WINDOW` + `None` 降级。
- **C6（git 挂死是启动楔子，不是性能问题）**。今天 `_git()`（`mw.py:4097`）无 `timeout`；而 `_write_pid`（`:271`）**在** `_write_serve_meta`（`:273`）**之前**。⇒ 若在新字段采集里 spawn 一个挂住的 git，`mw.pid` 已落盘而 launcher/conductor 永不 spawn：TS `waitForMwStart` 只查 PID 存活 ⇒ 误报"已启动"，`mw stop` 因 serve 卡在采集里读不到 `mw.stop` ⇒ 30 s 后失败。**采集必须整体前置到 `_write_pid` 之前**，保住"PID 文件存在 ⇒ 服务真的起来了"（`mw.py:245-246` 注释里的既有不变量）。
- **C7（比对时刻三层）**：(1) **启动**——不判漂移（自证无意义），只把身份写进 `serve.meta` 与 `mw.log` 一行（append、无轮转、跨会话留存，本仓实测 16,603 B / 32 条 serve 启动行）；(2) **每 tick**——conductor 每 60 s（模块常量 `_CODE_DRIFT_CHECK_SEC`，**不进 config 键**，AC-011）算一次，命中即双通道告警；(3) **按需**——至少 4 个不依赖该进程的入口（C9）。
- **C8（分类是四值而非二值，且必须"可见地不可判"）**：`fresh` / `drift(reason=content-changed|head-moved|schema-stale)` / `history-only`（HEAD 动了但 digest 相同 ⇒ **不告警**，只在状态面记一笔）/ `undecidable(reason=meta-missing|code-dir-missing|no-baseline|tree-unreadable|git-unavailable)`。**dirty 本身永远不是 drift**（AC-005"dirty 工作区不误报"），它只作为告警文案里的上下文与"为什么 commit 不可信"的解释。**唯一一处对 AC-005 字面的收窄**：`digest` 在场且相等时，`commit 不等`不告警（见 C1(b) 的假阳性），建议 design 阶段显式追认（§2.4 / §4.4）。
- **C9（"新鲜进程侧入口"给 4 个，且必须能在存量现场直接生效）**：关键是**旧 serve 写的 meta 虽无 `commit`/`code_digest`，但 `started_at_ms` 与 `code_dir` 从一开始就在**，所以"mtime 回退判据"今天就能判出真漂移——**不需要等任何一次 serve 重启**。四个入口：`mw status`（新增一行，退出码不变）、`mw doctor`（新增 `serve_code` section；`stale` ⇒ `issues` ⇒ exit 1，`undecidable` ⇒ `suggestions`）、`mw update-env` A3（升级为以 `meta.code_dir` 为基线 + commit 对）、TS `serveStaleness`/面板/`/mw status`（基线从 `findMwPy()` 改为 `meta.code_dir`）。外加一个**独立于 meta 的 OS 探针** `process_start_ms(pid)`（win32 ctypes `GetProcessTimes`，沿用 `mw_common._is_alive_win32` 的既有 ctypes 先例；POSIX 走 `/proc/<pid>/stat`），用来交叉核对 `meta.started_at_ms`，抓"meta 是上一次 serve 的残留 / PID 被复用"。
- **C10（"必须重启 serve"变成机器判据，而不是检查单）**：`meta.schema < EXPECTED_SCHEMA`（检查者自己代码里的模块常量）= "运行中的 serve 的写者不认识当前身份 schema ⇒ 它必然不含新守护" ⇒ capability drift 告警。存量 serve 的 meta 没有 `schema`，等价于 `schema=0 < 1`。这条把上游 P2 的"部署检查单"变成可机器判定的谓词；同时 `mw status` 常驻打印 `capability: stale (schema 0 < 1) -> /mw restart`。跨 worktree 时 `capability=unknown`（检查者无从知道另一棵树的代码内容），只报 `tree_verdict`。
- **C11（漂移时长 = now − 代码偏离的那一刻）**：内容判据命中 ⇒ `drift_age = now − mtime_now`（磁盘最后一次变更就是进程与磁盘分岔的时刻，即"我已经跑了多久的旧代码"）；只有 commit/schema 判据命中 ⇒ 分岔时刻落在 `[base, now]` 内不可知，报 `>= now − base` 并显式标注下界。同时报 `code_newer_by = mtime_now − base`（TS 现有 detail 的两时间戳对）与 `uptime = now − started_at_ms`。
- **C12（限频：内存 set 做快速预筛 + 时间线做跨 respawn 的持久去重，零新文件）**。键 = AC-005 指定的 `(code_dir, meta_commit, head_commit, serve_pid)`；第一层 `_CODE_DRIFT_SEEN`（模块级 set，同 `_ROADMAP_ALARM_SEEN` `conductor.py:2594` 先例）；**第二层复用 `_timeline_has_event`（`conductor.py:1899`）**——它在 `tail_events(limit=200)` 里按 `(ev, key, detail)` 查重，而时间线**跨 conductor respawn 与跨 serve 会话存活**，因此"同一漂移每 serve 生命周期一次"在 conductor 崩溃重启后依然成立，且**不新增任何去重文件**（种子倾向"不新增文件"，这里给出可落地的实现路径）。时间线轮转会淘汰该事件 ⇒ 允许重发一次（这本身是"记录已消失"的信号）。
- **C13（持久记录与事件记录都不是可依赖载体，唯一可复算载体是 meta 自身）**：本次现场实测，FeatureMigrator 的 3 代时间线合计只覆盖 **2026-09-30T01:40:47Z → 2026-10-13T04:13:12Z ≈ 12.8 天**，而本事故的漂移时长是 **16 天 23 小时 55 分**——**告警即便当年发过，也早已滚出保留窗口**；同时 `conductor.log` 每次 serve 会话 truncate（`mw.py:231`，现场读数 0 B）。⇒ 结论必须**可随时重算**，这正是"新鲜进程侧入口 + meta 里固化身份"的根本理由。
- **C14（重启后复核 pending 门禁：零新字段、零新文件，用既有三个事实）**。事后判据 = 对每个当前为终态、且 `created_at < T_restart` 的门禁：若 `answered_by` 以 `conductor-auto:` 开头（`conductor.py:6608` 的唯一写法）而 `answered_at > T_restart`，则"重启后新自动裁决改写了重启前的 pending 门禁"成立 ⇒ 一条 `config` 告警。`T_restart` 取新 serve 的 `serve.meta.started_at_ms`。三个输入（gate 文件、新 serve.meta、台账）全部既有，`gates.py` 的 `answer_source`/`auto_policy_id` 甚至无需启用。
- **C15（分工维持种子结论，但补一条硬约束）**：Python 拥有持久记录（stderr → `conductor.log` + timeline `config`）与 serve 生命周期限频；TS 只保留交互恢复（面板 STALE 行 / `/mw status` / `/autopilot enable` 自动重启），**不新增周期通知**；Python **不自动重启**（会与 `console.ts:621-632` 的 TS 自动重启互踩，且重启会 truncate 刚写下的 `conductor.log`）。补的硬约束：**比对基线必须取 `meta.code_dir`，不得取检查者自己的 `findMwPy()`/`_SCRIPT_DIR`**（`dual-root-worker.test.ts:239-245` 今天靠测试手工对齐；产品代码无此保证）。
- **C16（skip 集必须修一次，且要跨语言锁 parity）**。实测 `_mw_code_newest_mtime()`（`mw.py:5131`）今天扫到的 71 个文件里 **49 个（69%）在 `test/` 下**（`test/fixtures/**/case.json` 等）。改任何 fixture 都会把健康的 serve 判成 stale——在"告警进 stderr + timeline"之后，这不再是"多提示一次重启"的小噪音，而是持续假告警。⇒ 在 Python 的 `_UPDATE_ENV_SKIP_DIRS` 与 TS `mwCodeNewestMtimeMs` 的目录跳过集里**同时**加 `test` 路径分量，并由既有 parity 测试锁住（AC-006 要求两侧判据一致）。

## 证据

### §1 判据算法（纯函数，落地为 `mw_common.serve_code_verdict()`）

```
MTIME_SLACK_MS   = 2000            # 沿现有语义（FS 时间戳粒度）
EXPECTED_SCHEMA  = 1               # 模块常量：当前身份 schema；加守护时递增

serve_code_verdict(meta, checker_tree) -> verdict:
  tree = meta.code_dir or checker_tree          # 永远优先 meta 自己的树（C15）
  if meta is None:                  return undecidable("meta-missing")
  if not is_dir(tree) or not readable: return undecidable("code-dir-missing")
  base_ms = meta.code_mtime_ms or meta.started_at_ms
  if base_ms is None:               return undecidable("no-baseline")

  digest_now = runtime_digest(tree)              # 每次重检都算，~8ms（C1 / §5.6）
  mtime_now  = newest_runtime_mtime_ms(tree)
  commit_now = head_oid(tree)                    # 纯文件读；None = 不可用

  if meta.code_digest is not None:
      content_changed = digest_now != meta.code_digest   # 权威：覆盖增/改/删/改名
  else:
      content_changed = mtime_now is not None and mtime_now > base_ms + MTIME_SLACK_MS
  commit_moved = bool(meta.commit and commit_now and meta.commit != commit_now)

  if content_changed:
      return drift("content-changed", since=mtime_now or base_ms, lower_bound=(mtime_now is None))
  if commit_moved and meta.code_digest is None:
      return drift("head-moved", since=base_ms, lower_bound=True)     # 旧 meta：AC-005 字面
  capability = None if tree != checker_tree else ((meta.schema or 0) >= EXPECTED_SCHEMA)
  if capability is False:
      return drift("schema-stale", since=base_ms, lower_bound=True)
  if commit_moved:
      return history_only()                                           # digest 相同 ⇒ 字节没变
  if digest_now is None or mtime_now is None:
      return undecidable("tree-unreadable")
  return fresh(capability=capability)
```

要点与理由：
1. **判定次序**：内容 → commit（仅旧 meta）→ schema（capability）→ 无判据可用的 undecidable。内容优先保证"字节真变了"永远能报。
2. **`digest_now` 每次重检都算**，因为它是唯一能看见**删除/重命名**的判据；代价 7.6 ms / 60 s（§5.6）。若嫌 8 ms 仍重，可先跑 `newest_runtime_mtime` 预筛、**只在 mtime 命中时才**算 digest——代价是放弃"删除不可见"的兜底，不建议。
3. **`commit_moved and meta.code_digest is None`** 是 AC-005 单测"commit 不等 ⇒ 告警一次"的字面落点；当 digest 在场时它被降级为 `history_only`（不告警）——这是 C1(b) 的假阳性修复，**属于对 AC-005 字面的白名单式收窄，需 design 追认**（§5.4 给了反例与修正后的单测表）。
4. **`capability` 只在 `tree == checker_tree` 时有值**；跨 worktree 返回 `None`（unknown），避免检查者对另一棵树的内容做它没有依据的判断。
5. 所有分支**不抛异常**（`tree` 不可读、digest 失败、git 缺失都收敛到 undecidable），与 `tick()` "永不抛"（`conductor.py:2880-2883`）的契约一致。

### §2 `serve.meta` 身份字段设计

#### §2.1 目标 schema（`schema: 1`）

| 字段 | 类型 | 来源 | 缺失/为 null 语义 | 备注 |
|---|---|---|---|---|
| `schema` | int | 模块常量 `SERVE_META_SCHEMA = 1` | 视为 `0`（旧 writer） | **capability 判据**，不是产品版本号，只在"身份采集能力"变化时递增 |
| `pid` | int | `os.getpid()`（现有） | 旧读者必需 | 不变 |
| `started_at_ms` | int | `int(time.time()*1000)`（现有） | 不可判基线 | 不变；保留以兼容旧 TS 读者与 A3 |
| `code_dir` | str | `str(_SCRIPT_DIR)`（现有） | 回退检查者自己的树（降级 + 标注） | 现有但今天**零读者**；本设计把它变成比对基线的**唯一**来源（C15） |
| `commit` | str(40-hex) | 纯文件读 `.git/HEAD`（C4/C5）；失败时 `_git(["rev-parse","HEAD"])` 兜底 | `null` = 不可比 | **不用 `--short`** |
| `dirty_tracked` | int | `_git_dirty(code_dir)[0]`，`timeout=3` | `null` = 未知 | 见 §5.3 的 `_git_dirty` 吞错问题 |
| `dirty_untracked` | int | `_git_dirty(code_dir)[1]` | `null` = 未知 | 上下文，不参与判据 |
| `code_mtime_ms` | int | `int(_mw_code_newest_mtime(tree) * 1000)` | 回退 `started_at_ms` | **同域基线**（C2） |
| `code_digest` | str | `runtime_digest(tree)` = `"sha256:" + hex` | 回退 mtime 判据 | **权威判据**（C1） |
| `version` | str | `_framework_version()`（`mw.py:4354`，今 `0.83.0`） | `""` | 人读；**不参与判据**（版本号不随每次改动变化） |
| `written_at_ms` | int | `int(time.time()*1000)` | 无 | 区分"进程启动时刻"与"meta 落盘时刻" |

`runtime_digest` 的算法（必须跨进程、跨语言可复现）：

```
files = sorted(rel_posix(f) for f in rglob(tree) if is_runtime_file(f))
h = sha256()
for rel in files:
    h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(file_bytes(f))
digest = "sha256:" + h.hexdigest()

is_runtime_file(f):
    suffix in {".py", ".json"}
    and not name.startswith(("test_", "_"))
    and no path component in {"__pycache__", "dist", ".tmp", "test"}   # 第 4 项 = C16 修正
```

- 排序键用**相对 posix 路径**（Windows 反斜杠不可进摘要，否则两侧不互认）。
- 摘要**包含路径名**，所以删除/改名均可检（mtime 不可检，§1 要点 2）。
- 摘要**不含 mtime**（含 mtime 会退化成"内容+时间"混合判据，touch 也会翻），touch-only 变更因此不算漂移（AC-005"dirty 不误报"的正面实现）。
- 空 `files`（如 `code_dir` 指向空目录）⇒ 返回 `None` ⇒ 退回 mtime 判据，不告警。

#### §2.2 写入点 / 删除点：**不动**，但采集顺序前移

- 写入点仍是 `mw.py:273`（紧随 `:271 _write_pid`，同受 `wrote_pid` 标志管辖）；删除点仍是 `finally` 里的 `:398 _remove_serve_meta(project_dir)`。理由：pid 与 meta 必须同生共死，且"路由预检失败（`all_missing`）⇒ 不写 meta"这一既有语义（`:283-288` 提前 return）必须保住。
- **改动 1（顺序）**：把身份采集（`commit`/`dirty`/`mtime`/`digest`/`version`）全部**提到 `_write_pid` 之前**，然后 `_write_pid` → `_write_serve_meta(project_dir, identity)`。理由见 C6：`timeout` 只把楔子从"无限"降到"最多 3 s"，顺序前移才真正保住"PID 文件存在 ⇒ 服务已在启动路径上"这一被 PM 稳定窗口依赖的不变量。
- **改动 2（清理）**：`_remove_serve_meta` 顺带删同名 `.tmp` 残留（原子写的副产物）。
- 写入点**不得**挪到"conductor 起来之后"或"launcher 起来之后"——那样 serve 早期崩溃就没有身份记录，而崩溃时刻恰恰最需要它。

#### §2.3 原子写：temp + `os.replace`（同目录）

现写法 `p.write_text(json.dumps(meta))`（`mw.py:128-131`）是非原子的：读者可读到半截 JSON。本仓已有大量同模式先例（`mw.py:1186` / `:1999` / `:2399` / `:2815`，`mw_common.py:1395-1397` / `:1949` / `:2072`，`gates.py:326 _write_atomic`）。落地：

```
tmp = p.with_name(p.name + ".tmp")           # 同目录 ⇒ 同卷 ⇒ os.replace 原子
tmp.write_text(json.dumps(meta), encoding="utf-8")
os.replace(tmp, p)
```

- 今天"半截 JSON"只是让 TS `readServeMeta` 返回 `null`（`mw-runner.ts:210-215` catch）与 A3 退回 `started_ms=None`（`mw.py:5371 except json.JSONDecodeError`），**不致命**；但加上身份字段之后，半截 meta 会丢 `commit`/`code_digest`，把一次瞬时读竞态放大成"退化为旧判据"。所以原子写从"1 行顺手修"升级为**必要**。
- Windows 上 `os.replace` 对已存在文件是原子的（同卷），无需先 unlink。

#### §2.4 旧 meta（缺字段）兼容：**今天就能判**

旧 meta = `{pid, started_at_ms, code_dir}`。按 §1 算法：`code_digest is None` ⇒ 走 mtime 判据，`base_ms = started_at_ms`，语义与今天的 TS/A3 **逐字相同**。因此：
- **不需要任何迁移**，也不需要"先重启一次 serve 才能检测漂移"。
- `commit`/`code_digest` 缺失**永不单独构成告警**；`schema` 是唯一例外——存量 serve 的 `schema` 视为 0 < `EXPECTED_SCHEMA`，capability 判据**会**命中。这不是矛盾而是设计意图：capability 问的是"它有没有新守护"，答案确定是"没有"，且依据是写者自己落盘的自我声明，不是推测。
- 未来 `EXPECTED_SCHEMA=2` 时，`schema=1` 的 serve 同样命中 ⇒ 该判据天然是"合并新守护后必须重启 serve"的机器形式（C10）。

#### §2.5 与种子的差异（逐条）

| # | 种子（RQ-3 §2.4 推荐） | 本卡 | 差异原因 |
|---|---|---|---|
| D1 | `commit = _git_head_short(_SCRIPT_DIR)` | full 40-hex OID，纯文件读优先 | 缩写长度随对象库伸缩（本机 9 位 vs 40 位），字面比较恒假（C4） |
| D2 | 三判据 `commit + dirty + code_mtime_ms` | 增加 `code_digest` 并升为权威 | mtime 看不见删除；commit 看不见 dirty，且提交 dirty 会假阳（C1） |
| D3 | 比对"每 tick" | 每 60 s（模块常量） | tick 默认 `poll_interval_sec=4`（`config.py:86`），60 s 是 15 倍降频；两条判据都不需要秒级 |
| D4 | 限频"会话级 set" | 内存 set **+** `_timeline_has_event` 持久层 | conductor 崩溃后被 serve 1 s 内 respawn（`mw.py:140-198`），纯内存 set 会跨 respawn 重复告警（C12） |
| D5 | 建议"不新增文件" | 遵守（重启后复核也不用新文件，C14） | — |
| D6 | 判据 `commit 不等 ⇒ stale` | digest 在场时降级为 `history-only` | "提交 dirty 文件"假阳性（C1(b)）；需 design 追认 |
| D7 | `_UPDATE_ENV_SKIP_DIRS = ("__pycache__","dist",".tmp")`（含 TS 镜像） | 增加 `"test"` | 69% 的判据输入面是 fixture，重启告警化后成为持续假警（C16） |
### §3 比对与告警

#### §3.1 在哪些时刻比对

| 时刻 | 谁 | 判什么 | 输出 | 为什么 |
|---|---|---|---|---|
| **T0 serve 启动**（`mw.py:273` 邻域，采集后移前置） | serve 自己 | **不判漂移** | ①`serve.meta` 身份字段；②`mw.log` 一行 `[mw serve] code identity: commit=<full> version=<v> schema=<n> mtime=<iso> digest=<12hex> dirty=<t>/<u>` | 进程无法自证"我就是陈旧的那一个"（它跑的就是它自己），启动期判定无意义；但**身份必须落盘**，否则事后无从复算。写 `mw.log`（append、无轮转，`mw.py:223`）而不写 `conductor.log`（每会话 truncate，`mw.py:231`）——本仓 `mw.log` 实测 16,603 B / 32 条启动行，是可用的跨会话载体 |
| **每 tick（60 s）** | conductor（`tick()` 内，`:2880`） | `serve_code_verdict()` | 命中 ⇒ stderr + timeline `config` | 覆盖"serve 活着、代码在变"的持续窗口；60 s = `poll_interval_sec`(4) 的 15 倍降频，纯 stat + 8 ms 摘要，无 spawn |
| **按需（新鲜进程）** | `mw status` / `mw doctor` / `mw update-env` / TS 面板 | 同上 | 状态面行（+ doctor issue + 可选 push 告警） | **serve 不可自证时的唯一通道**（C9/C13）；也是"重启前"唯一能发现存量漂移的通道 |
| **重启后第一 tick** | conductor | §3.7 的 pending 门禁复核 | 命中 ⇒ stderr + timeline `config` | 上游 P2 |

- 三处必须**共用同一个纯函数**（`mw_common.serve_code_verdict`），否则"检查者各自重算基线"的历史分歧面（`findMwPy()` vs `_SCRIPT_DIR`，RQ-3 §2.3）会以新形态复活。
- 60 s 重检间隔放在 conductor 模块常量而不是 config：AC-011 明令不新增 config 键（20 键冻结 schema + `status-model.ts` 双镜像 + parity 测试的连带面）。节流实现 = 模块级 `_CODE_DRIFT_LAST_CHECK: float` + `if now - last < 60: skip`，避免把 stat 走查塞进 4 s tick。
- **不做**：不在 serve 的 1 s 主循环里比对（那是 serve 自己的树，自证无意义）；不在 tick 里 spawn git（每次 4 s 起一个进程的成本与弹窗风险都不值）。

#### §3.2 分类

| 分类 | 触发条件 | 推 `stderr`+timeline 告警？ | 状态面表述 |
|---|---|---|---|
| `fresh` | 内容未变（digest 相同或 mtime 未越过基线）且 commit 相同且 capability 为 `True`/`None` | 否 | `serve code: fresh (schema 1, digest 1e47fcd951ab, started +1.2h)` |
| `drift / content-changed` | `digest_now != meta.code_digest`（或旧 meta 且 `mtime_now > base + 2000ms`） | **是** | `STALE CODE (content changed: mw.py 2026-10-13T02:26:03Z, drift 16d23h, expected <c1> actual <c2>) -> /mw restart` |
| `drift / head-moved` | 旧 meta（无 digest）且 `meta.commit != head_oid(tree)` | **是**（AC-005 字面） | `STALE CODE (head moved <c1> -> <c2>)` |
| `drift / schema-stale` | `tree == checker_tree` 且 `(meta.schema or 0) < EXPECTED_SCHEMA` | **是** | `CAPABILITY DRIFT (meta schema 0 < 1: the running serve predates the drift self-check) -> /mw restart` |
| `history-only` | digest 在场、`commit_moved` 且 `digest_now == meta.code_digest` | **否** | `serve code: fresh (HEAD moved <c1> -> <c2>, content identical)` |
| `undecidable` | `meta-missing` / `code-dir-missing` / `no-baseline` / `tree-unreadable` / `git-unavailable` | **否**（不得因缺字段告警） | `serve code: unverifiable (<reason>) -> /mw restart` |
| （属性，非分类）`dirty` | `meta.dirty_tracked > 0` | 否 | 以 `dirty=11/9` 附在上述任一行；**只在漂移告警里解释"为什么 commit 单独不可信"** |

**"dirty 允许"的准确含义**（AC-005 明文）：dirty 工作区**本身**不得产生告警；本设计把它落成两条：①`code_digest` 冻结的是 dirty 内容，只要内容不动就判 fresh（本仓今天 `git status --porcelain` = 11 tracked + 9 untracked，正是常态）；②当 commit 与 digest 冲突时，**digest 胜**，commit 只在 digest 缺席（旧 meta）时独立成立。

#### §3.3 告警文案要素

固定要素（缺一不可，顺序固定便于 grep/单测）：`tree=` / `schema=<actual>/<expected>` / `serve_pid=` / `started=<iso> (+<uptime>)` / `expected commit=<full|unavailable>` / `actual commit=<full|unavailable>` / `code newest mtime=<iso> (base=<iso>)` / `drift_age><…>` / `dirty_at_start=<t>/<u>` / `version=<v>` / `digest=<12hex|unavailable>` / `fix: /mw restart`。

模板（单行，stderr 与 timeline `detail` 逐字一致——`_timeline_has_event` 的查重依据就是 `detail` 全等，两处用**同一个** `detail` 字符串）：

```
[conductor] serve code drift: tree=H:\git\Multi-Workers\packages\multi-workers schema=0/1 serve_pid=168160 started=2026-09-26T02:30:43Z (+409.7h) expected commit=cc9a46a1ad1ebb35eb1a5d96d8101c46cd3b78ad actual commit=4f1c2b9ab7... code newest mtime=2026-10-13T02:26:03Z (base=2026-09-26T02:30:43Z) drift_age>=16d23h55m dirty_at_start=0/0 version=0.83.0 digest=unavailable fix: /mw restart
```

- 上游 P0-① 的范例（`capability drift: serve started 2026-09-26T10:30:42 (408h), modules HEAD=ab546bb64 (+3 commits) — 提醒守护等未生效`）要求的三个要素——**期望/实际身份、已陈旧多久、修法**——都在上面这一行里，且加上了它没有的 `tree`（多 worktree 的分歧面）与 `dirty`（解释 commit 可信度）。
- 期望/实际 commit **不可得**时写 `commit=(unavailable)`（不写空串，避免"缺字段看起来像相等"）；`digest` 同理。
- 不出现多行、不出现换行（timeline 是 JSONL 单行；`detail` 里的换行会破坏 `_timeline_has_event` 的全等比较）。
- `fix` 文案只给 `/mw restart`：Python 侧**不自动重启**（C15）。不提 `mw stop`+`mw start`（会丢 env，见 `UPDATE.md:40` 的 P-015 备注）。

#### §3.4 "漂移时长"怎么算

三个量，全部从判据里直接得出，不做二次启发式：

| 量 | 公式 | 含义 |
|---|---|---|
| `uptime` | `now − meta.started_at_ms` | 该进程已运行多久（上游范例里的 `408h`） |
| `code_newer_by` | `mtime_now − base_ms` | 磁盘代码比"进程加载的那份"新多少（TS `detail` 今天的 `serve started X, mw code changed Y` 就是这个对） |
| **`drift_age`** | 内容判据命中：`now − mtime_now`；仅 commit/schema 命中：`now − base_ms` 并标注 `>=` | **"我已经跑了多久的旧代码"** = 从磁盘偏离进程快照的那一刻起算 |

- 取 `mtime_now` 作内容判据的起点，是因为磁盘上最后一次变更就是两边的分岔时刻；此后进程一直是陈旧的。
- 只有 commit/schema 命中时，分岔时刻落在 `[base_ms, now]`，不可知 ⇒ 报下界 `>= now − base_ms`，**不假装精确**（`>=16d23h55m` 而不是 `16d23h55m`）。
- 实测对照（本卡现场）：FeatureMigrator `started=2026-09-26T02:30:43Z`、`mtime_now=2026-10-13T02:26:03Z`、`now=2026-10-13T04:10:39Z` ⇒ `uptime=409.7h`、`code_newer_by=1,468,520s ≈ 16d23h55m`、`drift_age = now − mtime_now ≈ 1h45m`（= "最后那次改动落地后，这进程又跑了 1h45m 的旧代码"）。三个数都进告警行，避免操作者用错口径。

#### §3.5 限频键与去重（会话级 vs 持久）

- **键** = `(code_dir, meta_commit, head_commit, serve_pid)`（AC-005 指定）。`serve_pid` 在键里 ⇒ 重启后自然重新武装；`meta_commit`+`head_commit` 在键里 ⇒ commit 再变一次是一次新漂移，可再报一次。
- **两层去重**：
  1. 进程内 `_CODE_DRIFT_SEEN: set[tuple]`（模块级，紧挨 `_ROADMAP_ALARM_SEEN` `conductor.py:2594`），零 I/O 预筛；
  2. **持久层复用 `_timeline_has_event(project_root, ev, key, detail)`（`conductor.py:1899`）**，按 `(ev, "-\<key 由 timeline 归一\>", detail 全等)` 在 `tail_events(limit=200)` 里查。
- **为什么不落一个去重文件**：需要一个由 conductor 维护、启动时清理、且要在 serve 重启时失效的 sidecar，属于"新增文件 + 新失效窗口"，与 P-01（不新造通道/基础设施）相抵；而时间线**本来就是 conductor 的唯一权威事件流**、跨 respawn 存活、且 `_timeline_has_event` 已是本仓既有先例（证据回收 `EVIDENCE_RECONCILIATION_EVENT` 用的就是它）。
- **持久层的已知代价**：时间线每 10 MB 轮转、保留 3 代，实测保留窗口 ≈12.8 天（§5.1）。漂移持续超过保留窗口时会**重发一次**。这是想要的行为：一条 12 天前发过、现在已滚出窗口的告警，对操作者等价于没发过；重发让"记录消失了"自身变成信号。且重发频率被 200 条尾窗边界约束，不会刷屏。
- **明确不去重的**：状态面（`mw status` / 面板 / doctor）。状态面**每次调用都必须重算并显示当前真相**，不做"已通知过就静默"的抑制——这正是本 key 的 P-02（状态面优先于事件面）与 AC-001 的同构要求。

#### §3.6 双通道落点与 TS 分工

- 通道**完全复用**：`print(..., file=sys.stderr, flush=True)`（serve 把它重定向到 `.mw/conductor.log`，`mw.py:231`）+ `st.timeline.append("config", detail=detail)`（形状逐字照 `conductor.py:2617-2620` 的 `_emit_roadmap_failure`）。**不新造日志文件、不新造通知类型**（P-01 / AC-006）。实现上建议把 `_emit_roadmap_failure` 的"stderr + timeline + 查重"三段提升成一个通用 `_emit_alarm(project_root, st, *, key, detail, seen)`，门禁提醒与漂移告警共用——但**不新增第二条通道**。
- `ev` 用既有 `"config"`（`timeline.py:77` 已在 `EVENT_TYPES` 白名单内），**不新增事件类型**（省掉 TS `status-model.ts` 的 `EVENT_TYPES` 镜像同步面）。用 `detail` 前缀 `serve code drift:` 区分类别。
- 与 TS 的分工（C15）：TS 侧只保留 4 个既有消费点的**交互恢复**语义（`monitor.ts:782 STALE CODE` 行、`ui-bridge.ts:3413 /mw status`、`console.ts:621-632 enable 自动重启`、`pm-orchestrator.ts:1776-1783 启动横幅`）。**TS 不得因本设计新增周期 notify**；Python `stderr`/timeline 与 TS 面板因此是"持久记录 vs 状态面"的分工，不是同一通知的两份拷贝。

#### §3.7 重启后复核 pending 门禁（上游 P2，AC-005 末句）

零新字段、零新文件（C14），判据只用既有三处事实：

1. **门禁侧**：`gates` 目录里 `status` 为终态、`created_at < T_restart` 的门禁（`created_at`/`status` 是 v1 就有的必需字段）。
2. **裁决来源**：`answered_by` 是否以 `conductor-auto:` 开头（`conductor.py:6608` 是唯一写入点，格式 `conductor-auto:<rule_id>`；人工答复写 `hostname:pid`，`xkey-gate-guard.ts` 注释明确"human keystroke and a PM agent share the same pid"，所以**不做**更细的判别，只区分 auto / 非 auto）。
3. **重启时刻**：`T_restart = 新 serve 的 serve.meta.started_at_ms`（重启会覆盖 meta；旧值不可得，也不需要——判据只关心"答复发生在重启之后"）。

命中条件：`terminal(status) and created_at < T_restart and answered_by.startswith("conductor-auto:") and answered_at > T_restart` ⇒ 一条 `config` 告警：`post-restart auto-answer: gate <id> (<kind>) created <t> was pending across the serve restart and auto-answered by <rule_id> at <t2> - review the new auto-decision rules / autopilot auto_gate_mode`。

- 时序上放在 `tick()` 的 `_remind_pending_gates` 附近（`:2890` 之前），且只在**新 serve 会话的前 N 次 tick**（建议 `N=5`，或"`now − T_restart < 300s`")执行一次，避免每次 tick 重扫 gate 目录；去重走 §3.5 的同一机制（key 用 gate id）。
- 反向用例（必须绿）：人工答复（`answered_by=host:pid`）⇒ 不告警；重启前已终态的门禁 ⇒ 不告警；`created_at > T_restart` 的新门禁被 auto 答复 ⇒ 不告警（那是正常自动裁决）。
### §4 新鲜进程侧入口（本卡的关键要求）

#### §4.1 为什么必须，以及为什么**今天**就能生效

- **serve 不可自证**：判定逻辑写在 serve 加载的模块里，而"serve 加载的是旧模块"这一事实恰好让它自己看不到这个判定（Python 只在启动时 import；`ab546bb64` 的守护对该进程从未存在，已机械核实：`git show ab546bb64^:.../conductor.py` 中 `_remind_pending_gates` 出现 0 次，`ab546bb64:` 中 4 次）。
- **存量可判**：旧 serve 的 meta 虽无 `commit`/`code_digest`，但 `started_at_ms` + `code_dir` 自 stale-serve 修复起就在里面（`mw.py:122-131`）。因此**任何新起的一次性进程**都能用 mtime 回退判据当场判出真漂移——不需要等一次 serve 重启（这正是种子 RQ-3 §4.2 表里"立即生效"那一栏的落点）。
- **本卡现场实测证明它有效**：用判据函数在只读条件下复算 `E:\CLI_workspace\FeatureMigrator` ⇒ `started 2026-09-26T02:30:43Z` vs `newest runtime mtime 2026-10-13T02:26:03Z`，`stale=True`、`delta=1,468,520s`。今天没有任何一处会显示这个结论（`mw doctor`/`mw status` 零 serve 检查，RQ-3 §1.2）。

#### §4.2 入口 A：`mw status`（最小、最先落地）

在 `cmd_status`（`mw.py:486-504`）现有两行之后追加一行，**退出码语义完全不变**（仍是 `0 if pid else 1`）：

```
[mw status] serve code: STALE (content changed: mw.py 2026-10-13T02:26:03Z; drift >=16d23h55m; expected commit=cc9a46a1a..., actual=unavailable; tree=H:\git\Multi-Workers\packages\multi-workers; dirty_at_start=n/a) -> /mw restart
```

- 这是**最小的新鲜进程侧入口**：`mw status` 是独立进程，不 import serve 的状态，只读 `.mw/serve.meta` + `.mw/mw.pid` + 代码树 + `.git` 纯文件读。
- serve 未运行时打印 `[mw status] serve code: n/a (not running)`（不产生噪声，也不改变"not running"的既有输出与退出码）。
- 不给 `mw status` 新增 `--json` 开关（会扩大 CLI 面）；需要机器可读时用 `mw doctor --json`（入口 B 已有 `--json`）。

#### §4.3 入口 B：`mw doctor`（可机读 + 可判失败）

- 新增 section `report["serve_code"] = {...}`（在 `doctor_report()` `mw_common.py:3624-3650` 的 section 列表里，紧邻 `report["service"]`），字段：`running / verdict / reason / tree / schema / commit_expected / commit_actual / code_mtime / base_ms / drift_age_s / upper_bound / dirty_tracked / dirty_untracked / digest_expected / digest_actual / fix`。
- 失败分级：`verdict == "drift"` ⇒ 追加进 `_doctor_issues()`（`mw_common.py:3401`）的 `issues` ⇒ `summary.healthy=False` ⇒ `mw doctor` 退出码 1。`verdict in {"undecidable"}` ⇒ 进 `suggestions`（不翻 healthy，避免"缺字段就报错"）。`fresh`/`not running` ⇒ 静默。
- 兼容性已核实：TS 侧 `doctorMw()`（`mw-runner.ts:414-431`）明确容忍退出码 1（"doctor exits 1 on issues but still prints JSON"），因此把 stale serve 升级为 issue **不会**破坏 `/mw doctor` 的调用链。
- TS `DoctorJson`（`mw-runner.ts:341-400`）需要加可选 `serve_code?: {...}` 并在 `/mw doctor` 的文本渲染里显示一行；**可选**，但若不显示则"新鲜进程侧入口"在 TUI 里就只剩面板一行。

#### §4.4 入口 C：`mw update-env` A3（把既有检查修成权威）

A3（`mw.py:5362-5390`）今天**已经**是"新鲜进程侧的 mtime 判据"，只是三个缺陷：①基线树用检查者自己的 `_SCRIPT_DIR`（`_mw_code_newest_mtime()` 无参）而不是 `meta.code_dir`；②detail 里没有 commit 对；③不在 tick、不告警（这点保持——A3 是人敲的）。修法：

- `_mw_code_newest_mtime(root: pathlib.Path | None = None)`：加参数，内部 `root = root or _SCRIPT_DIR`，并把 `f.relative_to(_SCRIPT_DIR)` 改成 `f.relative_to(root)`（这是**必须**的改动：`relative_to` 对非同源路径会抛 `ValueError`）。
- A3 调 `serve_code_verdict()`，`detail` 含 `expected/actual commit`，`fix` 保持 `auto=True` + "重启 serve"。
- A3 也是**唯一**已存在的、会在输出里写"serve 陈旧"的 Python 面；把它与 status/doctor 的判据统一，避免三份实现。

#### §4.5 入口 D：TS 侧（`serveStaleness` + 面板 + `/mw status` + enable）

- `readServeMeta`（`mw-runner.ts:207-216`）增解析 `schema/commit/code_dir/code_mtime_ms/code_digest/dirty_*`（**全部可选**，缺失不 return null——现有实现只要 `pid`/`started_at_ms` 类型不对就 null，需保持该容忍）。
- `serveStaleness`（`:272-289`）改为：基线树 `readServeMeta(projectDir)?.codeDir ?? findMwPy()`（**这是 C15 的硬约束**）；判据同 §1（digest 权威 → mtime → commit），`detail` 含期望/实际 commit。现有单测 `agent-team-loop.test.ts:987-1022` 与 `dual-root-worker.test.ts:228-250` 全部是"传 mtime 覆盖值"的形态，改动后仍可绿（VC-016 的 `code_dir == pkg` 与检查者树一致，`capability` 有值）。
- 面板（`monitor.ts:340-355` 采集 / `:782-789` 渲染）保持 `STALE CODE … -> /mw restart` 的**文案骨架**（`autopilot-monitor.test.ts:737-770` 锁了这串），只让 detail 变长（已有 `trunc` + "cap 住 detail 保住 /mw restart" 的实现，`:783-788`）。
- 若 TS 侧暂时不做 digest（只做 commit/mtime），两侧判据会**短暂不一致**（TS 会把 `history-only` 报成 stale）。⇒ 至少要让 TS 读 `code_digest` 并优先用它；或明确接受"TS 比 Python 更保守"（多提示一次重启，代价可控，与既有 stale-serve 修复的取舍一致）。推荐前者。

#### §4.6 入口 E（可选加固）：独立于 meta 的 OS 进程启动时间探针

`meta.started_at_ms` 由 serve 自己写，因此有两类它管不了的假象：①**meta 是上一次会话的残留**（serve 崩溃未走 `finally` ⇒ 竟争：PID 被回收给另一个无关进程，`check_pid` 报"在跑"，而 meta 是旧的）；②meta 被手工/工具改写。用一个不依赖 meta 的探针交叉核对：

```
process_start_ms(pid) -> int | None
  win32 : ctypes OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetProcessTimes
          （返回 FILETIME 100ns-since-1601 ⇒ 转 epoch ms）
          —— 与 mw_common._is_alive_win32（:2184）同一套 ctypes 先例，零新依赖
  其他  : /proc/<pid>/stat 字段 22 (starttime, clock ticks) + /proc/stat 的 btime
          失败则 ps -o lstart= -p <pid>（timeout=3）；再失败返回 None
```

- 判据：`abs(process_start_ms(pid) − meta.started_at_ms) > 60_000` ⇒ 状态面报 `serve identity mismatch (pid <p> started <os> but serve.meta says <meta>)`；**只报状态面，不推告警**（false positive 面不可忽略：PID 复用、时区/时钟抖动、容器时钟）。这是"进程活着的那个 PID"与"meta 描述的那个进程"是否同一个的**独立**核对。
- 本机实测该探针可用：`Get-Process -Id 116368 | Select StartTime` = `2026/9/26 10:30:42`（+08:00）⇒ `2026-09-26T02:30:42Z`，而 meta 的 `started_at_ms` = `2026-09-26T02:30:43.021Z` ⇒ 相差 1.0 s（meta 在进程起来之后才落盘），**远小于 60 s 阈值**，说明阈值选得合理。
- 该探针是**可选**项：入口 A-D 已满足"至少一个不依赖该进程的入口"的硬要求；E 只解决"meta 自身是否可信"。
- `psutil` 本机可 import 但**全仓零使用**、也不是声明依赖 ⇒ 不引入（`AGENTS.md`：直接外部依赖要精确锁版本 + 审查）。

#### §4.7 这些入口如何被自动化验证

**（1）判据表驱动单测**（新增 `packages/multi-workers/test_serve_code_drift.py`，纯函数、无进程、无 git）：

| 用例 | fixture | 期望 |
|---|---|---|
| 内容不变 | meta(digest=D, mtime=M0, commit=A)；树 digest=D, HEAD=A | `fresh`，0 告警 |
| 内容变更 | 树 digest=E | `drift/content-changed`，1 告警，`drift_age = now − mtime_now` |
| **删除不可见（反例）** | 从树里删掉一个 `.py`，其余文件 mtime 全不动 | `drift/content-changed`（**mtime 判据会漏，digest 抓住**；这是 C1(a) 的锁定用例） |
| commit 前进但内容相同 | `git commit` 掉 dirty 文件（fixture 直接构造 HEAD=C、digest=D） | `history-only`，**0 告警**（C1(b) 锁定） |
| 旧 meta + mtime 漂移 | meta 只有 `{pid,started_at_ms,code_dir}`；`mtime_now > started+2s` | `drift/content-changed`（回退路径） |
| 旧 meta + commit 漂移 | 旧 meta + `head_oid != meta` 无法比（无 commit）⇒ | `undecidable`，**0 告警**（fail-open 锁定） |
| dirty 不误报 | `dirty_tracked=11`，树不变 | `fresh`，0 告警（AC-005 明文） |
| capability | `schema=0`（或缺失），树=检查者树，内容不变 | `drift/schema-stale`，1 告警（C10 锁定） |
| 跨 worktree | `code_dir != checker_tree`，内容不变 | `fresh` 且 `capability=None`；状态面含 `tree=` 不等于检查者树 |
| 目录消失 | `code_dir` 不存在 | `undecidable/code-dir-missing`，0 告警 |
| 去重 | 同一 verdict 连算 3 次（同一 tick 语义） | `stderr` 1 行 + timeline `config` 1 事件 |
| 去重（跨 respawn） | 先写一条同 `detail` 的 timeline 事件，再算一次 | 0 新告警（`_timeline_has_event` 命中） |

**（2）"新鲜进程侧入口"的契约测试（这是"如何被自动化验证"的正面回答）**：把入口**当子进程跑**，不 import 被测函数——这样测试证的是"一个新起的进程能不能独立判出漂移"，而不是"纯函数对不对"。

```
# packages/multi-workers/test_serve_code_drift_cli.py
def test_status_reports_stale_for_legacy_meta(tmp_path):
    # 1) fixture 项目：.mw/mw.pid = os.getpid()（pytest 进程活着 ⇒ check_pid 通过）
    #    .mw/serve.meta = {pid: os.getpid(), started_at_ms: T0, code_dir: <fake tree>}
    #    fake tree: a/mw.py mtime = T0 + 3600_000（比启动晚 1h）
    # 2) subprocess.run([sys.executable, "-X", "utf8", mw_py, "status", f"--project={tmp}"])
    # 3) assert returncode == 0 且 stdout 含 "serve code: STALE" 且含 "drift"
    # 4) 反例：把 mw.py 的 mtime 设为 T0 - 1000 ⇒ stdout 含 "serve code: fresh"
```

同型再各加一条 `doctor --json`（断言 `report["serve_code"]["verdict"]=="drift"` 且 `summary.healthy is False`）与 `mw update-env`（断言 anchor `serve` = `STALE`）。三条都不需要真 serve、不需要 git（`commit` 走 None 路径）。

**（3）Windows / 无 git 的自动化反例**：`monkeypatch.setenv("PATH", "")`（或 `shutil.which` 打桩返回 None）后跑同一组 CLI 测试 ⇒ 断言**不抛异常**、`commit=(unavailable)`、判据退回 mtime。这是"Windows 无 git bash"的可执行形式。

**（4）现场回归命令（上游给的复现命令的机器形式）**：上游要求人肉跑 `Get-Process -Id <pid> | Select StartTime` × `git log -1 -- ...conductor.py`。本设计把它变成一条命令：

```
python -X utf8 <mw.py> status --project E:\CLI_workspace\FeatureMigrator
# 期望（2026-10-13 现场）：serve code: STALE (… drift >=16d23h55m …) -> /mw restart
python -X utf8 <mw.py> doctor --project E:\CLI_workspace\FeatureMigrator --json
# 期望：serve_code.verdict == "drift" 且 summary.healthy == False
```

CICD 里可作为"实例回归"（只在显式要求时跑，因为它依赖一个真实的长驻项目）——本卡已用只读脚本复算过判据本身（`stale=True`, `delta=1,468,520s`），实现落地后该命令应逐字复现同一结论。

**（5）TS 侧**：`agent-team-loop.test.ts:987-1022` 扩 commit/digest 分支 + `code_dir` 优先于 `findMwPy()`；`dual-root-worker.test.ts:228-250` 增"`meta.code_dir` ≠ `findMwPy()` 时以 `code_dir` 为准"的反例；`autopilot-monitor.test.ts:67-72` 的 fixture 迁到新字段并断言 `STALE CODE … -> /mw restart` 骨架不变。
### §5 边界与反例

#### §5.1 保留窗口 < 漂移时长（C13 的实测支撑）

```
FeatureMigrator .agenticdoc/_autopilot/timeline.jsonl.2 : 2026-09-30T01:40:47Z -> 2026-10-06T00:35:53Z  (10,485,841 B)
FeatureMigrator .agenticdoc/_autopilot/timeline.jsonl.1 : 2026-10-06T00:35:58Z -> 2026-10-12T04:32:32Z  (10,485,838 B)
FeatureMigrator .agenticdoc/_autopilot/timeline.jsonl   : 2026-10-12T04:32:38Z -> 2026-10-13T04:13:12Z  ( 1,696,615 B)
⇒ 保留窗口 ≈ 12.8 天；本事故漂移 = 16 天 23 小时 55 分 ⇒ 漂移开始时的事件早已滚出
FeatureMigrator .mw/conductor.log = 0 B（每次 serve 会话 truncate，mw.py:231）
FeatureMigrator .mw/mw.log        = 4,841 B（append，无轮转）
H:\git\Multi-Workers\.mw/mw.log   = 16,603 B / 32 条 "[mw serve] started (PID …)" ⇒ 跨会话可用
```

⇒ **事件面与日志面都不能承载"当前是否陈旧"这个结论**；身份必须落在 `serve.meta`（可随时复算）+ 状态面（按需重算）。

#### §5.2 Windows 无 git bash

- `_git()` 用 `subprocess.run(["git", …])`；PATH 无 git ⇒ `FileNotFoundError`（实测确认是抛异常而非返回码），**注意它今天会从 `_git_dirty`/`_git_head_short` 直接冒泡**（两者只处理 returncode，不处理 OSError/TimeoutExpired）。
- 因此：①比对环节**不 spawn git**（C5）；②启动期 `dirty` 采集必须 `try/except (OSError, subprocess.SubprocessError) -> None`；③`_git()` 本身加 `timeout` + win32 `creationflags=CREATE_NO_WINDOW`（`mw.py:277-278` 对子进程已刻意这么做过）——否则无控制台进程里 spawn 控制台程序会闪窗。
- 无 git ⇒ `commit=None`、`dirty_*=None`，判据退回 mtime，**不告警**；`version` 仍可读（纯文件 `package.json`）。这正是"Windows 无 git bash 也要能工作"的落点。

#### §5.3 `timeout` 缺失的后果（比"慢"严重）

- `_write_pid`（`:271`）先于 `_write_serve_meta`（`:273`）⇒ 采集挂在 `_write_serve_meta` 内 ⇒ `mw.pid` 已存在、`mw.log` 无 "started" 行、launcher/conductor 永不 spawn。TS `waitForMwStart` 只查"PID 文件 + signal 0"（`mw-runner.ts:150-176`）⇒ 误判"已启动"，随后 `/autopilot enable` 承诺的 conductor 永不出现（这正是 stale-serve 修复当初的故障形态）；`mw stop` 写 `.mw/mw.stop` 后等 30 s（`mw.py:456-466`）⇒ 失败。（本卡未实测挂死行为，只从代码路径推出，见"残留与未验证"。）
- 修法：采集前置（C6）+ `timeout=3`（`dirty` 是可选字段，超时就 `None`）+ 异常全吞。**`status --porcelain` 在大 worktree / 杀软扫描下可能秒级**，3 s 是工程取值；`commit`/`mtime`/`digest` 都不需要它。
- 附带发现：`_git_dirty()`（`mw.py:5175-5185`）在 git 返回非 0 时 `return (0, 0)` —— **把"git 失败"汇报成"工作区干净"**。这是静默 fail-open 的反向错误（假"干净"）。本设计里 `dirty_*` 只是上下文，影响有限；但同一函数被 A4（framework-source）使用，那里会把"repo 有改动"误判为 ok。⇒ 属于本 key 顺手可修的相邻缺陷（`_git_dirty` 返回 `None` 表示不可判），**列入 design 决策点**（不在本卡强推，因为它会动到 A4 的既有断言）。
- 另有两处硬编码 `<dir>/.git` 存在的 helper——`_git_dirty_paths`（`:4507`，`if not (repo/".git").exists(): return None`）与 `_update_git_counts`（`:5155`）——对 `code_dir = <repo>/packages/multi-workers`（无 `packages/multi-workers/.git`，本机实测 False）**恒返回 None**。⇒ 身份采集**不得**复用它们；必须先解析 git top-level，或直接对 `<code_dir>` 调 `_git_dirty`（后者用 `cwd` 让 git 自行上溯：本机实测 `git -C packages/multi-workers status --porcelain` rc=0）。

#### §5.4 dirty 工作区：两个方向的反例

- **反例 1（漏报，仅 mtime 时）**：dirty 树里**删掉**一个 runtime 文件。mtime 判据看不到（其余文件 mtime 不变），HEAD 不变 ⇒ 判 fresh。⇒ digest 修（§1 要点 2）。
- **反例 2（假报，仅 commit 时）**：serve 在 dirty 树上启动（记 `commit=A`）；人类随后 `git commit -am` 把这批 dirty 改动提交（`HEAD=B`，**工作树字节零变化**）。commit-only 判据 ⇒ 报 drift，但进程跑的字节与磁盘完全一致 ⇒ 假警。**注意本仓 `packages/multi-workers` 今天就是 dirty（11 tracked + 9 untracked），而它同时是 FeatureMigrator 的 `serve.meta.code_dir`** ⇒ 这个假阳性不是理论问题。
- **反例 3（假报，仅 mtime 时）**：`git checkout` 切分支再切回（内容相同、mtime 变）⇒ mtime 判据假报；digest 判据不报。
- ⇒ 结论：**digest 为主、mtime 为时间戳来源/回退、commit 为命名与 capability**，三者缺一都会在真实开发机上出错。

#### §5.5 多 worktree

- `code_dir` 指向的是 `<worktree>/packages/multi-workers`；纯文件读必须从 `code_dir` **逐级上溯**到含 `.git` 的目录（本机实测：`packages/multi-workers/.git` 不存在，仓库根 `.git` 是目录 ⇒ 上溯 2 级）。
- `.git` 为**文件**（linked worktree）时内容为 `gitdir: <common>/.git/worktrees/<name>`：HEAD 与 `refs/` 在该 gitdir 下，但 **`packed-refs` 在 `commondir`（通常 `<common>/.git`）下**，且 gitdir 里的 `commondir` 文件可能是个相对路径。**本卡未在本机复现 linked worktree**（`git worktree list` 只有一棵），但这是已知必须处理的分支：解析器须按 `gitdir:` → `HEAD` → ref → `gitdir/refs/...` → **`commondir`/`packed-refs`** 的顺序找；任一环失败 ⇒ `commit=None`（fail-open）。不处理 `commondir` 会让 packed 分支的 worktree serve **永远 commit 不可判**（退化为 mtime，不至于假警，但丢掉 commit 命名）。
- **检查者树 ≠ 运行者树**是常态配置而非异常（`MW_PY` env > 全局 `.mw-py-path` sidecar > 仓库相对，`mw-runner.ts:29-55`；本机该 sidecar 指向 `H:\git\Multi-Workers\packages\multi-workers\mw.py` 的具体路径已在 RQ-3 证据 §5.3 记录，与两仓 `code_dir` 恰好相同）。⇒ 基线**只能**取 `meta.code_dir`（C15）；`capability` 在跨树时返回 `unknown`；告警/状态行必须带 `tree=` 让人看出比的是哪棵树。
- 多 worktree 的额外可见性（可选）：状态面同时打印 `checker_tree` 与 `HEAD(checker_tree)`，两者任一与 serve 侧不同就标 `cross-tree`——**只做状态面提示，不升级为告警**（不同 worktree 停在不同 commit 可能是合法的）。

#### §5.6 `_mw_code_newest_mtime` 的 skip 集（实测）

```
packages/multi-workers 下被 _mw_code_newest_mtime() 计入的文件 = 71 个 / 1,305,650 B
  其中 test/ 下 = 49 个（69%）  autopilot/ = 16  其余顶层 runtime 文件 = 6
  test/ 下的样本: test/fixtures/autopilot-config-corpus.json, test/fixtures/target-config-cases/0NN-*/case.json,
                  test/golden/target-baseline/{single,dual}.json
  runtime 摘要（71 文件、含 test/）实测耗时 7.6 ms
  skip 集现状（两侧一致）: 目录 __pycache__ / dist / .tmp；文件名前缀 test_ / _
```

- **漏洞 1（假报）**：`test/` 只是目录名，没有被跳过（只有 `test_xxx.py` 这类**文件名**被跳过）。改任何 fixture ⇒ 最新 mtime 前移 ⇒ 健康 serve 被判 stale。本仓 fixture 数量与改动频率都不低（49/71 的输入面），且 `test/fixtures/target-config-cases/*/case.json` 是活跃演进面。⇒ 目录 skip 集加 `test`（C16），并在 TS 侧同步（`mw-runner.ts:224-256` 的 walk 里 `if (e.name === "__pycache__" || e.name === "dist" || e.name === ".tmp") continue;` 加 `|| e.name === "test"`）。
- **漏洞 2（`_` 前缀副作用）**：文件名以 `_` 开头即被跳过（本仓无此命名的 runtime 文件，但未来若新增 `_helpers.py` 会被漏掉）。**接受**：这是既有约定，改动它会动到两侧 parity 与 A3 语义，收益不明确。
- **漏洞 3（只看后缀）**：`.yml`（`dispatch.yml`）、`.md`（skills）不计入——结论正确（serve 不 import 它们），但要注意 `providers.json` 计入了（对，`load_providers` 读它）。
- **`dist` 被跳过**：正确（bundle 产物；其陈旧由 `mw update-env` 的 A1/A1b/A2/A2b 与 `repo_bundle_anchor`/`sourcemap_drift` 负责）。本设计的漂移自检**只**管 `serve.meta.code_dir` 代表的 Python 侧，**不合并** bundle/dist 漂移（判据、修法、重启成本都不同，且本卡不做 spec 级取舍）。

#### §5.7 缩写 hash 长度不一致（实测）

```
git rev-parse --short HEAD      -> cc9a46a1a                (9 位；长度随对象库规模自动伸缩)
git rev-parse HEAD              -> cc9a46a1ad1ebb35eb1a5d96d8101c46cd3b78ad  (40 位)
纯文件读 .git/HEAD + refs/heads/dev/AgentTeam -> 同一个 40 位 OID
```

⇒ 写入 `commit` = 40 位；比较用**归一化后的全等**（不做前缀匹配，避免"7 位相等但 9 位不等"的模糊语义）；显示时截 9 位。若实现者图省事写成 `_git_head_short`，结果是**每 tick 必报漂移**（`cc9a46a1a` != 40 位串），且限频键每次相同 ⇒ 只报一次，但状态面会永久显示 STALE。这是本卡发现的最容易踩的实现陷阱。

#### §5.8 删除 / 重命名 / 新增对两条判据的可见性

| 变更 | HEAD | 最新 mtime | digest | mtime 判据 | digest 判据 |
|---|---|---|---|---|---|
| 改一个已有 `.py` | 不变（未提交） | 前移 | 变 | 抓到 | 抓到 |
| 删一个已有 `.py` | 不变 | **不变** | 变 | **漏** | 抓到 |
| 重命名 `.py` | 不变 | 前移（新名文件是新写的） | 变 | 抓到 | 抓到 |
| 新增一个 `.py` | 不变 | 前移 | 变 | 抓到 | 抓到 |
| `git commit` 掉 dirty | 前移 | 不变 | **不变** | 不报 | 不报（正确） |
| `git pull` 覆盖文件 | 前移 | 前移 | 变 | 抓到 | 抓到 |
| touch 一个文件（内容不变） | 不变 | 前移 | **不变** | **假报** | 不报（正确） |

⇒ digest 是唯一"零漏报 + 零 touch 假报"的判据；mtime 保留的价值是**提供漂移起点时间**与**旧 meta 回退**。

#### §5.9 "合并新守护后必须重启 serve" 如何变成机器可检

- 判据链：新增守护 ⇒ 身份采集器版本变化 ⇒ `SERVE_META_SCHEMA` 递增 ⇒ 老 serve 的 meta 缺 `schema`（=0）或低于当前值 ⇒ `capability=stale` ⇒ **drift/schema-stale** 告警 + `mw status`/面板常驻 `CAPABILITY DRIFT … -> /mw restart`。
- 与"检查单"的本质差别：
  1. 判据是**落盘事实**（写者自己的 schema 声明）而不是"提交信息里是否有新守护"的推断；
  2. 判据在**每次**按需调用时重算，因此不会随文档/记忆过期（RQ-3 §3.5 缺陷 A 的正面修复）；
  3. 判据对**存量**成立（缺字段 = 0 < 1），无需先重启一次。
- 反面：若实现时忘记递增 `SERVE_META_SCHEMA`，capability 判据失效——但**内容判据仍在**（新增守护必然改动了 runtime 文件，serve 的 mtime 基线早于该改动 ⇒ content-changed）。两条判据互为兜底，这是"schema + digest"双判据的额外收益。
- 还需一条**实现期纪律**（写进 design.md 的实施清单，并在测试里锁）：任何改动 `serve.meta` 身份字段集合/语义的提交，必须同步递增 `SERVE_META_SCHEMA`；单测断言 `SERVE_META_SCHEMA >= 1` 且字段集合与常量表一致（防止"加了字段忘了提 schema"）。

#### §5.10 meta 残留 / PID 复用

- serve 崩溃（强杀）不会走 `finally` ⇒ `mw.pid` 与 `serve.meta` 都残留；OS 随后可能把该 PID 给别人 ⇒ `check_pid` 通过，但那个"serve"与 meta 无关。此时判据可能给出**看似新鲜的结论**（meta 的 started_at_ms 与真实进程无关），也可能给出"陈旧"的假报。
- 处置：§4.6 的 OS 探针（`|os_start − meta.started_at_ms| > 60s` ⇒ `identity mismatch` 状态面告警）；另外 `mw doctor --fix` 已有"stale PID 清理"路径（`doctor_fix`），可把"PID 存活但 meta 与之不符"纳入同一修复动作（**决策点**：修 = 删 PID+meta 还是只报？建议只报，删由 human 决定）。
- 本卡实测 FeatureMigrator 的 meta 与 OS 启动时间相差 1.0 s（正常路径），说明该阈值不会误伤正常进程。
### §6 改动面 / 生效路径 / 测试面

#### §6.1 改动面（相对种子 RQ-3 §4.1 的 W1..W12 的增量与替换）

| # | 文件:落点 | 内容 | 相对种子 |
|---|---|---|---|
| W1 | `mw.py:122-131 _write_serve_meta` | 写 §2.1 的新字段 + temp/`os.replace` 原子写 | 扩：加 `code_digest` / `schema` / `written_at_ms`；`commit` 改 full OID；原子写同种子 |
| W2 | `mw.py` 新 helper（挨着 `_mw_code_newest_mtime`） | `_runtime_code_files(root)` / `_runtime_digest(root)` / `_git_head_oid_fileread(root)`（上溯 `.git` + `gitdir:` + `commondir`） | 新 |
| W3 | `mw.py:4097 _git()` | `timeout=`（`commit` 用不到；`dirty` 用 3 s）+ win32 `CREATE_NO_WINDOW` + `except (OSError, subprocess.SubprocessError) -> None` 语义 | 同种子 W2 |
| W4 | `mw.py:5131 _mw_code_newest_mtime` | 加 `root: pathlib.Path \| None = None` 参数（**函数体内**读 `_SCRIPT_DIR`，保 monkeypatch 语义）；`relative_to(root)`；skip 集加 `test` | 扩：种子只提"复用"，未提参数化与 skip 修正（C16） |
| W5 | `mw_common.py`（挨着 `pid_file:2180`） | `SERVE_META_SCHEMA=1` / `serve_code_verdict()` / `read_serve_meta()`（容半截 JSON ⇒ `{}`）/ `process_start_ms()`（可选） | 同种子 W4，但判据换成 digest 权威 |
| W6 | `conductor.py`（新 `_check_code_drift`，插在 `tick():2880` 的 `_remind_pending_gates` 之后） | 60 s 节流 + 判据 + 双通道告警；把 `_emit_roadmap_failure:2603-2620` 的三段（查重/ stderr / timeline）抽成通用 `_emit_alarm` 共用 | 扩：复用 `_timeline_has_event` 做持久去重（C12）、判定 `history-only` |
| W7 | `conductor.py`（新 `_recheck_restart_gates`，同 tick 邻域） | §3.7 的重启后复核 | 新（种子只在 RQ-3 里作为 P2 提及，无实现设计） |
| W8 | `mw.py:486-504 cmd_status` | 追加一行 serve code 判定（退出码不变） | 同种子 W9，但用统一判据 |
| W9 | `mw_common.py:3624 doctor_report` + `:3401 _doctor_issues` + `format_doctor_text` | 新 `serve_code` section；`drift` ⇒ issue | 扩：种子 W9 只在 `mw status` 提了一行 |
| W10 | `mw.py:5362-5390`（A3） | 调 `serve_code_verdict()`；基线改 `meta.code_dir`；detail 含 commit 对 | 同种子 W8 + 基线修正 |
| W11 | `mw-runner.ts:198-289`、`monitor.ts:340-355`、`ui-bridge.ts:3413-3419` | `MwServeMeta` 增字段；`serveStaleness` 基线改 `meta.code_dir`，判据同 §1（TS 需重实现 digest，见 §6.3） | 同种子 W10/W11，加"digest 跨语言一致"要求 |
| W12 | `UPDATE.md:40`（A3 行）+ `packages/multi-workers/CHANGELOG.md` + `packages/coding-agent/CHANGELOG.md` | 文档与 changelog（`[Unreleased]/Fixed` 或 `Added`） | 同种子 W12 |
| — | **明确不做** | 不新增 config 键（60 s 间隔用模块常量，AC-011）；不新增 timeline `ev` 类型（用 `config`）；不新增日志文件/通知类型（P-01）；不合并 bundle/dist 漂移；不自动重启（C15） | — |

#### §6.2 生效路径（P-04 标注）

| 生效时机 | 涉及 | 后果 |
|---|---|---|
| **需 `/mw restart`** | W1/W2/W3（新字段要新 serve 写）、W6/W7（新 tick 要新 conductor） | 老 serve 的 meta 永远缺 `schema`/`digest` ⇒ 只能走 mtime 回退 + capability 命中（**这正是"合并新守护必须重启"的机器判据本身**） |
| **立即** | W5/W8/W9/W10（`mw status`/`doctor`/`update-env` 都是新进程）、W11（TS `/reload` 或新窗口） | 首次上线后、第一次 `/mw restart` 之前，**唯一**能发现存量漂移的通道 ⇒ 因此检测绝不能只放在 conductor 里（与种子 RQ-3 §4.2 结论一致） |
| 需 `build --install` + `/reload`（TS） | W11 | 与既有 stale-serve 修复的部署路径一致（`UPDATE.md:40`） |

#### §6.3 Python / TS 两侧判据一致性的硬要求

- TS 侧若要复现 `code_digest`，必须逐字实现同一算法：**相对 posix 路径排序**（`path.relative(...).split(path.sep).join("/")`）、`rel + "\0" + bytes`、sha256、`"sha256:" + hex`。编码/排序/换行任一差异 ⇒ 两侧结论相反（VN/CRLF 尤其危险：摘要按**字节**算，CRLF 文件在两侧读到的字节相同，不受影响；但如果一侧做了 EOL 归一化就会分叉）。
- 若 TS 侧**不做** digest，则必须显式接受"TS 比 Python 更保守"（会把 `history-only` 报成 stale）——与既有 stale-serve 的取舍一致（TS 注释 `mw-runner.ts:266-271` 明确"false positive 的代价只是一次重启提示"）。**推荐做 digest**，并在 `autopilot-config-parity` 类型的一致性测试里加一棵两侧都能读的 fixture 树，断言两侧 digest 字符串**逐字相同**。
- **第 3 个解析面**（spec §5 坑点 2）：TS 里读 `serve.meta` 的地方不止 `readServeMeta`（还有 `monitor.ts:340-355` 自己再读一次 `readServeMeta()?.startedAtMs`）。加字段后 `monitor.ts` 与 `ui-bridge.ts` 都必须走 `serveStaleness()` 的结论，不得各自重算判据。

#### §6.4 要改 / 新增的测试

| 侧 | 文件 | 内容 |
|---|---|---|
| Py | `test_serve_meta.py:21-31`（`test_write_serve_meta_shape`） | 断言全部新字段 + `code_dir` 语义不变 + `schema == SERVE_META_SCHEMA` + 不留 `.tmp` 残留 |
| Py | `test_serve_meta.py`（新增） | 无 git 目录 ⇒ `commit is None`、`dirty_* is None`、不抛（fail-open） |
| Py | **新增** `test_serve_code_drift.py` | §4.7 的判据矩阵（含"删除不可见""commit-of-dirty 假阳性""dirty 不误报""capability""跨 worktree""去重两层"） |
| Py | **新增** `test_serve_code_drift_cli.py` | §4.7 的子进程契约测试（`status` / `doctor --json` / `update-env`），含 PATH 无 git 的反例 |
| Py | `test_update_env.py:101-116`（`test_mw_code_newest_mtime_skip_rules`） | 增加 `test/` 目录用例（C16）；**注意**：`test/` 是目录名，`test_x.py` 是文件名，两者都要断言 |
| Py | `test_update_env.py:77-80`（healthy world fixture） | **必须改数据**：`code_dir: "fake"` 在新判据下 ⇒ `code-dir-missing` ⇒ `undecidable`，会让 `:294 assert by_id["serve"]["status"] == "ok"` 变红。按 P-03（旧夹具改数据不改判据）把 `code_dir` 指向真实存在的目录（或删除该键以走"回退检查者树"分支） |
| Py | `test_update_env.py:374-389`（stale world） | 该 fixture 的 meta **无** `code_dir` ⇒ 走回退分支，语义不变；可保留 |
| Py | `test_mwds_t25_version_semantics.py:234-273` | 若 `version` 落 meta，补"单源 = `_framework_version()`"断言 |
| Py | `test_autopilot_conductor.py`（新增用例） | 每 60 s 节流；`history-only` 不告警；同日重复调用只 1 条 stderr + 1 条 timeline；`_timeline_has_event` 命中时不重发 |
| Py | **新增**（并入 `test_autopilot_conductor.py` 或新文件） | §3.7 重启后复核：auto 答复 + `answered_at > T_restart` ⇒ 1 条 `config`；人工答复 / `created_at > T_restart` / 重启前终态 ⇒ 0 条 |
| TS | `test/extensions/agent-team-loop.test.ts:987-1022` | `readServeMeta` 解析新字段（缺字段仍可用）；`serveStaleness` 的 digest→mtime→commit 分支；`code_dir` 优先于 `findMwPy()` |
| TS | `test/suite/dual-root-worker.test.ts:228-250`（VC-016） | 增加"`serve.meta.code_dir` ≠ `findMwPy()` ⇒ 以 `code_dir` 为准"的反例 |
| TS | `test/suite/autopilot-monitor.test.ts:67-72 / :737-770` | fixture 迁到新字段（保持旧字段也能跑）；`STALE CODE … -> /mw restart` 骨架断言不变 |
| TS | `test/suite/autopilot-console.test.ts:1291-1310` | enable ⇒ restarted 文案不变 |

## 残留与未验证

1. **未实测 git 挂死与 `CREATE_NO_WINDOW` 弹窗**：§5.3 的"启动楔子"是从代码路径推出的（`_write_pid` 早于 `_write_serve_meta`、`waitForMwStart` 只看 PID 存活、`mw stop` 只等 30 s），**没有**真的让一次 `git` 挂住来复现。同理，`CREATE_NO_WINDOW` 缺失时的闪窗行为只由 `mw.py:277-278` 的既有用法反推，未实测。
2. **未复现 linked worktree**：本机 `git worktree list` 只有 `H:/git/Multi-Workers cc9a46a1a [dev/AgentTeam]` 一棵；`.git` 为文件 + `commondir` + `packed-refs` 的分支（§5.5）**未构造反例**。纯文件读在本机的两条路径（loose ref 与根 `packed-refs`）都实测通过，worktree 分支只有代码级推演。
3. **所有"入口输出"是设计形态，不是实测输出**：本卡是只读卡，未落地任何代码。实测的部分只有**判据的输入**——`.mw/serve.meta` 字段、进程启动时间、runtime 文件 mtime、`.git/HEAD`/loose ref/`packed-refs`、`git rev-parse` 输出、runtime 文件集与摘要耗时、时间线保留窗口、`gate-reminder` 计数、`_remind_pending_gates` 的引入提交。§4.7 的期望输出是设计断言，需实现后逐条验。
4. **未实测 digest 在异常 `code_dir` 下的行为**：例如 `code_dir` 指向 npm 安装副本 / 含数万文件的目录 / 网络盘时 7.6 ms 的结论不成立；本卡只在本仓 `packages/multi-workers`（71 文件 / 1.3 MB / 本地 NTFS）实测。
5. **未验证 `_timeline_has_event` 对超长 `detail` 的行为**：告警行含两个 40 位 hash + 多时间戳，长度估算 ~350-420 字符。`timeline.append` 未见单行长度上限，但**未实测**；若存在上限（或 TS 侧解析对行长敏感），需要把 `detail` 拆成"短 detail + `data{}` 结构化字段"（`timeline.append` 的 `data` 已支持，读端 `_read_events` 原样透传）。
6. **未评估 TS 侧重实现 digest 的风险面**：跨语言字节一致性（排序、分隔符、编码）只做了设计级论证，未写两侧对照 fixture 实测。
7. **`_git_dirty` 返回 `(0,0)` 掩盖 git 失败**（§5.3）：本卡只把它列为 design 决策点，**未评估**改成 `None` 对 A4（framework-source anchor）既有断言与 `test_update_env.py` 的影响面。
8. **doctor issue 化的回归面未实测**：把 stale serve 升级为 `issues` 会让 `mw doctor` 退出码 1。已核实 TS `doctorMw` 容忍退出码 1（`mw-runner.ts:425-427`），但**未跑** `test_serve_doctor.py` 全量确认没有别的地方依赖 `summary.healthy`。
9. **§4.6 的 OS 探针在非 Windows 平台未实测**：`/proc/<pid>/stat` 字段 22 + `/proc/stat` 的 `btime`、以及 `ps -o lstart=` 的解析只在设计层给出，本机是 Windows。也没有验证"PID 复用"反例（需要真实制造一次 PID 回收）。
10. **`psutil` 可用但未采用**：本机 `import psutil` 成功（`find_spec` 非 None），但全仓零使用、无声明依赖 ⇒ 按 `AGENTS.md` 不引入；若 design 阶段认为 ctypes 方案在 macOS 上不可行，需重新评估这条决策。
11. **未定 `EXPECTED_SCHEMA` 的递增责任机制**：§5.9 给了"测试锁常量 + 字段表"的建议，但没有可执行的门禁（例如"改了 `_write_serve_meta` 字段集合却未递增 schema ⇒ 测试红"的具体实现）。
12. **重启后复核的成本未量化**：§3.7 只在前 N 次 tick 执行；gate 目录很大时（历史上有过 6684 gates/12h 的 flood，见 CHANGELOG）的扫描成本未实测。
13. **未决定 `written_at_ms` 是否值得保留**：它的唯一用途是把"进程启动"与"meta 落盘"区分开（也是 §4.6 阈值 60 s 的依据）；若无消费者可以删掉，本卡倾向保留。
14. **未评估 `mw status` 新增行的既有消费者**：grep 显示没有任何测试锁定 `[mw status]` 文本（只有 `test_autopilot_conductor.py:270` 提到 `conductor_status`），但**未**检查 TS `runMwCliRaw` 的所有调用点是否解析 stdout。
15. **`gate-reminder` 计数与进程证据的口径**：本卡实测 213,696 条事件（种子报告 212,609 条，同一现场不同时刻）⇒ 计数是**增量口径**，引用时必须带采集时刻；本卡未记录采集时刻的精确秒级时间戳（约 2026-10-13T04:10Z）。

## 上下文来源

| 来源 | 用途 |
|---|---|
| `packages/multi-workers/mw.py`: 46 / 114-137 / 140-198 / 223-231 / 245-246 / 271-273 / 283-288 / 398 / 456-466 / 486-504 / 1165-1186 / 1999-2001 / 2391-2399 / 2809-2815 / 4097 / 4350-4354 / 4507 / 5112 / 5131-5149 / 5155 / 5175-5185 / 5187 / 5362-5390 / 5607-5620 | serve 生命周期、`serve.meta` 写删、日志通道、`_git*`、`_mw_code_newest_mtime`、A3、`cmd_status`、argparse、原子写先例、`CREATE_NO_WINDOW` 先例 |
| `packages/multi-workers/mw_common.py`: 2180-2226 / 2289 / 2637 / 3401 / 3624-3650 | `pid_file`/`check_pid`/`_is_alive_win32`（ctypes 先例）、`_doctor_service`、`_doctor_issues`、`doctor_report` sections |
| `packages/multi-workers/autopilot/conductor.py`: 108 / 1899 / 2508 / 2512 / 2594-2660 / 2683-2751 / 2880-2890 / 6608 / 7173 | tick 插入点、`_timeline_has_event`（持久去重载体）、`GATE_REMINDER_EVENT`、alarm 双通道封装、`answered_by=conductor-auto:` 的唯一写入点、`conductor_status` |
| `packages/multi-workers/autopilot/timeline.py`: 60-140 / 282-352 / 422-500 | `EVENT_TYPES`（`config` 在白名单内）、`append(ev,key,stage,detail,data)`、`ROTATE_THRESHOLD_BYTES=10MB` / `ROTATE_GENERATIONS=2`、`tail_events(limit)` |
| `packages/multi-workers/autopilot/gates.py`: 92-152 / 210-260 / 326 / 689-712 | 冻结字段表与 `answer_source`/`auto_policy_id`（本次无需启用）、`Gate` 字段、`_write_atomic` 先例 |
| `packages/multi-workers/autopilot/config.py`: 83-134 | 20 键冻结 schema + `poll_interval_sec=4` ⇒ 为什么 60 s 用模块常量而非 config 键 |
| `packages/multi-workers/test_serve_meta.py`（全文）/ `test_update_env.py`: 70-120 / 374-389 / 440-460 | 现有断言面与**必须改数据的 fixture**（`code_dir: "fake"`） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`: 29-55 / 150-176 / 195-345 / 414-431 | `findMwPy`、`waitForMwStart`、`readServeMeta`/`mwCodeNewestMtimeMs`/`serveStaleness`/`restartMw`、`doctorMw` 容忍退出码 1 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`: 65-110 / 234-300 / 335-360 / 750-800 | `MonitorServe`、`scanPendingGate`、serve 采集与 `STALE CODE` 渲染（detail 截断 + 保住 `/mw restart`） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`: 3408-3419 | `/mw status` 交互恢复面 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`: 600-640 | `/autopilot enable` 的 stale ⇒ restart 语义（Python 不得与之抢重启） |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts`: 987-1022 / `test/suite/dual-root-worker.test.ts`: 205-250 / `test/suite/autopilot-monitor.test.ts`: 60-80,737-770 / `test/suite/autopilot-console.test.ts`: 1291-1310 | 要改的 TS 测试面 |
| `UPDATE.md`: 21 / 40 / 66 / 107-109 / 138-139 / 168 / 182 | A3 行（含 env 不落盘的 P-015 备注）与"每项目 `/mw restart`"的部署路径 |
| `packages/multi-workers/CHANGELOG.md` [Unreleased] / `packages/coding-agent/CHANGELOG.md` [Unreleased] | 文档落点（`### Added` / `### Fixed`，不得改已发布段落） |
| `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md`（4,217 B，本次逐字读过） | P0-① 的告警文案范例与"期望/实际 + 多久 + 修法"三要素、P0-②、P1×2、P2 部署检查单原文 |
| `E:\CLI_workspace\FeatureMigrator\.mw\{serve.meta,mw.pid,conductor.pid,conductor.log,mw.log,launcher-beat.*}` | 现场实测（§4.1 / §5.1 / §5.10） |
| `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\{timeline.jsonl,timeline.jsonl.1,timeline.jsonl.2}` | 保留窗口 12.8 天与 `gate-reminder = 0 / 213,696` 的实测 |
| `H:\git\E2Feature\.agenticdoc\AUTOPILOT-HANDOFF.md`（第 454 行：`mw update-env` 实测 `serve = ok（PID 140964，代码新鲜）`，并注明启动横幅的 `/mw restart` 是"过期信息，无需重启"） | "verdict 会过期"的散文缓存实证（RQ-3 §3.5 缺陷 A），本卡作为设计动机引用 |
| `H:\git\Multi-Workers\.mw\{serve.meta,mw.pid,mw.log}` + `git rev-parse` / `git show <ref>:<path>` / `git log -S` | fresh 对照（PID 168160）、`mw.log` 32 条启动行、缩写 hash 长度、`_remind_pending_gates` 的引入提交 |
| 本 key 的 `spec.md` §1(E7)/§2(AC-005,AC-006,AC-011,AC-012)/§3(P-01..P-08)/§4/§5/§6、`pm-state.md`、`tasks/T-07-drq3-drift-selfcheck.md`、`evidence/research/spec-rq3-serve-metadata-drift-20261013.md` | 需求、坑点、种子结论与差异口径 |

**本次使用的方法**：全仓只读（`read` / `grep` / `ls` / `git log` / `git show` / `git rev-parse` / `git worktree list` / `Get-Process` / `Get-ChildItem` / 只读 `python -c` 复算脚本）；`H:\git\E2Feature` 与 `E:\CLI_workspace\FeatureMigrator` 仅只读；未运行 `mw` 的任何子命令（避免触发 `update-env --apply` / `doctor --fix` 之类的写路径）；唯一写入是本证据文件本身。