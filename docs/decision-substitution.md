# 决策替换（Decision Substitution）

> 状态：mw-decision-substitution（W6 文档面）· 依据 spec rev3 / design §2 · 2026-10-20
> 决策服务本身（transport / 后端 / 凭据链）见 [`packages/multi-workers/README.md`「决策服务（mw decide）」](../packages/multi-workers/README.md)
> 与底座正式文档 `.agenticdoc/mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md`。

> 每个 dp 对应什么、何时触发、传给 jev 的 state 形状、失败码处置见 [`docs/decision-points.md`](./decision-points.md)；机器可读的同源配置是 `packages/multi-workers/decide_registry.json`（`mw decide dp export`）。

## 0. 一句话与边界

框架的真实瓶颈不是「agent 不会做」，而是「**agent 停下来等人**」：实测最高频的 `needs-clarification`
占 worker 终态 17.4%（42/242），`[CHECKPOINT]` mid/high 60 条，5 条人工消息间隔合计 ≈93.3 分钟
（中位 13.6 min，复核见 `.agenticdoc/mw-decision-substitution/evidence/runs/verify-mw-decision-substitution-20261020.md`）。

**决策替换**把所有「会等人」的位置抽象成 24 个 **dp（decision point）**，用一张**由人掌控的配置表**
`.mw/decide-points.json` 决定哪些 dp 由决策服务（jev）直接给答案或执行，其余照旧上抛人：

```
人 ──mw decide dp on/off/set（或直接改文件）──► .mw/decide-points.json（唯一授权，热重载）
                                                     │
调用点 ──decide_for(dp_id, trigger)──► 查注册表 ──► 查配置表 ──enabled=false──► 上抛人（零 spawn）
                                                     │enabled=true
                                                     ▼
                              build_state(≤2000B) ──► 决策服务（transport 见 .mw/decide.json）
                                                     │
                                mode=suggest ──► 只落档案 + 展示建议（acted=false）
                                mode=auto    ──► 执行器（acted=true, actual_action）
                                                     │
                                                     ▼
                        .agenticdoc/_autopilot/decisions.jsonl（4 类行 + 哈希链）
                                                     │ fold(decision_id)
                     phase 末报告（decision-review-*.md）＋ 收尾签收（sign-final.md）──► 门禁
```

**不是什么**（用户裁定，改动前先看这一节）：

| 不做 | 原因 | 替代 |
| --- | --- | --- |
| 不替代 pi 核心的破坏性确认 | DS-3：政策推迟 | dp12/dp13 保持 P0 默认关 |
| 不做 shadow 模式 | DS-6：PM 看到建议必然趋同，数据被锚定污染 | 观察期用 `mode=suggest`（人明知是观察） |
| 机器不自动改配置 | DS-9/DS-10：唯配置论，开关永远由人执行 | 报告给 `suggest: disable dpX`，人一条命令 |
| 不做 dp2+ 的自动结算 | MVP 只对 dp1 通道全量关联 | 其余 `settled_by=human` 或 `pending` |
| 不在 `context` 钩子做决策 | 每个 LLM 调用都跑，会多倍放大延迟/花费 | 只走 `ask_decision` 工具 / `tool_call` 钩子 / PM 派发点 |

## 1. dp 一览（24 项）

注册表唯一权威：`packages/multi-workers/decision_points.py:340`（`DP_REGISTRY`，import 期 fail-loud 校验
id 唯一、tier 合法、P0 必须写 `p0_consequences`、共 24 项）。TS 侧只持 id 字符串常量
（`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:87`），不持问题集。

档位与默认：**P2 默认开、P1/P0 默认关**（`decision_points.py:307` `_point()` 按 tier 推导
`default_enabled`；`_parse_row` 兜底同规则）。当前落位 P2=9 / P1=5 / P0=10 = 24。

| id | 决策点 | 档 | 默认 | 执行器 | 当前真实接线 |
| --- | --- | --- | --- | --- | --- |
| `dp1-dispatch-type` | 派发 type/角色/范围 | P2 | on | unwired（走 `intent=answer`） | **已接**：PM 派发前分诊（`pm/ui-bridge.ts:264`、`pm/triage-client.ts`） |
| `dp2-checkpoint-split` | checkpoint 拆/收/直执 | P2 | on | unwired（TS 侧执行） | **已接**：PM checkpoint（`pm/pm-orchestrator.ts:2244`），**只允许 `narrow`** |
| `dp3-worker-clarify` | worker 澄清（3a 事实可查 / 3b 意图需人 / 3c 已表态复用） | P2 | on | unwired（TS 侧执行） | **已接**：worker `finishSuccess`（`worker/worker-mode.ts:3897`） |
| `dp4-failure-handling` | 失败处置 | P1 | off | 无 | 仅注册 |
| `dp5-test-triage` | 测试失败归类 | P2 | on | unwired | 仅注册（缺 CI 基线字段） |
| `dp6-qg-verdict` | QG 结论处置 | P1 | off | 无 | 仅注册 |
| `dp7-gate-failure` | 相位门禁失败 | P2 | on | unwired | 仅注册（缺结构化输出） |
| `dp8-scope-change` | 变更范围 | **P0** | off | 无 | 仅注册；`p0_consequences` 已写 |
| `dp9-model-select` | 模型/降级选择 | P2 | on | unwired | 仅注册 |
| `dp10-dependency` | 依赖升级 | P1 | off | 无 | 仅注册 |
| `dp11-credential` | 凭据/权限 | **P0** | off | 无 | 仅注册 |
| `dp12-destructive` | 破坏性操作 | **P0** | off | 无 | 仅注册 |
| `dp13-commit-release` | 提交 / 发布 + 版本号 | **P0** | off | 无 | 仅注册（发布不可逆，故取 P0） |
| `dp14-rule-conflict` | 用户指令 vs 规则 | **P0** | off | 无 | 仅注册 |
| `dp15-autopilot-gate` | autopilot 6 类人工门 | **P0** | off | 无 | 仅注册（单次最贵） |
| `dp16-goal` | goal 确立/变更 | **P0** | off | 无 | 仅注册 |
| `dp17-spec-lock` | spec/AC 锁定 | P1 | off | 无 | 仅注册 |
| `dp18-claim` | key 抢占冲突 | P1 | off | 无 | 仅注册 |
| `dp19-foreign-write` | 越面写预授权 | **P0** | off | 无 | 仅注册 |
| `dp20-stage-close` | stage 闭环 | **P0** | off | 无 | 仅注册 |
| `dp21-refine` | project-refine 升级 | P2 | on | unwired | 仅注册 |
| `dp22-debug-plan` | debug 方案确认 | P2 | on | unwired | 仅注册 |
| `dp23-snapshot` | memory 快照 | P2 | on | unwired | 仅注册 |
| `dp24-pi-trust` | pi core 交互 | **P0** | off | 无 | 仅注册 |

读法：
- `unwired` = 注册表里挂了占位执行器（`_unwired_executor`，`decision_points.py:294`）：在
  `mode=auto` 下它会**故意抛错**，结果是 `escalated_reason=over-authority` 上抛人——DS-4 禁止默认动作，
  未接线的点不许假装执行。
- 「仅注册」= 没有任何调用点。开启它不会改变任何行为（没有代码去问），只会出现在 `dp list` 里。
- 当前真正产生自动决策收益的只有 **dp1 / dp2 / dp3**；其余 21 个是「先把授权面画清楚」的登记项。

## 2. 配置表：唯一授权来源

### 2.1 文件与分工

| 文件 | 管什么 | 谁写 |
| --- | --- | --- |
| `.mw/decide-points.json` | **授权**（哪个 dp 能自动、用 auto 还是 suggest） | 人（`mw decide dp ...` 或直接编辑） |
| `.mw/decide.json` | **传输**（backend / 模型 / 凭据 / 预算 / 超时） | 人（`mw decide set`） |
| `.agenticdoc/_autopilot/decisions.jsonl` | **审计**（决策档案） | `decide_archive.py` 单写者 |
| `.agenticdoc/_autopilot/triage-decisions.jsonl` | 传输证据行（底座，11 字段） | `decision.py` 单写者 |

两者互不写入：授权表里没有 transport 字段，`.mw/decide.json` 里也没有 dp 开关。文件缺失 = 全部走
注册表默认（P2 on / P1,P0 off），**不是**关闭整个特性。

> 本仓库 `.gitignore:53` 忽略 `.mw/`，所以授权表默认不进 git（每人/每机器各自一份）。要把它当
> 项目资产带版本，需要显式 `git add -f .mw/decide-points.json` 或调整忽略规则。

### 2.2 内容形状

`mw decide dp refresh` 首次生成的真实形状（省略中间行）：

```json
{
  "version": 1,
  "updated_at": "2026-10-20T08:55:57Z",
  "updated_by": "human:p0-confirm",
  "points": {
    "dp1-dispatch-type":  { "tier": "P2", "enabled": true,  "mode": "auto", "note": "" },
    "dp3-worker-clarify": { "tier": "P2", "enabled": true,  "mode": "suggest", "note": "trial phase" },
    "dp4-failure-handling": { "tier": "P1", "enabled": false, "mode": "auto", "note": "" }
  }
}
```

行内只认四个字段：`tier`（只作展示，**注册表 tier 永远优先**）、`enabled`（bool，真正的开关）、
`mode`（`auto|suggest`）、`note`（单行备注）。顶层 `version/updated_at/updated_by` 由 CLI 维护。

### 2.3 读侧 8 层降级（fail-soft，绝不崩 worker）

实现在 `decision_points.py:884` `_parse_row` / `:1008` `_parse_points_text`。

| 层 | 情形 | 后果 |
| --- | --- | --- |
| L0 | 文件缺失 | 全部用注册表默认（P2 on / P1,P0 off），`layer=L0` |
| L1 | JSON 语法错 / 顶层非对象 | 全部默认 + doctor/`dp list` warning |
| L2 | 某行不是对象 | 该 dp `enabled=false` + warning（其余不受影响） |
| L3 | 字段类型错（`mode`/`note`/`tier`） | 该 dp `enabled=false` + warning |
| L4 | `tier` 值非法 | 保留注册表 tier + warning（不关） |
| L5 | `enabled` 非 bool | 该 dp `enabled=false` + warning |
| L6 | 未知 dp id（注册表里没有） | **保留行并标 `orphaned`**，不静默删除（档案可能引用它） |
| L7 | `tier` 与注册表冲突 | 以注册表 tier 为准 + warning；`enabled` 仍以表为准 |

同一行同时命中多层时，报**最严重**的层（`L2 < L3 < L4 < L5 < L7`）。

### 2.4 热生效

- 每次 `decide_for` 前按 `(st_mtime_ns, st_size)` 双签名重读（`decision_points.py:853` 缓存），
  **人手改文件后下一次决策即生效，无需重启、无需任何命令**。
- 写侧（`mw.py:1214` `_dp_write_raw`）沿用 `.mw/decide.json` 的「锁 + tmp + `os.replace`」协议，
  并在「改完 mtime/size 都没变」时显式 `os.utime(ns=...)` 推一格，避免 Windows FAT 2 秒粒度让
  读侧拿到旧视图。
- 读侧无锁（写侧原子换 inode）；多 worker 并发读到的是「旧整份」或「新整份」，不会是半份。

### 2.5 指令面（`mw decide dp ...`）

全部命令都必须带 `--project <dir>`（默认 `.`）。退出码约定：`0` 成功 / `2` 参数或写入非法
（`mw.py:2397` `_decide_dp` 分发）。

```bash
# 一览：id / tier / enabled / mode / source(default|config) / P0-ON / ORPHANED
python mw.py decide dp list --project . [--json]
#   dp8-scope-change   P0  enabled=true  mode=auto  source=config  P0-ON

# 单点详情 + 最近 N 条档案行（默认 5）
python mw.py decide dp show dp3-worker-clarify --project . [--rows N] [--json]

# 开/关一个点（P0 必须带 --i-understand-p0）
python mw.py decide dp on  dp4-failure-handling --project .
python mw.py decide dp on  dp8-scope-change --project . --i-understand-p0
python mw.py decide dp off dp4-failure-handling --project .

# 改单行字段（白名单 tier|enabled|mode|note，非法值 exit 2）
python mw.py decide dp set dp3-worker-clarify mode=suggest note="trial phase" --project .

# 注册表 → 配置表单向补齐（只增缺失行；不动已有开关；无变化不写文件）
python mw.py decide dp refresh --project .
#   refresh: added=24 kept=0 orphaned=0 wrote .../.mw/decide-points.json
#   refresh: added=0 kept=24 orphaned=0 no changes (file untouched)   ← 幂等

# 体检：坏行/孤儿/tier 冲突（exit 0 干净 / 1 warning / 2 error）
python mw.py decide dp check --project .
#   check: ... (exists=true layer=OK)
#   check: 0 error(s), 0 warning(s) -> exit 0

# 应用人工签收（见 §5）
python mw.py decide dp apply .agenticdoc/<key>/evidence/review/sign-final.md --project .
```

`refresh` 的语义是「**注册表 → 表，只增不改**」：新增缺失行时用注册表默认值，已存在的 `enabled/mode`
一个字节都不动，孤儿行保留并计入 `orphaned` 计数（`mw.py:1605`）；每新增一行同时向档案追写一条
`kind=authority-change`（`by=refresh`，`change="add missing row <dp>"`），所以「表变了」本身也在审计里。
升级后补新 dp 用 `refresh`，调开关用人命令。

### 2.6 P0 的三道门槛（DS-12）

P0 可以打开，但必须有痕迹、有确认、有收尾复核：

1. **二次确认**：`dp on <P0>` 不带 `--i-understand-p0` → exit 2、打印该 dp 的 `p0_consequences`、
   **配置文件一个字节都不写**（`mw.py:1453` `_dp_require_p0_confirmation`）。
2. **强制留痕**：成功后面向档案追写一行 `kind=authority-change`，`by=human:p0-confirm`，
   `change="enable <dp>"`，`config_sha_after=<写后表 sha 前 16>`；`dp list` 对该行打 `P0-ON`。
3. **收尾必列**：签收文件的 `p0-open:` 行必须与「当前已开的 P0 集合」**完全一致**（漏列或多列都
   exit 2，`mw.py:1800` `_dp_apply_check_p0_open`）；经签收通道**不能**打开任何 P0
   （`mw.py:1822` `_dp_apply_plan` 明确拒绝，要求人手 `--i-understand-p0`）。

`dp set <P0> enabled=true` 同样要求 `--i-understand-p0`（`mw.py:1567` 走同一个 `_dp_require_p0_confirmation`）。

## 3. `mode` 语义

| mode | 决策服务被调用 | 档案行 | 行为改变 | 典型用途 |
| --- | --- | --- | --- | --- |
| `auto`（默认） | 是 | `kind=decide`，`acted=true`（执行器成功）/ `acted=false`（无执行器→上抛） | **生效**：注入 steer、写 `decision:` 头行、按建议收窄等 | 常态化授权 |
| `suggest` | 是 | `kind=decide`，`acted=false`，`authority=advisory` | **零行为改变**（等价于未开启，但对人可见） | P1 首次开启的观察期；怀疑某 dp 时降级观察 |

要点：

- `mode=suggest` 时**不注入**任何 steer，也**不写** task.md 的 `decision:` 头行。`auto` 且带
  `decision_id` 只是**必要条件不充分**：dp1 派发侧还有一道分歧闸——建议类型必须等于实际派发类型
  （`triage_type === 实际 type`），类型不一致时即使 `auto` 也不采纳、不写 `decision:` 头行
  （`pm/ui-bridge.ts:282` `dispatchDecisionOf` 的 AC-014 分歧闸；答案与 `decision_id` 仍留在
  ledger/report 通道里可观测）。所以 `suggest` 不会污染 settle 关联（否则会把未生效的建议错记成
  「已生效」）。
- dp3 走服务（3a）时，子进程未报 `mode`（或报了非法值）视为**不可用并上抛人**
  （`escalated_reason=unavailable`），**不回退本地配置**——「服务是否认为自己已作答」只有
  `payload.mode` 一个权威（D-036）。本地 `policy.mode` 只在零 spawn 的 3c 本地引用匹配
  路径上是依据（那里没有子进程可问）。dp3 的 3a 在注册表里是 **Jev 原生题型**：
  `answer_kind`（choice：`fact|intent|reuse`）+ `answerable`（noul：0..1 可答性概率）+ `candidate`
  （choice，候选由请求 state 的 `local_candidates` 渲染，是 `dynamic_choices` 题）。**没有自由文本题**：
  `box` 是**图像定位题**（官方答案 `{top,bottom,left,right}` 归一化坐标，请求必须带
  `TypeSafe-Danger-Zone-Images: true` 与 `state.assets` 图像），Jev 官方契约里根本没有自由文本类型，
  文本决策后端遇到 `box` 直接拒答（`available=false`, `reason="box-requires-image"`，不发任何 HTTP）。
  所以 3a 的「答案文本 + 引用」不由模型生成：模型只选候选（≤5 条，`c1..c5`）并给出可答性，
  `answer` 与 `path:line` 由 worker 侧在**本地文件**里取（选中文件的首个命中行），引用因此可复核。
  候选无法渲染（state 缺 `local_candidates` 或形状非法）→ `input-incomplete`，零 HTTP 上抛人。
- dp8 的 `scope_rationale`（原 `box`）改为 `scope_reason`（choice：`outside-write-face|
  cross-key-conflict|scope-creep|unclear-boundary`），同样不使用自由文本。
- `dp set <dp> mode=suggest` → `mode=auto` 的切换同样是**下一次决策即生效**（热重载，见 §2.4）。
- 建议路径：P1 首次打开用 `enabled=true, mode=suggest` 跑满一个 phase，看报告里的分歧样例，
  再转 `auto`（DS-13）。
- 与 `intent` 的区别：`mw decide run --dp <id>` 一律走 `intent="answer"`（`decision_points.py:1393`
  `decide_for` 的 `intent` 参数，D-035）——跳过执行器、只回答案，档案行仍记 `acted=false`；真正的
  「执行」发生在各调用点（dp1 派发侧注入、dp2 PM 写 steer、dp3 worker 自答）。`intent=act` 只给
  注册表里带真执行器的点用，目前没有点走这条路。
- 档案行的 `acted` 与消费侧的生效**不是同一个事实**（QG MINOR-2）：档案 `acted` 记录的是
  **Python 执行器是否成功**——`intent="answer"` 下恒为 `false`，而目前三个已接线的 dp 的
  执行器都没挂（没有 `intent=act` 调用点），所以 `.agenticdoc/_autopilot/decisions.jsonl` 里
  `kind=decide` 行的 `acted` **恒为 false**，报告「自动生效」列因此恒 0。真正生效的证据在
  **消费侧**：`trace.log` 的 `[DECISION] ... acted=1` 行与 task.md 的 `decision:` 头行
  （D-041：`acted` 由执行点显式给出）。要读「这次真的替人做了决定」请看这两处，
  不要用档案 `acted`。

## 4. 决策档案：字段与读法

### 4.1 位置与不变量

`.agenticdoc/_autopilot/decisions.jsonl`（`decision_points.py:71`、`decide_archive.py:39`）。

- **append-only**：没有 update 路径；撤销用负行（新的 `kind` 行），不改旧行。
- **单写者**：`decide_archive.py` 唯一写者，`O_CREAT|O_EXCL` 锁（`decisions.jsonl.lock`）。
- **哈希链**：`prev_sha` = 上一条可解析行 canonical JSON 的 `sha256[:16]`，首行全 `0`；链断裂由
  `fold` 的 `chain_breaks` 计数暴露（报告里可见），不自动修复。
- **半行尾**：写入中断留下的残行会被下一次追加前修复（保留不 truncate 已有可用行）。
- **幂等**：同一 `decision_id` 只允许一行 `kind=decide`；重复写入按「重放」处理
  （`duplicate="existing"` + `note=duplicate-replay`），不抛错、不加新行（D-032）。

### 4.2 四类行

| kind | 语义 | 关键字段 |
| --- | --- | --- |
| `decide` | 一次决策（含上抛） | `seq/prev_sha/decision_id/ts/dp/key/task_key/state_digest/questions_version/available/reason/answer/authority/escalated_reason/acted/actual_action/mode/model/transport/attempts/latency_ms/confidence/confidence_source`，`outcome` 恒 `pending` |
| `override` | 人推翻了这次自动决策 | `decision_id/override_by/override_reason`（不回写 decide 行） |
| `settle` | 结果关联（PM 回收终态） | `decision_id/outcome/settled_by`；`outcome=pending` 必须有 `note`，且只接受 `lost`/`needs-clarification`/`deferred-to-human` 之一 |
| `authority-change` | 授权面变动（开关/签收） | `dp/by/change/conclusion/config_sha_after`，`by ∈ {human, human:p0-confirm, signoff:continue\|narrow\|revoke, refresh}`；按 dp 展开一行一个 |

每行都写全 36 个字段（未使用的按 kind 置 `null`，`decide_archive.py:91` `_ROW_FIELDS` +
`:132` `_NOT_APPLICABLE`），所以读侧不用区分「字段不存在」和「本 kind 不适用」。

`decision_id = <dp>:<trigger_id>`，按**首个** `:` 切分（dp id 是 kebab-case，trigger 里可以再有冒号）：

| 来源 | trigger_id 例 |
| --- | --- |
| dp1 派发 | `<task_key>` |
| dp2 checkpoint | `<task_key>#ckpt<N>`（`N` = trace.log 里 `[CHECKPOINT]` 行数） |
| dp3 澄清 | `<task_key>#nc<N>` |
| dp 无任务上下文（含 `refresh`/开关） | ISO 时间戳，如 `2026-10-20T08:56:04+00:00` |

`state_digest = sha256(_encode_state(state))[:16]` **只由 Python 计算**并随响应回传（D-004），
TS 侧零哈希，避免两种分隔符算出不同指纹。

真实一行（`dp refresh` 产生的授权行，为便于阅读只留关键字段）：

```json
{"seq": 26, "prev_sha": "0fa8d0864067697c", "kind": "authority-change",
 "decision_id": "dp8-scope-change:2026-10-20T08:56:04+00:00", "dp": "dp8-scope-change",
 "by": "human:p0-confirm", "change": "enable dp8-scope-change",
 "config_sha_after": "204cdc6238d14772"}
```

### 4.3 怎么读

```bash
# 单点最近 N 行
python mw.py decide dp show dp3-worker-clarify --rows 5 --project .

# 折叠成报告（人读 / 机器读）
python mw.py decide report --project . [--key K] [--phase final] [--json]

# 直接读文件（jq 之类）也行：每行一个 JSON，按 decision_id 合并
```

折叠规则（`decide_archive.py:809` `fold`）：按 `decision_id` 合并 → `decide` 行是 base →
`override` 记 `human_override` → `settle` 取**最后一条生效行**（`(decision_id,outcome,run_id)` 去重）。
`kind=authority-change` 不改 base，只做授权时间线。

### 4.4 `settle` 的六个终态映射（dp1 通道全量）

PM 回收 worker 终态时按 `run.json` + `run.json.exit` + 模型耗尽标记映射
（`pm/pm-orchestrator.ts:852` `mapTerminalToSettle`）：

| worker 终态 | `outcome` | 是否进报告分母 |
| --- | --- | --- |
| `done`（exit 0 + 契约段齐） | `ok` | 进 |
| `failed`（exit 1） | `rework`（计入返工，**不计推翻率**） | 进 |
| `failed` + exit 3 / `model_exhausted` | `inconclusive` | **不进** |
| superseded（被重派覆盖且替代者落地） | `rollback` | 进 |
| `lost` | `pending` + `note=lost` | 不进 |
| `needs-clarification` | **不写行**（下一个人工澄清事件才是主体） | — |
| `status=done` 但 `exit≠0`（记录自相矛盾） | 不写行，报告 `inconsistent-run` | — |

无法自动关联的 5 类显式登记（报告「无法关联项」一节）：PM 本地决策（`task_key=null`）、长时延
（dp10）、复合归因（`note=composite`）、worker 内部 `tool_call`、跨 key 外溢。

## 5. 报告与签收

### 5.1 phase 末自动报告

`advance_phase.py` 推进成功后调用 `maybe_write_decision_review()`（`.agents/skills/agentic-task/core/scripts/advance_phase.py:534`）：
档案存在且该 phase 还没有报告时，跑 `mw decide report --key <key> --phase <prev_phase> --write`，
产出 `.agenticdoc/<key>/evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`。
任何失败只是 WARN，**绝不影响 phase 推进**。

手动生成同一个文件：

```bash
python mw.py decide report --project . --key <key> --phase <phase> --write
python mw.py decide report --project . --key <key> --json     # 机器读（阈值判定所需字段）
```

报告结构（`mw.py:2167` `_decide_report_markdown`）：

1. **概览**：`N`（有效 settle，剔 `inconclusive`/`pending`）、groups/行数、acted/上抛数、
   override 率、一致率 Wilson 95% 下界、dp3 的 `nc_raw`/`nc_human`、链断裂/跳过行。
2. **判据表**：逐条 `decision_id` 的 answer/confidence/mode/acted/outcome/override。**参考用，不作门控。**
3. **逐决策**：时间戳、授权、`actual_action`、settle 归属。
4. **分歧样例**：overrides / rollback / 人工授权变更，每条写「jev 答 X、人做 Y、理由」。
5. **候选调整**：机器只给一行建议，如 `suggest: disable dpX, N=12 override=3`。
6. **无法关联项**：见 §4.4。

**数据不足就不结论**：`N < 5` 时报告与 CLI 都强制输出「数据不足，不结论」（`mw.py:2026`
`_REPORT_MIN_N`）；`suggest:` 行的阈值是「最近 30 条滑窗内 override 率 > 0.15 且样本 ≥ 5」
（`mw.py:2027/2029/2142`）。机器**只建议不执行**——调整仍然要靠人一条 `dp off`。

### 5.2 收尾强制签收（done 门禁）

`GATES["done"]` 原有两条**现成** `check_type`（`.agents/skills/agentic-task/core/scripts/advance_phase.py:95-110`）；
FIX-P 在其后新增第三类 `decision_signoff`（条件生效 + 内容校验，见 §5.3）：

```python
("evidence/review/sign-final.md", "glob_has_files", 1, "..."),
("evidence/review/sign-final.md", "content_match",
 r"(?m)^conclusion:\s*(continue|narrow|revoke)\s*$", "..."),
```

即：key 收尾前必须有 `<key>/evidence/review/sign-final.md`，且含一行**列 0、单行**的
`conclusion: continue|narrow|revoke`。文件名固定（`content_match` 对含 `*` 的路径恒 False，D-014）。

签收文件由**人**写，格式（`mw.py:1726` `_dp_apply_parse`）：

```
conclusion: continue
promote: dp4-failure-handling, dp6-qg-verdict
demote: -
p0-open: -
```

- `conclusion:` 必填且只能是 `continue|narrow|revoke`。
- `promote:` / `demote:` 是逗号分隔的 dp id 列表，`-` 表示空；同一 dp 不能同时出现。
- `p0-open:` 必须**恰好等于**当前已开启的 P0 集合（§2.6）。
- `key : value`（冒号前带空格）会被 `apply` 拒绝：门禁的正则锚定 `key:`，两者必须一致。
- 三种结论的行为：`continue` 按 promote/demote 增量生效；`narrow` 只允许收窄（带 promote 即
  exit 2）；`revoke` 关掉当前所有已开启的 dp。

应用签收（**必须由人在 agent 会话外执行**）：

```bash
python mw.py decide dp apply .agenticdoc/<key>/evidence/review/sign-final.md --project .
```

`apply` 的顺序是「全量校验 → 取锁 → 重读表（防 TOCTOU）→ 复检 P0 集合 → 先写
`authority-change` 行 → 原子替换表」：任何一步失败都打印 `nothing was written` 并 exit 2。
会话内检测依据 `PI_CODING_AGENT` / `AI_AGENT` / `PI_WORKER_TASK` 任一存在即拒绝（`mw.py:1882`），
所以 PM 与 worker 都无法自己给自己开权限；写守卫另有 `tool_call` 层覆盖
`evidence/review/sign-final.md` 与 `.mw/decide-points.json`（`shared/xkey-gate-guard.ts`）。
`worker_file` 通道的签收守卫只认 `<key>/evidence/sign-final.md` 与
`<key>/evidence/review/sign-final.md` 两个落位；`evidence/<其它>/…/sign-final.md`
（如 `evidence/research/evidence/sign-final.md`）属于普通产物、可写。

### 5.3 `mw decide sign`：(a) 命令 + (b) 门禁内容校验（FIX-P，2026-10-21 裁定）

**(a) 命令：人只回结论，机器行由命令算。** `mw decide sign --project .agenticdoc/<key>`（也接
`--project <root> --key <key>`）先打印本 key 的决策摘要：`counted_rows`（`kind=decide` 行数）、
`n_available` / `n_acted` / `n_escalated`、`engines` 三元组计数、按 dp 计数、`escalated_reason` 分布、
已开 P0（读 `.mw/decide-points.json`，缺失写 `none`）、`rows_sha256`（被计数行的规范 JSON 哈希）。
带 `--conclusion` 才写 `evidence/review/sign-final.md`：`conclusion:` 列 0 单行，`counted_rows:` /
`rows_sha256:` 由 `decide_signoff.collect` 重算得出，`promote:` / `demote:` / `p0-open:` 一并写出，
所以同一份文件仍可直接给 `mw decide dp apply` 消费。写入成功后追加一条 `kind=authority-change`
（`by=signoff:<conclusion>`、`change=signoff`、`conclusion=<x>`）。`N=0` + `continue` 必须显式
`--allow-empty`（文件落 `allow_empty: true` 与 `counted_rows: 0`），`narrow`/`revoke` 不受此限
（减权）；校验不过 → stderr 逐条原因、exit 2、不写文件；agent 会话内拒绝（与 `dp apply` 同一组
环境变量判据，常量单一来源 `decide_signoff.AGENT_SESSION_ENV_VARS`）。`--json` 输出
`{conclusion, ok, problems, facts, path}`。

**(b) 门禁：`continue` 必须是真 jev，`narrow`/`revoke` 只要求链完整。** 新 `check_type`
`decision_signoff` **仅当** key 目录存在 `decision-scope.md` 时生效（其它 key 零影响；既有两条签收
检查不变）。它校验 ①文件存在 ②`conclusion:` 可解析 ③`counted_rows:` / `rows_sha256:` 存在
④用 `decide_signoff.collect` 重算并比对 sha（签名后档案被追加/篡改即失败）⑤`conclusion=continue`
时跑 `verdict()`：`n_available>=1` + **每行**`transport=timi-decisions` / `model=jev-latest` /
`confidence_source=api` + 链完整（`seq` 从 1 连续、`prev_sha` 闭合）。失败信息逐条指出具体原因
（`N=0` / 引擎不符并给出该行 seq / `rows_sha256` 不匹配 / 缺机器行），不留
"gate blocked"这种无法定位的报错。

**TUI 入口（FIX-Q，2026-10-21 用户裁定方案 B）。** 签收请求从「人跑到 agent 会话外敲 CLI」降到
「pi 窗口里一条 `/mw decide sign`」，但守卫语义同时从「agent 不可能签收」降级为
**「要蓄意伪造 flag 才能签收，且档案留痕」**：

- `/mw decide show` = 只读 preview（`mw decide sign --key <k> --json`，不写）：渲染计数、`engines:`
  直方图、三个 conclusion 的 verdict、`rows_sha256` 前 12 位与 `p0-open`。
- `/mw decide sign <continue|narrow|revoke>` 先跑同一条 preview；该 conclusion 的 `verdicts[<c>]` 有
  problems 时**直接报错、不弹确认框、零写入**；通过才 `ctx.ui.confirm`（标题 `确认签收 <key>`，正文带
  `conclusion` / `counted_rows` / `rows_sha256` 前 12 位），取消则 `cancelled, nothing written`。
- 确认后窗口转发 `mw decide sign ... --human-confirmed`；Python 侧仍重跑①-⑤（exit 2 且零写入），
  成功才写文件并追加档案行。`ctx.hasUI` 为假（headless / `-p` / rpc）一律拒——没有确认框就没有
  人工点击可收集，这也让「agent 自己调一次命令」拿不到豁免。
- 安全边界：`--human-confirmed` 只是**一条显式声明**，不是密码学凭证。它把失败模式从「agent 顺手
  就把自己签了」变成「agent 必须蓄意伪造一个名字里就写着 human 的 flag」，且产物固定落
  `signed_via: tui`（命令行正常签收 `signed_via: cli`）+ 一条 `by=signoff:<conclusion>` 的
  `authority-change` 档案行，事后可审计。相应地：`signed_via:` 不属于机器行词表，done 门禁与
  `mw decide dp apply` 都不读它（加行前后解析结果逐字节不变）；真正的门禁仍是 `rows_sha256`
  重算 + `verdict()`，豁免不改变内容校验。

## 6. 失败与回退路径

### 6.1 上抛人的七个理由（单一词表）

`escalated_reason` 是冻结的 7 值词表（`decision_points.py:101`，档案层同名校验）——**任何一条都是
「上抛人」，不是「猜一个默认动作」**：

| 值 | 触发点 | 说明 |
| --- | --- | --- |
| `disabled` | 步骤 2（`decision_points.py:1459`） | 表里 `enabled=false` 或默认关；**在 build_state/encode/backend 之前返回**，零 spawn、零网络、不构造 state |
| `unavailable` | 步骤 4/7 | 传输未配置（`.mw/decide.json` 缺失/关闭）、预算耗尽、超时、429/5xx、连接不可达 |
| `input-incomplete` | 步骤 5 | `build_state` 抛错或必需字段缺失（只报字段名，不报值——值可能是 L2） |
| `input-oversize` | 步骤 6 | canonical JSON 超 2000 B：先丢可选 L1 → 必需 L1 减半 → 仍超则拒发 |
| `low-confidence` | 步骤 8 | 答案不可用（空/缺 qid/值非法），或 `confidence_source=api` 且低于阈值（默认 0.7） |
| `over-authority` | 步骤 10/11 | `mode=auto` 但没有执行器/执行器抛错/执行器返回空动作 |
| `p0` | 预留 | P0 点触达传输层后需人确认（预留值，避免与档案层漂移） |

`confidence_source` 的值决定置信值能不能当门：`timi-decisions`（唯一传输）返回的 `confidence` 是**服务端
（jev）给出的 API 字段**，记作 `api`，参与门控；`model-self-report`/`unknown` 时**置信值不参与门控也不上抛**
（D-031）：否则每个 P2 自动决策都会被上抛人，整个特性空转。它只能作弱排序信号，展示时必须带来源标识。

### 6.2 三条「关闭态等价」保证

| 场景 | 保证 | 验证位置 |
| --- | --- | --- |
| dp 关（`enabled=false` 或默认关） | 字节同构：不 spawn、不构造 state、不写档案、回执与派发不变 | `backend.calls == []` 断言（`test_decision_points.py:535`） |
| `mode=suggest` | 只多一行档案，执行行为与关闭态一致（不注入 steer / 不写 `decision:` 头行） | AC-015 用例（`pm/decision-tool` 套件 `mode=suggest never acts`） |
| 整个 `.mw/decide-points.json` 不存在 | 走注册表默认；`mw decide dp list` 显示 `source=default, layer=L0` | `dp list` 实测输出 |

### 6.3 常见故障与处置

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 自动决策完全不发生 | dp 关 / `mode=suggest` / `.mw/decide.json` 未启用 | `dp list` 看 `enabled/mode/source`；`mw decide show` 看传输 |
| `dp list` 出现 `warning:` / `dp check` exit 1-2 | 手改表写坏了（L1..L5） | 按 warning 修那一行，或 `dp refresh` 补齐；`dp check --json` 给机器读 |
| `dp check` 报 orphaned | 注册表删过 dp | 保留即可（不删行，档案可能引用）；确认无用后手工删行 |
| 报告全是「数据不足」 | `N<5`（settle 太少，或全是 `inconclusive`） | 正常现象：继续跑，等 dp1 通道攒到 ≥5 个 `ok/rework/rollback` |
| 收尾门禁报「必须有决策签收记录」 | 缺 `sign-final.md` 或缺 `conclusion:` 行 | 人写签收文件（§5.2），再 `dp apply` |
| `dp apply` 报 `refusing inside an agent session` | 在 pi 会话里执行了 | 到普通终端执行 |
| `dp apply` 报 `p0-open:` 不一致 | 有 P0 开着但没列（或多列） | 补全/删除该行；或先 `dp off` 关掉相应 P0 |
| `authority-change` 行没写 | 档案层不可写 | `dp on/off` 会打 `warning: authority-change row not written`；表已生效，去修档案目录权限后重跑一次同命令即可补行 |

### 6.4 回退阶梯（从轻到重）

```bash
python mw.py decide dp off dp3-worker-clarify --project .            # 1. 关单个点 → 立刻回原路径
python mw.py decide dp set dp3-worker-clarify mode=suggest --project .  # 2. 降级为观察（最轻）
python mw.py decide dp check --project .                              # 3. 表健康体检
rm .mw/decide-points.json                                             # 4. 整表回默认（P2 on / P1,P0 off）
rm .mw/decide.json                                                    # 5. 连传输一起停 → 全部 escalated_reason=unavailable
```

- 回退**不需要重启**任何进程：配置热重载（§2.4），架构上也不存在「已生效的缓存的授权」。
- 回退**不需要改代码**：任何 dp 的关闭态都走同一条零 spawn 分支。
- 回退也留痕：`dp off` 会写 `authority-change`（`by=human`），报告与 `dp show` 都能看到时间线。

## 7. 当前边界（诚实清单）

写文档时复核过的未完成面——别把「已注册」当成「已生效」：

| 边界 | 现状 | 影响 |
| --- | --- | --- |
| 只有 dp1 / dp2 / dp3 有调用点 | 其余 21 个 dp 仅注册（§1 表「当前真实接线」列） | 开它们不改变任何行为 |
| dp1 的自动生效面只有「PM 发起的派发」 | conductor 的 13 个自动派发点未挂（底座波的边界） | 自动派发路径行为与关闭态完全相同 |
| dp2 只允许 `narrow` | `split` / `direct-exec` 一律回退成人告警（D-011） | 想拆/直执仍需人 |
| dp5 / dp7 缺结构化输入 | 注册表有占位执行器，无调用点 | 真正接线的卡未开 |
| 只有 dp1 通道有自动 `settle` 关联 | dp2/dp3 目前不进报告的分母 | 报告里 dp2/dp3 的数字要打折看 |
| 没有 `mw decide settle/override` 子命令 | `settle` 由 PM 侧直接调 `decide_archive.append_settle`；`override` 目前只有库函数 | 人工推翻要靠写档案的工具，未面化到 CLI |
| 哈希链 doctor 面化未做 | 链断裂只在报告里计数 | 需人工看 `chain_breaks` |
| dp3 的 3c 本地复用零档案行 | 3c 命中即零 spawn（`worker/worker-mode.ts` 三级复用），`decide_for` 不跑则 `decisions.jsonl` 无行 | 该次决策的 `decision_id` / `acted=1` 只在 `trace.log`，档案里查不到；「每次自动决策可 review」对它断链 |
| legacy `mw decide run` 路径不落档案行 | 未带结构化 state 的旧调用按 legacy 分支处理（`mw.py` `_decide_run` docstring 已注明） | 走这条路的决策只有响应、没有审计行 |
| `mw doctor` 的 `triage:` 行只看传输 | `_doctor_decide`（`mw_common.py:1645`）不读授权表 | dp 健康用 `mw decide dp check` |

## 8. 参考

| 内容 | 位置 |
| --- | --- |
| 注册表 + 配置读侧 + `decide_for` 11 步 | `packages/multi-workers/decision_points.py:340`、`:1085`、`:1393` |
| 决策档案（4 类行 / 哈希链 / fold） | `packages/multi-workers/decide_archive.py:91`、`:809`、`:917`、`:1036`、`:991`、`:1077` |
| `dp` CLI（list/show/on/off/set/refresh/check/apply） | `packages/multi-workers/mw.py:1281-1999`、`:2397` |
| 报告器与阈值 | `packages/multi-workers/mw.py:2026-2034`、`:2053`、`:2315` |
| 门禁两条 + phase 末报告钩子 | `.agents/skills/agentic-task/core/scripts/advance_phase.py:95-110`、`:534` |
| `ask_decision` 工具（仅 worker 注册） | `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:57`、`:765` |
| dp1 派发侧（`decision:` 头行） | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:264`、`:2158` |
| dp2 checkpoint（只收窄） | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1958`、`:2244` |
| dp3 worker 澄清 | `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3897`、`:4413` |
| 设计与验收口径 | `.agenticdoc/mw-decision-substitution/design.md`、`spec.md`（AC-001..015） |
| 验证记录 | `.agenticdoc/mw-decision-substitution/evidence/runs/verify-mw-decision-substitution-20261020.md` |
