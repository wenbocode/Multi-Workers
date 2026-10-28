# RQ-3 度量与灰度基线 —— 两种拆法怎么比、advisory 前后怎么取证

- Key: `claim-driven-review-orchestration` / 卡：`tasks/RQ-3-metrics-baseline.md`
- 类型：research（只读；只写本文件）
- 冻结快照时间：**2026-10-22T09:38:12Z**（此后台账仍在增长：本次作业期间 `start` 行 608 → 612，多 worker 并发在跑；下文所有数字均属该快照）
- 环境：Windows / PowerShell 5.1 + `python`（本机 `bash` 工具实为 PowerShell，故所有复算命令以 PowerShell here-string 形式给出，可直接粘贴）

## 结论

| # | 问题 | 结论 | 复核命令 / 锚点 |
|---|---|---|---|
| 1 | `runs.jsonl` 的 `start` 行有哪些字段 | **16 个键，612/612 行键集合完全一致**：`event,run_id,ts,source,project,key,task_key,type,role,cli,attribution,session_id,model,model_source,pid,cwd`。无 `claims`、无 argv、无 tool 计数 | `launcher.py:291`（`_usage_start_record`） |
| 2 | `session_id` 写入点 | 唯一写入口是 spawn 成功后立即写的 `start` 事件（`launcher.py:2846` 分配 → `:2883` 落盘）；`session_id` 经 `--session-id` 传入 pi（`launcher.py:2152`），也反解 owner key（`usage.py:343`） | `launcher.py:218,291,2152,2846-2888` |
| 3 | 上游 6/115 是真的吗 | **真的，但分母不是台账行**：分母是按 `trace.log` 的 `[START] … type=review` 段计的 attempt。把 attempt 截到 `< 2026-10-20T13:00:00Z` 时复算得 **115 attempt / 6 可 join**，与上游逐字一致。今天全时段是 **149 attempt / 40 可 join**（26.8%） | §2 复算脚本输出 `REVIEW_JOIN cut=...` |
| 4 | 那 token 到底能不能归因 | **能——只要 spawn 走过 launcher**。台账内 `start` 行 100% 带 `session_id`；真实项目 spawn **485/486** 能 join 到带 `usage` 的 pi 会话（**99.79%**，唯一缺口是一条仍在跑的 run）。`6/115` 的惨状来自 **105 次 pre-ledger-epoch attempt**（早于 `2026-10-19T10:20:32Z`），属结构性缺信号，不是 join 机制坏了 | §2 `JOIN {...}`、`REVIEW post-ledger-epoch` |
| 5 | proxy 侧有 per-session token 落盘吗 | **没有**。`proxy.log` 只有 `req=N start body_bytes=` / `req=N done bytes= duration_ms=`，无 token 计数；`session` 标签是 relay 模式下的 6 位随机 hex + cwd，不是 pi session id；`proxy_multi.py` 传 `logger=None` 且不传 `session_id`。**join 键不存在** | `~/.timi-anthropic-proxy/logs/proxy.log`（196,756 行）、`proxy_multi.py:36-47` |
| 6 | `mw stats` 里有 claims 列吗 | **没有，一行也没有**。`_run_claims_counts` 只从 ledger 事件读 `claims`/`claims_line`/`trace`，而 launcher 的 `end` 事件键集合是 `{event,exit,reconciled,run_id,status,ts,wall_s}` —— 没人写 claims。实测 `--key claim-driven-review` 17 runs，`rows with claims 0` | `mw.py stats`（§5 实测输出）、`usage.py:1021`、`launcher.py:320` |
| 7 | `mw status` 里有 `tokens_per_closed_claim` 吗 | 有字段但**恒为 `n/a`**：它只读 `run.json.claims.tokens`，而 worker 写死 `tokens: null`（设计如此，worker 无法自知 token）。3 条有 claims 的 run.json 全是 `tokens: null` | `autopilot/status-model.ts:1717,1750`、`worker-mode.ts:935` |
| 8 | 1×20 与 4×5 现在能并排比吗 | **不能**，三个硬缺口：①没有 20-claim 卡；②`usage.py` 只有 **per-run** `tokens_per_closed_claim`，没有 arm 级 `Σtokens/Σclosed` 聚合；③两臂读预算不对称（1×20 得 30 次取数 = 1.5/claim，4×5 每单元也得 30 次 = 合计 120 次 = 6/claim，**差 4 倍**） | `dispatch-card.ts:1042`（`min(30, 6n)`）、§6 |
| 9 | advisory 基线能扫多少 | `run.json` **409 条**；卡内带 `mw-claims: v1` 块 **8 条**（全在 `claim-driven-review` key），不带 **401 条**。review 子集：带块 6 / 不带块 49 | §7 实测表 |
| 10 | exit 分布能区分超时吗 | **不能**。worker 超时是 `exit=1` + trace `[TIMEOUT] <ts> <idle|wall>: <detail>`，`run.json` 无 timeout 字段、无 exit 124。语料里 `[TIMEOUT]` 共 **4 个目录**，`[IDLE_KILL]` **0** | `worker-mode.ts:3794-3832`、§7 |
| 11 | retrospective 能撑起结论吗 | **不能**。带块组 settled n=5（review 只有 3），Fisher 精确检验 `p=0.283`，什么都说明不了 | §8 |
| 12 | 新窗口要多长 | 检出 10pp 完成率变化需 **≈295 attempt/臂**（α=0.05，power 0.8）；review 观测吞吐 ~5/day（近 3 天 40 次），即 **≈59 天/臂**（若走 A/B 则 118 天）。n=47 只能排除 ≥27pp 的回归 | §8 功效表 |

**一句话整改建议**（本 RQ 最高杠杆项）：launcher 在 `end` 事件里补上 run.json 的 `claims` 子对象（5 个标量 + `tokens:null`），`usage.claims_metrics` 就能立刻用现成的 99.8% session join 把 `tokens_per_closed_claim` 从 `n/a` 变成真值；否则两条数据通路（TS 读 run.json、PY 读 ledger）永远不相交。

## 证据

### 1. `start` 行字段与写入点（实测）

字段清单与覆盖率（612 行）：

| 字段 | 空值 | 不同取值 | 说明 |
|---|---|---|---|
| `event` | 0 | 1 | 恒 `start` |
| `run_id` | 0 | 612 | `<UTC 秒>-<pid>-<seq>`（`launcher.py:204`） |
| `ts` | 0 | 545 | `2026-10-19T10:20:32+00:00` .. `2026-10-22T09:37:00+00:00`（台账纪元起点就是第一行） |
| `source` | 0 | 1 | 全部 `worker`（PM 单元不写台账，只能从会话侧推出） |
| `project` | 0 | 104 | 其中 126 行是 pytest 临时目录（fixture 污染） |
| `key` | 0 | 24 | owner key |
| `task_key` | 0 | 486 | |
| `type` | 0 | 8 | `coding 301 / phase-writer 157 / review 62 / research 50 / reviewer 26 / repair 12 / verifier 1 / vision 1` |
| `role` | 0 | 4 | |
| `cli` | 0 | 1 | 全部 `pi`（无 claude/codex 语料） |
| `attribution` | 0 | 1 | 恒 `exact`（`_usage_attribution` 只对 pi/claude 给 exact） |
| `session_id` | **0** | 612 | 100% 非空；`mw-<slug(key)>-<pid>-<seq>` |
| `model` | 126 | 5 | 空值 = fixture（`model_source=default`） |
| `model_source` | 0 | 6 | `config:coding 338 / default 126 / config:review 84 / config:research 38 / window 22 / fallback 2` |
| `pid` | 0 | 582 | 去重后 582 个唯一 pid |
| `cwd` | 0 | 104 | worker 实际 cwd（dual/partition 模式下不等于 `project`） |

写入时序：`subprocess.Popen` → `_usage_start(...)`（注释原文：*the ledger `start` row is written the moment the process exists*）→ `running_procs[...]`。即 **start 行保证在子进程存活之后、任何 LLM 调用之前**；失败路径另写 `spawn_failed`（14 行，无 `session_id`）。

`[CLAIMS]`/claims **不在** `start` 行、也不在 `end` 行（见结论 #6）。

### 2. 归因覆盖率实测（含复算命令）

#### 2.1 台账内覆盖率（复算 `6/115` 的同一脚本）

```powershell
cd H:\git\Multi-Workers; @'
import os,json,pathlib,re,collections,datetime
def pis(v):
    if not v: return None
    v=str(v).replace('Z','+00:00')
    try: return datetime.datetime.fromisoformat(v)
    except ValueError: return None
p=os.path.expanduser('~/.mw/usage/runs.jsonl')
starts=[json.loads(l) for l in open(p,encoding='utf-8',errors='replace') if l.strip()]
starts=[s for s in starts if s.get('event')=='start']
# pi 会话索引：header.id -> 文件
sroot=pathlib.Path(os.path.expanduser('~/.pi/agent/sessions')); idx={}
for f in sroot.rglob('*.jsonl'):
    with f.open('r',encoding='utf-8',errors='replace',newline='') as h: first=h.readline(65536)
    if '"session"' not in first: continue
    d=json.loads(first)
    if d.get('type')=='session' and d.get('id'): idx[str(d['id'])]=f
def usage(f):
    with f.open('r',encoding='utf-8',errors='replace',newline='') as h:
        for l in h:
            t=l.strip()
            if '"assistant"' not in t and '"compaction"' not in t: continue
            e=json.loads(t)
            if e.get('type')=='message':
                m=e.get('message') or {}
                if m.get('role')=='assistant' and isinstance(m.get('usage'),dict): return True
    return False
st=collections.Counter()
for s in starts:
    g='pytest' if 'pytest-of-' in (s.get('project') or '') else 'real'
    f=idx.get(s['session_id']); st[(g,'start')]+=1
    if f is None: st[(g,'no_file')]+=1
    else: st[(g,'usage' if usage(f) else 'no_usage')]+=1
print('JOIN', {f'{k[0]}/{k[1]}':v for k,v in sorted(st.items())})
# trace attempt 分母
root=pathlib.Path('.agenticdoc')
S=re.compile(r'^\[START\]\s+(\S+)\s+task=(\S+)\s+type=(\S+)')
rv=[]
for t in root.glob('**/workers/*/trace.log'):
    for l in t.read_text(encoding='utf-8',errors='replace').splitlines():
        m=S.match(l)
        if m and m.group(3) in ('review','reviewer','verifier'): rv.append((pis(m.group(1)), m.group(2)))
by=collections.defaultdict(list)
for s in starts: by[s['task_key']].append(s)
def hit(dt,task,tol=300):
    return any(abs((pis(s['ts'])-dt).total_seconds())<=tol for s in by.get(task,[]) if s.get('ts'))
for cut in (None,'2026-10-20T13:00:00Z'):
    sub=[x for x in rv if x[0] and (cut is None or x[0]<pis(cut))]
    print(f'REVIEW_JOIN cut={cut} total={len(sub)} matched={sum(1 for dt,t in sub if hit(dt,t))}')
post=[x for x in rv if x[0] and x[0]>=pis('2026-10-19T10:20:32Z')]
print('REVIEW post-epoch', len(post), 'matched', sum(1 for dt,t in post if hit(dt,t)))
'@ | python -
```

实跑输出（快照 2026-10-22T09:38:12Z）：

```
LEDGER events {'start': 612, 'end': 592, 'spawn_failed': 14}
LEDGER starts 612 non-empty session_id 612
LEDGER cli {'pi': 612}
LEDGER end exit {0: 535, 1: 21, 2: 14, 3: 7, 134: 13, None: 2}
LEDGER end status {'done': 535, 'failed': 41, 'needs-clarification': 14, 'lost': 2}
PI session files with header id 4723
JOIN {'pytest/no_file': 126, 'pytest/start': 126, 'real/no_file': 1, 'real/start': 486, 'real/usage': 485}
TRACE worker dirs 719 trace.log 701
TRACE review attempts(all time) 149
REVIEW_JOIN cut=None total=149 matched=40
REVIEW_JOIN cut=2026-10-20T13:00:00Z total=115 matched=6
REVIEW post-epoch 44 matched 40
```

读数：真实项目 spawn **486**，其中 **485** 能端到端归因（`start.session_id` → 会话 header `id` → 至少一条 `message.usage`）= **99.79%**。唯一缺口：`mw-daily-time-log-14372-7`（`H:\MWWorkeSpace\Z-Schedule`，`R-t04-example-layout`，`2026-10-22T09:10:56Z`），台账有 start 行但磁盘上无对应会话文件（截至快照仍在跑或 pi 尚未落首行）。126 条 pytest fixture spawn 共用假 CLI，无会话文件，属噪声，应过滤。

#### 2.2 `6/115` 的分母到底是什么

上游（`claim-driven-review/evidence/research/spec-rq1-review-corpus-20261020.md` §2.2）的 115 是 **`trace.log` 里 `type=review` 的 attempt 数**，不是台账行数。差异来源已实测定位：

- attempt 早于台账纪元（`2026-10-19T10:20:32Z`）的有 **105/149**，这 105 次**物理上没有** `session_id` 可 join —— 台账层当天才上线。
- 台账纪元之后：**44 次 attempt，40 次可 join；剩下 4 次全部是 `ds-qg-review`（2026-10-20T09:15:48 / 09:18:34 / 09:20:45 / 09:23:16）**，与上游点名的"那批 spawn 未写台账"完全吻合（实测无对应 ledger 行）。

所以 `6/115` 是**历史语料的覆盖率**，不是 join 机制的能力上限；把它当作"token 不可归因"的证据会误判（结论 #4）。

#### 2.3 token 总量口径（避免重复计数）

`usage.py` 的 `tokens` = `input + output + cache_read + cache_write`（`TOKEN_FIELDS`，`usage.py:95`），**不含** pi 会话里的 `usage.totalTokens`（后者与本式重复）。`usage.cost.*` 全为 0（本地代理不计费）→ **成本类指标不可用**。

### 3. 4×5 对照实验的最小可行形态

#### 3.1 现状约束

- 材料：`evidence/t07/claims-plan.md` 已有 **A/B/C/D 四张卡 × 5 条 = 20 条**可判断言（含 3 个真实产出：`cdr-t07b/e/f` 的 `[CLAIMS]` 行）。**没有**单张 20-claim 卡。
- 自动化：`dispatch.py` / agent-team-loop **没有**任何 `n>5 → ceil(n/5)` 的扇出实现（grep `Math.ceil(.*claims`/`mergeUnit` 均 0 命中），4+1 单元必须**手工写卡**。
- 读预算不对称（硬伤）：`claimBudgetCaps = { fileCap: min(callCap=30, perClaim=6 × n) }`。n=20 → 30；n=5 → 30。于是 1×20 臂只有 **30 次取数（1.5/claim）**，4×5 臂有 **4×30 = 120 次（6/claim）**，`byteCap` 同理 393,216 vs 4×393,216。**这一项就能单独解释"4×5 更贵/更多产物"，必须先对称化**（建议每单元 `floor(30/k)` = 7/8 次，合计 30/32）。
- `tokens_per_closed_claim` 只有 per-run 值；`status-model.ts:1750` 的 `Σtokens/Σclosed` 是按 **key** 聚合（不是按实验臂），且因 `tokens` 恒 null 而恒 `n/a`。

#### 3.2 报表行字段草案（字段名 + 来源 + 缺值语义）

| 字段 | 来源 | 缺值语义 |
|---|---|---|
| `exp_id` | **不存在**（需在卡/adoc 登记） | 缺 → 该行不进任何对照组 |
| `arm` ∈ `1x20` / `4x5` | **不存在**（同上） | 缺 → 同上 |
| `unit_id` | `run.json.task_key` / worker 目录名 | 缺 → 跳过 |
| `unit_role` ∈ `evidence` / `merge` | **不存在**（dispatch 无 merge 概念；需卡内显式声明） | 缺 → 按 `evidence` 处理但**不计分母**（保守） |
| `claims_total` | `run.json.claims.total` / `[CLAIMS] claims=` | 缺 → 该单元无度量（`None`，非 0） |
| `closed` / `partial` / `unverified` | 同上 | 同上 |
| `fetches` | `run.json.claims.fetches`（**只计放行读类调用**） | 缺 → `None` |
| `tokens` | 仅 `usage.py` 的 session join 能得到；`run.json.claims.tokens` 恒 `null` | 缺 → `n/a`，`attributable=false` |
| `tokens_per_closed_claim` | 派生 = `Σtokens / Σclosed`（arm 级） | 任一分量缺或 `closed=0` → `n/a` |
| `attributable_ratio` | 有 tokens 的单元数 / 单元总数 | 恒可算；<1 时主指标必须显示 `n/a` |
| `calls` | `usage.scan_pi_session` 事件数 = **assistant 消息数（≈turn 数，不是 tool 调用数）** | 缺 → `None` |
| `tool_calls` | `trace.log` 的 `[END] … tools=<n>`（1428/1428 END 行都有） | 缺 → `None`（run.json **无**此字段） |
| `wall_s` | `ledger end.wall_s`（spawn→reap） | 缺/未结束 → `None`（永不 0，永不拿会话跨度顶替） |
| `exit` | `run.json.exit` / `ledger end.exit` | 缺 → 仍在跑，必须**剔除**出完成率分母 |
| `timeout` | `trace.log` 含 `[TIMEOUT]`/`[IDLE_KILL]` | 缺 → `false`（exit 码无法区分，见结论 #10） |
| `model` | `ledger start.model` + `model_source`（run.json **无** model） | 缺 → `None`（fixture/未记账 spawn） |

#### 3.3 分母口径（必须写死，否则两臂不可比）

- **分子**：arm 内所有 attempt 的 `Σtokens`（含 merge 单元，因为 merge 真的烧 token）。
- **分母**：**仅 evidence 单元**的 `Σclosed`，且**按 claim id 去重**（id 来自各单元 `## 断言裁决` 表）。
- **merge 单元**：`tokens` 单列 `merge_tokens`；`closed` **不进分母**。理由可证伪：merge 若沿用同一张 20-claim 卡，`claims.total=20`、`closed≈20`，直接相加会把分母翻倍到 40，比值被人为腰斩；而 `[CLAIMS]` 行只有 5 个标量、**不含 claim id**，从计数器层面无法去重，只能回到 `## 断言裁决` 表按 id 合并。
- **敏感性口径**：同时给出 `tokens_per_closed_claim_incl_merge = (Σevidence + merge) / Σclosed_dedup`，并把两者差值报告为"编排开销占比"。
- **子单元求和 vs closed 数**：`closed_dedup` 与 `Σevidence closed` 只在"同一 claim 被两个单元重复裁决"时不同；实验必须记录 `dup_closed = Σevidence closed − closed_dedup`，非 0 说明扇出边界没切干净。

### 4. 替代指标取舍（token 若仍不可 join）

| 指标 | 真值状态（实测覆盖） | 当前样本 | 取舍 |
|---|---|---|---|
| `tool_calls`（`[END] tools=`） | **有真值**，684/701 trace 有 `[END]`，1428 attempt | 全语料 | **主替代指标**。与 token 强相关（每次工具调用的上下文字节是成本主因），且不受 session join 影响 |
| `wall_s`（ledger spawn→reap） | **有真值**，592/612 end 行有 `wall_s` | 全语料 | 次要指标（同时报 p50/p90）；受模型速率/机器负载污染，单用会把"换模型"读成"换拆法" |
| `exit` / 完成率 | **有真值**，`[END] exit` 1428 条 + `run.json.exit` 409 条 | 全语料 | 只用于**非劣性**检查，不用于"更划算"主张（split 后完成率通常不升） |
| `fetches/claim` | **有真值**但样本极小 | **3 run / 15 claim** | 一旦起实验即为主指标之一（它是上限硬约束的直接读数）；现状不足以比较 |
| `closed/unverified` 比 | **有真值** | 3 run | 同上；`unverified>40%` 时该单元应判"未收敛"，比值本身不可比 |
| `calls`（assistant 消息数） | 有真值 | 全语料 | **不单用**：与 `tool_calls` 高度共线，且 `usage.py` 的 `calls` 是 turn 数，容易被误读成工具数 |
| `cost` | 恒 0（本地代理） | — | **弃用** |
| `tokens_per_closed_claim` | 现状 `n/a`；但若实验走 launcher，**可 join 概率 99.8%** | 0 | 首选主指标；前提是补齐 `claims` → ledger（结论 #12 那条整改） |

取舍结论：实验报表**必须同时输出** `tokens_per_closed_claim`、`attributable_ratio`、`tools_per_claim`、`wall_s`、`exit_dist`。主指标 = token 比值（当 `attributable_ratio=1`），否则自动降级到 `tools_per_claim` + `wall_s`，并在行上打 `metric_source=ledger_join|trace_tools` 标记。

### 5. advisory 基线样本量与退出码分布（真跑，409 条 run.json）

分组判据：`task.md` 内含 `<!-- mw-claims: v1 -->`（严格正则，避免把"文中提到 mw-claims"的卡误判——`cor-rq3-metrics-baseline/task.md` 就是这种假阳性，已排除）。

全库基数：worker 目录 **719**，`trace.log` **701**（`[START]` 699、`[TOOL]` 697、`[END]` 684、`[CHECKPOINT]` 70、`[CLAIMS]` **3**、`[TIMEOUT]` **4**、`[IDLE_KILL]` 0），`run.json` **409**（全部同时有 trace.log），`task.md` 710（带块 **8**），`report.md` 421。

| 组 | n | exit 分布 | status 分布 | settled | done | 完成率 | 有超时标记目录 |
|---|---|---|---|---|---|---|---|
| 带 `mw-claims` 块 | 8 | `0:3, 2:2, None:3` | done 3 / needs-clarification 2 / running 3 | 5 | 3 | **0.600** | 0 |
| 不带块 | 401 | `0:327, 2:60, 1:1, 3:1, None:12` | done 327 / needs-clarification 60 / running 12 / failed 2 | 389 | 327 | **0.841** | 1 |
| **review 子集**：带块 | 6 | `0:1, 2:2, None:3` | done 1 / nc 2 / running 3 | 3 | 1 | 0.333 | 0 |
| **review 子集**：不带块 | 49 | `0:38, 2:8, 3:1, None:2` | done 38 / nc 8 / running 2 / failed 1 | 47 | 38 | **0.809** | 0 |

- `exit` 取值域实测只有 `{0,1,2,3,None}`；**没有 124**，也没有任何 timeout 状态值。
- 完成率分母**必须剔除 `status=running`（15 条）**，否则在跑的 run 会把完成率压低 3~4pp（0.807 全量 vs 0.841 settled）。
- 台账侧同一时间窗的独立口径（`end` 592 条）：`exit 0:535 / 1:21 / 2:14 / 3:7 / 134:13 / None:2`，`status done:535 / failed:41 / needs-clarification:14 / lost:2`。台账比 run.json 多 183 条 end，差额来自 `claim-driven-review` 之前的 key 没有 `run.json` 通道。
- `[END]` 口径（attempt 级，1428 条）：`exit 0:1339 / 2:63 / 3:19 / 1:7`；global 完成率 0.938，review 子集 0.799（与 `run.json` 的 0.809 同量级，交叉验证成立）。

按天分布（`run.json`，n / 带块 / done）：

```
2026-10-11  23 / 0 / 23 (1.00)     2026-10-16  16 / 0 / 15 (0.94)
2026-10-12  46 / 0 / 37 (0.80)     2026-10-19  15 / 0 / 15 (1.00)
2026-10-13  64 / 0 / 42 (0.66)     2026-10-20  41 / 0 / 38 (0.93)
2026-10-14  45 / 0 / 41 (0.91)     2026-10-21  46 / 2 / 39 (0.85)
2026-10-15  43 / 0 / 30 (0.70)     2026-10-22  70 / 6 / 50 (0.71)
```

带块样本只存在于 **2026-10-21 与 10-22 两天**（首条 `2026-10-21T09:15:14Z`），时间维度上无法与"历史 normal"对齐。

### 6. 混杂因素与需要多长窗口

| 混杂 | 实测证据 | 后果 |
|---|---|---|
| **时间** | 带块样本 100% 落在最后 2 天；不带块横跨 12 天 | 任何"设备/代理/模型/负载"变化都会混进组间差 |
| **模型** | review 带块组 6 条：`gpt-6.1-sol ×3` + `glm-5.3-flashx ×3`；不带块 49 条：`glm-5.3-flashx 24`、**无台账行/模型未知 21**、`glm-5.3 (fallback) 2`、`gpt-6.1-sol 2` | `gpt-6.1-sol` 在带块组占比 50% vs 对照组 4%，模型与分组强相关 |
| **任务类型** | 带块 8 条 = review 6 + coding 2；不带块 = coding 243 / research 109 / review 49 | 全域比较被 coding 主导，只能做 review 子集 |
| **自选择** | 8 张带块卡全部由 `claim-driven-review` 这个"正在实现 claims 机制"的 key 产出 | 卡作者=机制作者，编写质量高于平均，advisory 组的"好成绩"未必可外推 |
| **样本量** | review：3 settled vs 47 settled | Fisher 精确检验 `p=0.283`（双侧），无法拒绝"无差异" |

统计功效（两比例检验，α=0.05 双侧，power=0.8，p0=0.80）：

| 每臂 n | 可检出的最小绝对差（MDD） |
|---|---|
| 47 | 27pp |
| 114 | 17pp |
| 295 | **10pp** |
| 500 | 7.6pp |

- 需求样本（p0=0.80，p1=p0−Δ）：Δ=10pp → **295/臂**；15pp → 140；20pp → 83；25pp → 56。
- 观测吞吐：review attempt 近 3 天 40 次（`10-20:10 / 10-21:4 / 10-22:26`），全语料 144 次 / 34 天 ≈ 4.2/day，近期 ≈ 5~10/day。
- 结论：**若只靠自然流量观察 review 完成率的变化，检出 10pp 需 ≈30~59 天；检出 20pp 需 ≈8~17 天**。因此灰度方案不能把"退出码分布不变"作为 10pp 级的验收判据，只能作为 **20pp 级回归的看门狗**；真正的主判据必须换成 claims 层的确定性读数（`closed_dedup`、`fetches/claim`）——它们是**结构性确定**的，不需要成百上千次采样。

### 7. 可执行统计口径（伪流程，不写代码）

1. **快照与过滤**：读 `~/.mw/usage/runs.jsonl` 全量；`start` 事件按 `ts ∈ [arm_start, arm_end)` 半开区间取；**剔除** `project` 含 `pytest-of-`（fixture，126 行）与 `spawn_failed` 行；`end` 事件按 `run_id` 配对，无 `end` 者标 `running` 并排除出完成率分母。
2. **单元定型**：以 `task_key` 锚定 `{run.json, trace.log, task.md}` 三元组（`trace.log` 存在 701/719，`run.json` 409/719 —— 两侧不齐，行必须带 `has_run_json` / `has_trace` 标记）。`unit_role` 由卡内声明（当前无字段 → 手工登记表），未声明者按 `evidence` 处理但不进分母。
3. **归因**：`start.session_id` → pi 会话 header `id`（`usage.py:427` 同规则：header 优先、文件名兜底）；命中且至少一条 `message.usage` → `tokens = input+output+cache_read+cache_write`；**未命中写 `None`，绝不填 0**。
4. **claims 计数**：优先 `run.json.claims`（5 标量）；无则取 `trace.log` **最后一条**可解析 `[CLAIMS]`（重试 run 取末行，`usage.py:1007` 已实现该语义）；两者都无 → 该单元无度量。
5. **去重**：从各单元 `## 断言裁决` 表按 claim id 合并；`closed_dedup` 与 `Σevidence closed` 的差记为 `dup_closed`。
6. **输出列**：`exp_id, arm, unit_id, unit_role, model, exit, timeout, wall_s, tool_calls, claims_total, closed, partial, unverified, fetches, tokens, attributable` + arm 级派生 `closed_dedup, dup_closed, evidence_tokens, merge_tokens, tokens_per_closed_claim, tokens_per_closed_claim_incl_merge, attributable_ratio, fetches_per_claim, tools_per_claim, exit_dist`。
7. **判定顺序**：`attributable_ratio == 1` → 用 `tokens_per_closed_claim`；否则用 `tools_per_claim` + `wall_s`，并在报表眉标 `metric_source=trace_tools`。非劣性判据（exit 分布）用 Fisher 精确检验，且必须写明当前 n 只能排除多大回归。

### 8. 当前根本不存在、不许假设的字段

| 字段 | 状态 | 证据 |
|---|---|---|
| `arm` / `exp_id` / `unit_role`(merge) | 不存在 | 无任何实验登记结构；dispatch 无 merge 概念 |
| `run.json.model` | 不存在 | 409 条 run.json 键集合无 `model` |
| `run.json.tool_calls` | 不存在 | 只有 `trace.log` `[END] tools=` |
| `run.json.session_id` | 不存在 | 键集合无（也是 6/115 的根因） |
| `run.json.timeout` / `exit=124` | 不存在 | 超时 = `exit 1` + `[TIMEOUT]` 行 |
| ledger 事件里的 `claims` / `claims_line` | **代码支持但无人写** | `usage.py:972-976` vs `launcher.py:320` |
| `claims.tokens` 非空值 | 恒 `null` | `worker-mode.ts:935` 契约 |
| proxy 侧 per-session token | 不存在 | §5.4 日志实测 |
| `cost` 非 0 | 恒 0 | `usage.cost.total = 0`（本地代理） |
| `[CLAIMS]` 里的 claim id 列表 | 不存在 | 只有 5 个标量 |
| `run.json` 的 `model_exhausted` | 部分存在 | 409 条里仅 1 条有该键 |

## 残留与未验证

1. **未做 4×5 对照实验本身**：本 RQ 只交付可行形态与字段草案；`tokens_per_closed_claim` 的两臂真值仍是 0 个样本。
2. **`claims` → ledger 的整改未验证**：结论 #12 的补丁（launcher `end` 事件带 `claims`）是推断，未改代码、未跑测试。
3. **exit 134 语义未查明**：台账有 13 次 `exit=134`（`status=failed`），未取证是 pi abort 还是外壳；这 13 条会让"失败"口径偏大，但不影响 review 子集（review 里 0 次 134）。
4. **`type` 词表两套不齐**：台账 `type` 有 `phase-writer/repair/reviewer/verifier`，trace `[START] type=` 只有 `coding/research/review/default/vision`。按台账 `type∈{review,reviewer,verifier}` 数得 89，按 trace 数得 149——同一"review 语料"差 60，未逐条归因。
5. **proxy 侧改造收益未评估**：即使让 proxy 记 token，也没有 per-session 键（同端口多 worker 并发），只能按时间窗近似，属"近似值"，按上游判据应拒绝。
6. **未覆盖 claude/codex 通路**：语料 100% `cli=pi`，`claude_exact` 路径零样本。
7. **`_workers.parallel` 层未扫**：advisory 告警（`[claims]` 回执行）的条数/命中率没统计，只统计了终态 run.json。
8. **一次越界写（已回滚并披露）**：为取 `--detail` 的 claims 行，我执行了 `mw.py stats --detail --json`，该命令即使带 `--json` 也会落 HTML 到 `~/.mw/usage/reports/`（`mw.py:10381` `needs_html = args.html is not None or args.detail`），产生 `usage-20261022-173642.html` 与 `usage-20261022-173648.html` 两个文件；发现后已 `Remove-Item` 删除，目录恢复到我运行前的状态（最新为 `usage-20261022-155200.html`）。后续查询改用无 `--detail` 的 `--json`（不再写盘）。

## 未覆盖面

- 未覆盖 enforce 模式（`MW_CLAIM_GATE=enforce` 下 exit 分布会变，本 RQ 只测 advisory 默认）。
- 未覆盖 2026-10-19 之前 attempt 的任何成本（105/149 review attempt 结构性缺 `session_id`）。
- 未覆盖 PM 窗口 token 与 4×5 编排开销的实测值（`source=pm` 在 ledger 里恒 0，只能从非 `mw-` 会话 id 反推，未验证其 key 归属准确率）。
- 未覆盖跨机器/跨 key 的模型配置差异（本机 5 个 model 取值）。
- 未量化 `[TOOL]` 行截断（最长 124 字符）对 `fetches` 独立复核的影响。
- 未评估 `[CLAIMS]` 行缺失的构造成因（8 张带块卡只有 3 张产出 `[CLAIMS]`，另 5 张为何没有未取证）。

## 上下文来源

- 本卡：`.agenticdoc/claim-driven-review-orchestration/tasks/RQ-3-metrics-baseline.md`
- 上游证据：`.agenticdoc/claim-driven-review/evidence/t07-e2e-results-20261022.md`（L4 度量回读：`tokens_per_closed_claim="n/a"`）、`.agenticdoc/claim-driven-review/evidence/research/spec-rq1-review-corpus-20261020.md` §2（6/115 原判据）、`.agenticdoc/claim-driven-review/evidence/research/spec-rq2-seams-20261020.md` §5.3（落点建议）、`.agenticdoc/claim-driven-review/evidence/t07/claims-plan.md`（20 条断言夹具）
- 设计：`.agenticdoc/claim-driven-review/design.md` §4（拆分判定 `k = ceil(n/5)` + 1 merge）、§5（advisory/enforce 三门 G1/G2/G3）、§6（无 claims 块全链路跳过）
- 源码锚点：`packages/multi-workers/usage.py:95,343,427,846,990,1007,1021,1051,1071,1286,1399,1452`；`packages/multi-workers/launcher.py:204,218,291,320,2152,2846-2888`；`packages/multi-workers/proxy_multi.py:36-47`；`packages/multi-workers/mw.py:10370-10420`；`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:575,600,1042`；`.../worker/worker-mode.ts:935,961,3794`；`.../autopilot/status-model.ts:1552,1717,1750,1901`（注：卡里写的 `shared/status-model.ts` 实际在 `autopilot/` 下）
- 数据：`~/.mw/usage/runs.jsonl`（只读）、`~/.pi/agent/sessions/**`（只读，4723 个带 header id 的会话）、`~/.timi-anthropic-proxy/logs/proxy.log`（只读，196,756 行）、`.agenticdoc/**/workers/*/{run.json,trace.log,task.md}`（只读，719 目录）
- 目标锚点：`.agenticdoc/goal.md`（成本必须可测，否则"并行省了钱"只是信念）
