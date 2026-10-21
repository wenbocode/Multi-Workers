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

## 12. v0.4 增补（2026-10-21，用户反馈：窗口可读性有限，要静态 HTML + `--detail` 自动打开）

### 12.1 数据新鲜度（先回答问题）

`mw stats` **每次调用都重新取数**，没有任何 rollup/缓存（D-6）：
台账 `~/.mw/usage/runs.jsonl` 全量重读（341 事件级，毫秒）；token 侧按窗口扫描
`~/.pi/agent/sessions/**/*.jsonl`（实测 7d ≈ 3–5s，含 2.6GB 语料）。
正在跑的 worker 的会话文件会随 pi 落盘增长，所以 token 反映的是**最近一次落盘**，
`end` 行要等 reap 才出现（此前是 `open_run`/`running`，`wall_s=null`）。
因此「刷新」= 再调一次 `mw stats`，不需要额外机制。

### 12.2 新需求

- **R11 静态 HTML 报告**：`usage.render_html(report)` 产出**单文件、自包含**（内联 CSS，无外链、无网络、
  无脚本依赖）的 HTML；`mw stats --html [PATH]` 落盘并打印路径。
  默认路径 `<usage_dir>/reports/usage-<YYYYMMDD-HHMMSS>.html`（`MW_USAGE_DIR` 同源），每次调用新文件，不覆盖历史。
- **R12 `--detail` 自动打开**：窗口面 `/mw stats --detail` 在落盘 HTML 后**自动用默认浏览器打开**，
  文本仍照旧打印（终端里保留可复制的最小摘要）。自动化场景用 `--no-open`（或 `MW_STATS_NO_OPEN=1`）关闭；
  两者都不得影响 rc 与文本内容。
- **R13 HTML 内容**：①头部：生成时间（本地）、窗口 `since → until`、生效的过滤条件、
  ledger 路径/事件数/bad_lines；②汇总卡：runs（worker/pm 拆分）、calls、四个 token 分量；
  ③四张分组表（model / type / key / project，列为 calls、四分量、runs、wall p50/p90、n、wall_kind）；
  ④runs 明细表（started_at、wall、status、key、task_key、type、model、calls、四分量、session_id）；
  ⑤coverage 行与 `*`/`-` 脚注。**语义必须与文本输出一致**：`None` 渲染 `-`（不是 0），
  `wall_kind=session` 的墙钟加 `*` 并带同一条脚注，`open_run` 行明确标 `running`。
- **R14 HTML 转义**：所有来自台账/会话的字符串（key、task_key、model、project、路径）必须 HTML 转义，
  防止 `<`/`&` 破坏结构（台账里的用户输入不可信）。

### 12.3 验收补充

- **AC-018**：`mw stats --html <tmp>` 生成的文件存在、单文件（无 `http://`/`https://`/`src=`/`<script src` 外链）、
  `<html lang="zh">` + `<meta charset="utf-8">`，且包含窗口、汇总、四张分组表、明细表的锚点文本。
- **AC-019**：`--detail` 默认尝试打开浏览器；`--no-open` 与 `MW_STATS_NO_OPEN=1` 都不打开，
  且文本/JSON/rc 与不打开时完全一致。打开失败（无默认浏览器）只 warn，rc 仍为 0。
- **AC-020**：HTML 渲染的数值与同一 report 的文本渲染一致（同一 `report` dict 的两个渲染器，不各自取数）；
  `None` ⇒ `-`；`wall_kind=session` ⇒ `*` + 脚注；`open_run` ⇒ `running`。
- **AC-021**：HTML 里出现 `<script`/`<style` 由我们生成，但台账字段里的 `<`/`&` 必须转义（用一个含
  `<img src=x onerror=...>` 的 key 做单测，断言输出里没有可执行的原始标签）。

### 12.4 非目标

- 不做交互式仪表盘/自动刷新（用户要的是「刷新一次 → 静态文件」）。
- 不引 JS 框架、不引第三方 CDN、不写文件到仓库（默认写 `~/.mw/usage/reports/`）。
- 不改文本输出契约（`--detail` 文本仍照旧；HTML 是并列产物）。

## 13. v0.5 增补（2026-10-21，用户反馈：「都 html 了就把 run 都展示吧」）

### 13.1 问题

`--limit`（默认 20）是为**终端**存在的：文本表滚屏、`argv` 输出有长度上限，截断必须说清。
HTML 没有这个约束——一页 200 行明细完全可读（粘顶表头 + 斑马纹），
把 HTML 也截断成 20 行等于让用户「为了看全量再去改参数」，与「静态报告」的目的相反。

### 13.2 新需求

- **R15 HTML 全量 run**：HTML 明细表展示**窗口内全部** run，行数 = `runs_total`；**不受 `--limit` 影响**。
  标题写明总数（如 `runs (newest first) · 184`），不出现 `showing N of M` 这类截断提示。
- **R16 契约不变**：`--limit` 仍然只作用于**文本**与 **JSON `runs[]`**（R10 不变）。
  为不撑大 JSON，全量 run 只在「需要 HTML」时构建：`build_report(..., include_all_runs=False)`；
  为真时额外返回 `runs_all`（list，与 `runs` 同 schema），默认不出现该键。
- **R17 一致性**：`runs_all` 与 `runs` 的前 N 行逐字相同（同一批对象、同一排序），
  `len(runs_all) == runs_total`；`render_html` 优先用 `runs_all`，缺失时回退 `runs`（旧调用路径不炸）。

### 13.3 验收补充

- **AC-022**：`mw stats --since 24h --detail --limit 3 --no-open` 生成的 HTML 里
  `<tbody>` 的 run 行数 == `runs_total`（远大于 3），且不含 `showing 3 of`。
- **AC-023**：`build_report(include_all_runs=True)` ⇒ `len(runs_all) == runs_total`；
  默认调用返回的 dict **没有** `runs_all` 键（JSON 体积不回归）。
- **AC-024**：`runs_all[:k]` 与 `build_report(limit=k)["runs"]` 逐字段深比较相等（排序与内容一致）。

### 13.4 非目标

- 不给 HTML 加排序/筛选 JS（静态报告，粘顶表头 + 浏览器内 `Ctrl+F` 足够）。
- 不把全量 run 写进 JSON（`runs_all` 只是内部投递通道，CLI 的 `--json` 输出不裁剪也不扩：仍只输出 report 里实际存在的键，
  但 CLI **不带** `--json` 时才请求 `include_all_runs`，避免 JSON 模式顺带带上全量）。

## 14. v0.6 增补（2026-10-21，用户要求：`runs` 里加 `project` 字段）

### 14.1 问题

台账 `start` 行本来就带 `project`（launcher 写入 spawn 时的项目根），`by project` 分组也在用它；
但 run 级明细行丢了这个字段，导致同一次查询里「分组能看到 project、逐条看不到 project」。
跨项目并行（本机同时有 Multi-Workers / OverCode 等）时，明细无法区分来源。

### 14.2 新需求

- **R18 `runs[].project`**：明细行新增 `project`（字符串或 `null`）。
  取值顺序：台账 `project`（worker run）→ 会话 header 的 `cwd`（PM 会话，或台账缺字段的老行）→ `null`。
  不得为了这个字段额外扫描或读消息正文（`cwd` 来自已经解析过的 header）。
- **R19 展示**：
  - 文本 `--detail` 表在 `started_at` 之后插入 `project` 列，渲染为**路径末段**（basename，如 `Multi-Workers`），
    `null` ⇒ `-`；列宽沿用现有紧凑风格。
  - HTML 明细表同样插入 `project` 列，单元格文本是 basename，并带 `title="<完整路径>"`（悬停可看全路径）。
  - `by project` 分组、`--project` 过滤语义**不变**；明细行与分组必须用同一个 project 值（同一次 join），
    否则「按 project 过滤后明细里出现别的 project」会自相矛盾。
- **R20 兼容**：`project` 为 `null` 时 JSON 输出 `null`（不是空串），文本/HTML 渲染 `-`；
  旧 fixture（没有 project 的台账行）不得让行构造抛异常。

### 14.3 验收补充

- **AC-025**：worker run 行 `project` 等于该 run 台账 `start.project`；PM 会话行 `project` 等于会话 header `cwd`；
  两者都缺失时是 JSON `null`。
- **AC-026**：文本明细行含 basename 列；HTML 明细表同时含 basename 文本与 `title="<完整路径>"`。
- **AC-027**：`--project X` 过滤后，`runs[]` 里每一行（worker 与 PM）的 project 都匹配 X，
  且 `runs_total` 与分组 totals 的 runs 一致（不出现「明细多出/少掉」）。

### 14.4 非目标

- 不新增 `by project` 之外的分组维度。
- 不把 project 规范化成 slug（保留原始路径，展示层才取 basename）。
