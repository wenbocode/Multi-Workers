# RQ4：`decide_signoff.collect()` 判据与档案实测（2026-10-22）

研究问题：把"该 key 是否需要签收"的判据从 `decision-scope.md` 换成"该 key 档案里有 >=1 条真实 jev 决策行"，
这个判据能否直接当 done 门禁条件（足够便宜、不误判）。

实测环境：`H:\git\Multi-Workers`，`.agenticdoc/_autopilot/decisions.jsonl` 存在（39528 B / 44 行），
`.mw/decide.json` = `{"enabled": true, "transport": "timi-decisions", "model": "jev-latest", "signoff": "auto"}`。
本机 `bash` 工具解析到 PowerShell，所有命令形如 `@'<python>'@ | python -`（PowerShell here-string 管道给 python，
避免 PS 5.1 把 `-c` 里的双引号吃掉）。

---

## 1. `collect()` 的精确语义

入口 `packages/multi-workers/decide_signoff.py:287` `collect(project_dir, key) -> SignoffFacts`。

**读哪个文件**

- `decide_signoff.py:164-167` `_archive_path()`：`(root)/.agenticdoc/_autopilot/decisions.jsonl`。
  实现是拿 `decide_archive.ARCHIVE_RELATIVE_PATH`（`packages/multi-workers/decide_archive.py:39`，
  值 `.agenticdoc/_autopilot/decisions.jsonl`）去掉首段 `.agenticdoc` 再拼回解析出的 root。
  root 归一化在 `decide_signoff.py:145-152` `_agenticdoc_root()`：传项目根 / `.agenticdoc` / key 目录都可。
  `advance_phase.py:313` 传的是 `key_dir.parent`（= `.agenticdoc`），命中第二种。
- `decide_signoff.py:297` `all_rows = [row for _lineno, row in decide_archive.iter_rows(archive)]`。
  `decide_archive.py:770-795` `iter_rows()`：整文件 `read_text(encoding="utf-8")` → `splitlines()` →
  逐行 `json.loads` → 空行 / 非法 JSON（`ValueError`）/ 非 dict 三种静默跳过，yield `(物理行号, row)`。
- 档案不存在：`decide_archive.py:776-778` 捕获 `FileNotFoundError` 后 `return`（生成器立即结束），
  **不抛错**，等价于"0 行"。其它 `OSError` 包成 `DecisionArchiveError`（`decide_archive.py:779-780`，fail-loud）。
- 另外读 `<control root>/.mw/decide-points.json`（`decide_signoff.py:270-285` `_p0_open()`），只为 `p0_open` 字段，
  与"行数"判据无关。

**哪些行算"该 key 的决策行"**（三个合取条件，`decide_signoff.py:298-308`）

1. `decide_signoff.py:301` `row.get("kind") == "decide"`
   —— 只有 `decide`；`settle` / `override` / `authority-change` 一律不计（`decide_archive.py:46` 是全集）。
2. `decide_signoff.py:302` `_row_matches_key(row, key)`，定义在 `decide_signoff.py:223-230`：
   - `:225-226` `row.get("key") == key` → 命中（列相等优先）；
   - `:227-229` 否则取 `row["decision_id"]`，`if not key or not isinstance(decision_id, str): return False`
     —— 空 key 时后缀分支被禁用；
   - `:230` `decision_id.endswith(":" + key)` → 命中（**`:key` 后缀规则，仅当 key 非空且 decision_id 是 str**）。
   - 大小写敏感；`key` 列缺失（`None`）不会让判定失败，会继续走后缀分支。
3. `decide_signoff.py:307` `row.get("dp") != SIGNOFF_DP_ID`
   —— `SIGNOFF_DP_ID = "dp25-signoff-conclusion"`（`decide_signoff.py:98`），
   **dp25 自己的决策行被排除**（`decide_signoff.py:303-306` 注释即 D-067 理由：签名覆盖被签的决策，
   把产生签名的建议也算进去等于让 `continue` 自我背书，且每次重签都会移动 `rows_sha256`）。
   注意它判的是 `dp` **列**，不是 `decision_id` 前缀。

**命中之后**

- `decide_signoff.py:309-311` 按 `seq`（int）排序（只影响 `rows_sha256`，不影响行数）。
- `:312` 投影到 `_ROW_FIELDS`（`decide_signoff.py:107-118`，10 列快照）。
- `:314-317` 统计 `engines`（`transport/model/confidence_source` 三元组，`TRUE_ENGINE = ("timi-decisions","jev-latest","api")`，`decide_signoff.py:85`）。
- `:318` + `:270-285` `p0_open` / `p0_source`。
- `:319-` 组装 `SignoffFacts`，其中 `sha256 = rows_sha256(snapshots)`（`decide_signoff.py:243-246`，对快照列表做 canonical JSON 的 sha256），
  `chain_ok = _chain_ok(all_rows)`（`decide_signoff.py:248-267`，**遍历全部行**，与 key 无关）。
- `key` 归一化：`decide_signoff.py:295` `key = key or ""`。

**门禁侧谁消费它**：`advance_phase.py:271` `_decision_signoff_problems()` → `:313` `module.collect(key_dir.parent, key_dir.name)`，
`:314-325` 比对 `counted_rows:` / `rows_sha256:` 机器行，`:326-328` `conclusion=continue` 时跑 `module.verdict()`。
`:420-426` 的 `decision_signoff` check_type 只在 `key_dir/decision-scope.md` 存在时才被调用
（`full_path = key_dir / DECISION_SCOPE_MARKER`，`DECISION_SCOPE_MARKER` 见 `advance_phase.py:37`）。

---

## 2. 真实档案统计与耗时

命令（PowerShell，here-string 管道）：

```powershell
cd 'H:\git\Multi-Workers'; @'
import json,pathlib,collections,statistics
p=pathlib.Path(".agenticdoc/_autopilot/decisions.jsonl")
data=p.read_bytes(); lines=data.decode("utf-8").splitlines()
rows=[json.loads(l) for l in lines if l.strip()]
print("bytes:",len(data),"physical_lines:",len(lines),"parsed:",len(rows))
print("kinds:",dict(collections.Counter(r.get("kind") for r in rows)))
dec=[r for r in rows if r.get("kind")=="decide"]
print("decide_by_key:",collections.Counter(r.get("key") for r in dec).most_common(10))
print("all_by_key:",collections.Counter(r.get("key") for r in rows).most_common(10))
by=collections.defaultdict(list)
for l,r in zip(lines,rows): by[r.get("kind")].append(len(l.encode("utf-8")))
for k,v in by.items(): print(k,len(v),sum(v),round(statistics.mean(v),1))
'@ | python -
```

真实输出：

```
bytes: 39528 physical_lines: 44 parsed: 44
kinds: {'authority-change': 29, 'decide': 10, 'settle': 5}
decide_by_key: [('mw-decision-substitution', 4), ('mw-usage-monitor', 2), ('mw-signoff-per-key', 2),
                ('claim-driven-review', 1), ('mw-decision-dashboard', 1)]
all_by_key:    [('', 25), ('mw-decision-substitution', 11), ('mw-usage-monitor', 3),
                ('mw-signoff-per-key', 3), ('claim-driven-review', 1), ('mw-decision-dashboard', 1)]
authority-change 29 24941 860.0
decide           10 10190 1019.0
settle            5  4353 870.6
```

- 总行数 **44**（全部可解析，0 不可解析；无空行）；`kind=decide` **10** 行。
- 按 key 分组（decide 行）前 10：`mw-decision-substitution` 4、`mw-usage-monitor` 2、`mw-signoff-per-key` 2、
  `claim-driven-review` 1、`mw-decision-dashboard` 1（共 5 个 key，唯一 key 数 5）。
- 按 key 分组（全部 kind）前 10：`""` 25（全部是 `refresh` 型 authority-change）、`mw-decision-substitution` 11、
  `mw-usage-monitor` 3、`mw-signoff-per-key` 3、其余各 1。
- 平均每行字节数：全档 **897.4 B**（39484 内容字节 + 44 换行 = 39528）；
  分 kind：`decide` 1019.0 B、`authority-change` 860.0 B、`settle` 870.6 B。

`collect()` 实测（含 import，单进程内重复 7 次）：

```powershell
@'
import sys,time,pathlib,statistics
sys.path.insert(0,str(pathlib.Path("packages/multi-workers").resolve()))
import decide_signoff
root=pathlib.Path(".").resolve(); ts=[]
for _ in range(7):
    t0=time.perf_counter(); decide_signoff.collect(root,"mw-decision-substitution"); ts.append((time.perf_counter()-t0)*1000)
print([round(x,3) for x in ts],"median:",round(statistics.median(ts),3))
'@ | python -
```

```
[0.629, 0.618, 0.609, 0.609, 0.768, 0.737, 1.214] median: 0.629
```

- 单次 `collect()` 中位数 **0.63 ms**（44 行 / 39.5 KB）。
- 一次性 import 成本另计：裸 `python -c pass` 47 ms → `import decide_signoff` 117 ms（**+70 ms**，进程内只付一次）。
- 规模外推（合成行，parse + 过滤 + `_chain_ok` 三段分别计时，单位 ms）：

| N 行 | parse | filter | `_chain_ok`（全档 json+sha256） | 合计 |
| ---: | ---: | ---: | ---: | ---: |
| 44 | 0.25 | 0.01 | 0.41 | 0.67 |
| 440 | 1.90 | 0.08 | 2.84 | 4.81 |
| 4400 | 23.41 | 1.50 | 30.81 | 55.7 |
| 44000 | 230.05 | 15.97 | 302.07 | 548 |

线性、约 12.5 µs/行；`_chain_ok` 对**每一行**做一次 canonical json + sha256，占约一半。

- 全仓扫描成本（77 个 key 目录，逐 key 重扫）：

```
keys=77
minimal impl, per-key rescan: 18.6 ms total (0.24 ms/key)
authoritative collect(), per-key rescan: 51.0 ms total (0.66 ms/key)
single pass, build key->count map: 0.25 ms total
```

即：`collect()` 是 **O(keys × archive)**，没有索引。本仓库 77 key 全量重扫 51 ms（可忽略）；
4.4 万行时约 77 × 548 ms ≈ 42 s，必须改成"一次扫描建 `key -> count` map"（0.25 ms）。

`check_gate(key_dir, "done")` 现状基线（在进程内直接调用，未写 pm-state）：
77 个 key 共 123.8 ms（1.61 ms/key），其中只有 `mw-decision-substitution` 有 `decision-scope.md`。

---

## 3. "零行即跳过"的误判风险

### 3a. 档案文件不存在（新项目 / 没装 mw）

`iter_rows` 对 `FileNotFoundError` 静默返回 → `all_rows=[]` → `counted=[]`。实测（指向不存在的项目根）：

```
archive: Z:\nonexistent-project\.agenticdoc\_autopilot\decisions.jsonl
counted_rows: 0 n_available: 0 chain_ok: True
sha256: 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945   # = sha256("[]")
engines: {} p0_open: () p0_source: missing
verdict(continue): (False, ['N=0: no decide row for this key in the archive; run a real jev decision first, or sign narrow/revoke'])
```

关键风险：**"0 行"无法区分三种情况**——(i) 真的没有决策，(ii) 档案不存在（新项目 / 没装 mw），
(iii) 传错项目根（`_archive_path` 全相对 `project_dir`，且 `chain_ok` 空列表恒为 `True`）。
现在 `advance_phase.py:313` 传 `key_dir.parent`，只要 key 目录在 `.agenticdoc` 下就是对的；
但任何"把 0 行当跳过"的门禁都对 (ii)/(iii) 静默放行。空文件（0 字节）与缺文件不可区分（都 0 行）。
目录被当文件读 → `IsADirectoryError`（OSError）→ `DecisionArchiveError` fail-loud，不会静默 0 行。

### 3b. `key` 列缺失但 `decision_id` 以 `:<key>` 结尾

**算命中**（`decide_signoff.py:227-230`）。实测判定表：

```
got= True  key='k1'  row={'key':'k1','decision_id':'dp1:k1'}            # 列相等
got= True  key='k1'  row={'decision_id':'dp1:k1'}                       # 列缺失，后缀命中
got= False key='k1'  row={'decision_id':'dp1:k1:extra'}                 # 后缀不在末尾
got= True  key='k1'  row={'key':'','decision_id':'dp1:k1'}              # 列空串 → 落到后缀分支 → 命中
got= False key='k1'  row={'key':'K1'}                                   # 大小写敏感
got= False key='k1'  row={'key':None,'decision_id':None}                # 双空
```

风险：后缀规则对**短 key** 会过宽（key=`e` 会命中任何 `...:e`）。本档案上验证了所有
(行, key) 组合：**0 个跨 key 误命中**（5 个真实 key 均 >= 10 字符，且 decision_id 的 key 段后
总跟着 `@<ts>`，例如 `dp1-dispatch-type:signoff@mw-signoff-per-key@2026-10-21T17:01:31Z`，
并不会以 `:mw-signoff-per-key` 结尾 → 后缀规则对 dp25/authority-change 行实际不触发）。

### 3c. `kind` 不是 `decide` 的行（如 `authority-change`）

**不会误算**（`decide_signoff.py:301` 前置 and）。实测：

```
kind='decide'           counted=True
kind='override'         counted=False
kind='settle'           counted=False
kind='authority-change' counted=False
kind=None               counted=False
```

本档案 44 行里 **34 行对 `collect()` 不可见**（29 authority-change + 5 settle）。
注意 `_row_matches_key` 本身不看 kind（上表 `{'decision_id':'dp1:k1','kind':'authority-change'}` 也返回 True），
kind 过滤是 collect 的第二个条件，复刻时不能漏。

### 3d. `key` 为空字符串

- `decide_signoff.py:225` `if row.get("key") == key: return True` 先命中：
  `collect(root, "")` 会统计**所有 key 列为空串的 decide 行**（今天 0 行；空 key 的 25 行都是 authority-change）。
- `decide_signoff.py:228` `if not key …: return False`：空 key 时**禁用**后缀分支，
  否则 `endswith(":")` 会命中一切以冒号结尾的 decision_id。实测 `{'decision_id':'dp1:'}` + key `""` → False。
- 写入侧允许空 key：`decide_archive.py:395` 只要求 `isinstance(row.get("key"), str)`；
  `decision_points.Trigger.key` 默认 `""`（`decision_points.py:229`），`resolved_id()`（`:250-258`）
  在无 trigger_id 时依次回退 task_key → key → 时间戳。所以**"无 key 的 decide 行"是可表示的**，
  且它对任何真实 key 的 `collect()` 都不可见（见第 5 节）。

### 3e. 判据二选一的实测分歧（本档案的决定性风险）

| key | raw `kind=decide` 行 | 其中 dp25 | `collect().rows` |
| --- | ---: | ---: | ---: |
| mw-decision-substitution | 4 | 2 | **2** |
| mw-usage-monitor | 2 | 2 | **0** |
| mw-signoff-per-key | 2 | 2 | **0** |
| claim-driven-review | 1 | 0 | 1 |
| mw-decision-dashboard | 1 | 0 | 1 |

⇒ "`collect().rows == 0` 即跳过" 与 "raw jev 行 == 0 即跳过" 在本仓库 **5 个 key 中有 2 个结论相反**。
前者还会随每次签收**自我收缩**（dp25 行只会增加），是非单调判据；后者单调。
两个受影响的 key 现有 `sign-final.md` 都是 `counted_rows: 0`（`conclusion: narrow`，`signed_via: auto-decide`），
内容校验仍然通过 —— 说明现状下这两条 dp25 行正是"跑过签收流程"的证据本身。

---

## 4. 不导入 `decide_signoff` 的最小复刻实现

在 `advance_phase.py` 内加（只用 stdlib + 已 import 的 `json`/`Path`）：

```python
DECISIONS_REL = Path("_autopilot") / "decisions.jsonl"   # 相对 <key_dir>.parent (.agenticdoc)
SIGNOFF_DP_ID = "dp25-signoff-conclusion"

def _row_is_key(row: dict, key: str) -> bool:            # 复刻 decide_signoff.py:223-230
    if row.get("key") == key:
        return True
    if not key:                                          # 空 key 禁用后缀分支（:228）
        return False
    did = row.get("decision_id")
    return isinstance(did, str) and did.endswith(":" + key)

def _decide_row_count(agenticdoc_root: Path, key: str, *, exclude_signoff: bool = True) -> int:
    path = Path(agenticdoc_root) / DECISIONS_REL
    if not path.is_file():                               # 缺档 = 0 行（不抛）
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:                               # 非法 JSON 静默跳过（iter_rows 同）
            continue
        if not isinstance(row, dict):
            continue
        if row.get("kind") != "decide":                  # :301
            continue
        if exclude_signoff and row.get("dp") == SIGNOFF_DP_ID:   # :307
            continue
        if _row_is_key(row, key):                        # :302
            n += 1
    return n

def _requires_signoff(key_dir: Path) -> bool:
    """门禁判据：本 key 有 >=1 条 jev 决策行（含 dp25 行，保证单调）。"""
    return _decide_row_count(key_dir.parent, key_dir.name, exclude_signoff=False) > 0
```

**已验证等价**：对 81 个 key 字符串（77 个真实 key 目录 + `""` + 3 个边界值）比较
"最小实现的行集合" 与 `decide_signoff.collect().rows` 的 `seq` 集合 → **0 处不一致**。

**与权威实现的已知差异**

1. 不算 `chain_ok`（`decide_signoff.py:248-267` 遍历全部行）、不算 `p0_open`（`:270-285`）、不算 `sha256`
   → 复刻只能回答"有没有行/有几行"，**不能**复刻 `counted_rows:` / `rows_sha256:` 的内容校验。
   若判据只是决定"要不要跑签收校验"，够用；若还想替掉 sha 比对，必须用**完全相同的行集合**
   （dp25 排除 + `_ROW_FIELDS` 投影 + 按 seq 排序 + canonical JSON），否则合法签名会被判"篡改"。
2. 不做 `key` 归一化（`decide_signoff.py:295` `key or ""`）：`advance_phase` 传 `key_dir.name`，恒为 str，无差。
3. `_chain_ok` 之外的行为差异仅在异常面：`iter_rows` 用 `read_text(encoding="utf-8")`，非 UTF-8 字节抛
   `UnicodeDecodeError`（`ValueError` 子类，**两个实现都不捕获** → 都 fail-loud，一致）；
   但 `OSError`（非 FileNotFoundError）在 `iter_rows` 里被包成 `DecisionArchiveError`，复刻版会直接抛
   `OSError`。调用方必须把两者都当"失败即拦"，不能当"0 行放过"。
4. 复刻版每次调用重读全档（与 `iter_rows` 一样是整文件读），没有额外缓存；
   `decide_signoff.collect` 每次调用还多做一次全档 chain 重算（约 2 倍成本）。

---

## 5. 档案写入方：行里是否一定带 key

- **`kind=decide` 的唯一写入路径**：`decide_archive.append_decide()`（`decide_archive.py:953`）
  → `_base_row(...)` 里 `row["key"] = key`（`decide_archive.py:734`），
  `_validate_row` 只要求 `isinstance(key, str)`（`:395-396`，空串合法）。
  生产调用点只有一处：`decision_points._archive_decision()`（`decision_points.py:3804`），
  构造 `key=trigger.key`（`decision_points.py:3850`），写入器经 `_resolve_archive_writer()`
  （`decision_points.py:3790-3806`，懒 import + DI seam `ARCHIVE_WRITER:3782`）。
- **存在不带 key 的写入路径（结构性缺口）**：`Trigger.key` 默认 `""`（`decision_points.py:229`），
  `resolved_id()`（`:250-258`）回退链 `trigger_id → task_key → key → UTC 时间戳`。
  一个 `decide_for(dp, trigger)` 若既没有 `key` 也没有 `trigger_id`/`task_key`，
  会写出 `key=""` 且 `decision_id="<dp>:<timestamp>"` 的行 —— 该行**对任何真实 key 都不可见**，
  且后缀规则也救不回来（decision_id 里根本没有 key）。这是"零行即跳过"唯一的真误判源：
  行写进去了，判据仍说"这个 key 没有决策"。
  当前实测 10/10 decide 行 key 非空，且跨 key 后缀误命中为 0。
- `kind=settle`：`pm-orchestrator.ts:991` 用 `python -c "decide_archive.append_settle(...)"` 写，
  `dp` 由 decision_id 推导（`pm-orchestrator.ts:800` 注释）；key 由调用方给（`decide_archive.py:1091` 校验 str）。
  settle 行不是 decide 行 → 对判据无影响。
- `kind=authority-change`：`mw.py:1942-1967` `_dp_append_authority_change(key: str = "")` ——
  默认空 key 就是档案里 25 条 `key=""` refresh 行的来源（seq 1-24、39）；
  签收路径 `mw.py:4180` 带 `key=key` 且 `trigger_id=f"signoff@{key}@{ts}"`。

---

## 6. 换成"有 jev 行"后 `mw-decision-substitution` 是否变化

**不变。**

- 该 key 实际行数：`kind=decide` **4** 行（seq 25 `dp3-worker-clarify`、seq 26 `dp1-dispatch-type`、
  seq 34 与 seq 40 均 `dp25-signoff-conclusion`）；`collect()` 计数 **2**（dp25 两行被排除），
  `n_available=2`，两行引擎均为 `timi-decisions/jev-latest/api`。
- 它同时满足两个判据（`decision-scope.md` 存在 = True；jev 行 = 4 > 0），所以切换判据对它无行为变化；
  其 `evidence/review/sign-final.md`（`conclusion: narrow`、`counted_rows: 2`、
  `rows_sha256: eb447f1d44f6856008fe1767bf4bd37499b2262a266388b7b1ea8bff2dc71819`）与重算一致，
  `_decision_signoff_problems(key_dir)` 返回 `[]`（实测）。

**但其它 key 会变**（判据切换的真实影响面）：77 个 key 中

- 现在被内容校验覆盖：**1** 个（只有 `mw-decision-substitution` 有 `decision-scope.md`）。
- 换成"有 jev 行"后覆盖：**5** 个（+`mw-usage-monitor` 2 行、+`mw-signoff-per-key` 2 行、
  +`claim-driven-review` 1 行、+`mw-decision-dashboard` 1 行）。
- 这 4 个新增 key 里，`mw-usage-monitor` / `mw-signoff-per-key` 已有合法 `sign-final.md`（`counted_rows: 0`，narrow）
  → 内容校验通过；`claim-driven-review`（Phase=VERIFY）与 `mw-decision-dashboard`（Phase=EXECUTE）
  **没有** `sign-final.md`，且其 1 条 decide 行都是真 jev 行 → 切判据后它们从"不检查"变成"必须签收"。
- 重要前提：`done` 门禁里"存在 `evidence/review/sign-final.md`"和"含 `conclusion:` 机器行"这两条
  **本来就是无条件对所有 key 生效**的（`advance_phase.py:107-121`，例外只有 `.mw/decide.json` 的
  `signoff: "disable"`，见 `advance_phase.py:343`）。所以 `decision-scope.md` 只控制**内容重算**这一层；
  全仓 74 个 key 现在就会因"缺 sign-final.md"被拦（实测），切换判据只是多给上述 2 个 key 一行同样的 MISSING。

---

## 结论

1. 能当门禁，但判据必须取 **raw `kind=decide` 行数 > 0**（含 dp25 行），不能取 `collect().rows`：后者排除 dp25，会随每次签收自我收缩（本仓库 5 个 key 中 2 个 raw>0 而 counted=0）。
2. 成本可忽略：单次 `collect()` 中位数 0.63 ms/44 行；最小复刻 0.24 ms/key，77 key 全量 18.6 ms；但两者都是 O(keys×archive)，4.4 万行时逐 key 重扫约 42 s，应改为一次扫描建 map（0.25 ms）。
3. 主要误判源不是行数，而是"0 行"的三种成因不可区分（无决策 / 档案缺失 / 传错 root，且 `chain_ok` 空列表恒 True）：门禁必须区分"档案不存在"和"档案存在但无行"。
4. 复刻必须原样保留 `kind=="decide"`、`key` 列/`":"+key` 后缀（含 `not key` 守卫）、`dp != dp25` 三条件；漏掉空 key 守卫会让空 key 命中一切以冒号结尾的 id。
5. 切换会让 `claim-driven-review`、`mw-decision-dashboard` 新增"必须签收"（两者无 `sign-final.md`，现在就被无条件存在性规则拦住），属可接受的收紧但需显式裁定。
