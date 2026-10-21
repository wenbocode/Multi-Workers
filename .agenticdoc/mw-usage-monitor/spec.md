# Spec: mw-usage-monitor（本机 token/耗时监控）

- Key: mw-usage-monitor
- Version: v0.2（2026-10-19；v0.1 需求定稿 → v0.2 按 RQ1–RQ4 证据回填事实项，改动见 §8）
- Deps: agent-team-loop
- 证据：`evidence/research/spec-rq1-pi-session-usage-20261019.md`、`spec-rq2-dispatch-lifecycle-20261019.md`、
  `spec-rq3-cli-worker-logs-20261019.md`、`spec-rq4-surface-storage-20261019.md`、`spec-rq0-research-plan-20261019.md`

## §0 Goal Alignment

**goal.md 锚点**：项目目标「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个
Worker Agent 并行开发同一个项目」；交付面含「mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行」与
「项目级目标对齐（goal.md）」。约束含「Worker 进程级隔离」「工具白名单按任务类型」「超时看门狗」。

**当前缺口**：框架能调度、能看进度，但**回答不了成本问题**——这台机器上 token 花在哪些模型、哪些任务类型
（coding/review/research/vision）、哪些 key/项目、各占多少，每次 worker 跑了多久。没有这个面，并行是否真的
省时、`dispatch.yml` 角色模型选型、超时预算都只能靠印象。

**预期收益**

1. 一屏回答成本分布：按模型 / 任务类型 / key / 项目四组，tokens（in/out/cacheRead/cacheWrite）与运行次数。
   实测 cacheRead 占全库 totalTokens 的 **97%**（12.1G/34.6G），故四分量必须拆分呈现，否则数字无解释力（RQ1 §5）。
2. 墙钟数据支撑「并行 vs 串行」与超时预算（p50/p90），并暴露慢任务类型。
3. 为 `.mw/dispatch.yml` 的 `models:` 角色默认提供数据依据（哪个角色在哪个模型上贵/慢）。
4. 机器级、跨项目、纯本地文件、无网络依赖、不改 pi core。

## §1 需求（用户已定，不再讨论）

| ID | 需求 | 来源 |
| --- | --- | --- |
| R1 | 机器级存储 `~/.mw/usage/`（跨项目一份，行内带 project） | 用户 2026-10-19 |
| R2 | 只统计 tokens（input/output/cacheRead/cacheWrite[/total]），**不算钱**、不输出金额列 | 同上 |
| R3 | 响应时间只用低成本墙钟（worker start→end），不做 TTFT、不做逐请求延迟分析 | 同上 |
| R4 | pi 窗口提供 `/mw stats` 简报（另有 CLI `mw stats`） | 同上 |
| R5 | 台账行区分 `source=worker|pm`，两者可分别过滤 | 同上 |
| R6 | 范围：**pi** 的 worker + PM 窗口必须统计；codex/claude CLI worker 能低成本读到就纳入，读不到显式降级 | 用户「按推荐」 |

## §2 统计口径（证据回填）

**token 权威源 = pi 会话 JSONL 的 `usage`**（不是 LLM 代理：RQ4 证实默认 worker 路由 timi 直连不经代理，
`proxy_multi.py` / `timi_proxy_cli` 无 usage 钩子）。

- 每条 assistant message 恰好对应一次 provider 响应（RQ1 §1：`retryAssistantCall` 不聚合 usage，失败尝试落
  `EMPTY_USAGE` 消息；全库 0 组重复 `(provider, responseId)`）→ **直接逐条相加**，不做去重。
- `compaction` entry 也带 usage（本机 1,699 条）→ **同样计入**（是真实调用）。
- 四分量分别记账：`input` / `output` / `cacheRead` / `cacheWrite`（+ `cacheWrite1h` 可选）；`total` 一律由分项
  求和得出，**不直接信任落盘 `totalTokens`**（跨 CLI 定义不同，见 RQ3 §4）。
- **模型**：键为 `provider/model`（RQ1 §6：`responseModel` 全库非空 0 条）；台账额外记请求值 + 来源
  （`task|config:<role>|window|default|fallback`，RQ2 §1.9-1.10）与运行期 `[MODEL]` 事实（trace.log）。
- **墙钟**：worker = 台账 `start`（spawn 成功）→ `end`（reap）；PM = 会话 header `timestamp` → 末条 entry
  `timestamp`（RQ1 §6：span p50 569.5 s，max 25.2 天 → **跨天统计按消息 timestamp 切桶，不按文件归属**）。
- **项目**：控制工作区根（control root）为 project 标识；dual 模式下 worker cwd 在 game 根，台账仍记 control 根。
- **归因**（RQ1 §4、RQ3 §3）：worker 会话由 launcher 显式分配 id：pi `--session-id mw-<key>-<pid>-<seq>`
  （唯一，同 id 会 resume 旧文件 → **禁止复用**）、claude `--session-id <uuid>`；`mw-` 前缀即 source=worker。
  无前缀且无 worker-identity entry → source=pm。claude 精确读 `projects/<cwd-slug>/<uuid>.jsonl`（含
  `<uuid>/subagents/**` 并账）；codex 无 session id → 台账照记运行，token 记 `-` + `attribution=unknown_cli`。
- **deferred flush**：pi 在首条 assistant 响应前不落盘（RQ1 §3）→ 崩溃于首响应前 = 无文件 = 无 usage，
  台账行 token 为 `-`（不是 0），墙钟照记。

## §3 交付面

1. **机器级台账** `~/.mw/usage/runs.jsonl`（append-only，一行一次运行），字段：
   `run_id, source, project, key, task_key, type, role, cli, attribution, model, model_source, session_id,
   pid, start, end, exit, wall_s, spawned, reconciled`。
   - 目录解析：`usage_dir()` = `MW_USAGE_DIR` → `USERPROFILE`/`HOME` → `~/.mw/usage`（照
     `machine_rag_servers_path` 的显式序，不用 `expanduser` 裸调，RQ4 §3）。
   - 写入：`acquire_lock(runs.jsonl.lock)` → 每条独立 `open("a", encoding="utf-8", newline="\n")` 写一行
     `json.dumps(..., ensure_ascii=False)` → 释放（抄 `archive_stale_entries`，RQ4 §4）。fail-soft：写失败只
     warning，绝不阻断 spawn。
2. **`mw stats`**：`[--since 7d|24h|YYYY-MM-DD] [--key K] [--type T] [--model M] [--project P] [--source worker|pm]
   [--json]`。默认窗 7d。落位 `mw.py:7018` 之后、doctor 之前；**必须声明可选 `--project`**（TS runner 恒追加）。
   默认人读表格（四行组 × `calls,in,out,cache_read,cache_write,wall_p50,wall_p90,n`，`n<5` 分位数列显 `-`）；
   `--json` 整体切换（照 doctor `:655-661`）。
   - 组行另带 `wall_kind=run|session|none`，标明分位数 `wall_p50/wall_p90/n` 的样本来源：`run` = 台账
     spawn→reap 墙钟，`session` = 会话 header→末条跨度，`none` = 无可用样本或样本 <5（此时两个分位数均为 `-`，
     `n` 仍报有效样本数）。两种来源**绝不混源**：组内只要存在 worker run 墙钟，PM 会话跨度就不进入分位数
     （即使因此凑不满 5 也不回填）；文本里 session 来源行的 p90 末尾加 `*`，并在 `coverage:` 前插脚注。
3. **`/mw stats`**：`ui-bridge.ts` 分支 + `mw-runner.ts` 包装 + `notify` 回显（照 `/mw model show` 链）。
4. **覆盖率声明**：简报尾行固定 `coverage: pi N runs (exact) · claude M (exact) · codex K (未统计)`，
   明确区分「无运行」与「有运行但未统计」。
5. **不做 rollup（v1）**：实测 7 天扫描 2.9 s、全库 11.1 s（RQ1 §5）→ 按需扫描即可；阈值（>30 天窗或
   预计 >10 s）写进 design 作为未来增量缓存的触发条件，不实现。
6. **文档**：`packages/multi-workers/CHANGELOG.md` + `README.md` 命令面。

## §4 验收标准

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | launcher 每次 worker spawn 写 start 行、reap 写 end 行（正常 / exit-3 重派 / 孤儿收敛三分支），字段齐全；4 worker 并发写无交错、无丢行 | pytest（并发 + 分支） |
| AC-002 | 给定 session_id，`mw stats` 汇总 tokens 与手工扫该会话一致（Δ=0），requests = 统计到的 usage 条数（含 compaction） | pytest |
| AC-003 | `mw stats --since 7d` 输出 model/type/key/project 四组分布（四分量 + calls）；`--json` 字段稳定且被测试固定 | pytest |
| AC-004 | 每 run 有 `wall_s`（无 end 的孤儿行不算 0）；汇总给 p50/p90，`n<5` 显 `-` | pytest |
| AC-005 | `source=pm` 可统计（模型/tokens/会话墙钟），可与 worker 分别过滤；PM 跨天会话按消息 ts 切桶 | pytest |
| AC-006 | `/mw stats` 在 pi 窗口输出简报；失败路径有可见错误（不静默吞 stderr） | TS 测试 |
| AC-007 | codex/claude 不可统计时：台账行 `attribution=unknown_cli`、token 列 `-`、简报尾行 coverage 明示 | pytest |
| AC-008 | 输出与台账**无**金额字段（不引入 cost） | pytest（schema 断言） |
| AC-009 | 零回归：`packages/multi-workers` 非 e2e 全量 + 相关 vitest | 测试输出 |
| AC-010 | 文档同步：CHANGELOG [Unreleased] + README；示例输出与实际一致 | 人工 + 固定样例 |
| AC-011 | worker 会话 id 唯一性：`mw-<key>-<pid>-<seq>` 通过 `assertValidSessionId`，同 key 多次 spawn 不复用（不会 resume 旧文件） | pytest |
| AC-012 | `--since` 过滤先用 header/首行粗筛再全量解析（header-only 全库 0.54 s 级），7 天窗口墙钟 < 5 s（本机基准） | pytest（计时不设硬阈值，记录数值） |
| AC-013 | 无 usage 的会话/运行：token 记 `-`，不参与加总，也不显示 0 | pytest |

## §5 非目标

- 不做跨机器聚合、不做实时仪表盘/TUI 曲线、不做费用估算、不做 TTFT、不改 pi core、不引入网络依赖。
- 不采集 prompt/响应**正文**（隐私面最小化）：只读 `usage`/`model`/`provider`/`timestamp`/entry `type`。
- 不重构 launcher/serve，只加台账与查询面；不改 codex worker 的输出形态（`--json` 捕获方案留后续）。
- v1 不做增量 rollup、不做 doctor `usage` 段（RQ4 §6 取舍）。

## §6 风险与预案

| 风险 | 预案 | 依据 |
| --- | --- | --- |
| 同 session id 复用会 resume 旧文件，两次 spawn 混进一个文件 | id 内嵌 pid + 递增 seq，永不复用 | RQ1 §3 |
| 首响应前崩溃 → 无文件、无 usage | 台账照记运行，token 记 `-` | RQ1 §3 deferred flush |
| 多 launcher 并发 append 交错 | 跨进程锁 + 每条独立 open/close | RQ4 §4 |
| 全库扫描随语料增长变慢 | 按窗口扫 + header 粗筛；>30 天窗再考虑 rollup | RQ1 §5 |
| codex 无 session id → 归因不可靠 | v1 显式 `unknown_cli`，不猜 | RQ3 §3/§6 |
| 自定义 session 目录对其他窗口 `/resume` 不可见 | v1 不改目录，只加 id 前缀（可读、可辨） | RQ1 §3 |

## §7 决策记录（RQ 回读后）

| ID | 决策 | 依据 |
| --- | --- | --- |
| D-1 | token 只从 pi session JSONL 取，不接 LLM 代理 | RQ4：timi 直连、proxy 无钩子 |
| D-2 | 四分量分列，`total` 自算 | RQ3 §4 跨 CLI 定义不同；RQ1 §5 cache 占 97% |
| D-3 | worker 归因靠 launcher 显式 `--session-id`（pi）/`--session-id uuid`（claude），`mw-` 前缀 | RQ1 §4、RQ2 §1.4 |
| D-4 | codex v1 不统计 token，`unknown_cli` + coverage 行 | RQ3 §3/§6（无 session-id、0 真实样本） |
| D-5 | 存储 `~/.mw/usage/` + `MW_USAGE_DIR` 显式解析（不改 `~/.agents/mw/usage`） | RQ4 §3（用户已批 `~/.mw`；改动面最小） |
| D-6 | v1 不做 rollup / 不做 doctor `usage` 段 | RQ1 §5（2.9 s/7 天）、RQ4 §6 |
| D-7 | 台账只存元数据，token 查询时 join（不冗余存 token） | 避免双份真相；扫描成本已实测可接受 |

## §8 v0.1 → v0.2 变更

- §2 全部改为证据口径：assistant 一条一响应对加 compaction、四分量、PM 会话界定、deferred flush、归因 id 形态。
- §3 台账字段定稿；新增覆盖率声明；rollup 明确推迟（v0.1 是「可选」）。
- §4 新增 AC-011（id 唯一性）、AC-012（扫描粗筛/成本）、AC-013（无 usage 记 `-`）。
- §6 风险表按证据重写；新增 §7 决策记录 D-1…D-7。

## §9 可复用资产（不要重造）

| 资产 | 位置 | 用途 |
| --- | --- | --- |
| 跨进程文件锁 | `mw_common.py:2369-2388`（`acquire_lock`/`release_lock`，`O_CREAT\|O_EXCL` + 指数退避） | 台账 append、rollup 重写 |
| 锁内 append 唯一先例 | `mw_common.py:2481-2503`（`archive_stale_entries`） | 台账写入形态照抄 |
| 机器级路径 env 解析序 | `mw_common.py:685-703`（`machine_rag_servers_path`） | `usage_dir()` 的 `MW_USAGE_DIR`→`USERPROFILE` 显式序 |
| 原子重写（锁→tmp→replace） | `mw.py:772-790`（`_decide_write_config`）、`console_run.py:192-195` | 未来 rollup / 标记文件 |
| JSONL 追加写法 | `decision.py:941-970`（`utf-8` + `newline="\n"` + `ensure_ascii=False`，best-effort） | 每条事件的落盘格式 |
| Windows JSONL 三坑对策 | `timeline.py:275-276`（`newline`）、`:398-420`（torn tail 修复）、`:281-283`（单写者 D-109） | 解析与写入容错 |
| 定宽列渲染 | `mw.py:6933`（`{id:<18}`）、`mw_common.format_doctor_text:4381` | 简报表格不自造渲染器 |
| pi Usage 类型定义 | `packages/ai/src/types.ts:364-385`；`anthropic-messages.ts:584-585`（`totalTokens` 四分量和） | 四分量语义 |
| trace 尾部解析 | `mw_common.parse_end_exit:2772-2795` | 孤儿收敛取 `[END] exit` |
| pi session id 校验 | `session-manager.ts:212-218`（`assertValidSessionId` 正则） | `new_session_id()` 自检 |
| CLI 双输出先例 | `mw.py:655-661`（doctor `--json`）、`:6967-6971`（update-env） | `mw stats --json` |
| 测试先例 | `test_rag_cli.py:207-247`、`test_decide_cli.py:128-196`、`test/suite/rag-window.test.ts:129-237` | pytest / vitest 形态 |

## §10 需规避坑点（证据已坐实）

| 坑 | 后果 | 规避 | 证据 |
| --- | --- | --- | --- |
| Windows `expanduser("~")` 读 `USERPROFILE`、**不读** `HOME` | 与仓库既有机器级解析序不一致、不可注入测试 | 自己写 `usage_dir()` 的显式 env 序 | RQ4 §3 |
| 追加写未指定 `newline="\n"` | CRLF 翻倍、逐行解析出现空行 | 显式 `newline="\n"` + `encoding="utf-8"` | RQ4 §4 |
| 复用长文件句柄做多进程追加 | 交错/截断（`mw.py:281-282` 只适用单写者） | 每条事件独立 open/close + 跨进程锁 | RQ2 §6、RQ4 §4 |
| 同 `--session-id` 再跑 = **resume** 旧文件 | 两次 spawn 混进一个会话，墙钟与归因歧义 | id 内嵌 pid + 递增 seq，永不复用 | RQ1 §3 |
| pi 首条 assistant 响应前不落盘（deferred flush） | 崩溃于首响应 → 无文件 | 台账照记运行，token `-` 而非 0 | RQ1 §3 |
| codex `token_count` 相邻事件成对重复 | 求和 → 2× 虚增 | v1 不读 codex；未来取最后一条累计值 | RQ3 §2a |
| claude 同一 `message.id` 写 2–4 行 | 求和虚增 1.41–1.87× | 按 `message.id` 去重 | RQ3 §2b |
| codex `input_tokens` 含 cache；pi/claude 不含 | 直接比 total 系统性偏大 | 四分量分列，`total` 自算 | RQ3 §4 |
| 自定义 `--session-dir` 对其他窗口 `/resume` 不可见 | 用户找不到 worker 会话 | v1 不改目录，只加 `mw-` id 前缀 | RQ1 §3 |
| TS `runMwCliRaw` 恒追加 `--project` | 未声明 → argparse exit 2 | `stats` 必须声明可选 `--project` | RQ4 §2 |
| 仓库无 p50/p90 与 token 记账实现 | 自造术语/渲染器 | 只复用 `wall`、`[END] elapsed`、`input/output/cacheRead/cacheWrite` 术语 | RQ4 §5 |
| timi 的 `usage.cost` 恒 0 | 误以为免费或有数据 | 不读 cost、不输出金额 | RQ1 §6 |
| 长命 PM 会话一个文件活数周（max 25.2 天） | 按文件归属切桶 → 跨天统计错 | 按消息 `timestamp` 切桶 | RQ1 §6 |
| timi 路由直连不经代理 | 代理侧看不到主力流量 | 只从会话 JSONL 取 token | RQ4 §5 |
| 旧 `serve` 进程仍跑旧 launcher | 台账为空，误判“没数据” | 落地后 `/mw restart`；无台账时显式提示 | RQ2 §5 |

## 11. v0.3 增补（2026-10-21，用户反馈：窗口只能看用量，看不到调用方）

### 11.1 问题

v1 的输出只有 4 个维度的聚合行（`by model` / `by type` / `by key` / `by project`），
聚合行回答了“花了多少”，没有回答“这 30986 input tokens 是哪一次运行、哪个 task、哪个会话烧的”。
同时时间维度只有下界 `--since`（默认 7d），没有上界：想复盘“昨天 14:00 到现在”只能看整段。
窗口面 `/mw stats` 参数是透传的（`ui-bridge.ts` `runMwStatsCommand` → `splitCommandLine` → `statsMw`），
所以只要 CLI 有这两个能力，窗口自动具备，不需要改 TS。

### 11.2 新需求

- **R7 时间上界**：`--until <7d|24h|30m|YYYY-MM-DD|YYYY-MM-DDTHH:MM>`，窗口为 `[since, until)`；
  缺省 = now。`--until` 早于 `--since` ⇒ rc=2。相对形式（`24h`）以 now 为基准，与 `--since` 一致。
- **R8 运行级明细**：`--detail` 在文本尾部追加 `runs` 明细表，一行一次运行；
  `--json` 固定新增 `runs[]`（**不受 `--detail` 影响**，`--detail` 只控制文本是否渲染它，
  避免“要 JSON 明细必须加 flag”的二段契约）。
- **R9 明细字段**：`run_id, started_at, ended_at, key, task_key, type, model, calls,
  tokens{input,output,cache_read,cache_write}, wall_s, wall_kind, status, attribution, session_id, open_run`。
  `open_run=true`（有 `start` 无 `end`）⇒ `wall_s=null`、`wall_kind="none"`，绝不回填会话跨度（沿用 T-06 规则）。
- **R10 明细截断**：`--limit N`（默认 20，`0` 表示不限），按 `started_at` 倒序取前 N 条；
  被截断时文本必须写出 `showing N of M runs (--limit)` 且 JSON 给 `runs_total`，否则用户会把截断当成全量。

### 11.3 验收补充

- **AC-014**：`--until` 生效且为半开区间；窗口外的 run 同时从 `totals`/`groups`/`runs` 消失；
  `--until < --since` 与非法取值均 rc=2 且 stderr 说明期望格式。
- **AC-015**：`--detail` 文本每行含 key、task_key、type、model、calls、四个 token 分量、wall、status；
  `runs` 与 `totals.runs` 在同一过滤条件下自洽（N 条明细的 tokens 之和 = totals，除非被 `--limit` 截断）。
- **AC-016**：`runs[]` 字段名与 §11.2 逐字一致；`open_run=true` 的行 `wall_s` 是 JSON `null`（不是 0）。
- **AC-017**：窗口 `/mw stats --detail --since 24h` 可直接用（零 TS 改动）；`--help` 文本更新。

### 11.4 非目标（v0.3 明确不做）

- 不做按 task_key 分组的第 5 个维度（`--detail` 已能看，聚合能加就成噪音）。
- 不做分页/游标（`--limit` 足够，7d 窗口最多千级 run）。
- 不改 `runs.jsonl` 台账 schema（明细全部来自查询期 join，D-7 不变）。

### 11.5 复用到的既有资产

- `usage.parse_since`（`usage.py:312`）的 相对/日期 解析与 `_local_tz` 语义直接复用给 `--until`。
- `usage.load_runs`（`usage.py:717`）已产出 `open_run/wall_s` 语义，明细行只是不再被折叠进聚合。
- `usage._format_row`（`usage.py:1215`）的 `-` 表示 `None` 的渲染约定。
- `usage.SESSION_WALL_FOOTNOTE`（`usage.py` 的 `*` 脚注）在明细表里同样适用。
