# 设计调研：决策档案写入器（D2 / RQ-3 spec §6）

任务卡：`tasks/D2-decision-archive.md`（key `mw-decision-substitution`，worker `ds-d2-decision-archive`）。
范围：`packages/multi-workers/decide_archive.py` 写入器接口设计、seq/prev_sha 并发正确性、幂等、4 类行字段矩阵、读侧 fold、与 11 字段传输行对账。只设计，不改码。
事实基线（本会话实读核对）：spec §6 = `spec.md:164-192`；上游设计 = `evidence/research/spec-authority-audit-model-20261016.md` Q2/Q5/Q6；全仓 `rg prev_sha` 零命中——哈希链是 spec §6.1 新增，无既有实现可复用，但四层保证的每一层都有仓内先例（见各节）。

---

## Q1 写入器接口（RQ-1）

### Q1.1 模块定位与错误模型

单模块 `packages/multi-workers/decide_archive.py`，独占 `.agenticdoc/_autopilot/decisions.jsonl` 的**全部写路径**（可 grep 审计：除本模块外无任何 `open(...decisions.jsonl...)` 写模式）。与既有两类 JSONL 的关系：

| 文件 | 写者 | 错误模型 | 先例 |
| --- | --- | --- | --- |
| `triage-decisions.jsonl`（11 字段传输行） | `DecisionClient._append_evidence`（`decision.py:940-968`） | best-effort 永不抛（D-005） | `decision.py:962-968` 只 `open("a")`、异常吞掉 |
| `auto-decisions.jsonl`（conductor 台账） | Python `conductor.py:7638-7647` + TS `recordDispatchAlarm`（`pm-orchestrator.ts:645-664`） | best-effort / 无锁 | 两端都写、`seq` 靠行数计数——已知非严格并发安全（上游 Q2.1 自认） |
| `decisions.jsonl`（本档案） | **仅** `decide_archive.py`，持锁 | **失败即抛** | 见下 |

档案与传输行的关键差异：11 字段行丢了只是少一条审计（D-005 契约），而档案是**正确性依赖**（幂等去重、settle 关联、AC-006 门禁证据）——所以 `append_*` 对 I/O 失败与校验失败一律抛异常，由调用方（决策服务/PM）映射为 exit 2 上抛人。这是与 `_append_evidence` 唯一的语义分歧点，显式登记为 D2-S0（有意不同，非疏漏）。

### Q1.2 公开函数签名（代码骨架）

```python
"""Decision archive writer/reader: .agenticdoc/_autopilot/decisions.jsonl.

Append-only, hash-chained, single-writer (spec §6.1 / mw-decision-substitution
D2). Unlike triage evidence (decision.py:940-968, D-005 best-effort), this
archive IS a correctness dependency (idempotency + settle correlation):
append_* raise on validation or I/O failure; callers map that to exit 2 and
escalate to a human.
"""

ARCHIVE_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "decisions.jsonl"
_LOCK_SUFFIX = ".lock"            # → decisions.jsonl.lock, 同目录
_GENESIS_PREV = "0" * 16          # 首行 prev_sha

_KINDS = frozenset({"decide", "override", "settle", "authority-change"})
_AUTHORITY = frozenset({"advisory", "binding", "human"})
_ESCALATED_REASONS = frozenset(
    {"unavailable", "low-confidence", "over-authority", "p0", "input-invalid"})
_OUTCOMES = frozenset({"pending", "ok", "rework", "rollback", "inconclusive"})
_SETTLED_BY = frozenset({"pm-auto", "human"})
_CHANGE_BY = frozenset({"human", "human:p0-confirm",
                        "signoff:continue", "signoff:narrow", "signoff:revoke",
                        "refresh"})
_MODES = frozenset({"auto", "suggest"})


class DecisionArchiveError(ValueError):
    """契约违约或 I/O 失败；CLI 边界映射 exit 2（上抛人）。"""


class DecisionArchiveDuplicate(DecisionArchiveError):
    """同一 trigger_id 已存在 kind=decide 行（spec §6.1 幂等）。"""


def state_digest(state: object) -> str:
    """sha256(decision._encode_state(state))[:16] —— 原样复用 decision.py:402-417。"""

def iter_rows(path: pathlib.Path) -> Iterator[tuple[int, dict]]:
    """逐行 yield (1-based 行号, 解析成功的 dict)；空行/坏行跳过（坏行计数交给 fold 的入参方）。"""

def fold(rows: Iterable[Mapping]) -> FoldResult: ...   # Q5

def append_decide(path, *, dp, key, task_key, trigger_id, state, questions_version,
                  available, authority, answer=None, reason=None,
                  escalated_reason=None, acted=False, actual_action=None,
                  mode=None, transport=None, model=None, attempts=0, latency_ms=0,
                  confidence=None, confidence_source=None, cost_tokens=None,
                  note=None, evidence_line=None, now=None,
                  duplicate: Literal["raise", "existing"] = "raise") -> tuple[dict, bool]: ...

def append_override(path, *, decision_id, dp, key, override_by, override_reason,
                    ref_seq=None, note=None, now=None) -> dict: ...

def append_settle(path, *, decision_id, dp, key, task_key, outcome,
                  settled_by, evidence_ref=None, note=None, now=None) -> dict: ...

def append_authority_change(path, *, dp, key, by, change, trigger_id=None,
                            conclusion=None, config_sha_after=None,
                            note=None, now=None) -> dict: ...
```

### Q1.3 入参校验与返回值

公共校验（四个 append 共用，`_validate_common` 内聚）：`kind` 在 `_KINDS`；`decision_id = "<dp>:<trigger_id>"` 由写侧拼装——`append_decide`/`append_authority_change` 收 `(dp, trigger_id)`，`append_override`/`append_settle` 收已确定的 `decision_id` 且校验 `decision_id.startswith(dp + ":")`、`trigger_id` 非空且不含 `":"`（`<dp>` 本身含 `:` 无妨，取首个 `:` 切分）；`dp` 非空字符串（是否在注册表由调用方保证——`decide_for(dp_id)` 出口已挡未知 dp，AC-011；档案层不重复查注册表，避免 import 环）；`key` 为 str（空串 = 项目级/PM 本地）；`task_key` 为 str 或 None（None 仅限 PM 本地决策，spec §6.2）；`now` 可注入 ISO-UTC 字符串（默认 `datetime.now(timezone.utc).isoformat(timespec="seconds")`，先例 `decision.py:946`），便于测试确定性。

逐 kind 校验（域定义见 Q4 矩阵，此处只列规则）：

- `append_decide`：`authority ∈ _AUTHORITY`；`available` 是 bool；`available=false ⇒ answer=None 且 reason ∈ REASON_CODES`（8 值，`decision.py:88-99`；非法值直接拒绝——不像 `_append_evidence:960-962` 那样静默改写成 `upstream-error`，档案层宁可抛）；`authority=human ⇒ escalated_reason ∈ _ESCALATED_REASONS 必填`，`authority∈{advisory,binding} ⇒ escalated_reason=None`；`acted=True ⇒ authority=binding 且 actual_action 非空`；`mode="suggest" ⇒ acted 必为 False`（AC-015）；`answer` 形状 `{qid:{value, confidence: float|None}}`（`_normalize_answers` 产物，`decision.py:873-893`）；`state` 经 `state_digest()` 消化后不落原文（D-003）。返回 `(written_row, created)`；`duplicate="existing"` 且已存在时返回 `(existing_row, False)` 且**不写任何新行**。
- `append_override`：`override_by` 非空且必须以 `human` 语义发起（机器只建议不执行，spec §7.3——写侧强制 `override_by == "human"` 或 `<human-account>` 形式，拒绝 agent 身份串）；`override_reason` 非空；`ref_seq` 若给出必须是该 `decision_id` 组内已存在 decide 行的 seq。返回写入行。
- `append_settle`：`outcome ∈ _OUTCOMES`；`settled_by ∈ _SETTLED_BY`；`outcome="pending"` 仅作登记行、必须携带 `note ∈ {"lost", "needs-clarification", "deferred-to-human"}`（D2-S2，见 Q4/Q5：lost/needs-clarification 按 spec §6.2 保持 pending，但要在档案里显式登记，否则报告层无从区分"没结算"与"结算为不可结"）。返回写入行。
- `append_authority_change`：`by ∈ _CHANGE_BY`；`change` 非空单行描述；`by=signoff:* ⇒ conclusion ∈ {continue, narrow, revoke} 必填`，其余 `by ⇒ conclusion=None`；`config_sha_after` 可选 str16。返回写入行。

四个 append 的公共骨架（`_append_row` 私有函数，Q2 详述锁与恢复）：

```python
def _append_row(path: pathlib.Path, row: dict) -> dict:
    lock = path.with_name(path.name + _LOCK_SUFFIX)
    mw_common.acquire_lock(lock)                     # mw_common.py:2369-2384
    try:
        _repair_tail_if_dangling(path)               # Q2.4：半行收尾，绝不 truncate
        for _ in range(3):                           # 锁外写者的尺寸复核
            head, size = _chain_head(path)           # 尾扫最后一条可解析行
            if size == _size(path):
                break
        else:
            raise DecisionArchiveError("tail kept moving under lock")
        row["seq"] = (head["seq"] + 1) if head else 1
        row["prev_sha"] = _row_sha(head) if head else _GENESIS_PREV
        _validate(row)                               # kind 专属矩阵（Q4）
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass                                  # fsync 尽力而为，行已在页缓存
        return row
    finally:
        mw_common.release_lock(lock)
```

`iter_rows` 读侧不做任何写（`path.read_text(encoding="utf-8")` → `splitlines` → `json.loads`，跳过空行/坏行/非 dict——容错精神与 `decide_last_evidence` 一致，`mw_common.py:1637-1641`，但从"坏尾行返回 None"弱化为"逐行跳过"，因为 fold 需要全量视图）。`FoldResult` 为 frozen dataclass：`groups: dict[str, FoldedDecision]`、`stats: FoldStats`（Q5）。

---

## Q2 seq 与 prev_sha（RQ-2）

### Q2.1 seq 取法：读链尾，不数行

`seq = 链尾.seq + 1`（链尾 = 从文件尾向前扫到的最后一条可解析 dict 行），首行 `seq=1`。不采用两种计数法：

- 数非空行（`recordDispatchAlarm` 的 `split("\n").filter(trim!="").length + 1`，`pm-orchestrator.ts:648-657`）：Q2.4 的"半行保留"策略会让物理行数 ∉ 行号集合，且每次 append O(文件大小)。
- 数可解析行（`_append_auto_decision_row` 的 `len(rows) + 1`，`conductor.py:7643`）：同样 O(N)/次。

读链尾是免费的——算 `prev_sha` 本来就需要链尾整行 JSON，一次有界尾读（seek 到 `size-8KB` 窗口找最后一个 `\n`，不足则全读）同时供给 seq 与 prev_sha，单次 append O(窗口)。doctor 侧做交叉核对：`非空行数 ≥ 链尾.seq`，差值 = 坏行数（只报告，不修复）。

### Q2.2 并发正确性：临界区覆盖"读尾 → 算 sha → 追加"

锁 = `mw_common.acquire_lock`/`release_lock`（`mw_common.py:2369-2390`，`O_CREAT|O_EXCL` 重试协议；同目录 `<file>.lock`；用法先例 `_decide_write_config`，`mw.py:772-792`——配置写同样是"读-改-写共享文件全程持锁"）。正确性论证：

1. **守约写者互斥**：所有 append 走同一 lock 文件，临界区互斥 ⇒ 任一时刻至多一个写者在"读尾→sha→append"窗口内，链头不会在读取与追加之间被守约写者改变。
2. **锁外写者防御**：临界区内 `stat` 记 `size0`，写前复核 size；变化 ⇒ 有进程绕过锁写了 ⇒ 重扫链头（≤3 次），持续变化 ⇒ `DecisionArchiveError` 上抛人。这把"读尾→算 sha→追加"的原子性从"约定"升级为"检测"，闭合无锁写者竞争窗口。
3. **撕裂行防御**：单次 `write(line + "\n")` + O_APPEND 语义（`open("a")`）保证行字节连续；即便如此，进程在 write 中途被 kill 仍可能留半行——这正是 Q2.4 恢复协议的输入，而非正确性漏洞（链头扫描天然跳过半行）。
4. **单写者收敛**：TS 侧**永不写** `decisions.jsonl`（沿用 single-writer 契约措辞，`triage-client.ts:25-28` 注释；TS 需要读时走 `iter_rows` 的只读等价物或经 mw CLI）。这是对 `auto-decisions.jsonl` 双端无锁写（`conductor.py:7638-7647` + `pm-orchestrator.ts:645-664`）的刻意修正。
5. **fsync 语义**：行 `flush` 后尽力 `fsync`（失败忽略）——锁在 fsync 之后才释放，保证"锁释放 ⇒ 行对后续读者可见"（页缓存可见性足够；掉电丢行属可接受残留，与全部先例同级）。

### Q2.3 首行约定

文件不存在/为空 ⇒ `seq=1`、`prev_sha="0"*16`（genesis 常量）。读侧校验：首条可解析行若 `seq!=1` 或 `prev_sha!="0"*16` 计 `chain_breaks`。

### Q2.4 坏尾行（半行 JSON）恢复

约束：直接追加会断链（新行 prev_sha 无从计算）；truncate 又违反第 1 层"无 update 路径"。方案：**收尾不删除（terminate-and-preserve）**，全部在锁内执行：

1. 文件非空且末字节 ≠ `\n` ⇒ 先补写一个 `\n`，把悬挂半行变成独立（必为坏）行。悬挂半行只可能是"上一次 write 被中断"的产物：完整行在单次 write 中要么整行落盘、要么留下无内嵌换行的前缀，不会产生多行垃圾。
2. 从尾向前找最后一条可解析 dict 行 = 链尾；`prev_sha` 链接到它，中间的坏行不参与链（**链定义在可解析行子序列上**，读侧校验同样跳过坏行——fold 本就要求"跳过 + 计数"，上游 Q5.2）。
3. 新行可选 `note="tail-repaired"`；doctor 计数 `tail_repaired=N`。半行原始字节保留在文件里作法证证据。

选型理由（对 truncate 的否决）：truncate 是一条能自身中途崩溃的写路径（留下更短的垃圾尾），改动已存在字节（违反四层保证第 1 层），且销毁证据；terminate 保持"文件只增不减"的绝对不变量，坏行处理逻辑与 mid-file 腐败（本就必须容忍）完全同构，零新增失败模式。特例：悬挂尾若是完整 JSON 只丢了 `\n`，收尾后它成为合法链尾，新行正确链接——算法无需特判。

### Q2.5 prev_sha 规范化输入

链哈希输入 = **前一行的规范化 JSON 字节**：

```
canonical(row) = json.dumps(row, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), default=str).encode("utf-8", "replace")
prev_sha = sha256(canonical(prev_row)).hexdigest()[:16]     # str16
```

与 `decision.py:402-417`（`_encode_state`）的关系——**同四参、一分歧、两个用途**：

| 参数 | `_encode_state`（402-417） | 链 canonical | 说明 |
| --- | --- | --- | --- |
| `sort_keys` | True | True | 一致 |
| `ensure_ascii` | False | False | 一致 |
| `default=str` | True | True | 一致 |
| `separators` | 缺省（`", "`/`": "`） | **`(",", ":")` 紧凑** | 显式分歧，见下 |
| 输入 | 决策 state 对象 | 前一行 row dict | 用途不同 |

分歧理由：`_encode_state` 的输出字节就是**实际发给后端的 state 序列化**（stdin），语义被 D-003/响应冻结面钉死，一个字节都不能动——`state_digest` 必须**原样 import 复用**该函数（不是抄逻辑），保证"档案 digest ↔ 发送内容"一一对应（上游 Q2.3）。链的输入是 row dict：内存构造行与读回解析行的 key 插入序可能不同（fold/doctor/report 都会重新序列化行），逐字节链会在任何合法重序列化下假性断链；紧凑 `separators` 给出与插入序无关的稳定规范形，这正是上游 Q5.1"上一行**规范化** JSON 的 sha256 前 16 hex"的含义。被否决的替代：raw-line-bytes 链（验证最简、对任何字节篡改敏感）——但它把 prev_sha 绑定到磁盘序列化细节，且无法在"收尾保留"（Q2.4）之外容忍任何未来的行重发工具；规范形链在"防篡改"上只少覆盖空白变化，而空白变化必然同时改变其余字段哈希，实际检测面等价。

---

## Q3 幂等（RQ-3）

### Q3.1 规则与实现选型

规则（spec §6.1）：同一 `trigger_id` 只允许一行 `kind=decide`。**只对 decide 去重**：override/settle/authority-change 天然多行（组内多次结算取最后，fold 语义），去重会破坏负行/多结算模型。

实现：**持同一把锁的全量扫描**——在 `_append_row` 临界区内、写前，顺序扫全部可解析行，发现 `kind=="decide" 且 decision_id 相同` ⇒ 冲突。三个候选的取舍：

- 尾 N 行：漏旧重复 ⇒ 假接受，直接违反 AC-006"同 task_key 重复写即拒"。否决。
- 辅助索引（sidecar trigger→seq 映射）：引入第二个可变文件与它自己的崩溃一致性问题（档案 append 与索引 append 之间崩溃，恰好重新制造索引要防的洞），v1 否决。
- 全量扫描：无第二真相源。代价见 Q3.3，可接受。

### Q3.2 冲突行为

- 异常：`DecisionArchiveDuplicate(DecisionArchiveError)`，基类 `ValueError`——镜像 `DecisionInputError(ValueError)`（`decision.py:138-145`）的"唯一允许外抛"通道与 CLI exit 2 语义（`mw.py:794-800` 入参错误 return 2）。CLI 边界把 `DecisionArchiveError` 一律映射 exit 2、stderr 带 `decision_id` ⇒ **上抛人**（spec §6.1"冲突即上抛人"；AC-006）。
- **不落 `note=duplicate-suppressed` 行**：被拒的重复如果落行，(1) 等于档案里出现第二条 decide 行，破坏本检查维护的不变量本身；(2) 污染 override/rework 比率分母。重复尝试只进 trace/worker.log，不进档案。
- 重放路径的出路：崩溃在"append 成功之后、下游使用之前"时，调用方以 `append_decide(..., duplicate="existing")` 重入——返回既有 decide 行（`created=False`），流程幂等续行；不提供 `--force`（对应 P0 的 `--i-understand-p0` 精神：幂等冲突没有人类确认后的强写通道）。

### Q3.3 性能上限（1 万行）

10k 行 × ~400–600 B ≈ 4–6 MB；CPython `json.loads` 全扫 ≈ 20–60 ms，内存峰值 ≈ 行总字节 ×2。决策节奏是每派发/每检查点一条（单 key 每天数十条），万行量级约需数月积累，每次 decide 多花几十毫秒完全可忽略。可选优化（v2，不改契约）：进程内 memo `dict[decision_id → (st_mtime_ns, st_size)]`，命中且 stat 匹配才可信（文件被外部改动 ⇒ memo 作废全扫）；若未来 archive 达 10^5+ 行，再引入"启动时从档案全量重建、只读校验"的索引文件——重建式索引可随时丢弃重算，不产生第二真相源问题。

---

## Q4 4 类行字段矩阵（RQ-4）

图例：**R**=必填，o=可选，`=`该 kind 恒定值/不出现（写侧强制）。域：`kind` 4 值；`authority ∈ {advisory, binding, human}`；`escalated_reason` **5 值** `{unavailable, low-confidence, over-authority, p0, input-invalid}`；`outcome` **5 值** `{pending, ok, rework, rollback, inconclusive}`；`by` ∈ `{human, human:p0-confirm, signoff:continue, signoff:narrow, signoff:revoke, refresh}`；`settled_by ∈ {pm-auto, human}`；`mode ∈ {auto, suggest}`（AC-015）；`confidence_source ∈ {api, model-self-report, unknown}`（`decision.py:101-103`）；`reason ∈ REASON_CODES ∪ {null}`（8 值，`decision.py:88-99`）。

| 字段 | decide | override | settle | authority-change | 域 / 格式 / 依据 |
| --- | --- | --- | --- | --- | --- |
| `seq` | R | R | R | R | int，链尾+1（Q2.1）；先例 `conductor.py:7643`、`pm-orchestrator.ts:648-657` |
| `prev_sha` | R | R | R | R | str16，首行 `"0"*16`（Q2.3/Q2.5） |
| `kind` | **R**=`decide` | **R**=`override` | **R**=`settle` | **R**=`authority-change` | 4 值枚举 |
| `decision_id` | R | R | R | R | `<dp>:<trigger_id>`（spec §6.1）；trigger_id 规则 `task_key` / `task_key#ckpt<N>` / `ts`（上游 Q2.2） |
| `ts` | R | R | R | R | ISO-UTC seconds，`decision.py:946` 先例；settle 行的 ts 即 settled_at（上游 Q2.4 的 `settled_at` 由公共 `ts` 承担，不设双字段） |
| `dp` | R | R | R | R | 注册表 dp id（spec §4）；注册表成员资格由调用方（`decide_for` 出口）保证 |
| `key` | R | R | R | R | str，空串=项目级/PM 本地 |
| `task_key` | R(可 None) | o(=None) | R(可 None) | `=`None | None 仅限 PM 本地（spec §6.2）；与 `run.json.task_key` 同名同义 |
| `state_digest` | R | `=`None | `=`None | `=`None | str16 = `sha256(decision._encode_state(state))[:16]`，原样复用 `decision.py:402-417`（Q6.3 说明为何不参与传输行对账） |
| `questions_version` | R | `=`None | `=`None | `=`None | `q-<8hex>`，问题集常量内容 sha 短码（上游 Q2.1） |
| `available` | R | `=`None | `=`None | `=`None | bool；False ⇒ `answer=None` 且 `reason ∈ REASON_CODES` |
| `reason` | o(≠None 当 unavailable) | `=`None | `=`None | `=`None | 8 值域（`decision.py:88-99`）；非法值**拒绝**（区别于 `_append_evidence:960-962` 的静默改写，D2-S0） |
| `answer` | R(available 时) / `=`None | `=`None | `=`None | `=`None | `{qid:{value, confidence}}`（`decision.py:873-893`） |
| `authority` | R | `=`None | `=`None | `=`None | advisory/binding/human |
| `escalated_reason` | o（authority=human 时 **R**） | `=`None | `=`None | `=`None | **5 值**；AC-005 映射：不可用→`unavailable`、低置信→`low-confidence`、输入缺失→`input-invalid`、未开启/越权→`over-authority`、P0 强开→`p0` |
| `acted` | R | `=`None | `=`None | `=`None | bool；True ⇔ binding 且执行成功（写侧强制）；advisory/human 恒 False；`mode=suggest` 恒 False（AC-015） |
| `actual_action` | o（acted=True 时 **R**） | `=`None | `=`None | `=`None | 单行动作串，如 `dispatch type=coding` |
| `outcome` | **R**=`"pending"` 恒定 | `=`None | R ∈ 其余 4 值 + 登记特例 | `=`None | decide 行永不回填（上游 Q2.4）；settle 取 `{ok, rework, rollback, inconclusive}`；`"pending"` 仅作登记行且必须带 `note ∈ {lost, needs-clarification, deferred-to-human}`（D2-S2） |
| `settled_by` | `=`None | `=`None | R | `=`None | {pm-auto, human}（上游 Q2.4） |
| `evidence_ref` | `=`None | `=`None | o | `=`None | 如 `workers/<key>/run.json#<run_id>` |
| `override_by` | `=`None | R | `=`None | `=`None | 必须人语义（机器零推翻，spec §7.3，写侧拒绝 agent 身份串） |
| `override_reason` | `=`None | R 非空 | `=`None | `=`None | str |
| `ref_seq` | `=`None | o | `=`None | `=`None | 被推翻 decide 行的 seq（组内校验） |
| `by` | `=`None | `=`None | `=`None | R | 6 值域；`human`=dp on/off/set（AC-010，仅人执行）、`human:p0-confirm`=P0 强开（AC-002）、`signoff:*`=收尾签收三结论（AC-009）、`refresh`=dp refresh（AC-010，只增缺失行） |
| `change` | `=`None | `=`None | `=`None | R 非空 | 单行描述：`dp4 enabled=true mode=auto` / `conclusion=continue` / `refresh added=3 kept=21` |
| `conclusion` | `=`None | `=`None | `=`None | o（by=signoff:* 时 **R**） | {continue, narrow, revoke} |
| `config_sha_after` | `=`None | `=`None | `=`None | o | str16，变更后 `.mw/decide-points.json` 字节 sha 前 16（上游 Q1.7 快照互证） |
| `evidence_line` | o | `=`None | `=`None | `=`None | int，本决策 11 字段传输行的 1-based 行号（Q6 对账主键）；authority=human 等未调后端的路径恒 None |
| `mode` | o | `=`None | `=`None | `=`None | {auto, suggest}（AC-015） |
| `model`/`transport` | o | `=`None | `=`None | `=`None | 抄自响应，过 `_redact`（`decision.py:948-950`） |
| `attempts`/`latency_ms` | o | `=`None | `=`None | `=`None | int ≥0（`decision.py:951-952`） |
| `confidence`/`confidence_source` | o | `=`None | `=`None | `=`None | min-of-answers（`decision.py:419-435`）；`confidence_source != api` 不参与门控 |
| `cost_tokens` | o | `=`None | `=`None | `=`None | int 或 None（MVP 可缺，上游 Q2.1） |
| `note` | o | o | R（outcome=pending 登记行时） | o | 复合归因 `composite` / `lost` / `model-error` / `tail-repaired` 等标记（上游 Q3.3/Q3.4） |

**D2-S1（authority-change 的 decision_id 落法）**：上游 Q4.4 让签收行用 `decision_id="signoff@<key>@<ts>"` 单行携带 `dps` 列表——这破坏 spec §6.1 的 `<dp>:<trigger_id>` 通用文法。本设计改为**每个受影响 dp 一行**：dp on/off/set/p0-confirm ⇒ `decision_id="<dp>:<ts>"`；签收 ⇒ `"<dp>:signoff@<key>@<ts>"`；refresh ⇒ `"<dp>:refresh@<ts>"`。同批行共享 trigger_id（可 grep 聚合），每行文法统一、fold/时间线无特例；代价是签收 24 dp 时最多 24 行（可接受）。conclusion/change 逐行重复，换取行自包含。

---

## Q5 读侧折叠 fold（RQ-5）

`fold(rows: Iterable[Mapping]) -> FoldResult`，纯函数、不触文件系统、不查注册表。

### Q5.1 折叠规则

1. **分组**：按 `decision_id` 分组（4 类行同 id 同组；坏行/非 dict 行在上游 `iter_rows` 已跳过）。
2. **组内排序**：按 `seq` 升序（输入顺序为稳定副键——链与文件序对已提交行一致，坏行只造成 seq 空洞不改变相对序）。
3. **基行**：组内第一条 `kind=decide` 行为不可变基（answer/authority/escalated_reason/acted/state_digest/model/… 全取基行）。组内无 decide 行（decide 行损坏等）仍输出折叠项并标 `base_missing=true`，不静默丢弃。
4. **outcome**：组内 `seq` 最大的 settle 行的 `outcome`；无 settle ⇒ `"pending"`。登记行（outcome=pending + note，D2-S2）按定义把组保持为 pending，与"无 settle"同值但 `note` 可区分"从未结算"与"结算为不可结"。
5. **human_override**：组内存在 override 行 ⇒ true，附最后一条 override 的 `override_by`/`override_reason` 与 `override_count`；无 override 行 ⇒ false（不预置任何覆写字段——上游 Q5.2"存在 override 行即 true"）。
6. **authority 当前值**：**不**从行折叠——配置/快照文件（`.mw/decide-points.json`、`.mw/decide-authority.json`）是唯一权威（上游 Q5.2 明文）；fold 仅暴露 `authority_last`（组内最后一条 authority-change 行）供审计互证（`config_sha_after` 与现配置 sha 不符 ⇒ 报告层告警）。
7. **坏行**：跳过并计数，`stats.skipped_unparsable`/`skipped_non_dict`——`decide_last_evidence` 对坏尾行返回 None 的容错精神（`mw_common.py:1637-1641`），但从整文件降级弱化为逐行降级（档案是全量视图，不能因一行坏全弃）。
8. **链校验**：fold 顺带校验 `prev_sha`（对前一可解析行重算 canonical sha，Q2.5）⇒ `stats.chain_breaks`；seq 单调性破 ⇒ `stats.seq_breaks`。doctor 与报告只读这两个计数，不因断链拒绝服务（审计可读性优先，断链本身就是要报告的事实）。

### Q5.2 orphaned dp 的行仍然折叠——理由

`dp refresh` 给注册表中被移除的 dp 标 orphaned，且"orphaned 行不被删除"（AC-012）。fold 对 orphaned dp 的行**照常折叠**：

1. fold 是纯视图，文件本就完整保留；视图层过滤会造成"两处真相"。
2. 历史可审计性：正是这些行的 override/rework 数据支撑了"退役该 dp"的决策本身——折叠时剔除等于销毁该决策的证据链，违背 AC-006"旧行仍可读"精神。
3. 正确性依赖：Q3 幂等扫描与链校验必须看见全部行，与 dp 是否在册无关。
4. 归属：orphan 标记是注册表语义，由**报告层**做 join（行 `dp` ∉ 当前注册表 ⇒ 打 `orphaned=true` 旗），fold 保持无注册表依赖（也避免 import 环）。

### Q5.3 返回形状

```
FoldResult(groups={decision_id: FoldedDecision(
              decision_id, dp, key, task_key, base: decide行, outcome,
              settled_by, evidence_ref, human_override, override_by,
              override_reason, override_count, authority_last, note,
              base_missing)},
           stats=FoldStats(rows_total, parsed, skipped_unparsable,
              skipped_non_dict, chain_breaks, seq_breaks, groups))
```

展开面：`mw decide show --decisions` 或新子命令输出折叠视图；doctor 独立 section（不动既有 triage section 字节，零扰动承诺，上游 Q5.2）。

---

## Q6 与 11 字段行对账（RQ-6）

### Q6.1 前提：并存不升级，1:1 只对"真调了后端"的决策成立

11 字段行（`_EVIDENCE_FIELDS` = ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source，`decision.py:121-134`）由 `_append_evidence` 继续写入 `triage-decisions.jsonl`（路径 `decision.py:74`），格式被 D-005 冻结；消费者 `mw decide show`/doctor（`mw.py:845-878`、`mw_common.py:1645-1686`）零改动。档案行冗余携带全部 11 键（Q4），但注意：**不是每个档案 decide 行都有传输行**——`authority=human` / 未调后端的失败路径（如 input-invalid 在出口就被拒）根本不产生 11 字段行。对账前提按 `evidence_line` 是否为 None 分流，不能假设 1:1。

### Q6.2 对账键：evidence_line + evidence_sha 为主，(ts, dp) 为兜底

- **主通道（写时捕获）**：决策服务在一次 `decide()` 内的顺序是 `_append_evidence`（`decision.py:940-968`）→ `decide_last_evidence`（`mw_common.py:1620-1642`，恰返回 `(行号, record)`）→ `append_decide`。档案 decide 行因此写入 `evidence_line`（11 字段行 1-based 行号）与 `evidence_sha`（str16 = 该行 canonical sha，Q2.5 同一 canonical 函数）。对账 = 按行号直达 + sha 相等，O(1)、无歧义。
- **兜底（evidence_line 为 None 的旧行/异常路径）**：`(ts, dp)` 精确匹配 + 平手裁决元组 `(available, reason, confidence, attempts, latency_ms)` 逐项相等 + 按传输行文件序对齐。**已知歧义**：`ts` 只有秒精度（`decision.py:946`），同 dp 同秒两次调用无法区分 ⇒ 报 `ambiguous`，不静默配对。
- **方向不对称是常态**：`evidence_line=None` ⇒ "本决策无传输行"，正常（human 路径）；反向"传输行无档案行" ⇒ archive 写入器未启用时期的遗留 ⇒ 报告计数 `unarchived_transport_rows`，仅提示。

### Q6.3 state_digest 为何只在档案侧、算法是什么、不能对账什么

算法：`state_digest = sha256(decision._encode_state(state))[:16]`（原样复用 `decision.py:402-417`：dict → `json.dumps(ensure_ascii=False, sort_keys=True, default=str)` → UTF-8，失败降级 `str()`；上限同 `max_state_bytes`，`decision.py:244`）。11 字段行**没有** state 字段——state 只走 stdin 不落盘（D-003，`triage-client.ts:22-23`），因此**事后无法从传输行重算或核对 state_digest**：它的对账对象是 (a) 决策发生时的结构化输入记录（spec §5，若落地），(b) 前向关联（task.md `decision:` 头行、settle 归因）。明确结论：**state_digest 是档案侧溯源字段，不承担 archive↔triage 的 join 职责**；两文件对账靠 Q6.2 的 evidence_line/(ts,dp)，与上游 Q6"对账键 = (ts,dp) + state_digest"的表述相比收窄了 state_digest 的角色——因为传输行侧根本不存在可比较的 digest 值（上游 Q6 同段自己也承认"传输行没有 digest 时用 (ts,dp,available,reason) 近似对账"，本设计把它定为唯一路径并加 evidence_line 主通道）。

### Q6.4 对不上的报告

对账是报告器（phase 末 review，spec §7.1）的**只读审计**，永不阻塞、永不"修复"任何一侧（D-005 精神）。输出三段：

1. 汇总计数：`{matched, missing_transport, ambiguous, sha_mismatch, unarchived_transport_rows}`；
2. 逐条明细：`{decision_id, evidence_line, field, archive_value, transport_value}`（字段级差异，如 reason/confidence 不一致）；
3. 归入报告"无法对账项"节，与 Q3.4"无法关联清单"（上游）同页呈现，供人工裁决。

---

## 结论

1. 写入器收敛为单模块 `packages/multi-workers/decide_archive.py`，6 个公开函数（4 append + iter_rows + fold），错误模型与 best-effort 的 11 字段行**有意分道**：档案失败即抛 → CLI exit 2 上抛人（D2-S0；对照 `decision.py:940-968` 与 `decision.py:138`）。
2. seq 取链尾+1（不数行）；`acquire_lock`（`mw_common.py:2369-2390`，用法先例 `mw.py:772-792`）临界区覆盖"读尾→sha→追加"，另有尺寸复核防锁外写者；半行尾**收尾保留不 truncate**，链定义在可解析行子序列上。
3. `prev_sha` = 前一行 canonical JSON（`sort_keys=True, separators=(",",":"), ensure_ascii=False, default=str`）的 sha256 前 16 hex；与 `decision.py:402-417` 同 sort_keys/ensure_ascii/default=str、仅 separators 不同且理由明确；`state_digest` 则逐字节复用 402-417 不动。
4. 幂等：锁内全量扫描拒重复 decide；冲突抛 `DecisionArchiveDuplicate`（ValueError 系，`decision.py:138` 先例）→ exit 2 上抛人；**不落 duplicate-suppressed 行**；重放走 `duplicate="existing"`；10k 行全扫 ≈ 20–60 ms，节奏下无压力。
5. 字段矩阵（Q4）：`escalated_reason` 5 值、`outcome` 5 值、`by` 6 值全部落表并绑定 AC（AC-002/005/009/010/015）；authority-change 按 dp 展开为多行以保住 `<dp>:<trigger_id>` 文法（D2-S1）；settle 的 outcome=pending 登记行承载 lost/needs-clarification 显式登记（D2-S2）。
6. fold（Q5）：decide 基行不可变、outcome 取最后 settle（无则 pending）、override 存在即 true、坏行跳过计数、orphaned dp 行照常折叠（视图纯函数，注册表 join 留给报告层）。
7. 对账（Q6）：主键 `evidence_line + evidence_sha` 写时捕获（借 `decide_last_evidence` 的 `(行号, record)` 返回，`mw_common.py:1620-1642`），兜底 `(ts, dp)` + 平手裁决元组、同秒歧义报 ambiguous；state_digest 明确不参与两文件对账（传输行无 state，D-003）；对不上只报告不修复。

需人/PM 裁决的设计点：**D2-S0** 档案 fail-loud 与传输行 fail-soft 分道；**D2-S1** 签收/refresh 行按 dp 展开多行（偏离上游 Q4.4 单行 dps 列表）；**D2-S2** settle 允许 outcome=pending 登记行（note 必填）；**D2-S3** 规范形链 vs 逐字节链（本设计取规范形，理由见 Q2.5）。

## 残留与未验证

- 未实现未测：本文是设计交付，`decide_archive.py` 骨架未落码、未跑 pytest；`FoldResult` 字段名属实现期可微调面。
- 未验证：`open("a")` O_APPEND 在 Windows NTFS 下对无锁恶意写者的行原子性（接受为残留风险，靠锁 + 尺寸复核兜底，与全部先例同级）；`fsync` 在项目常见网络盘上的代价（已做失败忽略）。
- 依赖假设：`trigger_id` 不含 `":"`（task_key/`task_key#ckpt<N>`/ISO ts 三来源均满足，未见反例）；`decide_for` 出口已保证 dp ∈ 注册表（AC-011），档案层不复查。
- 哈希链 doctor 告警面化在 spec §11 列为推后项，本设计的 `chain_breaks/seq_breaks` 计数是其数据源，展示面未设计。

## 上下文来源

- spec：`.agenticdoc/mw-decision-substitution/spec.md` §6（164-192）、§8 AC（212-230）、§11（254）。
- 上游设计：`.agenticdoc/mw-decision-substitution/evidence/research/spec-authority-audit-model-20261016.md` Q2（116-173）/Q5（270-293）/Q6（294-306）/MVP（308-318）。
- Python 先例：`packages/multi-workers/decision.py` 74, 88-99, 101-103, 121-134, 138-145, 244, 402-417, 419-435, 873-893, 940-968；`packages/multi-workers/mw_common.py` 1620-1642, 2369-2390；`packages/multi-workers/mw.py` 772-792, 794-800, 845-878；`packages/multi-workers/autopilot/conductor.py` 7638-7647, 7650-7664, 7683-7703。
- TS 先例：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` 645-664；single-writer 契约措辞 `pm/triage-client.ts` 25-28（转引自上游 Q6）。
- 反证检索：`rg prev_sha` 于 `packages/` 零命中（2026-10-19，链为全新设计）。

Q-answered: 6/6
