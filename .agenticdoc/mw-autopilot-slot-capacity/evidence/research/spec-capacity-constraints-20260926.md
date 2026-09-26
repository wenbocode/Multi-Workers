# Research: 并行容量约束 —— 机器与基础设施层面先坏在哪（RQ-2）

> key: `mw-autopilot-slot-capacity` · 角色：spec 期调研（只读，未改任何代码）· 2026-09-26
> 数据窗：既有证据 2026-09-09…2026-09-26；实时采样 2026-09-26T07:29–07:40Z（本地 15:29–15:40）

## TL;DR

- **proxy 是全局共享的单进程**（固定端口 7001/7003/7004），不是每项目一个；今天本机所有 worker 走 `timi` **直连**，`mw serve` 打印 `proxy disabled; direct routes only` ⇒ 当前并行度不经过代理。代理真启用时每端口有 **8 条上游连接池**这一硬顶。
- **凭证隔离是"剥全部 + 注入唯一一个 key"**；同一 provider 的 N 个 worker 拿到**同一个 key 值**，客户端无任何限流器；726 个任务目录里**没有观测到 429/rate limit/quota**。
- **进程/内存不是首个瓶颈**：实测 10 个在飞 worker（本机现况）；有 task.md 的 8 个 pi worker WS 中位 185 MB / 均值 204 MB / 最大 373 MB；190 GB RAM / 32 逻辑核，10 worker 时 CPU 21–26%、可用内存 57 GB。真正的内存风险是**单个失控工具子进程**（151 GB 事故锚点 + 本机当前 89 GB 的 `tools/chatbox/serve.py`）。
- **账本类文件全部有锁**（`_workers.parallel`/`_index.parallel`/`_workers.acked`/`_autopilot/config.json`）；**没锁的是 tracked 产物 `packages/coding-agent/dist`（953 个文件，只有"脏树拒跑"护栏）和每任务目录的 trace/output**（后者的真实事故形态是"事后改写他人轮次 output.md"，靠来源校验而非锁兜住）。
- **活动看门狗误杀已经发生，而且发生在当前并行度下**：14 次 idle 机器判据，死亡时刻并发 = 1‥3（均值 2.14）。"并发↑ ⇒ 误杀↑"目前只有机制推理（`[推断]`），没有高并发对照样本（≥4 并发只占 1.2% 的分钟）。
- **实测并发峰值**：全机 7（3 个项目，2026-09-22T09:24:03Z）；单 key 6（MW，2026-09-26T06:19:31Z，超过 `max_parallel_keys=2`）⇒ **key 层 gate 管不到 worker 层，worker 层无上限**（`--max-workers` 默认 None 且无配置键接线）。

## 决策问题

支撑 spec §1.1 的两层并行度、§4 风险 1–4 的量化、以及 U-4/U-5 的边界判定：把并行度从 2 往上抬时，

1. LLM proxy 的进程/端口/路由模型能承载多少并发 worker，谁是硬顶；
2. 凭证隔离在并发下的真实含义（同 key 共享是否天然受限）；
3. 每 worker 的资源开销（实测）+ 本机余量；
4. 并行度上升会放大哪些写入竞争，哪些写有锁、哪些没有；
5. 活动看门狗/墙钟兜底在"机器更忙 ⇒ 单步变慢"时会不会误杀。

不做：给出"应该改成 N"的结论（RQ-4 负责）。

## 调研方法与出处

只读探测（命令留痕，未改任何文件）：

- 代码走读：`packages/multi-workers/{mw.py,launcher.py,mw_common.py,proxy_multi.py,providers.json,dispatch-table.md,README.md}`、`autopilot/{conductor.py,dispatch.py,config.py,xkey.py}`、`packages/coding-agent/src/extensions/agent-team-loop/{worker/worker-mode.ts,shared/{file-lock.ts,index-store.ts,worker-store.ts,ack-store.ts}}`、外置依赖 `E:\CLI_workspace\claude-hook\timi-proxy-cli\src\timi_proxy_cli\proxy.py`。
- **实测 1（并发重叠）**：解析三项目 `.agenticdoc/<key>/workers/<task>/trace.log` 的 `[START] <iso> …` / `[END] <iso> …`，构造区间后扫描事件点求"同时存活 worker 数"与"同一 key 同时存活数"。样本：729 个任务目录，717 个有效区间（12 个无 [START] 或时间不可解析）。**测量欠账**：仅 1/729 的 trace.log 有多个带时间戳的 [START]（重试通常换新目录），故"取首个 [START]、末个 [END]"不会系统性高估并发。
- **实测 2（时间占比）**：09-20T00:00Z–09-26T08:00Z 每分钟采样一次并发数，共 9120 分钟。
- **实测 3（进程/内存/负载，2026-09-26T07:29–07:40Z）**：`Get-CimInstance Win32_Process`（按命令行过滤 `pi-coding-agent` / `mw.py serve|launcher.py|conductor.py|proxy_multi`，取 `WorkingSetSize`）、`Get-NetTCPConnection -State Listen`、`Get-Counter '\Processor(_Total)\% Processor Time'` / `PhysicalDisk(_Total)% Disk Time` / `Memory\Available MBytes`（各 3 采样）。
- **实测 4（失败态）**：扫 726 个任务目录的 `worker.log|output.md|trace.log`：`[END] … exit=` 分布、`output.md` 的 `idle timeout: no activity for Ns` 机器判据、`429|rate[ _-]?limit|insufficient_quota|overloaded_error` 模式。
- 台账/事故锚点：`.agenticdoc/_pitfalls.md`（P-015/017/018/019）、`.agenticdoc/mw-worker-tree-kill/evidence/research/spec-worker-exit-orphan-2026-09-19.md`、`.agenticdoc/mw-autopilot-verify-cli/{spec.md,achieved.md,key-decision.md}`、`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\worker-idle-timeout.md`、`.mw/mw.log|launcher.log`、`packages/{multi-workers,coding-agent}/CHANGELOG.md`。
- 临时脚本写在 `%TEMP%\rq2\*.py`（P-001：不用 PowerShell 多行 `python -c`），跑完已删除。

## 发现

### 1. LLM proxy 与端口

**[事实] 一个进程、多个端口、全局共享**

- `proxy_multi.py` 在**同一个 Python 进程内**起 2–3 个 `LocalProxyServer`：`run(pi_port, claude_port, deepseek_port)` → `_start_proxy_with_retry(...)`（`proxy_multi.py:36-75`、`run` 在 `:76-104`），端口默认 `--pi-port=7001 --claude-port=7003 --deepseek-port=None`（`proxy_multi.py:131-136`）。
- `mw serve` 决定是否拉代理：只有**端口路由**（`providers.json` 里带 `port` 的 claude / claude-cli / deepseek）有凭证时才 spawn（`mw.py:291-306`）；否则打印 `no proxy-routed credentials (claude/claude-cli/deepseek) - proxy disabled; direct routes only`（`mw.py:302-306`）。
- **共享而非独占**：`proxy_already_running = _port_is_bound(args.pi_port) and _port_is_bound(args.claude_port)`（`mw.py:299`，`port_is_bound` 在 `mw_common.py:1612`）；命中则 `proxy=shared` 复用已存在的代理（`mw.py:307-312`）。⇒ **代理是机器级单例**（端口固定），不是"每项目一个进程"。
- 端口是**固定默认值**，只能靠 CLI 覆盖：`mw.py:5040-5042`（`--pi-port 7001 / --claude-port 7003 / --deepseek-port None`），`mw start` 转发（`mw.py:417-428`），`mw bootstrap` 硬编码 7001/7003（`mw.py:4494-4495`）。launcher 端口镜像自 serve（`mw.py:322-326`）。
- 实测（07:33Z）：本机 9 个 `mw serve` 进程（JCodingAss、`H:\git\E2Feature`、`H:\git\Multi-Workers`、`E:\CLI_workspace\FeatureMigrator`、`E:\CLI_workspace\OverCode`、`E:\UEMigrator`、`F:\weekly-report-knot\MW`、`C:\Users\wenbozhou`、`%TEMP%\mw-bs-e2e`），只有 **1 个** `proxy_multi.py`（pid 63128，同时监听 127.0.0.1:7001 与 :7003，`Get-NetTCPConnection`），父进程是 JCodingAss 的 serve（pid 88908）⇒ "一个代理服务所有项目/所有 worker"已实测成立。

**[事实] 哪些 provider 走代理、哪些直连**

| 路由 | 通道 | 锚点 |
|---|---|---|
| pi + timi（`model: timi/...`） | **直连**（注入 `TIMI_API_KEY`，无 base_url） | `launcher.py:234-249`、`dispatch-table.md` 第 4 行 |
| pi + zai-coding-cn | **直连**（`ZAI_CODING_CN_API_KEY`） | `launcher.py:251-267` |
| pi + openai-codex / codex CLI | **直连**（用 codex 自身配置，env 只剥不注） | `launcher.py:269-276`、`:301-307` |
| pi + anthropic / deepseek（`claude/…`、`deepseek/…` 前缀） | **直连**（注入对应 key，`*_BASE_URL` 仅当 serve env 已设时透传） | `launcher.py:278-299` |
| claude CLI（`claude-cli`）、pi 空 provider、deepseek CLI | **走代理**：注入 `http://localhost:<port>` + key | `launcher.py:309-320`（`route_for` 默认 pi→`claude`(7001)，`mw_common.py:101-104`） |

- `mw serve` 侧的可用性判定来自 `route_precheck`（`mw_common.py:1390+`）；本机 `providers.json`（`packages/multi-workers/providers.json`）里 `timi` / `zai-coding-cn` **无 port 字段** ⇒ 不算 proxy 路由。
- 实测本机现况：`.mw/mw.log` 中 MW 多次重启全是 `no proxy-routed credentials … proxy disabled; direct routes only (timi / zai-coding-cn / codex-native)`（最近一次 serve pid 78608，10:30:51）；`.mw/proxy.log` 最后写入 2026-08-22。所有在飞 worker 的命令行是 `pi --provider timi --model deepseek-v4.1-flash -p …`（`Get-CimInstance` + `.mw/dispatch.yml` 全为 `timi/...`）⇒ **0 个 worker 经过代理**。

**[事实] 代理启用时的并发硬顶 = 每端口 8 条上游连接**

- `_ConfiguredThreadingHTTPServer(ThreadingHTTPServer)`，`daemon_threads = True`（无线程上限）= 每请求一线程；上游连接由 `_UpstreamPool` 管理，`size: int = 8`，`acquire()` 用 `queue.Queue.get()`（**无超时**）在池满时阻塞（依赖侧 `timi-proxy-cli\proxy.py:97-121`，池在 `:243-246` 按端口各建一个）。
- 流式 LLM 请求在整个生成期间占用一条连接 ⇒ **同一端口最多 8 个并发生成流**；第 9 个 worker 会在 `pool.acquire()` 静默排队（不报错、不超时，直到有槽释放）。`proxy_multi.py` 起 2–3 个端口 = 2–3 × 8 条。
- `[推断]` 只有在启用 claude/claude-cli/deepseek 路由后此顶才生效；它比 `max_parallel_keys` 高，所以在"2 槽"下不会被撞到，但在更高并行度 + 端口路由组合下会成为**静默排队**型首坏点。

**[事实] leftover 端口会让 serve 直接死**

- `proxy_already_running` 要求**两个端口同时被占**（`mw.py:299`）。若只有 7001 被遗留进程占着，serve 会尝试 spawn 新代理 → `_start_proxy_with_retry` 8 次重试（3s 间隔）后抛错（`proxy_multi.py:50-75`）→ 子进程退出 → `mw serve` 判定代理死亡并 FATAL 退出（`mw.py:360-366`）。`[推断]` 这是"多项目 + 残留代理"下的真实启动失败面（本机当前 9 个 serve 全部带同一对默认端口，靠 `shared` 分支避开）。

### 2. 凭证隔离与同 provider 并发

**[事实] 剥离集合与注入点唯一**

- `_stripped_env`（`launcher.py:90-110`）：从**全量继承的 os.environ** 起，pop 掉 ① `providers.json` 里声明的**全部** credential env 名（`mw_common.credential_env_names`，`mw_common.py:1082-1095`）、② 遗留额外项 `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`TIMI_BASE_URL`（`mw_common.py:61-65`）、③ **所有** provider 的 `base_url_env`、④ RAG 声明的 `mcp.token_env` 名（存在 RAG 配置时）。之后 `_build_env` 的每个分支只**注入恰好一个** key（`launcher.py:223-323`），基址只在代理路由下被显式写成 `http://localhost:<port>`（`launcher.py:320`）。
- 注意：任务正文提到的 `mw_common._partition_token_names` **不是**凭证分区函数——它是 toolchain 占位符 `{parent}/{partition}/…` 的名字表（`mw_common.py:2965-2980`）。凭证一侧的正确锚点是 `_stripped_env` + `credential_env_names`。记下来避免后续笔记引用错锚点。
- 凭证解析链 `resolve_credential`（`mw_common.py:1048-1079`）：env → 文件（如 `~/.pi/agent/auth.json` 的 `timi.key`），**每次 spawn 现读，无缓存**。

**[事实] 同 provider 的 N 个 worker 共用一个 key 值，客户端无并发闸**

- 所有走同一路由的 worker 注入的是**同一个 `value`**（同一个 env 或同一文件的同一字段）⇒ provider 端看到的是同一凭证的 N 路并发；mw/pi 侧**没有任何 per-key 并发计数器或限流器**（全仓 grep `rate|limit|semaphore` 在 launcher/dispatch 无命中）。
- 实测（负面证据）：726 个任务目录的 `worker.log|output.md|trace.log` 对 `429|rate[ _-]?limit|insufficient_quota|overloaded_error` **0 命中**；`_workers.parallel` 状态分布 MW 163 done/11 failed/5 running、E2 455/29/1、JCodingAss 70/2/0（失败率 ≈6%），失败原因里没有限流。
- `[推断]` 在 ≤7 并发的实测范围内，**provider 端限流没有成为首坏点**；但共用一个 key 意味着上限由 provider/端点决定，本仓库没有可观测手段（无 429 计数、无 per-key 并发指标）——这是数据缺口，不是"没有上限"。
- `[事实]` codex 路由（`cli=codex` 与 `pi+openai-codex`）**不注入任何凭证**（`launcher.py:269-276`、`:301-307`），其并发上限完全在 codex 自己的 auth/配置里；凭证隔离在这条路由上表现为"什么都不给第 1 个 worker"。

### 3. 进程与内存（实测）

**[实测] 每 worker 开销**（2026-09-26T07:33Z 快照）

- 打印模式（worker）pi 进程 **10 个**；其中 8 个命令行能解析出 `workers\<task>\task.md`：WS = 127/127/128/165/205/214/288/373 MB ⇒ **中位 185 MB、均值 204 MB、min 127、max 373**。全部 18 个 pi node 进程（含 8 个交互式 PM 窗口）合计 **3.88 GB**，均值 215 MB，min 19 MB、max 539 MB。
- 每个 worker 的进程链 = `launcher.py`（共享）→ `cmd.exe /c pi.CMD …` → `node cli.js …`（实测 pid 13040→115268→103152），node 线程数 47，另有工具调用期的 bash/pytest/node 子进程。⇒ **每个 worker ≈ 2 个常驻 OS 进程（cmd.exe 可忽略 + node ~200 MB）**，工具突发期再叠加子进程。

**[实测] 框架侧常驻开销**

- 9 × `mw serve`（15.4–43.2 MB）+ 9 × `launcher.py`（15.4–30.0 MB）+ 3 × `conductor.py`（43.2/46.1/113.3 MB）+ 1 × `proxy_multi.py`（30.9 MB）≈ **0.6 GB**，进程数 22。`[事实]` 其中 launcher 每 5s 轮询一次（`DEFAULT_POLL_INTERVAL = 5`，`launcher.py:49`；`mw.py:5043`），机器上 = 9 launcher × 12 次/分。
- `[事实]` 有两类**疑似泄漏/遗留**的 serve：`%TEMP%\mw-bs-e2e`（serve pid 66872，存活 258 h）与 `C:\Users\wenbozhou`（serve pid 81332，存活 73 h）——说明 serve 的存活期可以远长于其"项目"的生命周期，机器层面需要清理面（本笔记只记录，不处置）。

**[实测] 本机余量与负载**

- 32 逻辑核（AMD Ryzen 9 9950X 16C/32T）、RAM 189.6 GB、可用 56.9 GB、commit limit 416 GB。
- ~10 个在飞 worker + 8 个 PM 窗口 + 无关开发进程（含 163 MB 的 pytest、71 MB 的 `migrator validate`）下：CPU **23.6/26.3/21.0 %**（3 采样）、`PhysicalDisk(_Total)% Disk Time` **1.5/1.6/1.6 %**、可用内存 58.3 GB。
- `[推断]` N ≤ 20 时按 ~200 MB/worker 计算 ≈ 4 GB，与 RAM 相比不是约束；CPU 也有 ~4× 余量（前提是工具不全是 CPU 密集的 pytest/tsgo/编译）。

**[事实] 真正的内存风险是单个失控工具子进程，不是 N × 200 MB**

- 2026-09-19 事故：idle 看门狗杀死的 worker 留下孤儿 `python probe2.py`，50 分钟涨到 **WS 151 GB / 私有 252 GB**（`packages/coding-agent/CHANGELOG.md:151`；`mw-worker-tree-kill/evidence/research/spec-worker-exit-orphan-2026-09-19.md:16`：孤儿链 已死 worker(60816) → shim(43948) → pythoncore-3.14(62724)）。
- 本机当前就有一个同族实例：`tools/chatbox/serve.py --port 8100`（pid 103904）**WS 89.3 GB / 私有 137.8 GB**，与 mw 无关但占掉近半物理内存 —— 说明"护栏"不在"给 worker 限内存"，而在子进程树终止（`killTrackedDetachedChildren`）+ 看门狗；
- `[推断]` 并发度↑ ⇒ 同时在飞的 bash 工具子进程数↑ ⇒ **撞上失控子进程的概率↑**（p ≈ N·p₁，非平方），但这不是"平均内存 × N"的线性模型能描述的风险。

### 4. 磁盘与文件竞争：哪些有锁、哪些没有

**[事实] 有锁（RMW 全量重写 + tmp/rename 原子替换）**

| 文件 | 锁 | 写者锚点 | 备注 |
|---|---|---|---|
| `.agenticdoc/_workers.parallel` | `.mw/workers.lock` | `mw_common.update_status:1512-1524`、`archive_stale_entries:1532-1545`、`autopilot/dispatch.py:534-547`、conductor orphan 回填 `conductor.py:4030-4032`、TS `shared/worker-store.ts:57-68` | 全量重写：`_write_workers_file`（`mw_common.py:1497-1506`）。规模实测：E2 485 行/127 KB，MW 176 行/35 KB ⇒ 写成本 O(行数) |
| `.agenticdoc/_index.parallel` | `.mw/index.lock` | TS `shared/index-store.ts:59-60/75/95`（tmp+rename `:131-155`）、Python `agentic-task/.../update_index.py:117-144/218-236` | 两侧同锁，claim/demote 原子 |
| `.agenticdoc/_workers.acked` | `.mw/workers.lock` | TS `shared/ack-store.ts:20-21/55-67` | |
| `.agenticdoc/_autopilot/config.json` | `.mw/autopilot-config.lock` | `mw.py:3344-3350`、`mw.py:3483-3489`；TS 侧同路径（`mw-autopilot-verify-cli/achieved.md:26`） | 修前实测两个 console 写者 30 轮**丢 28 次**（`achieved.md:27`）⇒ "没锁时并行写真的会丢"的本地实证 |
| xkey ledger | 专用锁 | `autopilot/xkey.py:559` | |
| conductor 命名锁 | `.mw/{config,workers}.lock` | `conductor.py:135-156`（唯一有 **age-based steal** 的地方） | |

**[事实] 没锁（真风险面）**

1. **`packages/*/dist` tracked 产物**：`git ls-files packages/coding-agent/dist` = **953**、`packages/multi-workers/dist` = 1（本机实测）。`npm run build` 无 clean、无锁；`mw build --install` / `mw bootstrap` 只有**脏树拒跑**护栏（`mw.py:3944-4004` `_git_dirty_paths`/`_refuse_dirty_build`/`_bootstrap_dirty_guard`，CLI 开关 `mw.py:5228-5240`，`--allow-dirty` 可绕过，非 git 目录跳过）。直接 `npm run build` 或 `npm run check`（全仓 `--write`）不经过该护栏 —— P-017（`.agenticdoc/_pitfalls.md:185-193`）+ `mw-autopilot-verify-cli/spec.md:120`（"npm run build 亦写 953 个 tracked dist 文件（RQ-3 §5）⇒ 脏树上构建会污染他人未提交代码（正是 AC-009(d) 的动因）"）。
2. **每任务目录的 `trace.log` / `worker.log` / `output.md` / `progress.md`**：无锁，设计上"每任务目录单写者"（一个 worker 进程）。真实事故形态不是并发写坏行，而是**事后改写**：repair worker 在已失败轮次的 `trace.log` 结束之后重写该轮 `output.md`，把 `below` 洗成 `meets`（`packages/multi-workers/CHANGELOG.md` 的 `feature-verdict-provenance-guard` Fixed 条目）⇒ 靠**来源/新鲜度校验**而非锁兜住。`worker.log` 由 launcher 以 `"wb"` 截断打开（`launcher.py:955-958`），重派同一 key 会重截断（历史只有 launcher.log 有 per-session 截断约定，`mw.py:243-249`）。
3. **`.mw/launcher-beat.<pid>`**：`launcher_beat_write` 只覆盖自己的文件，注释明确 "No lock: one small file per launcher, overwritten"（`mw_common.py:1857-1869`）。
4. **`.mw/mw.log` / `launcher.log` / `proxy.log` / `serve-console.log`**：append 或 per-session 截断，无锁（每进程单写者）。
5. `[事实]` **锁语义两侧不对称**：Python `acquire_lock` 默认 `retries=20`、`base_delay=0.05` 指数退避，累计等待 ≈ **14.6 h** 才抛 `RuntimeError`（`mw_common.py:1482-1497`）；TS `acquireLock` 默认 `retries=10`、`baseDelayMs=50`，≈ **102 s** 后抛错（`shared/file-lock.ts:10-13`）。除 conductor 的命名锁外**没有 age-based steal**（`conductor.py:143-154` 是唯一实现）⇒ 硬杀持锁进程后，Python 写者会长时间空等而不是快速报错。`[实测]` 当前三项目 + FM 的 `.mw` 下**没有任何残留 `*lock*` 文件**（`Get-ChildItem … -like '*lock*'` 为空），该风险尚未实际发生。
6. `[事实]` **跨项目不共享锁**：锁路径都是 `<project>/.mw/*.lock`（`lock_path` `mw_common.py:1440-1441`、`index-store.ts:60`、`ack-store.ts:21`）⇒ 三个项目各自的账本写互不串行；机器层面的写竞争只在 `packages/*/dist`（同一 git 检出）与共享凭据文件上。

### 5. 看门狗与机器负载的交互

**[事实] 判定依据（什么算 activity）**

- 常量：`DEFAULT_IDLE_MS = 10 * 60_000`（`worker-mode.ts:148`）、`DEFAULT_BUDGET_MS = 60 * 60_000`（`:142`）；`resolveIdleMs(process.env.PI_WORKER_IDLE_MS)`（`:163-167`）与 `resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS)`（`:155-160`）。
- activity 源：`message_update`（token delta，唯一区分"慢生成"与"死连接"的信号，`:803-806`）、`message_start`/`message_end`、`turn_start`/`turn_end`、`agent_start`、`tool_execution_update`/`tool_execution_end`、`tool_execution_start`（`:807-810`、`:825-830`）、`agent_end`（`:837`）。全部汇入 `touch()` → `lastActivityAt`（`:800-802`）。
- 判定：`idleTimer = setInterval(…, 30_000)`，`idleForMs = now - lastActivityAt`，`>= idleMs` 即 `timeoutExit("idle", …)` 并 `process.exit(1)`（`:1022-1036`）；墙钟 `wallTimer = setTimeout(…, budgetMs)`（`:1036-1041`）。两分支都先同步写 `output.md`/`trace.log` 再杀子进程树（`:911-937`）。

**[事实] 配置键 `worker_timeout_min` 没有消费者**

- `worker_timeout_min`（默认 30）只在 config 定义/校验、TS 镜像、README 出现：`autopilot/config.py:18/54/72`、`status-model.ts:81/108/138`、`README.md:228`。没有把它写进 task.md `timeout:` 或 `PI_WORKER_TIMEOUT_MS` 的代码路径（全仓 grep 确认）。
- 实测佐证：4 个 worker 的 `[END] … elapsed=3600s` 恰好命中 60m 默认（E2 的 `config.json` 写的是 `worker_timeout_min: 30`，未生效）⇒ **有效墙钟 = task.md `timeout:` > env > 60m**。

**[实测] 误杀已经发生，且在低并发下**

- `output.md` 带机器判据的 idle 死亡 **14 次**（文件 167 B，`## Exit Reason` = `idle timeout: no activity for 602–622s`；最小 602、最大 622，即阈值 600s + 一个 30s 检查粒度）。
- 每次死亡时刻的**同时存活 worker 数**：1,1,2,2,2,3,3,2,2,2,2,2,2,2 ⇒ **均值 2.14、max 3**。窗口 2026-09-20…09-25，横跨 E2 与 MW。
- 另有 3 个 `output.md` 含 `idle timeout` 但无 `no activity for Ns` 机器行（旧格式/工具错误路径），合计 17 处提及。
- 复盘文档：`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\worker-idle-timeout.md`（12 次实例清单；触发者画像 spec/design-writer 长读+长推理；直接成本 ≈ 10 min/次、共 ~2 h，且 `feature-sampling-human-channel` 因"无槽位可重试"被推迟 ~1 h、`feature-gui-time-mvp-board` 连死两次整 key stalled）。
- 该文档的决策（用户 2026-09-25）：**不抬 `PI_WORKER_IDLE_MS`**，理由是 ① 抬高会同时放松**资源护栏**（"框架注释记过 idle-killed 伴随 151 GB 失控探测"）、② "本项目并行吐量只有 2 槽"，抬高阈值反而延长占槽。
- 另一条独立证据：P-015 / FM 台 A-05 —— `PI_WORKER_IDLE_MS` 不落盘，重启路径不同则 env 丢失，导致默认 600s 生效、worker 被 572–630s 杀死（`.agenticdoc/_pitfalls.md:163-173`）。

**[推断] 并发度↑ ⇒ 误杀概率↑ 的推理链**

1. 判据只认 token delta / 工具事件 / turn 边界；机器更忙 ⇒ (a) 首个 token 与 delta 间隔变长（上游排队/调度）、(b) 工具（pytest/npm check/tsgo/编译）本身墙钟变长，而工具执行期间**只有** `tool_execution_update/start/end` 会 touch——长跑命令若在 update 事件之间也变稀疏，静默窗口同步变长、(c) 30s 检查粒度再叠加最多 +30s。
2. 实测杀伤区间 602–622s 说明阈值**紧贴**合法静默分布的上沿（文档记录典型静默 608–613s）；负载只要把分布右移 ~1–2%，跨越 600s 的样本比例就显著上升。
3. 因此"并发↑ ⇒ 误杀↑"是**机制上必然**的单调关系（无新缺陷参与），但当前**没有 ≥7 并发的样本**（见 §6 时间占比），所以只能标 `[推断]`。
4. 反向约束：idle 看门狗同时是**资源护栏**（151 GB 事故发生在被 idle 杀死的 worker 退出瞬间之前），所以"误杀减少"与"失控子进程早终止"是两个相反方向的诉求——这正是 RQ-4 的取舍面。

### 6. 实测并发与容量（支撑结论的量化）

**[实测] 区间重叠峰值**（三项目 717 个有效区间）

- 全机器同时存活 worker 峰值 = **7**：`2026-09-22T09:24:03Z` = MW `mw-rag-integration` 的 t01/t02/t03/t07/t08（5 个，同一 key）+ E2 `feature-params-service` 005 + E2 `feature-vc013-idempotence-repair` spec-writer-a1。
- 单 key 峰值 = **6**：`2026-09-26T06:19:31Z`，MW `mw-autopilot-verify-cli` 的 6 个 `design-rqd1..rqd6` 同时存活 ⇒ **远超 `max_parallel_keys=2`**，即 key 层 gate（`conductor.py:289`）管不到 "PM/用户直接派发的 worker 层"。
- 分项目峰值：Multi-Workers **6**、E2Feature **4**、JCodingAss **2**。
- 今日实时（07:33Z）：打印模式 worker **10** 个（MW `msc-rq1..rq6` 一族 + E2 `feature-gui-contract-respec` 2 个 + 其它 2 个），其中单 key 同时 5–6 个 —— 与上面的历史峰值同量级。
- 时长分布（714 个有 `[END]` 的 elapsed）：p50 = 540 s、p90 = 1326 s、max = 3600 s；≥1800 s 的 36 个，=3600 s 的 4 个（墙钟死）。

**[实测] 并发时间占比**（09-20T00:00Z–09-26T08:00Z，9120 个分钟样本）

| 同时存活 worker | 分钟 | 占比 |
|---|---|---|
| 0 | 5486 | 60.2% |
| 1 | 1627 | 17.8% |
| 2 | 1626 | 17.8% |
| 3 | 267 | 2.9% |
| 4 | 54 | 0.6% |
| 5 | 42 | 0.5% |
| 6 | 18 | 0.2% |

⇒ 有 worker 在跑的时间只占 39.8%；**≥3 仅 4.2%，≥4 仅 1.2%**。任何"高并发下的失效模式"在这台机器上几乎没有样本。

**[事实] worker 层没有上限**

- `--max-workers` 只有 CLI 入口（`mw.py:5044`、`launcher.py:1021`，`default=None`），TS 侧零命中；没有任何项目层/机器层配置键接线它（`autopilot/config.py` 13 键里没有）。
- `_poll_once` 对**每个** `status == pending` 的行都直接 `_spawn`，只在 `max_workers` 非空时才入 `pending_queue`（`launcher.py:819-843`）⇒ 默认"有几个 pending 起几个"；跨项目时每项目一个 launcher ⇒ 机器层面 = 项目数 × 无限。

**[实测] 完成/失败面**

- 726 个任务目录：`[END] exit=0` 694、`exit=1` 20、无 `[END]` 6（其中 5 个是本次运行中的 rq/tasks-writer，1 个是旧 smoke）。
- 队列行状态：MW 163 done / 11 failed / 5 running、E2 455/29/1、JCodingAss 70/2/0 ⇒ 失败率 ≈ 6%，与 idle 误杀次数（14）同阶。

## 结论 → 决策映射

按"**已经实测发生**"优先排序（这才是"首个瓶颈"的正确判据，而不是按理论上限排）：

1. **idle 看门狗误杀（已发生，且不依赖高并发）** —— 支撑 spec §4 风险 4，并给出量化：14 次 / 6 天 / 三项目，每次白烧约 10 min 墙钟 + 1 个槽位（E2 复盘 12 次 ≈ 2 h，另有"无槽可重试 ⇒ 该 key 延迟 ~1 h"与"连死两次 ⇒ key stalled ⇒ 5–9 h 人工等待"两个尾部）。死亡时刻并发均值 2.14 ⇒ 提高 `max_parallel_keys` **不能**消除该失败模式，反而（按 §5 的机制链）提高其发生率；同时它是资源护栏，不能单方向放松（与 §4 风险 1/4 共同约束）。
2. **worker 层无上限 + key 层 gate 不覆盖 PM 直发** —— 支撑 §1.1 的两层并行度与 §4 风险 1：`--max-workers` 默认 None、无配置键；实测单 key 6 并发。任何"提高并行度"的方案必须同时回答 worker 层的闸在哪，否则机器暴露在不受控的 N 上（而 §5 的误杀会随 N 放大）。
3. **代理上游连接池 8/端口（有端口路由时才有意义）** —— 支撑 §4 风险 3 的一半：provider 端限流未观测到（726 次 0 命中 429），但若将来启用 claude/claude-cli/deepseek 路由，第 9 个并发 worker 会**静默排队**（`queue.get()` 无超时），表现为"变慢但不报错"，且这一顶在监控面板上不可见（面板显示的是 key 槽位）。
4. **未加锁写面：tracked 产物 + 事后改写家族** —— 支撑 §4 风险 2 的**准确形态**：账本类文件（`_workers.parallel`/`_index.parallel`/`_acked`/autopilot config）已被锁保护，实测修前 30 轮丢 28 的教训已闭环；剩下的是 ① `packages/*/dist`（953 tracked 文件；只有脏树拒跑，`npm run build` 与 `npm check --write` 可绕过 —— P-017），② 每任务目录 trace/output 的**事后改写**（verdict-provenance 家族，靠来源校验兜住）。并行度上升的放大系数是"同时写者数 × 同一 git 检出"，而不是"账本行数"。
5. **RAM / CPU 不是首坏点** —— 190 GB / 32 核，10 worker 时 CPU 21–26%、磁盘 1.5%、可用内存 57 GB；每 worker 150–370 MB。真正的内存风险是**单个失控工具子进程**（151 GB 事故 + 本机当前 89 GB 的无关进程），它与并行度是"概率相加"而非"容量相乘"的关系。
6. **机器层服务进程已是 N 倍模型** —— 9 个 serve + 9 个 launcher + 3 个 conductor + 1 个共享代理（≈0.6 GB），说明"一台机器多项目"在实现层面就是"多份轮询循环 + 一个共享代理"；这直接影响 spec U-5（机器层是否统一计额）：代理已经是机器级共享资源，而槽位计数不是。

**不要在本 key 得出的结论**：具体的 `max_parallel_keys` 目标值、worker 层闸的取值、是否抬 idle 阈值 —— 属 RQ-4。

## 数据缺口

1. **无高并发样本**：≥4 并发只占 1.2% 分钟、峰值 6–7，且都在 ≤3 项目的混合负载下；"并发↑ ⇒ 误杀/失败↑"只有机制推理，缺对照实验（例如受控地同时跑 8–12 个 worker 测 idle/wall/锁竞争）。
2. **provider 端速率限制未测**：timi 直连是内网端点，仓库侧无 429 计数能力；只有"726 次运行 0 命中"的负面证据。
3. **CPU/IO 峰值未测**：只有 10 worker 空闲等待态的 3 个采样；缺"多 worker 同时跑 pytest / `npm run check` / tsgo / 编译"时的 CPU、磁盘队列与单步耗时测量（这正是 §5 推断链的关键中间量）。
4. **账本写频率与持锁时长未测**：只知写成本 O(行数)（E2 127 KB/485 行）；未统计 `_workers.parallel` 每分钟重写次数、`workers.lock` 的实际持有时长分布，也未确认 TS 侧 102 s 锁超时是否真的发生过。
5. **代理端口路由环境不可复现**：本机 `proxy disabled`，`_UpstreamPool(size=8)` 的排队行为无法在这台机器上实测（只能从依赖源码读出）。
6. **`_workers.acked`/`trace.log` 的写入竞争未实测**：读侧无锁（`readAll` 直接读，可能读到 tmp+rename 之间的旧文件——原子替换下不会撕裂，但无实证）。

## [VERIFY]

```
[VERIFY] RQ-2: proxy=global-single-process(ports 7001/7003/7004 fixed, shared when bound; disabled today, upstream pool=8/port) cred=stripped-then-single-key(N workers share one key, no client limiter) disk_locked=4/4 _workers.parallel|_index.parallel|_workers.acked|_autopilot-config disk_unlocked=dist(953 tracked files, dirty-tree guard only)+trace.log/output.md/beat measured_overlap_max=7 (per-key 6; live print-workers=10) idle_kills=14 at conc<=3 (mean 2.14) wall_default=60m machine=32c/190GB CPU=21-26% @10 workers
```
