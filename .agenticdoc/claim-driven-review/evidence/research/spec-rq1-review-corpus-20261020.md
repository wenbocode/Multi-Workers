# RQ-1 标定：review 类 run 的成本语料

- Key: claim-driven-review · Task: cdr-rq1-review-corpus · type: research
- 语料：`.agenticdoc/*/workers/*/trace.log`（601 个文件 / 1,973 个 `[START]…[END]` attempt 段）
- 生成日：2026-10-21

## 0. 结论先行

1. **review 类 run = 115 次 attempt / 47 个 task 目录**（判据：`[START]` 行的 `type ∈ {review, reviewer, verifier}`；实测只有 `review` 一种取值）。取数次数 p50 **53**、p90 **99.6**、max **148**；历史 p50 已是本文建议值（30）的 1.8 倍。
2. **token 归因只有一条可靠通路**：launcher 写入 `~/.mw/usage/runs.jsonl` 的 `start` 事件里的 `session_id`（`mw-<key>-<pid>-<seq>`，同时作为 pi 的 `--session-id` 传入）→ pi 会话 JSONL 的 header `id`。本语料 **6/115** 次 attempt 可精确 join（`run.json` / argv / `_workers.parallel` 都不带 session id），其余 109 次**缺 ledger start 行**，不做近似归属。
3. **每次取数的上下文成本（实测）**：p50 **3,230** tokens、p90 **4,854**、max **4,977**；单次 read 结果平均 3,712–16,748 chars（3 次无读预算约束的 gpt-6.1-sol attempt 均值 15.5–16.7 k chars）。
4. **`chars/4` 系统性低估**：`estimateTokens` 估出的 token = 实测内容 token 的 **0.795**（p50，范围 0.709–0.812），真实成本约 **1.26×** `chars/4`。
5. **取数次数与断言数量几乎无关**：42 个可计目录的判定单元 p50 **11** / p90 **21**，与取数次数 Pearson r=**0.136**、Spearman **0.115**；历史 **每 1 条判定单元摊 5.97 次取数**（p50），反过来说每次取数只对应 **0.168** 条判定单元。
6. **预算建议**：单 worker **30 次取数**（硬上限 35）、单次 read **12 KiB**、每 turn **3–4 次取数**、每单元 claim 数 **K=6**；判定式 `U × K > 30`（即 **U ≥ 6 条判定单元**）就把 1×N 拆成 **4×2**。失败普查显示撞墙阈值不是次数而是**累计读取字节**（gpt-6.1-sol：654k–666k chars 必降级，269k–394k chars 全部存活）。

## 1. 全量 review 语料清单

### 1.1 判据与计数命令

判据：`trace.log` 中每个 `[START] <ISO> task=<task> type=<type> phases=<…>` 段即一次 attempt；`type ∈ {review, reviewer, verifier}` 判为 review 类。全语料出现过的 type 只有 `coding / research / review / default / vision`，**没有** `reviewer` / `verifier` 取值；review 段内 `model unavailable` 命中 0 次。

```python
# %TEMP%\rq1_scan.py（只读扫描脚本）
START_RE = re.compile(r"^\[START\] (\S+) task=(\S+) type=(\S+) phases=(\S+)")
print("segments", len(segs))                       # 1973
print("review(type)", sum(1 for r in out if r["type"].lower() in ("review","reviewer","verifier")))  # 115
print("types", collections.Counter(r["type"] for r in out).most_common())
# [('coding', 1423), ('research', 427), ('review', 115), ('default', 4), ('vision', 4)]
```

名字法（task 名含 review/reviewer/verifier）会再多出 **75** 段，类型全是 `coding`(43) / `research`(32)，例如 `ga-spec-design-review-2`、`mw-rag-qg-review-c`、`cdr-rq1-review-corpus` —— 它们是“关于 review 功能的实现/研究任务”，不是 review run，**已排除**。

### 1.2 汇总分位数（115 次 attempt）

| 指标 | p50 | p90 | max | min | mean |
| --- | --- | --- | --- | --- | --- |
| 取数次数（read+find+grep+ls） | 53 | 99.6 | 148 | 0 | 52.4 |
| distinct 目标数（uniq_targets） | 32 | 53.6 | 73 | 0 | — |
| `[END] elapsed`（秒） | 730 | 1,638 | 3,547 | 7 | — |

工具总量：`read 3,313`、`grep 2,084`、`find 183`、`ls 451`（合计 6,031）。`[END] exit` 分布：`0 → 90`、`3 → 16`、`2 → 8`、`无 END → 1`。

`uniq_targets` 是**下界**：`[TOOL]` 行按终端宽度截断（观察到最长 124 字符），长路径会被截成同一前缀（例：`…\workers\ds-qg-review-`），不同文件可能合并计数。

### 1.3 热文件（review attempt 的 read 目标，前 6）

| 次数 | 文件字节 | 目标 |
| --- | --- | --- |
| 142 | 371,529 | `packages/multi-workers/autopilot/conductor.py` |
| 130 | — | `…/agent-team-loop/worker/worker-mode.ts`（trace 截断） |
| 77 | — | `…/agent-team-loop/pm/ui-bridge.ts`（trace 截断） |
| 74 | 456,879 | `packages/multi-workers/mw.py` |
| 63 | 248,512 | `packages/multi-workers/mw_common.py` |
| 48 | 135,804 | `packages/multi-workers/launcher.py` |

793 个不同 read 目标 / 3,313 次 read（截断使 distinct 为下界）。注意 `mw.py` 现为 **456,879 B**（卡上写的 401,562 B 是当时快照）。读取工具自身对单文件截断在 **50 KiB / 2000 行**（`packages/coding-agent/src/core/tools/truncate.ts:11-12`：`DEFAULT_MAX_LINES = 2000` / `DEFAULT_MAX_BYTES = 50 * 1024`），所以“读一次 mw.py”实际是 ~50k chars ≈ 12.5k est tokens ≈ **15.7k 实测 tokens** —— 一次 read 就吃满整个 reserve。

## 2. token 归因

### 2.1 join 逻辑（读透 `usage.py`）

| 环节 | 位置 | 原文 |
| --- | --- | --- |
| session id 生成 | `packages/multi-workers/usage.py:268` | `def new_session_id(key: str, pid: int, seq: int) -> str:` → `mw-<slug(key)>-<pid>-<seq>` |
| 归因键 | `packages/multi-workers/usage.py:290` | `def _key_from_session_id(...)`：从 `mw-` 前缀反解 owner key |
| 传给 CLI | `packages/multi-workers/launcher.py:2152-2165` | `_argv_with_session_id`：在尾部 `-p` 之前插入 `["--session-id", sid]` |
| 写入台账 | `packages/multi-workers/launcher.py:2876-2887` | `# mw-usage-monitor T-02: the ledger start row is written the moment the process exists (its pid is what the session log is joined against).` + `session_id=session_id` |
| 会话侧 id | `packages/multi-workers/usage.py:427` | `session_id = str(header.get("id") or session_id)`（header 优先；文件名 `<ts>_<id>.jsonl` 兜底，见 `usage.py:300 _session_id_from_path`） |
| 查询侧 join | `packages/multi-workers/usage.py:1010-1014` | `by_session = { run["session_id"]: run for run in runs if isinstance(run.get("session_id"), str) and run["session_id"] }` |
| worker/PM 分流 | `packages/multi-workers/usage.py:1029` | `if session_id.startswith("mw-"):` |

结论：**session id 的唯一持久化来源是 `runs.jsonl` 的 `start` 事件**。逐项排除其它候选：

- `run.json`：**没有** session_id。全仓 311 个 `run.json` 的键集合为 `{artifacts, ended_at, exit, kind, last_heartbeat_at, model_exhausted, owner_key, pid, run_id, schema, started_at, status, task_key}`。
- argv：不落盘（`launcher.py` 无 argv 记录文件；`_build_command` 只在内存里拼）。
- `_workers.parallel`：`grep "session_id" .agenticdoc/_workers.parallel` → `False`。
- `worker.log`：只在 pi 打印 `Warning: No project session found with id '…'` 时出现，且**每次 attempt 覆盖**。608 个 `worker.log` 中只有 33 个带 id（例：`Warning: No project session found with id 'mw-mw-decision-substitution-82544-15'; creating a new session with that id.`）→ 只能拿到**最后一次** attempt 的 id。

### 2.2 可 join 面与缺口

- 可精确 join：**6/115**（全部在 2026-10-20T12:01 之后，即 `runs.jsonl` 已有本仓 `start` 行之后；本仓最早 start 行 `2026-10-20T11:37:29`）。
- 不可 join：**109/115**。**缺的信号 = ledger `start` 事件（`session_id`）**。该层 2026-10-19 才落地；`ds-qg-review`（09:15–09:23）虽在时间上更晚，但那批 spawn 未写台账（`runs.jsonl` 无对应行）。
- 时间+cwd 兜底**不可用**：pi 会话文件名首段是会话创建时间，与 `[START]` 只差 ~4.4 s，但同一秒可能有多个 worker 同时起。实测 109 次不可 join 的 attempt 中，±5 s 窗口内候选会话文件数为 `1 个 → 52 次`、`2–4 个 → 28 次`、`5–99 个 → 29 次`。**一半以上存在歧义，故整类不用于测量**（不拿近似值充实测）。

### 2.3 join 正确性自证

JSONL 里的检索类 `toolCall` 计数与 trace 的取数次数**逐条相等**：53/53、44/44、41/41、94/94、61/61、89/89。这条等式同时验证了 trace 计数口径与 session 归属。

补一条语料级对照：attempt 1（`…-9`）最后一条 assistant 消息 `usage.totalTokens=214,216`、`stopReason=error`、`rawStopReason=incomplete.max_output_tokens`、`errorMessage="stream closed before response.completed"` —— 即卡上“死于 214k 上下文”的精确证据；prompt 序列为 `… 181,644 → 214,200`（+32,556）。

## 3. tokens/次取数 常数

定义：一次“取数”= 一次 read/find/grep/ls 调用。成本取两种口径：(a) **内容口径** = 该 turn 的 prompt 增量减去该 turn 的 assistant 输出 token；(b) **上下文口径** = prompt 增量全额（含输出）。

| 口径 | p50 | p90 | max | mean |
| --- | --- | --- | --- | --- |
| (a) 内容 tokens/次 | 2,970 | 4,793 | 4,924 | 3,091 |
| (b) 上下文 tokens/次 | 3,230 | 4,854 | 4,977 | 3,226 |

6 个 run 的逐次值（内容口径）：`3863 / 4661 / 4924 / 2076 / 1554 / 1464`；(b) 口径：`3934 / 4731 / 4977 / 2527 / 1638 / 1550`。离散度大（max/min = 3.4×），驱动因子是**每次 read 的字节数**，不是模型：

| session | read 次数 | read 平均 chars | grep 次数 | grep 平均 chars |
| --- | --- | --- | --- | --- |
| …-9 | 41 | 15,480 | 5 | 4,619 |
| …-11 | 39 | 16,435 | 3 | 8,430 |
| …-13 | 39 | 16,748 | 0 | — |
| …-15 | 40 | 8,177 | 45 | 6,302 |
| …-17 | 40 | 4,201 | 20 | 5,034 |
| …-19 | 62 | 3,712 | 22 | 7,411 |

### 与 `estimateTokens`（chars/4）比较

`packages/coding-agent/src/core/compaction/compaction.ts:266`：`export function estimateTokens(message: AgentMessage): number {` … `return Math.ceil(chars / 4);`（注释自称 “conservative (overestimates tokens)”）。

实测 **est/实测 = 0.795（p50）**，区间 0.709–0.812，即 `chars/4` **低估 20.5%**，真实成本 ≈ `chars/4 × 1.26`。低估来源：toolResult 文本之外还有 JSON 包装（`toolCallId` / `toolName` / `timestamp` / `type`）与消息框架，只截文本的 `chars/4` 抓不到这部分。

**误差量级**：单次 read 15,480 chars → `chars/4` = 3,870 tokens，实测 **4,867** tokens，差 **997 tokens/次**；一次 50 KiB 的 read → `chars/4` = 12,500，实测 **~15,700**，单次误差 3,200 tokens（≈ 20% 的 reserve）。用它做预算会系统性超支 26%。

## 4. 断言供给量

### 4.1 判定单元的计数规则（机读）

源：`task.md` front matter 的 `card_path`（相对 key 目录）指向的卡；无 `card_path` 时依次退到 `task.md` 内联的 `<!-- mw-dispatch-card: v1 -->` 块、再退到 `task.md` 本身（表 T1 最后一列给出计数）。

单元 = 去重的 `MAJOR-\d+` / `MINOR-\d+` / `BLOCKER-\d+` / `NIT-\d+` 编号（发现条目）+ 去重 `AC-\d+` + 去重 `VC-\d+` + 首个“交付格式”标题之前的顶层编号要求行（`^\d+[.)]`）。

覆盖情况：`card_path` 存在且可解析 **20/47**；其余 27 个无 `card_path`（其中 9 个靠内联 dispatch card 计数，18 个直接数 `task.md`）。

### 4.2 结果

| 指标 | p50 | p90 | max |
| --- | --- | --- | --- |
| 判定单元数 U（42 个可计目录） | 11 | 21 | 34 |
| 每次取数对应单元数 | 0.168 | 0.411 | 4.25 |
| 每单元摊到的取数次数 | 5.97 | 12.51 | 49.50 |

相关性（n=42，剔除 4 个 0 单元 manual run 与 1 个 0 取数 run）：**Pearson r = 0.136，Spearman = 0.115** —— 取数次数与断言数量基本无关。

极端对照：`mwg-qg-review-20261010` 34 个判定单元只用 8 次取数（4.25 单元/次）；`mwg-qg2b-code-adversarial` 28 个单元用了 148 次（0.19 单元/次）；`ds-qg-review-2` 平均 48 次取数对应 20 个单元。**历史基准：1 条判定单元 ≈ 6 次取数**（p50 5.97），而这条基准正是“读工程”而非“判断言”的产物。

## 5. 预算推荐值

窗口事实（`packages/coding-agent/src/core/compaction/compaction.ts:132-136`）：

```
export const DEFAULT_COMPACTION_SETTINGS: CompactionSettings = {
	enabled: true,
	reserveTokens: 16384,
	keepRecentTokens: 20000,
};
```

触发式（`compaction.ts:235-237`）：`return contextTokens > contextWindow - settings.reserveTokens;` → 200,000 − 16,384 = **183,616** 才压缩。

实测起点：首个 assistant 请求的 prompt = `5,709 / 5,709 / 5,709 / 6,014 / 5,710 / 5,710`（均值 5,760），即 worker 一开局就吃掉 5.8k。可用预算 = 200,000 − 16,384 − 5,760 = **177,856 tokens**。

| 推荐值 | 取值 | 推导（来自哪个分位数） |
| --- | --- | --- |
| 单 worker 取数上限 | **30 次**（硬上限 35） | 177,856 ÷ p90 单次成本 4,854 = 36.6 → 取 30（留 18% 余量）；硬上限 = 177,856 ÷ max 4,977 = 35.7。历史 41–53 次取数的 4 个 run 全部撞墙（末次 prompt 209,761–214,200），与该边界吻合。 |
| 单次 read 字节上限 | **12,288 B**（12 KiB） | 目标：一个 turn（3–4 次取数）不吃穿 reserve 16,384 → 单次 ≤ 4,096 tokens → chars = 4,096 × 0.795 × 4 = 13,025 → 取 12 KiB。12,288 B ≈ 3,072 est ≈ 3,870 实测 tokens。 |
| 每 turn 取数上限 | **3 次**（绝对上限 4） | 16,384 ÷ 4,854（p90 单次）= 3.4。实测事故正跨过这条：prompt 181,644 → 214,200（+32,556，单 turn 8 次取数），而 181,644 < 183,616，压缩检查被整个跳过。 |
| 每单元 claim 数 K | **6** | §4 的 p50「每单元取数次数」= 5.97 → 6。p90 的 12.51 不可负担（12.51 × 4,854 = 60,724 tokens/单元，11 个单元 = 668k ≫ 177,856）。 |
| 单 worker 可承载单元数 | **U ≤ 5** | 30 ÷ 6 = 5（次数约束）；177,856 ÷ (6 × 4,854) = 6.1（上下文约束）→ 取更紧的 5。 |
| 拆分判定式 | `U ≤ 5` → 1×N；`U ≥ 6` → **4×2**；`U > 8` → 4×⌈U/4⌉ | 4×2 = 每 worker 2 个单元 = 2×6 = 12 次取数（上限 30 的 40%），上下文 5,760 + 12×4,854 = 63,808 ≤ 183,616（35% 占用）。判定式用第 3、4 步常数写成：`U × K > C_max`，K=6（p50 5.97）、C_max=30（p90 推导）。 |

对照现状：判定单元 p50 = 11、p90 = 21 → 按本判定式，**中位数卡片就该拆 4×3，p90 卡片拆 4×5**；而历史 115 次 attempt 里 90 次是单 worker 跑完（p50 53 次取数），这解释了它们为何在 p50 上仍成功、却在 p90 上撞窗。

明确否决两个既有默认值：

- `DEFAULT_READ_FILE_CAP = 8` / `DEFAULT_READ_BYTE_CAP = 65_536`（`packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:31-32`；`l2_read_byte_cap=65536` 见 `packages/multi-workers/autopilot/config.py:95-96`，镜像展示字段见 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:88-89`）：65,536 B = 16,384 est tokens ≈ **20,600 实测 tokens**，一次 read 就吃满并超过整个 reserve（16,384）。
- pi read 自带 50 KiB 上限（`truncate.ts:12`）：同上，单次 ≈ 15,700 tokens。

## 6. 失败普查

| 失败形态 | attempt 数 | 实例路径 |
| --- | --- | --- |
| 成功（exit 0） | 90 | `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2c/trace.log`（61 次取数，362 s，exit 0） |
| **超窗降级**（exit 3 → `[MODEL_RETRY]` / `[MODEL_FALLBACK]`） | **16**（6 个 task 目录） | `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/trace.log` 第 1 段：prompt 214,200、`stopReason=error`、`rawStopReason=incomplete.max_output_tokens`，随后 `[MODEL_RETRY] … attempt=1` → `[MODEL_FALLBACK] from=timi/gpt-6.1-sol to=timi/glm-5.3` |
| **needs-clarification**（exit 2） | **8** | `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/trace.log` 第 4 段（glm-5.3，94 次取数，1790 s，exit 2） |
| 超时（`[TIMEOUT]`） | **0** | review 目录 0 命中（全语料 7 条 `[TIMEOUT]` 全在非 review run，如 `.agenticdoc/mw-console-storm-hardening/workers/csg-w03-ts-entry/trace.log`） |
| 无产物 | **0**（目录级） | 47 个 review 目录全部有 `output.md`（最小 397 B，最大 152,154 B）；逐 attempt 的无产物**不可观测**（`output.md` 每次 attempt 覆盖写） |
| 其它（无 `[END]`） | **1** | `.agenticdoc/mw-jev-provider-integration/workers/jev-t05-qg-review/trace.log`，`2026-10-16T10:56:10.478Z` 起，59 次取数后无 END 行 |

`[MODEL_RETRY]` 全语料 11 条、`[MODEL_FALLBACK]` 4 条，**全部落在 review run 内**（review 是唯一出现模型降级的类型）。exit 码映射见 `packages/multi-workers/launcher.py:976-982`（`0→done` / `2→needs-clarification` / 其它 `→failed`）与 `worker/worker-mode.ts:2699-2701`。

### 超窗降级 ↔ 取数次数 / 字节

**取数次数不能区分**：exit 3 的 16 次 attempt 取数区间 `33,35,35,38,41,41,44,45,46,46,53,56,65,68,73,78`，exit 0 的 90 次区间 1–148（中位 53）——两条分布重叠。

**累计取数结果字节能区分**（6 个可精确归因的 run）：

| attempt | exit | 取数 | 累计 toolResult chars | 末次 prompt |
| --- | --- | --- | --- | --- |
| …-9 | 3 | 53 | 658,001 | 214,200 |
| …-11 | 3 | 44 | 666,333 | 213,872 |
| …-13 | 3 | 41 | 654,031 | 209,761 |
| …-15 | 2 | 94 | 614,347 | 253,273（中途 1 次压缩） |
| …-17 | 0 | 61 | 268,785 | 110,666 |
| …-19 | 0 | 89 | 394,225 | 149,328 |

阈值区间：gpt-6.1-sol 上 **> 650k chars（≈163k tokens）必降级**，**< 400k chars（≈100k tokens）全部存活**，400k–650k 为未观测灰区（`…-15` 用 glm-5.3 在 614k chars 下靠压缩勉强存活，说明阈值还依赖模型窗口）。结论：预算应按**累计取数字节 / 上下文**设，而不是按次。

## 数值表

### T1 per-task-dir summary (47 dirs / 115 attempts)

| key | task | attempts | calls_p50 | read | grep | find | ls | uniq_p50 | exit_last | elapsed_p50 | retry | fallback | exit2 | units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| _scratch | manual-1789974535494 | 4 | 1 | 6 | 0 | 0 | 0 | 1 | 0 | 8 | 0 | 0 | 0 | 0 |
| _scratch | manual-1789974660966 | 4 | 2 | 6 | 0 | 0 | 1 | 2 | 0 | 12 | 0 | 0 | 0 | 0 |
| _scratch | manual-1789974753377 | 4 | 4 | 15 | 0 | 0 | 2 | 4 | 0 | 14 | 0 | 0 | 0 | 0 |
| mw-autopilot-gate-alarm-liveness | mwgal-t18-adversarial-qg | 1 | 110 | 63 | 37 | 1 | 9 | 52 | 0 | 2097 | 0 | 0 | 0 | 14 |
| mw-autopilot-slot-capacity | msc-qg-quality-gate | 4 | 76 | 121 | 159 | 15 | 34 | 51 | 0 | 1282 | 0 | 0 | 0 | 6 |
| mw-autopilot-stall-feedback | mw-stall-feedback-l3-review | 4 | 72 | 143 | 107 | 8 | 19 | 38 | 0 | 926 | 0 | 0 | 0 | 12 |
| mw-autopilot-stall-feedback | mw-stall-feedback-l3-review-a2 | 4 | 17 | 53 | 14 | 0 | 0 | 6 | 0 | 452 | 0 | 0 | 0 | 14 |
| mw-console-storm-hardening | csg-qg-review | 1 | 62 | 32 | 22 | 1 | 7 | 33 | 0 | 1162 | 0 | 0 | 0 | 8 |
| mw-decision-substitution | ds-qg-review | 4 | 35 | 163 | 63 | 6 | 17 | 32 | 2 | 154 | 2 | 1 | 1 | 11 |
| mw-decision-substitution | ds-qg-review-2 | 4 | 48 | 159 | 53 | 10 | 10 | 41 | 2 | 230 | 2 | 1 | 1 | 20 |
| mw-decision-substitution | ds-qg-review-2c | 1 | 61 | 40 | 20 | 0 | 1 | 27 | 0 | 362 | 0 | 0 | 0 | 15 |
| mw-decision-substitution | ds-qg-review-2d | 1 | 89 | 62 | 22 | 1 | 4 | 46 | 0 | 466 | 0 | 0 | 0 | 15 |
| mw-dispatch-card-gate | mwd-t11b-adversarial-qg | 1 | 99 | 60 | 27 | 0 | 12 | 53 | 0 | 1883 | 0 | 0 | 0 | 2 |
| mw-dispatch-card-gate | mwd-t17-final-qg | 1 | 83 | 39 | 40 | 2 | 2 | 41 | 0 | 1753 | 0 | 0 | 0 | 3 |
| mw-dispatch-flow-fixes | code-review-1 | 3 | 60 | 71 | 86 | 3 | 22 | 30 | 0 | 1151 | 0 | 0 | 0 | 4 |
| mw-dispatch-flow-fixes | ga-spec-review-2 | 3 | 13 | 11 | 18 | 0 | 6 | 8 | 0 | 488 | 0 | 0 | 0 | 4 |
| mw-dispatch-settle-gates | mds-qg-a-evidence-chain | 1 | 101 | 39 | 49 | 4 | 9 | 59 | 0 | 1242 | 0 | 0 | 0 | 13 |
| mw-dispatch-settle-gates | mds-qg-b-code-adversarial | 1 | 78 | 43 | 23 | 3 | 9 | 39 | 0 | 1130 | 0 | 0 | 0 | 12 |
| mw-done-closure-repair | dcr-review-spec-design | 4 | 62 | 136 | 89 | 2 | 23 | 28 | 0 | 1214 | 0 | 0 | 0 | 6 |
| mw-gate-verdict-hardening | mwg-qg-review-20261010 | 1 | 8 | 6 | 0 | 0 | 2 | 7 | 0 | 54 | 0 | 0 | 0 | 34 |
| mw-gate-verdict-hardening | mwg-qg2a-evidence-chain | 1 | 114 | 45 | 61 | 3 | 5 | 62 | 0 | 1483 | 0 | 0 | 0 | 25 |
| mw-gate-verdict-hardening | mwg-qg2b-code-adversarial | 1 | 148 | 71 | 68 | 0 | 9 | 58 | 0 | 1398 | 0 | 0 | 0 | 28 |
| mw-guard-form-hardening | mwgf-qga-code-adversarial | 1 | 100 | 33 | 47 | 2 | 18 | 45 | 0 | 1532 | 0 | 0 | 0 | 5 |
| mw-jev-provider-integration | jev-t05-qg-review | 4 | 43 | 138 | 37 | 1 | 7 | 30 | no-end | 260 | 2 | 1 | 0 | 11 |
| mw-jev-provider-integration | jev-t05b-qg-review | 1 | 54 | 30 | 19 | 1 | 4 | 27 | 0 | 1326 | 0 | 0 | 0 | 6 |
| mw-jev-provider-integration | jev-t06-qg-review-full | 1 | 36 | 24 | 12 | 0 | 0 | 24 | 0 | 832 | 0 | 0 | 0 | 22 |
| mw-l3-fail-marker-forms | fmr-review-spec-design | 4 | 44 | 112 | 40 | 4 | 11 | 20 | 0 | 992 | 0 | 0 | 0 | 16 |
| mw-model-error-perception | qg-review-mep | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 74 | 0 | 0 | 1 | 10 |
| mw-model-error-perception | qg-review-mep-2 | 1 | 78 | 37 | 24 | 6 | 11 | 44 | 0 | 326 | 0 | 0 | 0 | 10 |
| mw-model-error-perception | qg-review-mep-final | 3 | 65 | 139 | 25 | 3 | 12 | 49 | 3 | 336 | 2 | 0 | 0 | 8 |
| mw-model-error-perception | qg-review-mep-final2 | 4 | 76 | 174 | 85 | 5 | 26 | 45 | 2 | 419 | 2 | 1 | 1 | 8 |
| mw-model-fallback-cli | review-fallback-cli | 2 | 50 | 69 | 26 | 0 | 5 | 28 | 2 | 1430 | 1 | 0 | 1 | 8 |
| mw-model-fallback-cli | review-fallback-cli-r2 | 1 | 36 | 24 | 11 | 0 | 1 | 21 | 0 | 563 | 0 | 0 | 0 | 7 |
| mw-rag-integration | mw-rag-integration-design-critique | 4 | 8 | 33 | 0 | 0 | 0 | 7 | 0 | 730 | 0 | 0 | 0 | 9 |
| mw-rag-integration | mw-rag-integration-design-review | 4 | 88 | 159 | 157 | 16 | 28 | 48 | 0 | 1040 | 0 | 0 | 0 | 10 |
| mw-rag-integration | mw-rag-integration-ref-verify | 4 | 53 | 113 | 114 | 1 | 3 | 19 | 0 | 760 | 0 | 0 | 0 | 21 |
| mw-rag-integration | mw-rag-qg-review | 4 | 112 | 260 | 110 | 9 | 32 | 66 | 0 | 1312 | 0 | 0 | 0 | 19 |
| mw-rag-integration | mw-rag-qg-review-a | 4 | 62 | 152 | 72 | 10 | 15 | 48 | 0 | 928 | 0 | 0 | 0 | 19 |
| mw-rag-integration | mw-rag-qg-review-b | 4 | 70 | 127 | 108 | 7 | 22 | 46 | 0 | 893 | 0 | 0 | 0 | 13 |
| mw-worker-output-contract | acb-v1 | 1 | 38 | 17 | 14 | 3 | 4 | 14 | 0 | 787 | 0 | 0 | 0 | 4 |
| mw-worker-output-contract | acb-v2 | 1 | 18 | 10 | 6 | 2 | 0 | 12 | 0 | 234 | 0 | 0 | 0 | 4 |
| mw-worker-tree-kill | manual-1789974567567 | 4 | 13 | 42 | 0 | 10 | 5 | 12 | 0 | 38 | 0 | 0 | 0 | 0 |
| mw-worker-tree-kill | review-mw-worker-tree-kill | 4 | 44 | 62 | 78 | 10 | 10 | 26 | 0 | 522 | 0 | 0 | 0 | 11 |
| mw-workspace-incident-probe | wip-qg-review | 2 | 77 | 70 | 41 | 21 | 22 | 42 | 0 | 2262 | 0 | 0 | 0 | 11 |
| mw-worktree-junction-guard | wjg-qg-evidence-closure | 1 | 65 | 36 | 25 | 3 | 1 | 36 | 2 | 981 | 0 | 0 | 1 | 17 |
| mw-worktree-junction-guard | wjg-w12-negative-space-audit | 1 | 111 | 46 | 51 | 9 | 5 | 58 | 2 | 1986 | 0 | 0 | 1 | 13 |
| mw-worktree-junction-guard | wjg-w15-delta-adversarial | 1 | 53 | 22 | 24 | 1 | 6 | 36 | 2 | 1645 | 0 | 0 | 1 | 8 |

### T2 per-attempt machine table (CSV, 115 rows; one row per attempt)

```csv
key,task,start,data_calls,read,grep,find,ls,uniq_targets,exit,elapsed_s,model_retry,model_fallback,model_unavailable,exit2,tool_err
_scratch,manual-1789974535494,2026-09-21T07:09:00.398Z,3,3,0,0,0,3,0,13,0,0,0,0,0
_scratch,manual-1789974535494,2026-10-09T07:09:02.895Z,1,1,0,0,0,1,0,7,0,0,0,0,0
_scratch,manual-1789974535494,2026-10-09T12:11:16.780Z,1,1,0,0,0,1,0,9,0,0,0,0,0
_scratch,manual-1789974535494,2026-10-10T03:02:00.534Z,1,1,0,0,0,1,0,8,0,0,0,0,0
_scratch,manual-1789974660966,2026-09-21T07:11:05.809Z,3,3,0,0,0,3,0,10,0,0,0,0,0
_scratch,manual-1789974660966,2026-10-09T07:09:02.886Z,1,1,0,0,0,1,0,11,0,0,0,0,0
_scratch,manual-1789974660966,2026-10-09T12:11:20.034Z,2,1,0,0,1,2,0,16,0,0,0,0,0
_scratch,manual-1789974660966,2026-10-10T03:02:11.734Z,1,1,0,0,0,1,0,13,0,0,0,0,0
_scratch,manual-1789974753377,2026-09-21T07:12:35.529Z,3,3,0,0,0,3,0,10,0,0,0,0,0
_scratch,manual-1789974753377,2026-10-09T07:09:02.765Z,5,4,0,0,1,5,0,16,0,0,0,0,0
_scratch,manual-1789974753377,2026-10-09T12:11:25.739Z,4,4,0,0,0,4,0,15,0,0,0,0,1
_scratch,manual-1789974753377,2026-10-10T03:02:14.782Z,5,4,0,0,1,5,0,14,0,0,0,0,0
mw-autopilot-gate-alarm-liveness,mwgal-t18-adversarial-qg,2026-10-13T13:05:59.549Z,110,63,37,1,9,52,0,2097,0,0,0,0,0
mw-autopilot-slot-capacity,msc-qg-quality-gate,2026-09-26T11:20:23.259Z,102,41,53,1,7,54,0,1487,0,0,0,0,0
mw-autopilot-slot-capacity,msc-qg-quality-gate,2026-10-09T07:08:19.933Z,78,22,43,4,9,48,0,1053,0,0,0,0,0
mw-autopilot-slot-capacity,msc-qg-quality-gate,2026-10-09T12:01:52.303Z,75,29,28,8,10,44,0,1101,0,0,0,0,2
mw-autopilot-slot-capacity,msc-qg-quality-gate,2026-10-10T02:50:10.763Z,74,29,35,2,8,56,0,1464,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review,2026-09-22T16:03:08.545Z,77,41,31,5,0,46,0,485,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review,2026-10-09T07:08:23.149Z,51,31,17,0,3,34,0,807,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review,2026-10-09T12:01:55.804Z,82,43,29,1,9,43,0,1079,0,0,0,0,1
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review,2026-10-10T02:50:14.127Z,67,28,30,2,7,32,0,1044,0,0,0,0,1
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review-a2,2026-09-22T16:12:23.789Z,14,13,1,0,0,7,0,173,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review-a2,2026-10-09T07:08:22.858Z,16,12,4,0,0,6,0,810,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review-a2,2026-10-09T12:01:56.718Z,18,15,3,0,0,5,0,428,0,0,0,0,0
mw-autopilot-stall-feedback,mw-stall-feedback-l3-review-a2,2026-10-10T02:50:14.385Z,19,13,6,0,0,5,0,475,0,0,0,0,0
mw-console-storm-hardening,csg-qg-review,2026-10-15T09:15:54.393Z,62,32,22,1,7,33,0,1162,0,0,0,0,3
mw-decision-substitution,ds-qg-review,2026-10-20T09:15:48.218Z,35,33,1,0,1,31,3,161,1,0,0,0,0
mw-decision-substitution,ds-qg-review,2026-10-20T09:18:34.464Z,35,31,2,0,2,33,3,130,1,0,0,0,0
mw-decision-substitution,ds-qg-review,2026-10-20T09:20:45.411Z,33,31,2,0,0,28,3,147,0,1,0,0,0
mw-decision-substitution,ds-qg-review,2026-10-20T09:23:16.597Z,146,68,58,6,14,63,2,3547,0,0,0,1,3
mw-decision-substitution,ds-qg-review-2,2026-10-20T12:01:08.488Z,53,41,5,5,2,50,3,284,1,0,0,0,0
mw-decision-substitution,ds-qg-review-2,2026-10-20T12:06:00.257Z,44,39,3,2,0,41,3,175,1,0,0,0,0
mw-decision-substitution,ds-qg-review-2,2026-10-20T12:09:01.278Z,41,39,0,1,1,39,3,157,0,1,0,0,0
mw-decision-substitution,ds-qg-review-2,2026-10-20T12:11:47.478Z,94,40,45,2,7,41,2,1790,0,0,0,1,0
mw-decision-substitution,ds-qg-review-2c,2026-10-20T12:16:04.435Z,61,40,20,0,1,27,0,362,0,0,0,0,0
mw-decision-substitution,ds-qg-review-2d,2026-10-20T12:16:04.425Z,89,62,22,1,4,46,0,466,0,0,0,0,0
mw-dispatch-card-gate,mwd-t11b-adversarial-qg,2026-10-12T13:05:54.067Z,99,60,27,0,12,53,0,1883,0,0,0,0,1
mw-dispatch-card-gate,mwd-t17-final-qg,2026-10-12T15:05:48.988Z,83,39,40,2,2,41,0,1753,0,0,0,0,1
mw-dispatch-flow-fixes,code-review-1,2026-10-09T07:08:26.587Z,81,26,42,2,11,50,0,1824,0,0,0,0,1
mw-dispatch-flow-fixes,code-review-1,2026-10-09T12:01:59.790Z,60,21,31,1,7,30,0,1052,0,0,0,0,0
mw-dispatch-flow-fixes,code-review-1,2026-10-10T02:50:17.356Z,41,24,13,0,4,25,0,1151,0,0,0,0,0
mw-dispatch-flow-fixes,ga-spec-review-2,2026-10-09T07:08:26.643Z,15,4,10,0,1,8,0,504,0,0,0,0,0
mw-dispatch-flow-fixes,ga-spec-review-2,2026-10-09T12:01:59.709Z,13,4,4,0,5,9,0,488,0,0,0,0,0
mw-dispatch-flow-fixes,ga-spec-review-2,2026-10-10T02:50:17.284Z,7,3,4,0,0,4,0,242,0,0,0,0,0
mw-dispatch-settle-gates,mds-qg-a-evidence-chain,2026-10-11T09:44:53.652Z,101,39,49,4,9,59,0,1242,0,0,0,0,0
mw-dispatch-settle-gates,mds-qg-b-code-adversarial,2026-10-11T09:44:53.665Z,78,43,23,3,9,39,0,1130,0,0,0,0,1
mw-done-closure-repair,dcr-review-spec-design,2026-09-25T03:57:37.448Z,66,33,28,2,3,30,0,1494,0,0,0,0,0
mw-done-closure-repair,dcr-review-spec-design,2026-10-09T07:08:27.935Z,63,36,21,0,6,26,0,2267,0,0,0,0,0
mw-done-closure-repair,dcr-review-spec-design,2026-10-09T12:01:59.609Z,60,35,18,0,7,28,0,716,0,0,0,0,0
mw-done-closure-repair,dcr-review-spec-design,2026-10-10T02:50:18.463Z,61,32,22,0,7,28,0,935,0,0,0,0,0
mw-gate-verdict-hardening,mwg-qg-review-20261010,2026-10-10T11:54:54.942Z,8,6,0,0,2,7,0,54,0,0,0,0,0
mw-gate-verdict-hardening,mwg-qg2a-evidence-chain,2026-10-10T11:56:35.486Z,114,45,61,3,5,62,0,1483,0,0,0,0,0
mw-gate-verdict-hardening,mwg-qg2b-code-adversarial,2026-10-10T11:56:45.114Z,148,71,68,0,9,58,0,1398,0,0,0,0,3
mw-guard-form-hardening,mwgf-qga-code-adversarial,2026-10-12T02:42:37.833Z,100,33,47,2,18,45,0,1532,0,0,0,0,0
mw-jev-provider-integration,jev-t05-qg-review,2026-10-16T10:40:17.998Z,41,34,5,0,2,32,3,164,1,0,0,0,0
mw-jev-provider-integration,jev-t05-qg-review,2026-10-16T10:43:05.008Z,38,33,5,0,0,27,3,357,1,0,0,0,0
mw-jev-provider-integration,jev-t05-qg-review,2026-10-16T10:49:06.906Z,45,39,5,0,1,34,3,421,0,1,0,0,0
mw-jev-provider-integration,jev-t05-qg-review,2026-10-16T10:56:10.478Z,59,32,22,1,4,28,,,0,0,0,0,3
mw-jev-provider-integration,jev-t05b-qg-review,2026-10-16T11:28:05.335Z,54,30,19,1,4,27,0,1326,0,0,0,0,2
mw-jev-provider-integration,jev-t06-qg-review-full,2026-10-16T12:44:09.975Z,36,24,12,0,0,24,0,832,0,0,0,0,0
mw-l3-fail-marker-forms,fmr-review-spec-design,2026-09-25T08:32:20.727Z,28,17,10,1,0,14,0,841,0,0,0,0,1
mw-l3-fail-marker-forms,fmr-review-spec-design,2026-10-09T07:08:30.565Z,52,36,10,0,6,30,0,1413,0,0,0,0,0
mw-l3-fail-marker-forms,fmr-review-spec-design,2026-10-09T12:02:13.170Z,41,30,8,2,1,19,0,1006,0,0,0,0,0
mw-l3-fail-marker-forms,fmr-review-spec-design,2026-10-10T02:50:50.640Z,46,29,12,1,4,20,0,978,0,0,0,0,0
mw-model-error-perception,qg-review-mep,2026-10-15T12:04:35.436Z,0,0,0,0,0,0,2,74,0,0,0,1,0
mw-model-error-perception,qg-review-mep-2,2026-10-15T12:06:15.880Z,78,37,24,6,11,44,0,326,0,0,0,0,1
mw-model-error-perception,qg-review-mep-final,2026-10-15T12:53:43.471Z,68,48,14,2,4,55,3,857,1,0,0,0,0
mw-model-error-perception,qg-review-mep-final,2026-10-15T13:08:02.969Z,65,51,8,1,5,49,3,336,1,0,0,0,0
mw-model-error-perception,qg-review-mep-final,2026-10-15T13:13:39.709Z,46,40,3,0,3,33,3,331,0,0,0,0,0
mw-model-error-perception,qg-review-mep-final2,2026-10-15T13:21:06.584Z,56,44,6,1,5,43,3,189,1,0,0,0,0
mw-model-error-perception,qg-review-mep-final2,2026-10-15T13:24:17.924Z,78,55,19,1,3,53,3,503,1,0,0,0,0
mw-model-error-perception,qg-review-mep-final2,2026-10-15T13:32:45.185Z,73,48,20,1,4,41,3,452,0,1,0,0,0
mw-model-error-perception,qg-review-mep-final2,2026-10-15T13:40:22.779Z,83,27,40,2,14,47,2,386,0,0,0,1,2
mw-model-fallback-cli,review-fallback-cli,2026-10-15T15:38:41.459Z,46,31,12,0,3,28,3,1168,1,0,0,0,1
mw-model-fallback-cli,review-fallback-cli,2026-10-15T15:58:12.844Z,54,38,14,0,2,29,2,1692,0,0,0,1,1
mw-model-fallback-cli,review-fallback-cli-r2,2026-10-15T16:30:29.083Z,36,24,11,0,1,21,0,563,0,0,0,0,1
mw-rag-integration,mw-rag-integration-design-critique,2026-09-22T08:38:49.552Z,9,9,0,0,0,9,0,301,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-critique,2026-10-09T07:08:46.125Z,8,8,0,0,0,7,0,716,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-critique,2026-10-09T12:02:47.265Z,8,8,0,0,0,7,0,788,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-critique,2026-10-10T02:51:27.981Z,8,8,0,0,0,7,0,743,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-review,2026-09-22T08:31:09.460Z,77,36,28,8,5,40,0,385,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-review,2026-10-09T07:08:46.942Z,93,44,42,2,5,50,0,1110,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-review,2026-10-09T12:02:51.713Z,83,35,37,2,9,45,0,970,0,0,0,0,0
mw-rag-integration,mw-rag-integration-design-review,2026-10-10T02:51:30.170Z,107,44,50,4,9,55,0,1469,0,0,0,0,0
mw-rag-integration,mw-rag-integration-ref-verify,2026-09-22T08:38:49.560Z,75,28,46,1,0,23,0,328,0,0,0,0,0
mw-rag-integration,mw-rag-integration-ref-verify,2026-10-09T07:08:46.599Z,53,32,19,0,2,20,0,968,0,0,0,0,0
mw-rag-integration,mw-rag-integration-ref-verify,2026-10-09T12:02:53.091Z,50,26,24,0,0,18,0,687,0,0,0,0,0
mw-rag-integration,mw-rag-integration-ref-verify,2026-10-10T02:51:34.639Z,53,27,25,0,1,16,0,832,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review,2026-09-22T12:51:33.403Z,50,39,4,5,2,41,0,199,0,0,0,0,1
mw-rag-integration,mw-rag-qg-review,2026-10-09T07:08:46.589Z,103,58,33,1,11,64,0,1168,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review,2026-10-09T12:02:57.480Z,121,79,31,2,9,69,0,1457,0,0,0,0,1
mw-rag-integration,mw-rag-qg-review,2026-10-10T02:51:38.020Z,137,84,42,1,10,73,0,1623,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-a,2026-09-22T12:55:33.364Z,57,40,11,6,0,51,0,174,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-a,2026-10-09T07:08:46.957Z,63,37,22,0,4,44,0,1264,0,0,0,0,1
mw-rag-integration,mw-rag-qg-review-a,2026-10-09T12:02:59.441Z,68,42,17,2,7,52,0,898,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-a,2026-10-10T02:51:41.798Z,61,33,22,2,4,46,0,958,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-b,2026-09-22T12:55:43.033Z,42,36,2,4,0,37,0,94,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-b,2026-10-09T07:08:46.973Z,82,35,37,1,9,49,0,2135,0,0,0,0,0
mw-rag-integration,mw-rag-qg-review-b,2026-10-09T12:03:01.447Z,75,29,35,2,9,49,0,845,0,0,0,0,2
mw-rag-integration,mw-rag-qg-review-b,2026-10-10T02:51:48.074Z,65,27,34,0,4,43,0,941,0,0,0,0,0
mw-worker-output-contract,acb-v1,2026-10-15T06:35:34.805Z,38,17,14,3,4,14,0,787,0,0,0,0,0
mw-worker-output-contract,acb-v2,2026-10-15T06:35:39.735Z,18,10,6,2,0,12,0,234,0,0,0,0,1
mw-worker-tree-kill,manual-1789974567567,2026-09-21T07:09:30.561Z,20,13,0,5,2,14,0,48,0,0,0,0,0
mw-worker-tree-kill,manual-1789974567567,2026-10-09T07:08:59.019Z,12,10,0,1,1,12,0,27,0,0,0,0,0
mw-worker-tree-kill,manual-1789974567567,2026-10-09T12:09:12.151Z,11,8,0,1,2,10,0,29,0,0,0,0,0
mw-worker-tree-kill,manual-1789974567567,2026-10-10T02:59:10.283Z,14,11,0,3,0,11,0,48,0,0,0,0,1
mw-worker-tree-kill,review-mw-worker-tree-kill,2026-09-19T14:47:37.443Z,37,19,16,1,1,18,0,748,0,0,0,0,0
mw-worker-tree-kill,review-mw-worker-tree-kill,2026-10-09T07:08:59.078Z,8,7,1,0,0,7,0,35,0,0,0,0,1
mw-worker-tree-kill,review-mw-worker-tree-kill,2026-10-09T12:09:18.405Z,50,15,28,4,3,34,0,443,0,0,0,0,1
mw-worker-tree-kill,review-mw-worker-tree-kill,2026-10-10T02:59:15.403Z,65,21,33,5,6,45,0,600,0,0,0,0,2
mw-workspace-incident-probe,wip-qg-review,2026-10-10T09:19:08.733Z,69,30,18,9,12,39,0,2994,0,0,0,0,3
mw-workspace-incident-probe,wip-qg-review,2026-10-12T08:05:56.815Z,85,40,23,12,10,45,0,1531,0,0,0,0,3
mw-worktree-junction-guard,wjg-qg-evidence-closure,2026-10-13T16:30:28.199Z,65,36,25,3,1,36,2,981,0,0,0,1,0
mw-worktree-junction-guard,wjg-w12-negative-space-audit,2026-10-13T17:03:36.137Z,111,46,51,9,5,58,2,1986,0,0,0,1,1
mw-worktree-junction-guard,wjg-w15-delta-adversarial,2026-10-14T00:03:25.129Z,53,22,24,1,6,36,2,1645,0,0,0,1,0
```

### T3 token 归因（6 次 review attempt，session id 由 ledger 精确 join）

| task | session_id | 取数(trace) | 取数(jsonl) | requests | prompt_sum | prompt_max | ret_chars | 内容 tokens/次 | 含输出 tokens/次 | est(chars/4)/次 | est/实测 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ds-qg-review-2 | mw-mw-decision-substitution-82544-9 | 53 | 53 | 10 | 1,031,560 | 214,200 | 658,001 | 3,863 | 3,934 | 3,104 | 0.803 |
| ds-qg-review-2 | mw-mw-decision-substitution-82544-11 | 44 | 44 | 8 | 784,483 | 213,872 | 666,333 | 4,661 | 4,731 | 3,786 | 0.812 |
| ds-qg-review-2 | mw-mw-decision-substitution-82544-13 | 41 | 41 | 8 | 697,598 | 209,761 | 654,031 | 4,924 | 4,977 | 3,988 | 0.810 |
| ds-qg-review-2 | mw-mw-decision-substitution-82544-15 | 94 | 94 | 76 | 10,483,255 | 253,273 | 614,347 | 2,076 | 2,527 | 1,634 | 0.787 |
| ds-qg-review-2c | mw-mw-decision-substitution-82544-17 | 61 | 61 | 12 | 713,969 | 110,666 | 268,785 | 1,554 | 1,638 | 1,102 | 0.709 |
| ds-qg-review-2d | mw-mw-decision-substitution-82544-19 | 89 | 89 | 16 | 1,429,404 | 149,328 | 394,225 | 1,464 | 1,550 | 1,107 | 0.756 |

### T4 分工具结果体量（同 6 个 session 的 toolResult 文本）

| session | read n | read 平均 chars | grep n | grep 平均 chars | find n | ls n |
| --- | --- | --- | --- | --- | --- | --- |
| …-9 | 41 | 15,480 | 5 | 4,619 | 5 | 2 |
| …-11 | 39 | 16,435 | 3 | 8,430 | 2 | 0 |
| …-13 | 39 | 16,748 | 0 | — | 1 | 1 |
| …-15 | 40 | 8,177 | 45 | 6,302 | 2 | 7 |
| …-17 | 40 | 4,201 | 20 | 5,034 | 0 | 1 |
| …-19 | 62 | 3,712 | 22 | 7,411 | 1 | 4 |

### T5 预算推导（窗口 200,000 / reserve 16,384 → 触发线 183,616）

| 量 | 值 | 来源 |
| --- | --- | --- |
| 起始 prompt P0 | 5,760（5,709–6,014） | 6 个 session 的首个 assistant 请求 |
| 可用预算 | 177,856 | 200,000 − 16,384 − 5,760 |
| 单次成本 p50 / p90 / max | 3,230 / 4,854 / 4,977 | T3「含输出 tokens/次」 |
| 折算取数上限 | 55.1 / 36.6 / 35.7 | 177,856 ÷ 上述成本 |
| 采用值 | 30（硬 35） | p90 推导 × 0.82 余量 |
| 单次 read 上限 | 12,288 B | 16,384 ÷ 4 次/turn = 4,096 tokens → ×0.795×4 chars |
| K（claim/单元） | 6 | §4 p50 5.97 |
| 拆分线 | U ≥ 6 | 30 ÷ 6 = 5 → 6 起拆 4×2 |

## 未找到清单

| 要求 | 状态 | 命令 + 输出 |
| --- | --- | --- |
| 109 次 review attempt 的 session id | **未找到** | `python rq1_join.py` → `review attempts 115 ledger joined 6`；`grep session_id .agenticdoc/_workers.parallel` → `False`；`run.json` 键集合无 `session_id` |
| review attempt 的逐次 needs-clarification 文本标记 | **未找到** | 扫描器内 `"needs-clarification" in line.lower()` 对 review 段计数 → 全 0；只能用 `[END] exit=2` |
| 逐 attempt 的“无产物” | **未找到** | `output.md` 每 attempt 覆盖写；目录级 0 缺失（`n==0 → 0`，最小 397 B） |
| `worker.log` 的 per-attempt session id | **未找到** | 608 个 `worker.log` 仅 33 个带 id，且为最后一次 attempt |
| review run 的 `[TIMEOUT]` | **未找到** | review 段 `timeout` 计数全 0（全语料 7 条均在非 review 目录） |
| `model unavailable` 字样 | **未找到** | review 段 `unavailable` 列全 0 |
| 27/47 目录的 `card_path` | **未找到** | `Counter({'no': 27, 'has': 20})`；已用内联 dispatch card / `task.md` 兜底 |

## 未覆盖面声明

- **不进设计**：本卡只标定常数，不提出 review 协议 / claim 数据结构的改动。
- **不覆盖非 pi CLI**：6 个可归因 run 全为 `cli=pi`；语料里 review 类 claude/codex run 为 0（`usage.py:574 scan_claude_session` 的 dedup 路径未参与测量）。
- **不覆盖 400k–650k chars 灰区**：无观测样本，不下结论。
- **不覆盖 2026-10-19 之前的 attempt 成本**（109/115，缺 ledger 信号）。token 常数只基于 6 次 attempt；虽然 join 已用 toolCall 计数逐条自证，但**样本量小且集中在同一 key**，外推到全语料属于推断而非实测。
- **不做 vitest / pytest**：只读扫描，未执行任何测试套件。

## 结论

review “读工程”式成本常数已标定：单次取数 p50 3,230 / p90 4,854 tokens（内容口径 p50 2,970），`chars/4` 低估 20.5%，历史每 1 条判定单元摊 5.97 次取数且与断言数量无相关（r=0.136）。据此单 worker 上限 30 次 / 单次 12 KiB / 每 turn 3–4 次、K=6，`U ≥ 6` 即 4×2 拆分；失败阈值应由累计取数字节（>650k chars 降级）而非次数决定。

## 证据

- 语料：601 个 `trace.log` → 1,973 个 attempt 段 → 115 个 review attempt / 47 个目录（判据与计数命令见 §1.1）。
- 归因：`usage.py:268/290/300/427/1010-1014/1029` + `launcher.py:2152-2165/2876-2887`；6/115 精确 join，JSONL toolCall 数与 trace 取数次数逐条相等。
- 成本：6 个 session 的 prompt 增量与 toolResult 文本实测（表 T3 / T4）；`compaction.ts:132-136/235-237/266` 给出窗口与 `chars/4` 口径。
- 断言供给：42 个可计目录的判定单元 vs 取数次数（r=0.136 / ρ=0.115）。
- 失败：exit 分布 90/16/8/1；`ds-qg-review-2` 三次 attempt 的 `incomplete.max_output_tokens` 原文。

## 残留与未验证

- 109/115 attempt 无 session id → 成本常数样本仅 6 次、单一 key（`mw-decision-substitution`），跨 key 外推未验证。
- 400k–650k chars 灰区无样本；glm-5.3 的窗口上限未测（其 253k prompt 未报错）。
- 逐 attempt 无产物、逐 attempt needs-clarification 文本标记不可观测（仅 exit 码）。
- `uniq_targets` 受 trace 截断影响，为下界。
- 建议值未做端到端回归（本角色只读，无法跑 worker）。

## 上下文来源

- `.agenticdoc/claim-driven-review/tasks/RQ-1-review-corpus-calibration.md`
- 全仓 `.agenticdoc/*/workers/*/trace.log`、`run.json`、`task.md`、`output.md`、`worker.log`、`progress.md`
- `.agenticdoc/*/tasks/*.md`（20 个 review 卡）
- `packages/multi-workers/usage.py`、`launcher.py`、`autopilot/config.py`
- `packages/coding-agent/src/core/compaction/compaction.ts`、`core/tools/truncate.ts`、`extensions/agent-team-loop/worker/read-scope.ts`、`worker/worker-mode.ts`、`autopilot/status-model.ts`
- 机器级台账 `runs.jsonl` 与 pi 会话 JSONL（只读）

[VERIFY] 取数次数 p50=53 p90=99.6 max=148 (115 review attempts) · tokens/次 p50=3230 p90=4854 max=4977 · chars/4 低估 20.5% · 每单元取数 p50=5.97 · 单 worker 上限 30 次 / 12 KiB / turn 3-4 · K=6 · U>=6 → 4x2 · 超窗阈值 >650k chars
