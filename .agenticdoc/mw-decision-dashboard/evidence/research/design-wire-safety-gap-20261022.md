# D-RQ5 传输脱敏、上下文与锁的接线核查（design 合并稿 §4.4/§9 复核）

> 卡片 `tasks/D-RQ5-wire-safety.md`；spec AC-005/008/011/012/016；goal `.agenticdoc/goal.md`。
> 只读：未改代码/配置/档案，未发网络、未调真实模型、未执行测试。行号取自 2026-10-22 工作树；按符号定位优先。
> 前期证据已读：`design-wire-lifecycle-records-20261022.md`（RQ2）、`design-dp-observation-contract-20261022.md`（RQ3）。本卡只补三项负空间，不重复调研。

## 1 结论

1. **捕获点只能是 `_http_post`，且必须拆开 `_decode_bytes(response.read())` 这一行**（`decision_backends.py:255`）：raw bytes 在该表达式内被替换解码后即丢失；HTTPError 分支 `exc.read()`（`:259-262`）是 4xx/5xx 正文（最可能带秘密）的唯一入口，合并稿 §9 完全没提。
2. **现有 `_redact` 不足以覆盖线上字节**（`decision.py:531`）：它只扫 env 中名以 `_API_KEY/_TOKEN/_KEY/_SECRET/_PASSWORD` 结尾且长度≥8 的值（`:518-528`）；而 timi key 的真实来源还有 `~/.pi/agent/auth.json` 的 `timi.key`（`decision_backends.py:169-192`）和 `cfg.extras["api_key"]`（`:791` `key = _cfg_get(cfg, "api_key") or resolve_timi_api_key()`），两者都不在 env ⇒ 原值会原样落盘。**必须把 `headers["Authorization"]` 的值（`decision_backends.py:573-576`）作为强制 secret 注入**，不能只靠名字启发式；`decision_book._check_secrets`（`decision_book.py:1016-1037`，`decision._redact(x)!=x` 判命中）继承同一盲点。
3. **sha 只能对"落盘后的文本"取，不能对含秘密原文取**；`raw_len` 语义必须拆成 `wire_len`（真实线上字节数）与 `stored_len`（落盘字节数）。既有 `state_digest = sha256(_encode_state(state))[:16]`（`decision_points.py:2723-2725`）**不是**请求字节的哈希：线上 body 是 `json.dumps({"model","state","questions"}, ensure_ascii=False)`（`decision_backends.py:612-624`），`_encode_state` 是 `sort_keys=True` 的 state-only 规范化（`decision.py:572-590`），而且 `questions` 还带 registry instructions。`decide_archive.state_digest` 的 docstring（`decide_archive.py:261-266`）"produces the exact bytes that are sent" 是**错误陈述**，必须改叙述而不是复用它做字节证明。
4. **call_id 必须在逻辑调用处产生，`_http_post` 只发号 `attempt_index`**。RQ2 结论 3（"call_id + attempt_index 必须在 `_http_post` 内生成"）与它自己的 §2/§4（call_id = 一次 `DecisionClient.decide`）自相矛盾；按前者实现会让 `calls` 退化成 POST 计数，直接破坏 AC-012 的 calls/attempts/decisions 三列。**结构上让 `_http_post` 无法造 call_id**：它只从 ContextVar 读 `CallState`，读不到就不写账。
5. **contextvar 是唯一可行 seam，不是"设计口味"**：`test_decide_backends.py:66` 的桩是 `__call__(self, url, headers, payload, timeout_s)`（`:81` monkeypatch），给 `_http_post` 加第 5 个参数会直接 TypeError 打爆既有套件；因此 scope 只能经显式对象 + ContextVar 传递。合并稿 §9 "不依靠线程默认contextvar传播" 作为**语义要求**正确，作为**实现描述**不可执行，须改写为"显式 scope 对象由调用方创建，ContextVar 仅作进程内传递，默认 None ⇒ 零写账"。
6. **锁的"约100s"是错的**：`acquire_lock(lock, retries=20, base_delay=0.05)`（`mw_common.py:2388-2401`）在第一次 FileExistsError 后按 `0.05*2**attempt` 睡 attempt=0..19，合计 `0.05*(2**20-1)=52,428.75s≈14.6h`，且**没有 stale lock 判定、没有 deadline**。任何走默认参数的采集路径会把决策卡死数小时；生产档案路径 `decide_archive.py:650` 也用默认值。≤250ms 只能靠显式参数：`retries=5, base_delay=0.008` ⇒ 睡眠和 `0.008*31=0.248s`；但 Windows 默认计时器粒度 15.6ms，5 次 sleep 实测可超 250ms（+~78ms），所以硬保证需要给 `acquire_lock` 加可选 `deadline_s`（默认 None 保持现状与 TS 协议不变）。
7. **短写必须用无缓冲二进制写 + 计数循环 + fsync**：现有 `path.open("a")` 文本缓冲写，`fh.write()` 常返回全量而在 close/flush 才抛错，且 `except Exception: return`（`decision.py:1254-1256`）把失败彻底吞掉——既有 `_append_evidence` 是"静默 best-effort"，与 AC-016 "采集失败均有明确标记" 冲突。半行处理不要截断，复用 `decide_archive._repair_tail_if_dangling`（`:556-582`）的"补 `\n` 不删字节"语义。
8. **测试 scope 的真实泄漏点是 triage 旁账，不是 archive**：`decide_for(archive=False)` 只跳过 `append_decide`（`decision_points.py:2137-2140`），但 `decision_points.py:2442` 自建的 `DecisionClient(cfg, backend, project_root=project)` 没传 `evidence_path`，`_emit` 仍会 append 到生产 `.agenticdoc/_autopilot/triage-decisions.jsonl`（`decision.py:109,1210,1225`）⇒ VC-008 "生产triage字节不变" 必红。修法不需要新 API：测试路径传 `client=DecisionClient(..., evidence_path=<test>)`（ctor 已支持，`:823`）。
9. 结论：合并稿的**方向正确，接线不可实施/有漏**。按 §3-§5 的最小增量（`decision_wire.py` 新模块 + `_http_post` 内两处 hook + `decide`/`decide_for` 各一处 scope + 一个可选 `deadline_s`）可以在不改 `_http_post` 签名、不改 respond dict 键集、不改档案/签收的前提下落地。

## 2 真实函数链（path:line）

| 环节 | 位置 | 事实 |
|---|---|---|
| 请求字节 | `decision_backends.py:248` | `data = json.dumps(payload, ensure_ascii=False).encode()`，即 `Request(data=...)` 实际发送体；唯一可用的"原文" |
| 响应字节 | `:255` / `:259-262` | 成功分支 raw 只作为 `_decode_bytes(...)` 的实参存在；HTTPError 分支另有 `exc.read()`，`OSError` 时 `body=""`，与"空 body"不可区分 |
| 解码 | `:232-233` | `errors="replace"` ⇒ 非 UTF-8 不可逆、且当前无任何标记 |
| 后端重试 | `:720-758` | `retry-after` 存在时后端自行再 POST（`:749-752`），`max_retries` 封顶；一次逻辑调用 → 1..N 次 POST |
| 客户端重试 | `decision.py:829,929-1014` | `attempts += 1`（`:935` 附近）只数客户端轮次；backoff/预算耗尽路径不产生 POST |
| 响应出口 | `decision.py:1182-1211` | `_emit` 是唯一返回点（约 9 处调用），既有 `attempts/latency_ms/reason/transport/model`，无 call/attempt 级 ID |
| 证据旁账 | `decision.py:1227-1256` | 静默 best-effort；路径 `_evidence_file()`（`:1213-1225`） |
| 决策级 | `decision_points.py:2278-2498` | `decision_id` 在 `:2328` 就绪；`:2443` 调 `client.decide`；`:2137` `_maybe_archive` |
| 决策结果 | `decision_points.py:2221-2236` | `_outcome` 单点构造 `DecisionOutcome`（含 `archived/replayed/state_digest/truncated`） |
| 锁 | `mw_common.py:2388-2407` | `O_CREAT\|O_EXCL`，指数睡眠，无 deadline、无 stale 判定；`release_lock` 无 owner 校验 |

## 3 脱敏 / 限长 / sha / raw_len（最小可实现方案）

### 3.1 secret 集合（按优先级，注入而非猜测）
`S = [headers.get("Authorization")] + cfg.extras.api_key + resolve_timi_api_key() + _credential_values()`，去空、去重、按长度降序；长度 < 6 的值只做精确子串替换、不进尾部 scrub。`_redact` 的两条正则（`Bearer …`、`sk-…`，`decision.py:514-515`）保留为第二层。`decision_wire` 只 import stdlib + `mw_common`（取锁），redact 逻辑由 `decision.py` 以 `scope.redact` 可调用对象注入（避免 `decision → decision_wire → decision` 环）。

### 3.2 采集与脱敏（顺序不可换）
1. `raw` 已由 `_http_post` 持有；采集切片 `head = raw[:head_cap]`，`head_cap = seg_cap + 4KiB = 28KiB`，`read_capped = len(raw) > head_cap`；`wire_len = len(raw)`（解析仍用全量 `raw`，不改解析语义）。
2. 解码：先 `raw.decode("utf-8")` 严格；失败 ⇒ `raw.decode("latin-1")`（1 byte↔1 char 无损），`encoding="latin-1"`, `decode_errors=True`。**禁止**用 `errors="replace"` 做落盘表示（会永久丢字节）。
3. 脱敏：在**完整** head 文本上做 `str.replace`，再跑两条正则；`redactions = 命中次数`（含精确值与正则）。保持其余文本逐字不变——不重序列化 JSON，脱敏后不再是合法 JSON 是允许的，用 `redacted=True` 标注。
4. 尾部部分秘密清洗（仅 `read_capped=True` 时）：若文本尾是任一 secret 的真前缀（k=1..len-1，尾部窗口 64 字节），截掉该前缀，`boundary_scrubbed=True`。这是"先脱敏后限长"的真实漏洞点：读切片可能把一个秘密切成前缀，`replace` 就再也匹配不上。
5. 限长：按 `encoding` 编码后逐字符收缩到最大前缀使 `len(text.encode(enc)) <= seg_cap`（UTF-8 最多退 3 字节），`truncated = (len(enc(text))>seg_cap)`。
6. sha：`captured_redacted_sha256 = sha256(落盘文本.encode(enc)).hexdigest()`；`stored_len = len(落盘字节)`。**永不**输出 `sha256(raw)` / `sha256(data)`。

字段命名（替换合并稿含糊的 "len、sha、raw_len"）：
`wire_len`(线上字节数) / `stored_len` / `captured_redacted_sha256` / `redactions`(int) / `truncated` / `read_capped` / `boundary_scrubbed` / `decode_errors` / `encoding∈{utf-8,latin-1}` / `byte_exact = (not redactions and not truncated and not read_capped and not decode_errors)`。
`byte_exact` 是诚实性开关：只有它为 true 才允许说"落盘即线上原文"；否则 VC-016 只能比"服务端收到的字节 == 脱敏后应得文本"，不能比 sha。

### 3.3 64KiB 行界（序列化后判定，不是文本段判定）
1. 文本段先按 3.2 收到 `seg_cap=24KiB`，元字段各自硬上限（url_path 512B、content_type 128B、error_class 64B、model 128B）。
2. `line = json.dumps(row, ensure_ascii=False, separators=(",",":")) + "\n"`，按 UTF-8 字节测长。转义会膨胀（`\\`、控制字符），所以**不能**用 24+24<64 推断安全。
3. 若 `len(line) > line_cap=64KiB`：最大文本字段按 25% 递减重序列化，最多 8 轮，`truncated=True`；仍超 ⇒ 丢文本字段（`text_omitted=True`）只留元数据；仍超（元数据上限保证不会）⇒ 写一行最小 `capture-failed`。
4. 读侧单行上限独立：`reader_line_cap=1MiB`，超限行跳到下一个 `\n` 并计 `oversized_line`，不解析、不崩溃。

## 4 call / attempt / context 接线

### 4.1 两级 scope（显式对象 + ContextVar 仅作传递）
```
decision_wire.WireScope:  sink(Path|None), scope_kind("production"|"test"), evidence_path(Path|None),
                          decision_id, dp, key, task_key, origin, lock_path, caps, fail_closed,
                          submission_id, redact(callable), errors[]
decision_wire.CallState:  call_id(uuid4.hex), attempt_index:int, attempts_started[]
_CALL:  ContextVar[CallState|None] = None      # 只有 DecisionClient.decide 能 set
_SCOPE: ContextVar[WireScope|None]  = None     # decide_for / 测试提交服务 set
```
- `_http_post` 只读 `_CALL`；`_CALL is None` ⇒ **零写账**（`probe_matrix:852` 与全部既有单测天然不受影响，行为字节不变）。它**没有**造 call_id 的代码路径。
- `DecisionClient.decide`：入口 `state = CallState(new call_id)`；`_SCOPE is None` 时自建 production scope（sink 默认 `.agenticdoc/_autopilot/decisions-wire.jsonl`），`with use(...)` 包裹全函数，`finally` `token.reset()`；`_emit` 落 `call-end`（`attempts` = 客户端轮次、`wire_attempts = len(state.attempts_started)`、`zero_call = wire_attempts==0`）。新增 keyword-only `record_scope: WireScope|None = None`（不传即现行为）；测试路径用它显式绑定。
- `decide_for`：`:2328` 后建/接 `WireScope(decision_id=...)`，`with use(scope)` 包住 function body（不逐个改 ~10 处 `_outcome` 调用），`_outcome`（`:2221`）从 `current_scope()` 落 `decision-end`（`call_id = 最近一次 CallState.call_id` 由 scope 记下，冷门零调用路径为 null）。`archive=False` 时 `decision-end.archive=skipped` 是既有事实透传，不是新状态。
- 线程：ContextVar 是 per-thread，`ThreadPoolExecutor` **不**复制调用方 context ⇒ 监控服务必须在 worker 函数**内部** `with wire.use(scope)`，或在提交时把 scope 作为参数传入；不能依赖提交线程已 set 的 scope。这条要写成实施注意 + 单测断言（见 VC-R8）。
- 嵌套：无生产嵌套；`CallState` 每层 new + `reset`，`attempt_index` 归属 CallState 而非模块计数，嵌套也不会串号。

### 4.2 关联与零网络（AC-012）
- `calls = count(distinct call_id)`；`attempts = count(attempt-start)`；`decisions = count(distinct decision_id 且有决策级记录)`。三者由 writer 的字段决定，读侧不推算。
- `decide_for` step2 disabled / step4 未配置 / step5 缺字段 / step6 超预算：**零 attempts**，只有 `decision-end`（`call_id` 可能为 null，视是否走到 client）；UI 必须显示"零 HTTP"，不得因 `mode/available` 推断。
- 客户端 backoff 轮次之间没有 HTTP：只影响 `call-end.attempts`，不产生 attempt 行。

### 4.3 writer / reader 对应
| 字段 | 唯一写者 | 读者 | 缺失时 |
|---|---|---|---|
| `call_id` | `DecisionClient.decide` | monitor 详情/计数 | 缺失=采集前历史，显示"未记录" |
| `attempt_index` | `_http_post`（读 CallState 自增） | AC-012 attempt 计数 | 缺失=未发送或被 kill |
| `request_*` | `_http_post`（`data`） | 详情"实际请求" | 无 start 行=发送前终止 |
| `response_*`/`status` | `_http_post`（含 HTTPError/read 异常） | 详情"实际返回" | 有 start 无 end="已开始发送，未记录到响应"（**不能说"上游未收到"**） |
| `wire_attempts/attempts` | `_emit` / `_http_post` | 调用计数 | null 不按 1 回填 |
| `decision_id/archive/state_digest` | `_outcome` | 决策↔调用 join | 无决策行=`call-only` |
| `capture_status` | 由该事件所有行的状态归并 | UI 标记 | 行级 `failed` 优先于 `ok` |

`capture_status ∈ ok|partial|failed`：`ok` = 行已落且 `byte_exact`；`partial` = 行已落但 `redactions>0 / truncated / decode_errors / read_capped`（安全但非全保真）；`failed` = 写行失败/超锁/序列化失败/无 scope 需采而未采。**不放进 `DecisionClient.decide` 的返回 dict**：`_RESPONSE_FIELDS`（`decision.py:224-233`）键集被 `test_decide.py:188` 逐键断言，加键即破；`capture_status` 只进 wire 行、monitor HTTP 信封和 `client.last_capture_status` 属性。

## 5 锁、短写与错误语义

### 5.1 ≤250ms 锁预算（复用现有 API）
- `append_line` 在锁外完成序列化与限长；只把 open/write/fsync 放进临界区（锁内零网络，保持合并稿约束）。
- 调用 `mw_common.acquire_lock(scope.lock_path, retries=5, base_delay=0.008)`：睡眠和 0.248s，6 次尝试。默认参数（14.6h）**禁止**用于采集路径。
- 硬保证补齐（1 处小改，向后兼容）：`acquire_lock(..., deadline_s: float|None = None)`，循环内 `remaining = deadline - (monotonic()-t0)`，`remaining<=0 ⇒ raise`，`sleep(min(delay, remaining))`；TS 侧不调用该函数，协议/文件格式不变，故 parity 不破。`fsync` 不在 250ms 承诺内（合并稿已声明）。
- 失败语义：`acquire` 失败 ⇒ `write_row` 返回 `"failed"`，记 `error_class=lock-timeout`；**绝不 unlink 疑似残留锁**（`release_lock` 无 owner 校验，`:2403-2407`，只能在 acquire 成功后调用一次；建议把 acquire 结果布尔化，杜绝 finally 里误删他人锁）。UI 提示"可能存在崩溃残留锁"，由人处理。
- 并发：同一 key 下多 worker 进程各自决策 ⇒ 同一 production sink ⇒ 同一锁；锁内只有一次 ≤64KiB 写，理论尾延迟 ~ms。

### 5.2 追加与短写
- `fd = os.open(path, O_WRONLY|O_CREAT|O_APPEND)`；`view=memoryview(line.encode())`；`while view: n=os.write(fd,view); n<=0 ⇒ OSError; view=view[n:]`；`os.fsync(fd)`；`os.close(fd)`。无缓冲 ⇒ 短写当场可见，不推迟到 close。
- 写前（锁内）"补 `\n` 不删字节"：复用 `_repair_tail_if_dangling` 语义（`decide_archive.py:556-582`），避免自己的半行被下一行粘成长行并污染 JSON 解析。
- 崩溃残行：`attempt-start` 已落、`attempt-end` 未落 ⇒ 读侧显示 unfinished；这是设计要的"无法撤销在途请求"事实。

### 5.3 读侧（monitor）
- 无锁增量读：`seek(cursor)` → 64KiB chunk → 只消费以 `\n` 结尾的行，未终结尾段留在 `pending`（计 `incomplete_tail`，不解析、不报错）；`size < cursor` ⇒ 视为轮转，重置 0 并计 `rotated`。
- 每行：`len>1MiB ⇒ oversized_line`；严格 UTF-8 失败 ⇒ `bad_utf8`；JSON 失败 ⇒ `bad_json`；`schema_version` 非 1 ⇒ `unknown_schema`。四类都只计数 + 跳过，UI 显示"记录损坏/未知版本"而不是伪造成功。

### 5.4 失败可见与零发送
- 采集（production）：`write_row` 永不抛；错误累积到 `scope.errors`，在 `call-end` 的 `capture_status=failed` 暴露，并**每逻辑调用最多一条告警**（防风暴），业务返回不变。
- 测试提交 `submission-start`：`fail_closed=True` ⇒ 写失败立刻返回 `outcome=record-failed`，**在 `decide_for` 之前返回 ⇒ 零 HTTP**。去重检查与 start 行必须在**同一把锁**内完成（check-then-append），不能只靠"1 个执行任务"的调度假设。
- `record-failed` 与"未发送"必须分列：start 成功但 `attempt-end` 失败 ⇒ "已发送，响应未记录"，不得反推为未发送/零费用。

## 6 合并 design 的错误与未验证项

| # | 位置 | 问题 | 修正 |
|---|---|---|---|
| E1 | §9 "研究默认约100s" | 实际 `0.05*(2^20-1)=14.6h`，且无 stale 判定（`mw_common.py:2388`；档案路径 `decide_archive.py:650` 同样默认） | 明确"默认不可用于采集"；给 (retries=5, base=0.008) + 可选 `deadline_s` |
| E2 | RQ2 结论 3 | "call_id + attempt_index 在 `_http_post` 内生成" 与 call_id=一次逻辑调用矛盾；会让 calls≡POST | call_id 由 client 产生，`_http_post` 只能自增 attempt_index |
| E3 | §9 "不依靠线程默认contextvar传播" | 作为实现描述不可执行：`_http_post` 4 参签名被 4 参桩 monkeypatch（`test_decide_backends.py:66,81`），加参即 TypeError | 显式 scope 对象 + ContextVar 传递；默认 None ⇒ 零写账 |
| E4 | §9 边界捕获 | 只提成功分支；漏 HTTPError 分支（`decision_backends.py:259-262`，4xx/5xx 正文最可能带秘密）与 `read()` 抛错 / `exc.read()` 抛 OSError 后 `body=""` 不可区分 | 三分支都落 attempt-end（`error_class=response-read`），空体不得当"空响应" |
| E5 | §4.4 "sha" vs §9 `captured_redacted_sha256` | 命名不统一；且 `state_digest`（`decision_points.py:2723`，16 hex）被当成"发送字节"证据（`decide_archive.py:261-266` docstring 错误） | 只有 `captured_redacted_sha256`；`state_digest` 仅作档案 join 键，禁作线上字节证明 |
| E6 | §9 "每段24KiB/总64KiB" | 无序列化后测长；转义膨胀可越界 | 序列化后按字节测长 + 确定性收缩循环（§3.3） |
| E7 | §9 "先完整脱敏再截断" | 正确但漏两处：读切片可把秘密切成前缀而 `replace` 匹配不上；`errors="replace"` 丢字节且无标记 | 尾部前缀清洗 + latin-1 无损视图 + `decode_errors` |
| E8 | §4.4 `capture_status` 但 §9 无通道 | 返回 dict 键集被 `test_decide.py:188` 逐键断言，加键即破；`_append_evidence` 静默吞异常（`decision.py:1254`） | `capture_status` 只进 wire 行/HTTP 信封/`last_capture_status`；采集失败必须可见 |
| E9 | §9 "测试scope显式绑定client与observer" | 真正泄漏点未点名：`decide_for` 自建 client 不传 `evidence_path`（`decision_points.py:2442`）⇒ 观察仍写生产 triage（`decision.py:109,1210`）；`archive=False` 只挡档案（`:2137-2140`） | 测试路径传 `DecisionClient(evidence_path=<test>)`（既有 ctor），scope 带 `evidence_path` |
| E10 | §4.4 "pre-send事件仅证明attempt-started" vs RQ2 §2 "留下'已发出'的事实" | attempt-start 写在 urlopen 之前，不能证明已发出 | 统一措辞：attempt-start 只证"准备发送"；有 end/状态才证"收到响应"；无 end = 未知，不得断言未收到/未计费 |
| E11 | §4.4 "event_id/scope/submission_id" 与 RQ3 test record 的 `call_id`（"每次实际发送唯一"） | 同名异义：RQ3 把 call_id 当"每次发送"，与 RQ2 的逻辑调用冲突 | 测试记录：`submission_id` 分组 + `(call_id, attempt_index)` 标识单次发送；按 RQ3 自己的"冲突以 RQ2 为准"收敛 |

未验证（本卡未跑）：Windows 上 `O_APPEND`+锁的实测尾延迟与 `fsync` 抖动；`fsync` 在 NTFS 的实际成本；`response.read()` 全量读的峰值内存（现状已全量读，采集切片不改变）；`usage` 是否真出现在 `/v1/decisions` 响应正文。

## 7 VC（可执行判据，当前未执行）

局部真实 HTTP：stdlib `http.server` 绑 `127.0.0.1:0`，`cfg.extras={"base_url": ..., "api_key": "test-not-real-key-000"}`，wire/证据路径落 `tmp_path`，零外网零付费。

- VC-R1 字节保真：服务端 `rfile.read(Content-Length)` 与 attempt-start 文本逐字节相等（`redactions==0` 时），`byte_exact==true`；`captured_redacted_sha256 == sha256(落盘文本)`。
- VC-R2 attempt≠call：429+`retry-after: 0`、`max_retries=1` ⇒ 同 `call_id` 两条 attempt（index 1,2）、`call-end.attempts==1 && wire_attempts==2`、`calls==1`。
- VC-R3 非 UTF-8：响应体 `b"\xff\xfe{\"a\":"`+… ⇒ `decode_errors==true, encoding=="latin-1"`，落盘文本按 latin-1 回编码 == 原字节（逐字节），既有解析仍走 `errors="replace"` 不变。
- VC-R4 秘密脱敏：`api_key` 同时出现在请求 state 与响应 body（且**不在 env**）⇒ 文件内原值出现 0 次、`redactions>=2`、`Authorization` 值 0 次（只存 `header_names`）。
- VC-R5 边界：200KiB 响应 ⇒ `wire_len==200KiB`、`read_capped&&truncated`、`stored_len<=24KiB`、整行 `<=64KiB`；把秘密放在 `head_cap` 附近 ⇒ 落盘尾部无该 secret 的 ≥6 字节前缀（`boundary_scrubbed==true`）。
- VC-R6 锁预算：外部先占锁 ⇒ 单次 attempt 总等待 ≤250ms（±计时粒度）、`capture_status==failed`、`error_class=lock-timeout`、决策 `available` 不变、外部锁文件仍存在（`unlink` 次数 0）。
- VC-R7 零发送：注入 `submission-start` 写失败 ⇒ 服务端请求计数 0、`outcome=record-failed`。
- VC-R8 多进程/线程隔离：进程 A 跑生产 `mw decide run`、进程 B 跑测试提交 ⇒ 两文件互不出现对方行，生产 triage/decisions/signoff 字节与 `collect().rows_sha256` 不变；同进程内 `ThreadPoolExecutor` 在提交线程 set scope、worker 内不 set ⇒ 断言**无**行写入（证"不靠继承"），worker 内 set ⇒ 有行（证正确接线）。
- VC-R9 无 scope 静默：`probe_matrix` 与既有 `test_decide_backends` 桩路径 ⇒ 零行、零新文件，`_http_post` 签名不变。
- VC-R10 读侧健壮：手工拼接"完整行 + 半行"、>1MiB 行、未知 `schema_version` ⇒ `incomplete_tail=1 / oversized_line=1 / unknown_schema=1`，无异常。

## 8 未覆盖

- 未测 Windows 上 `os.fsync` 对 64KiB 行的实际耗时，以及 antivirus 扫描下的写延迟（合并稿已声明 fsync 不在 250ms 内）。
- 未验证 `retry-after` 为负/超大值对锁预算与 attempt 计数的影响（`_retry_after_s:354` 未读）。
- 未覆盖 monitor HTTP 层如何把 `capture_status` 映射到页面文案（属 UI 卡）。
- 未覆盖 `decisions-wire.jsonl` 的跨 key 归属与 dual-root（与 RQ2 残留同一处）。
- 未覆盖 `_redact` 对高熵自定义密钥（非 `sk-`、非 env 命名）的通用检测；本方案靠"Authorization 值 + 配置值"闭集覆盖，未做熵/格式泛化。
- 未执行：任何测试/构建/真实调用；以上 VC 均为待执行判据，不得声称已通过。
