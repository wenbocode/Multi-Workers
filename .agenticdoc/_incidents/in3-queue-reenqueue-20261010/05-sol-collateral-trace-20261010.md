# IN-3 派生调用实证：gpt-5.6-sol 在 2026-10-10 的 12 次 worker 调用

- **建档**：2026-10-11 15:30 本地（UTC+8）　**建档窗口**：`mw-ack-verify-stdout`（claim `WENBOZHOU-PC4:1768`，PM 直执）
- **被审计日**：**2026-10-10（本地）**，即 IN-3 第 2 次整表重建当天。此前的上游答复见本目录对话；2026-10-11 全天无 worker 开工（见 §0 注）
- **归属**：IN-3 事故档案的补充证据（跨 key 档案，见 `README.md`）。本事故的修复项归属 key = `mw-gate-verdict-hardening`（其 G5）
- **起因**：用户问"今天 gpt-5.6-sol 的这 12 个调用都是 IN-3 事故造成的吗"。本文件是该答复的取证底稿
- **性质**：**只读审计 + 建档**。未改队列、未 kill 进程、未动任何 `.agenticdoc` 产品文件
- **数据源**：`.agenticdoc/_workers.parallel`（快照 A 253 行 / 快照 B 277 行）、`.agenticdoc/_workers.acked`（261 行）、22+ 个 `workers/*/{trace.log,worker.log,task.md}` 的 mtime 与内容、`~/.pi/agent/sessions/**/*.jsonl` 的 `model_change` 事件
- **复算命令**：见 §5（脚本未入库，均为一次性只读脚本）

---

## 0. 结论

| 问题 | 判定 | 依据 |
|---|---|---|
| 这 12 次 sol 调用是 IN-3 造成的吗 | **是，12/12** | §1 队列行落在重建单秒窗口内 + §2 任务在事故前已 ack 终态 + §3 与三波重派时间线逐个吻合 |
| 是各自 key 的 PM 派发的吗 | **不是** | 12 行同属一次整表扫描重写（owner key 纯字母序、owner 间零交错、全部 8 域），且所属两个 key 均已 DONE（`goal-autopilot` 2026-09-10 19:32、`mw-target-partition` 2026-09-19 13:59，见 `_index.parallel` 与 `_project_log.md`） |
| 10-10 的这 4 个 `failed` 也是 IN-3 造成的吗 | **不是**。IN-3 只造成"被调用"；失败是独立缺陷 | §4：4 个 `failed` = 4 个含 `stream closed before response.completed` 的 worker.log，进程 `exit=0`，判定已落盘 |
| 为什么"只有这 12 个"是 sol | sol 的 per-task 钉子只存在于这 12 张老卡（`goal-autopilot` 5 + `mw-target-partition` 7） | 同秒重建重派了**全项目 252 个任务**，其余 240 个走各自角色默认模型（deepseek-v4.1-flash / glm-5.3），故不可见 sol 痕迹 |

一句话：**这 12 次是"IN-3 全项目重派"在 sol 上的可见切片；同一批重派的另外 ~240 个任务不是 sol，所以从模型角度看不到事故。**

**时间边界注**：被审计的 12 次全部发生在 2026-10-10（本地 10:50–11:37）。建档时（2026-10-11 15:26 本地）复查：`2026-10-10T16:00Z` 之后**全项目 0 条 `[MODEL]` 开工行**（不限模型），即 10-11 无任何 worker 运行，队列文件最后写入时间为 10-10 21:30:48。

**快照注**：`.agenticdoc/_workers.parallel` 是活文件。本文件建档时（2026-10-11 15:26）读取为 **277 行 / 29 owner / 31 连续段 / 8 域 / 268 done + 9 failed**；同一事件更早一次读取为 253 行 / 28 owner / 29 段。差额（24 行，`dispatched_at` 在 `10-10T10:09Z–13:21Z`）是 `mw-gate-verdict-hardening`（20 行 `mwg-*`）与 `mw-dispatch-settle-gates`（4 行 `mds-*`）的**合法派发**，与本事故无关。所有队列计数均为**快照值**，复算时以读取时刻为准；下文 §1.1 给出两个快照。

---

## 1. 证据 A：队列行（事故指纹逐项命中）

### 1.1 全表统计（两个快照：`.agenticdoc/_workers.parallel`）

| 指标 | 快照 A（10-10 更早） | 快照 B（10-11 15:26，建档时） | 与档案 §5 指纹的对照 |
|---|---|---|---|
| 行数 | 253 | **277** | 重建当时 252 行（README §3） |
| 域数（列数） | 全部 8 域 | 全部 8 域（无 `origin`） | 命中"所有新行列数一致且偏少（本次全部 8 域）" |
| owner key 数 / 连续段数 | 28 / 29 | 29 / 31 | 命中"owner 之间零交错＝一次扫描顺序 append"（少量回跳来自后续合法派发） |
| 行序 | `autopilot-monitor` → `goal-autopilot` → `mw-*` … 纯字母序 | 同 | 同上 |
| `ap-*` 行 | 0 | 0 | 命中"0 个 ap-* 行（conductor 过滤仍生效）" |
| `dispatched_at` 落在 `02:50:05.220–.637Z` 单秒窗口内 | **234 行** | **234 行**（不变） | 命中"同一秒内" |
| 窗口外（事故后正常派发） | 19 行 | 43 行 | 与"重建当时 252 行，此后陆续正常重派"一致 |
| 状态分布 | 244 done / 8 failed / 1 running | 268 done / 9 failed | 与 README §3「11:26 时 243 done / 8 failed / 1 running」同族 |

窗口外 19 行（快照 A）：`xkey-rm-*` 10、`_scratch/manual-*` 3、`wjg-*` 2、`mw-dr-autodispatch`、`w1-pi-extension-interception`、`w2-p002-guard-precedent`、`wip-qg-review`。

### 1.2 12 个 sol 行（字段逐列）

格式：`task_key | status | cli | provider | task_path | dispatched_at | updated_at | model`（原文为 8 域空格填充；`task_path` 前缀均为 `H:\git\Multi-Workers\.agenticdoc\`）

| task_key | status | dispatched_at | updated_at | model |
|---|---|---|---|---|
| `ga-spec-design-review-2` | failed | 2026-10-10T02:50:05.229Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |
| `t18-quality-gate` | done | 2026-10-10T02:50:05.243Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |
| `t18-quality-gate-2` | done | 2026-10-10T02:50:05.245Z | 2026-10-10T03:20:40+00:00 | gpt-5.6-sol |
| `t18-quality-gate-3` | done | 2026-10-10T02:50:05.246Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |
| `t18-quality-gate-4` | done | 2026-10-10T02:50:05.248Z | 2026-10-10T03:20:40+00:00 | gpt-5.6-sol |
| `mwtp-final-review` | failed | 2026-10-10T02:50:05.551Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |
| `mwtp-final-review-2` | failed | 2026-10-10T02:50:05.553Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |
| `mwtp-final-review-3` | done | 2026-10-10T02:50:05.555Z | 2026-10-10T03:20:41+00:00 | gpt-5.6-sol |
| `mwtp-verify-gate` | done | 2026-10-10T02:50:05.567Z | 2026-10-10T03:20:41+00:00 | gpt-5.6-sol |
| `mwtp-verify-gate-2` | done | 2026-10-10T02:50:05.569Z | 2026-10-10T03:02:54+00:00 | gpt-5.6-sol |
| `review-mw-target-partition-design` | failed | 2026-10-10T02:50:05.570Z | 2026-10-10T03:04:02+00:00 | gpt-5.6-sol |
| `review-mw-target-partition-spec` | done | 2026-10-10T02:50:05.572Z | 2026-10-10T03:02:19+00:00 | gpt-5.6-sol |

`dispatched_at` 全部落在档案记录的重建窗口 `02:50:05.220–.637Z`（README §3、§5）内，逐行间隔 1–3 ms，属同一次扫描顺序写入。

### 1.3 会话侧一一对应（独立数据源交叉验证）

`~/.pi/agent/sessions/--H--git-Multi-Workers--/` 中，今天有 **12 个会话**的 `model_change` 事件（`type == "model_change"` 且 `modelId == "gpt-5.6-sol"`）时间戳为
`02:50:09.477/.772/.818/.997`、`02:50:10.035`、`02:53:40.300/45.615/49.451`、`02:54:29.256/33.149/39.978/47.570`，
与 §1.2 的 12 行 worker 运行逐个对应（另在 `%TEMP%\pi-runtime-cwd-b-1791603749241-*` 还有 1 个 sol 会话，`03:43:05.878Z`，内容仅 `other` / `What would you like help with?` 两条消息，无工作、不产生 task 目录 ⇒ **本仓库内合计 12 个**，两个数据源一致）。
**会话级与队列级两个独立数据源在"12 个"上一致**，可排除"还有别的 sol 调用漏记"。

---

## 2. 证据 B：这 12 个任务在事故前已终态（`.agenticdoc/_workers.acked`）

`_workers.acked` 当前 261 行；12 个任务全部在内，ack 时间全在 9 月：

| task_key | ack 行原文 |
|---|---|
| `ga-spec-design-review-2` | `ga-spec-design-review-2 \| 2026-09-21T07:15:01.329Z` |
| `t18-quality-gate` | `t18-quality-gate \| 2026-09-21T07:15:01.329Z` |
| `t18-quality-gate-2` | `t18-quality-gate-2 \| 2026-09-21T07:15:01.329Z` |
| `t18-quality-gate-3` | `t18-quality-gate-3 \| 2026-09-21T07:15:01.329Z` |
| `t18-quality-gate-4` | `t18-quality-gate-4 \| 2026-09-21T07:15:01.329Z` |
| `mwtp-final-review` | `mwtp-final-review \| 2026-09-19T08:01:43.590Z` |
| `mwtp-final-review-2` | `mwtp-final-review-2 \| 2026-09-19T08:52:05.504Z` |
| `mwtp-final-review-3` | `mwtp-final-review-3 \| 2026-09-19T09:29:26.997Z` |
| `mwtp-verify-gate` | `mwtp-verify-gate \| 2026-09-19T05:43:45.648Z` |
| `mwtp-verify-gate-2` | `mwtp-verify-gate-2 \| 2026-09-19T05:57:07.008Z` |
| `review-mw-target-partition-design` | `review-mw-target-partition-design \| 2026-09-18T17:12:12.869Z` |
| `review-mw-target-partition-spec` | `review-mw-target-partition-spec \| 2026-09-18T17:13:40.683Z` |

**推论**：12 个任务在 09-18～09-21 之间就已"已读回执 = 终态"；10-10 10:50 的整表重建把它们重新写成 `pending`，launcher（`packages/multi-workers/launcher.py:822`，只 spawn `status == "pending"`）随即全量 spawn（worker 于 02:50:09 起开工，比重建晚 4 秒）。
⇒ **这批派发不是"新工作"，而是"已终态任务被当成从未派发"**，正是 IN-3 根因（派发判据看"行是否存在"而非"任务是否终态"）的直接后果。

配套：`task.md` 的 mtime 也都在 9 月，与"老卡"一致（`ga-spec-design-review-2` 2026-09-08 20:53:09；`t18-quality-gate{,-2,-3,-4}` 2026-09-10 17:34–18:16；`mw-target-partition` 7 张 2026-09-19 01:07–17:22；唯 `mwtp-verify-gate-2` 为 2026-10-09 15:08:15，即被 10-09 15:08 那一波重写）。

---

## 3. 证据 C：三波重派 + 逐任务开工时间线

### 3.1 波次对照

| 波次 | 时间（本地 UTC+8） | 对应事件 | 证据 |
|---|---|---|---|
| 原始运行 | 09-08 / 09-10 / 09-18 / 09-19 | 任务正常创建与执行，随后 ack | `task.md` mtime + ack 记录 + 残留的 `trace.log` 开工行 |
| 重派 W-A | 10-09 15:08 | 档案**未记录**（早于 `b8bc115ff` 列漂移 16:27），触发者未坐实 | 12 个 trace 均有 `2026-10-09T07:08:5x` 开工行 |
| 重派 W-B | 10-09 20:01–20:05 | **IN-3 第 1 次整表重建**（README §3：10-09 20:01:47） | 12 个 trace 均有 `2026-10-09T12:01–12:05` 开工行 |
| 重派 W-C | **10-10 10:50–10:54** | **IN-3 第 2 次整表重建**（README §3：10-10 10:50:05） | §1.2 队列行 + 12 个 trace 的 `2026-10-10T02:50–02:54` 开工行 |

### 3.2 逐任务开工记录（UTC；本地 +8h）

| task | 原始开工 | W-A | W-B | W-C（今日） | 今日耗时/工具 | 今日 `exit` |
|---|---|---|---|---|---|---|
| `ga-spec-design-review-2` | 09-08T12:53（仅存 FLOW 行） | 10-09T07:08:17.442 | 10-09T12:01:51.091 | 10-10T02:50:09.485 | 1m / 37 | 0 |
| `t18-quality-gate` | 未存（卡 09-10） | 10-09T07:08:18.563 | 10-09T12:01:51.385 | 10-10T02:50:09.778 | 9m / 79 | 0 |
| `t18-quality-gate-2` | 未存（卡 09-10） | 10-09T07:08:19.463 | 10-09T12:01:51.348 | 10-10T02:50:10.006 | 18m / 71 | 0 |
| `t18-quality-gate-3` | 未存（卡 09-10） | 10-09T07:08:19.350 | 10-09T12:01:51.400 | 10-10T02:50:09.834 | 6m / 61 | 0 |
| `t18-quality-gate-4` | 未存（卡 09-10） | 10-09T07:08:18.864 | 10-09T12:01:51.397 | 10-10T02:50:10.041 | 25m / 91 | 0 |
| `mwtp-final-review` | 09-19T07:46:56.072 | 10-09T07:08:51.326 | 10-09T12:04:46.172 | 10-10T02:53:40.305 | 4m / 42 | 0（无 END 行） |
| `mwtp-final-review-2` | 09-19T08:41:07.796 | 10-09T07:08:51.666 | 10-09T12:04:49.546 | 10-10T02:53:45.620 | 4m / 60 | 0 |
| `mwtp-final-review-3` | 09-19T09:22:50.423 | 10-09T07:08:52.894 | 10-09T12:04:52.678 | 10-10T02:53:49.456 | 43m / 103 | 0（无 END 行） |
| `mwtp-verify-gate` | 09-19T05:39:57.952 | 10-09T07:08:52.998 | 10-09T12:05:24.694 | 10-10T02:54:29.261 | 18m / 86 | 0 |
| `mwtp-verify-gate-2` | 09-19T05:55:23.362 | 10-09T07:08:53.133 | 10-09T12:05:25.869 | 10-10T02:54:33.153 | 8m / 75 | 0 |
| `review-mw-target-partition-design` | 09-18T17:07:44.511 | 10-09T07:08:53.033 | 10-09T12:05:29.825 | 10-10T02:54:39.983 | 9m / 61 | 0 |
| `review-mw-target-partition-spec` | 09-18T17:09:04.313 | 10-09T07:08:53.107 | 10-09T12:05:34.854 | 10-10T02:54:47.575 | 3m / 13 | 0 |

⇒ 每个任务在 4 天内至少被执行 **4 次**（原始 + W-A + W-B + W-C），其中 W-B/W-C 两次确定是 IN-3 的两次整表重建。今日 12 次合计模型运行时间 **≈ 148 分钟**。

### 3.3 trace 完整性注记（影响"原始运行"的可取证性）

- `goal-autopilot` 5 张卡：原始运行的 `[START]/[MODEL]/[END]` 行**已不存在**（`t18-*` 的 trace 首行直接是 `[START] pid=…`），仅 `ga-spec-design-review-2` 残留 09-08 的 `[FLOW]`/`[HEARTBEAT]` 行可证首跑。⇒ 命中档案 §5 指纹"trace.log 被截断/重写"。
- `mw-target-partition` 7 张卡：09-18/09-19 首跑的开工行完整保留。
- `[START]/[MODEL]` 次数与 `[END]` 次数不平衡的有 4 个：`mwtp-final-review`（4/3，缺今日 END）、`mwtp-final-review-3`（4/3，缺今日 END）、`t18-quality-gate-2`（3/4）、`t18-quality-gate-4`（3/4）。
- **今日这 12 次中无一属于 §4 之外残留进程**：`04-residue-scan` 里被清掉的 3 棵孤儿重跑 worker 是 `msc-d4-evidence-provenance` / `msc-t14-docs-dist-regression` / `mwtp-s4-verify`，命令行模型均为 `deepseek-v4.1-flash`，不在本清单内。

---

## 4. 证据 D：10-10 的 4 个 `failed` 是**独立缺陷**，不是 IN-3

### 4.1 4 个 `failed` 与 4 个含流中断的 worker.log 完全重合

| task | worker.log | output.md | 判定摘要 |
|---|---|---|---|
| `ga-spec-design-review-2` | `done exit=0 elapsed=1m tools=37` + `stream closed before response.completed` | 24,851 B | `## Summary` 段空，正文为 BLOCKING issues 清单 |
| `mwtp-final-review` | `done exit=0 elapsed=4m tools=42` + 同上 | 11,035 B | FAIL：5 个 BLOCKER（partition 配置撕裂、profile 陈旧、AC-018 违规） |
| `mwtp-final-review-2` | `done exit=0 elapsed=4m tools=60` + 同上 | 7,741 B | FAIL：8/9 findings 已修，YAML `null` fails open |
| `review-mw-target-partition-design` | `done exit=0 elapsed=9m tools=61` + 同上 | 24,595 B | FAIL：spec/design 3 处互斥矛盾 |

四个 `output.md` 尾部均有 `## Exit Reason: Agent settled after N tool call(s)`，且 `[END] … exit=0`（`mwtp-final-review` 缺 END 行）。
⇒ **进程正常退出、判定已落盘，队列却记 `failed`**。此 `exit=0 → failed` 的不一致**未定位到写入方**（见 §6）。

### 4.2 流中断的模型特异性（本项目全量 worker 运行统计）

| 模型 | 运行次数（`trace.log [MODEL]` 行） | 含 `stream closed before response.completed` 的目录数 |
|---|---|---|
| **gpt-5.6-sol** | 53 | **15（4 个任务目录）** |
| deepseek-v4.1-flash | 814 | 0 |
| glm-5.3 | 83 | 0 |
| gpt-5.6-luna | 8 | 0 |
| deepseek-v4-flash-vision-exp | 4 | 0 |

错误首现日：09-18（1）→ 09-19（2）→ 10-09（8）→ 10-10（4）。代码锚点：`packages/ai/src/api/openai-codex-responses.ts:1377`
`if (!sawCompletion) throw new Error("WebSocket stream closed before response.completed");`

### 4.3 与 IN-3 的边界

- IN-3 解释**为什么这 12 次被发起**；不解释**为什么其中 4 次被记 failed**。
- IN-3 的修复项（G5 / AC-019～023）不覆盖流中断；后者建议独立 key（如 `mw-review-stream-truncation`）。

---

## 5. 复算命令（只读）

```powershell
# 5.1 队列：域数 / owner 连续性 / 重建窗口
python -c "rows=[l.rstrip() for l in open(r'.agenticdoc\_workers.parallel',encoding='utf-8') if l.strip()];
print(len(rows), sorted(set(len(r.split('|')) for r in rows)));
o=[r.split('|')[4].split(chr(92))[-4] for r in rows];
seq=[];
[seq.append(x) for x in o if not seq or seq[-1]!=x];
print('owners=%d runs=%d' % (len(set(o)), len(seq)));
print(sorted(set(r.split('|')[5].strip()[:23] for r in rows))[:5])"

# 5.2 12 个 sol 行
Get-Content .agenticdoc\_workers.parallel | Select-String 'gpt-5\.6-sol'

# 5.3 终态 ack
Get-Content .agenticdoc\_workers.acked | Select-String 'mwtp-|t18-quality-gate|ga-spec-design-review-2'

# 5.4 逐任务开工记录（START/MODEL/END）
Get-ChildItem .agenticdoc\*\workers\*\trace.log | ForEach-Object {
  $t = Select-String -Path $_.FullName -Pattern '^\[(START|MODEL|END)\]'
  if ($t -match 'gpt-5\.6-sol|2026-10-10') { "$($_.FullName)`n" + ($t | Select-Object -Last 8 | ForEach-Object { '   ' + $_.Line }) }
}

# 5.5 会话侧（独立数据源）：2026-10-10 选中 sol 的会话
python -c "import glob,json,os
MC=chr(34)+'model_change'+chr(34)
n=0
for f in glob.glob(os.path.expanduser('~/.pi/agent/sessions/**/*.jsonl'),recursive=True):
    for line in open(f,encoding='utf-8',errors='replace'):
        if MC not in line: continue
        try: o=json.loads(line)
        except Exception: continue
        if o.get('type')=='model_change' and o.get('modelId')=='gpt-5.6-sol' and o.get('timestamp','').startswith('2026-10-10'):
            print(o['timestamp'], os.path.basename(os.path.dirname(f))[:60]); n+=1
        break
print('2026-10-10:',n)"
```

---

## 6. 未坐实 / 边界（复发取证时先看这里）

1. **谁写了 `failed`**：12 行全部 `exit=0`，其中 4 行却是 `failed`。队列 `updated_at` 是批量扫描值（`03:02:19Z` 同时出现在 6 行、done 与 failed 混有；`mwtp-final-review-3` 约 03:37Z 才结束而 `updated_at=03:20:41Z`），因此不能据此断定写入时刻。
2. **W-A（10-09 15:08）那一波的触发者**：档案此前只记录两波整表重建；此波早于列漂移提交（`b8bc115ff` 16:27），机制未坐实。
3. **`goal-autopilot` 5 张卡原始运行的 `[START]/[END]` 行缺失原因**：是重跑重写文件头，还是另有截断路径，未取证。
4. **worker.log 里那句报错的来源**：仓库内唯一匹配是 `openai-codex-responses.ts:1377`，但其消息带 `WebSocket ` 前缀，而 worker.log 文本无此前缀 ⇒ 也可能来自上游 timi 代理的同义报错（未坐实）。
5. **`_workers.acked` 的写入时刻**：文件当前 mtime 是 10-10（今天有 3 条新 ack：`mgh-rq5`、`wjg-rq2`、`wjg-rq1`），因此"12 条 ack 值来自 9 月"是**值可信、写入时刻未取证**；不排除事故期重写过该文件（README §3 已记其 10-10 11:33:45 被写）。
6. **同秒重建中被重派的另外 ~240 个任务的影响未逐一定损**：本文件只证明 sol 的 12 次是 IN-3 派生；其余任务的重派影响面见 `02-impact-assessment.md`。

---

## 7. 与修复项的对应（建议 gate 采纳）

| 本实证发现 | 对应修复项 | 建议的回归判据 |
|---|---|---|
| 12 个已 ack 任务被当"从未派发"重跑 | AC-022（产物自带终态优先，done 永不重派） | **`_workers.acked ∩ _workers.parallel(pending)` 必须为空**——可直接复算的判据 |
| 行丢失 ⇒ 全量重派 | AC-020（fail-closed）、AC-023（丢行计数/告警/不回删） | 队列行数与上轮快照的突变告警（README §7 观测项） |
| 单次派发副作用面 = 全项目（252 行 / 28 key） | AC-019（PM 侧自动派发收窄到本 key）、AC-021（单轮配额） | 一次派发轮次 != 1 个 owner key 即告警 |
| `exit=0` 与 `failed` 不一致（4/12） | 未覆盖 | 建议单列：判定/状态映射一致性检查（与 G5 同源） |
| sol 流中断（独立缺陷，IN-3 仅放大曝光） | 未覆盖 | 建议独立 key（`mw-review-stream-truncation`）：同一张 review 卡在 sol / glm-5.3 各跑一次，量三元组（worker.log 尾行、output.md 大小、队列 status/exit） |
