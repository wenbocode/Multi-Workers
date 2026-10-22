# spec-gate-structure-20261022 — RQ2：`decision_signoff` 门禁结构（只读研究）

- key: `mw-signoff-decide-only` / 任务卡 `tasks/RQ2-gate-structure.md`
- 被分析对象（canonical）：`.agents/skills/agentic-task/scripts/advance_phase.py`
  - 38274 B, sha256 `4a7f341e806aadc6…`，与 `core/scripts/`、`claude/scripts/` 三份字节一致
  - AgenticTask clone HEAD `d0834ae`；`scripts/advance_phase.py` 工作区有未提交改动（FIX-P/FIX-Q 面）
- 交叉阅读：`packages/multi-workers/decide_signoff.py`、`decide_archive.py`、
  `test_decide_signoff.py`、`test_decide_sign_auto.py`、
  `.agents/skills/agentic-task/scripts/test_advance_phase.py`、`install.py`、`.gitignore`
- 方法：全文阅读 + 行号定位；另把"改法草案"打到 `%TEMP%` 的副本上实跑（未改动仓库任何文件），
  结果见 §3 末尾的行为矩阵。

---

## 1. `check_gate` 的规则循环：谁决定"这条规则是否执行"

### 1.1 循环骨架（`check_gate` = 行 332–443）

| 行 | 代码 | 语义 |
|---|---|---|
| 334 | `root = key_dir.parent` | `root` 即 `.agenticdoc`（不是项目根） |
| 335 | `rules = GATES.get(target, [])` | 每条规则是长度为 3 或 4 的 tuple |
| 337 | `for rule in rules:` | 顺序执行，**没有 early-exit**：所有规则都会跑到 |
| 338 | `path_pattern, check_type = rule[0], rule[1]` | 只有这两个位置在循环头被解包 |
| 339 | `full_path = key_dir / path_pattern` | 路径**永远相对 key 目录**；含 `*` 的模式在这里得不到展开（`Path("a/*").is_file()` 恒 False） |
| 343–344 | `if path_pattern == DECISION_SIGNOFF_REL and _decision_signoff_disabled(key_dir): continue` | 循环级短路：只对**字面等于** `evidence/review/sign-final.md` 的规则生效 |
| 443 | `return len(failures) == 0, failures` | 没有任何 warning 通道；`failures` 是纯字符串列表 |

### 1.2 分支表：`check_type` 是唯一的执行派发器

| 分支行 | check_type | 该规则的"是否执行"判据 | 不执行时的表现 |
|---|---|---|---|
| 346–354 | `file_min_bytes` | 无条件执行；先 `is_file()` 再比 `st_size` | — |
| 355–365 | `dir_has_files` | 无条件；`is_dir()` + `glob("*.md")` 计数 | — |
| 366–374 | `content_match` | 无条件；`is_file()` 后 `re.search(pattern, text)`，**不加 flags** | — |
| 375–392 | `spec_goal_alignment` | 条件：`_goal_established(root)` 才执行 | goal 未确立 → 静默跳过 |
| 393–404 | `spec_ac_numbered` | 无条件；数 `AC-\d{3}` 去重个数 | — |
| 405–410 | `glob_has_files` | 无条件；用 `key_dir.glob(path_pattern)`，**忽略 `full_path`** | — |
| 411–419 | `mermaid_valid` | 无条件；`is_file()` + `check_mermaid_file` 可用才校验 | mermaid 模块缺失 → 静默降级 |
| 420–426 | `decision_signoff` | **条件：`full_path.is_file()`**，即 key 目录存在 `decision-scope.md` | 标记缺失 → 整条检查不调用 |
| 428–441 | `memory_feedforward` | 条件：三份记忆文档任一 `_has_table_data` | 全空/不存在 → 静默跳过 |

关键事实（RQ2 的根因）：

1. `decision_signoff` 分支**从不读** `decision-scope.md` 的内容，只用 `is_file()` 当开关。标记文件是纯粹的触发位，本身没有语义。
2. 除 `decision_signoff` 外，没有任何分支因为"某个文件存在/不存在"而改变**自己是否被调用**（`spec_goal_alignment` / `memory_feedforward` 的条件是项目级状态，不是当前 key 的标记）。
3. 循环没有 `else` 兜底：`check_type` 拼错或新增名字但漏写分支 → 该规则永远不产生 failure（静默 no-op）。这是下面"加新 check_type"方案的主要缺点。

### 1.3 让 `decision_signoff` 无条件执行的最小写法

三个候选：

| 方案 | 改动量 | 是否影响其它规则 | 评价 |
|---|---|---|---|
| A. 哨兵 `path_pattern` + 去掉分支里的 `is_file()` 守卫（推荐） | 3 处 | 否 | 最少改动，语义直白；`check_type` 派发不变 |
| B. 保留 `path_pattern = DECISION_SIGNOFF_REL`，只去掉 `is_file()` 守卫 | 1 处 | 否（但把规则绑在一个它不读的文件路径上） | 更短，却让"规则名 = 被读文件"的假象留了下来；`343` 行的 disable 短路会继续作用于它（当前恰好是我们想要的行为，但属于隐式耦合） |
| C. 新增 check_type（如 `decision_signoff_unconditional`） | 2 处（`GATES` + 新分支）并须删旧分支 | 否 | 必须同时删旧分支，否则两条规则重复执行；没有收益，且受 §1.2 第 3 点（漏写分支即静默 no-op）影响 |

为什么 A 不会影响其它规则（可逐条核对 `path_pattern` 的全部消费点）：

- 消费点只有两个：行 339 拼 `full_path`、行 343 与 `DECISION_SIGNOFF_REL` 比较。空串哨兵既不等于 `evidence/review/sign-final.md`（不改变 disable 短路的作用对象），也不会被 `decision_signoff` 分支之外的任何代码使用。
- `key_dir / ""` 在 `pathlib` 下等于 `key_dir` 本身（目录），即使有人误加 `is_file()` 也只会恒 False，不会误判为通过。
- 另外两条签收规则（`glob_has_files` / `content_match`，行 108–121）继续使用 `DECISION_SIGNOFF_REL`，行 343 的 `signoff: disable` 短路对它们仍然生效 —— 行为不变。

可粘贴草案（行号为 canonical 当前行号）：

```python
# 行 34–37 区域：删掉 DECISION_SCOPE_MARKER（全文件仅行 37 定义、行 125 使用），
# 换成不读路径的占位哨兵。
DECISION_SIGNOFF_REL = "evidence/review/sign-final.md"
# `decision_signoff` 规则不读任何路径；空串只作占位，且刻意 != DECISION_SIGNOFF_REL，
# 以免与行 343 的 `signoff: disable` 短路比较产生隐式耦合。
DECISION_SIGNOFF_RULE_TARGET = ""
```

```python
# 行 124–133（GATES["done"] 的最后一条）：
        (
            DECISION_SIGNOFF_RULE_TARGET,
            "decision_signoff",
            None,
            "签收内容校验（无条件执行；适用性由检查函数判断：`signoff: disable` 或该 key "
            "无 kind=decide 行 → 跳过）：counted_rows/rows_sha256 必存且与档案重算一致；"
            "conclusion=continue 还要求 N>=1 且每行都来自真 jev；narrow/revoke 只要求哈希链完整",
        ),
```

```python
# 行 420–426：
        elif check_type == "decision_signoff":
            # 无条件执行（不再看 decision-scope.md）；适用性判断全部下沉到
            # `_decision_signoff_problems`（disable / 无决策行 → []）。
            failures.extend(_decision_signoff_problems(key_dir))
```

配套要求：若采用 A，`_decision_signoff_problems` 必须在**文件存在性检查之前**先做廉价判据（见 §2、§3），否则每个没有 mw checkout 的项目 `done` 门禁会集体变红。

---

## 2. `_decision_signoff_problems` 当前控制流与最安全插入点

### 2.1 控制流（行 271–329）

| 行 | 步骤 | 早退结果 |
|---|---|---|
| 282–283 | `_decision_signoff_disabled(key_dir)`：读 `<key_dir>/../../.mw/decide.json`，只有显式 `signoff == "disable"` 才为真（缺文件/坏 JSON/其它值都当"没关"） | `return []` |
| 284–286 | `sign = key_dir / DECISION_SIGNOFF_REL`；`not sign.is_file()` | `[MISSING: …]` |
| 287–290 | `sign.read_text` 失败（`OSError`） | `[SIGNOFF: cannot read …]` |
| 291–296 | `DECISION_CONCLUSION_RE.search(text)`（`(?m)^conclusion:`） | `[SIGNOFF: … 缺机器行 …]` |
| 297–299 | 解析 `counted_rows` / `rows_sha256` 机器行 | — |
| 300–306 | 任一机器行缺失 → 收集两条问题后整体返回 | `[SIGNOFF: 缺机器行 counted_rows… , …rows_sha256…]` |
| 307–312 | `_load_decide_signoff(key_dir)`：先试 `import decide_signoff`，失败则在 `key_dir` 与脚本目录向上找 `packages/multi-workers/mw.py` 并插 `sys.path` 再导入；仍失败 → `None` | `[SIGNOFF: cannot import decide_signoff …]`（硬失败） |
| 313 | `module.collect(key_dir.parent, key_dir.name)` → `SignoffFacts`（key 目录名即 key） | — |
| 314–319 | 比 `rows_sha256` | 追加 `SIGNOFF: rows_sha256 不匹配 …` |
| 320–324 | 比 `counted_rows` 与 `len(facts.rows)` | 追加 `SIGNOFF: counted_rows … 不符` |
| 325–328 | `conclusion == "continue"` 时 `module.verdict(facts, conclusion)` | 追加 `SIGNOFF: …` |
| 329 | 返回累积的 `problems` | — |

注意：`collect` 自己已经把 `dp == "dp25-signoff-conclusion"` 的行排除在 `facts.rows` 之外（`decide_signoff.py:299-307`），所以"该 key 的决策行"有两个不同集合：**参与过的行**（任意 `kind=decide`）与**参与计数的行**（`collect().rows`）。

### 2.2 插入"该 key 无决策行 → 返回 []"的最安全位置：行 283 与 284 之间

```python
# 行 282–284 之间插入
    if _decision_signoff_disabled(key_dir):
        return []
    # 决策模型从未参与 → 无签收要求（AC-001 / AC-002b）：必须在文件存在性、
    # 机器行解析和 decide_signoff 导入之前，否则无决策行的 key 会先撞 MISSING，
    # 或对没有 mw checkout 的项目硬失败。
    if not _key_has_decide_rows(key_dir):
        return []
    sign = key_dir / DECISION_SIGNOFF_REL
```

为什么是这一行，而不是更靠后的位置：

- **必须在 284 之前**：否则"无决策行 + 无 `sign-final.md`"仍然返回 `MISSING`，AC-001 不成立。
- **必须在 307（`_load_decide_signoff`）之前**：这是 spec §5 点名的坑——门禁改为无条件执行后，导入失败会把每个未装 `packages/multi-workers` 的项目的 `done` 变红；廉价判据必须挡在导入前。
- **必须在 313（`collect`）之前**：`collect` 会读整个档案并算 sha，不值得给零决策行的 key 付这份成本。
- **放在 282 之后**：`signoff: disable` 是最强的显式关闭面（D-071），应当先判、最便宜；两者都返回 `[]`，顺序只影响"who wins"，不影响结果。
- **不要放在 305（`if problems: return problems`）之后**：那一行之前已经对缺失文件/缺失机器行返回，零决策行 key 永远走不到。

---

## 3. 不依赖 `decide_signoff` 导入的廉价判据（canonical 内实现）

### 3.1 代码草案

插入位置：`_decision_signoff_disabled` 之后、`_decision_signoff_problems` 之前（当前行 269/270 之间）。

```python
# 档案路径与 key 归属规则必须与 decide_signoff 保持一致（不导入它）。
# `key_dir.parent` 就是 `.agenticdoc`（`_decision_signoff_disabled` 用的是再上一层做项目根）。
DECISION_ARCHIVE_REL = "_autopilot/decisions.jsonl"


def _matches_key(row: dict, key: str) -> bool:
    """`key` 列，否则 `decision_id` 的 `:<key>` 后缀。

    与 `decide_signoff._row_matches_key`（decide_signoff.py:223-230）逐分支对齐：
    不做 str() 强转，不加 strip，非字符串 `decision_id` 直接 False。
    """
    if row.get("key") == key:
        return True
    decision_id = row.get("decision_id")
    if not key or not isinstance(decision_id, str):
        return False
    return decision_id.endswith(":" + key)


def _key_has_decide_rows(key_dir: Path) -> bool:
    """该 key 的档案里是否有 >=1 条 `kind=decide` 行（廉价判据，早退）。

    返回 False 表示"可以证明没有"；无法判断（读失败/坏编码）返回 True，
    交给后面的完整校验 fail-loud，避免读错误静默放行。
    """
    archive = key_dir.parent / DECISION_ARCHIVE_REL
    try:
        text = archive.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False                      # 档案不存在 == 没有决策行
    except (OSError, UnicodeDecodeError):
        return True                       # 读不清就不当"没有"
    key = key_dir.name                    # 与 collect(key_dir.parent, key_dir.name) 同一个 key
    for line in text.splitlines():
        if not line.strip():
            continue                      # decide_archive.iter_rows 跳过空行
        try:
            row = json.loads(line)
        except ValueError:
            continue                      # 坏 JSON 行跳过（与 iter_rows 一致）
        if isinstance(row, dict) and row.get("kind") == "decide" and _matches_key(row, key):
            return True                   # 命中即停：大档案不必扫完
    return False
```

（`json` / `Path` 在文件头已导入：行 18、19。无需新增 import。）

### 3.2 与 `_row_matches_key` 对齐时必须守住的边界

| # | 边界 | 正确写法 | 写错的后果 |
|---|---|---|---|
| 1 | `key` 列是原始值比较 | `row.get("key") == key`，**不** `str()` | 把 `key=123` 或 `None` 强转成字符串后可能误命中/误漏 |
| 2 | `decision_id` 必须真是 `str` | `isinstance(decision_id, str)` 后才 `.endswith` | 非字符串会抛 `AttributeError`，把门禁变成 traceback |
| 3 | 空 key | `if not key: return False`（只在后缀分支） | `key=""` 时 `endswith(":")` 会把 `dp1:trigger:` 之类误判为命中；`collect` 对空 key 仍可用 `key` 列命中（`key or ""`），保持一致 |
| 4 | 冒号前缀 | `endswith(":" + key)` | 少了冒号，`xk-signoff` 会命中 `k-signoff` |
| 5 | trigger 后缀 | **只靠 `key` 列兜底** | `decision_id` 形如 `"<dp>:<trigger>"`；真实档案里 dp25 行是 `dp25-signoff-conclusion:mw-usage-monitor@2026-10-21T16:22:25+00:00`，checkpoint 触发则可能是 `<key>#ckpt3`——`:<key>` 后缀都**不匹配**（实测见 3.3）。缺 `key` 列时两侧会一起漏，属于"一致地漏"，可接受 |
| 6 | `kind` 严格相等 | `row.get("kind") == "decide"` | `None`/`authority-change`/`override`/`settle` 都不算；`mw decide sign` 写的是 `authority-change`，若判据写成"该 key 有任何行"就会被签名自身撑起来 |
| 7 | 行级容错 | 逐行 `json.loads`，跳过空行/坏 JSON/非 dict | 用整文件 `json.load` 会在 JSONL 上直接失败 |
| 8 | 编码/IO 失败 | `FileNotFoundError` → False；其它 `OSError`/`UnicodeDecodeError` → True | 一律 False 会把"读不到"当"没有决策行"，静默放行（fail-open） |
| 9 | `dp25` 是否排除 | 见 §5 的取舍 | 排除后与 `collect().rows` 严格一致，但会让"N=0 + continue"在门禁上不可达 |
| 10 | 成本 | 命中即 return，不排序、不算 sha、不改 `sys.path` | 全量读入 + 排序在多 key 项目里白付成本 |

### 3.3 实测（真实档案 `.agenticdoc/_autopilot/decisions.jsonl`，44 行 / 10 条 decide）

| key | `kind=decide` 总数（含 dp25） | `collect().rows`（排除 dp25） | 只用 `:<key>` 后缀 |
|---|---:|---:|---:|
| claim-driven-review | 1 | 1 | 1 |
| mw-decision-dashboard | 1 | 1 | 1 |
| mw-decision-substitution | 4 | 2 | 2 |
| mw-signoff-per-key | 2 | **0** | **0** |
| mw-usage-monitor | 2 | **0** | **0** |

结论：`key` 列是载荷判据，`:key` 后缀只是兜底；只写后缀规则会把两条真实 dp25 行漏掉。

### 3.4 草案行为矩阵（在 `%TEMP%` 副本上实跑，未改仓库）

| 场景 | `_decision_signoff_problems` 结果 |
|---|---|
| A 无档案 + 存在 `decision-scope.md` | `[]`（AC-001 / AC-002b） |
| B 1 条真 jev 行 + 无签收文件 | `[MISSING: evidence/review/sign-final.md …]`（AC-002） |
| C 只有别的 key 的行 | `[]` |
| D 只有坏 JSON / 非对象行 | `[]` |
| E 无 `key` 列，`decision_id = "dp3:k1"` | `[MISSING: …]`（后缀兜底生效） |
| F 只有 dp25 行（`key` 列命中、后缀不命中） | `[MISSING: …]`（取决于 §5 的取舍） |
| G 只有 `authority-change` 行（即 `mw decide sign` 自己写的行） | `[]` |
| H `check_gate(key_dir,"done")`（A 场景） | 无 SIGNOFF failure，`passed=False` 仅由既有 achieved/quality-gate 规则造成 |

---

## 4. `advance_phase.py` 的副本：谁是源、谁是镜像、谁是临时产物

| 路径 | 大小 / sha256 前缀 | 仓库跟踪 | 角色 | 处理 |
|---|---|---|---|---|
| `.agents/skills/agentic-task/scripts/advance_phase.py` | 38274 / `4a7f341e806aadc6` | 否（`.gitignore:57` 忽略 `.agents/`）；但它**是 AgenticTask repo 的 git clone**（自身 `.git`，HEAD `d0834ae`），该文件在其中被跟踪且当前 `M` | **canonical 源** | 唯一改动点；提交/推送到 AgenticTask repo |
| `.agents/skills/agentic-task/core/scripts/advance_phase.py` | 38274 / `4a7f341e806aadc6` | 同上（clone 内跟踪） | `scripts/` 的**字节镜像** | 不手改。跑 `install.py` 的 `sync_script_mirrors()` 生成（`MIRROR_SCRIPT_DIRS = ("claude/scripts","core/scripts")`，方向 `scripts/` → 镜像） |
| `.agents/skills/agentic-task/claude/scripts/advance_phase.py` | 38274 / `4a7f341e806aadc6` | 同上 | 同上 | 同上；由 `test_decide_sign_auto.py:504-523` 的字节一致断言锁定 |
| `.claude/scripts/advance_phase.py` | 37023 / `fad92da5d8a0f884` | 否（`.gitignore:21` 忽略 `.claude/`） | **安装产物**（`install.py::install_claude` 把 `claude/{commands,agents,skills,scripts}` 复制到 `<project>/.claude/`） | 不手改；改完 canonical 后重跑 `install.py` 刷新。当前已滞后：文件里没有 `_decision_signoff_disabled`（D-071 面） |
| `packages/multi-workers/.tmp/agentic-task/{scripts,core/scripts,claude/scripts}/advance_phase.py` | 26521 / `4111bff403bc4c8b` | 否（`.gitignore:63` 忽略 `.tmp/`，`git check-ignore -v` 明确命中）；2026-09-21 | **过期临时夹具**：`grep decision_signoff` = 0 命中，早于 FIX-P | 不同步；测试也不读它（`test_decide_signoff.py:40` 指向 `.agents/...`） |
| `.tmp/rq3c-fake/agentic-task/**`、`.tmp/rq3c-fake/project/.claude/scripts/...` | 26852 / `9427abe2ecc0366b` | 否（同上） | 假项目夹具残留，2026-09-22 | 不同步；不要当基线 |

判据总结：**"git 跟踪 + install.py 同步方向"** 两者结合——仓库内没有任何一份 `advance_phase.py` 被主仓库跟踪（`.agents/`、`.claude/`、`.tmp/` 全被忽略）；唯一真实源是 AgenticTask clone 的 `scripts/`，两份镜像由 `install.py` 从它生成，其余都是安装/测试残留。因此 RQ2 的实现落地应发生在 AgenticTask repo 的 `scripts/advance_phase.py`，然后 `python .agents/skills/agentic-task/install.py <project>` 刷镜像与 `.claude/`。

---

## 5. 受影响的测试与应改的断言

### 5.1 `packages/multi-workers/test_decide_signoff.py`

| 行 | 用例 | 现在为什么过 | 改条件后 | 应改成 |
|---|---|---|---|---|
| 604–611 | `test_gate_ignores_keys_without_decision_scope_marker` | 无标记 → 分支不执行 | 仍然过（无档案 → 廉价判据 `[]`），但**已验证的东西变了**：不再证明"标记被忽略" | 改名 `test_gate_skips_signoff_for_keys_without_decision_rows`；保留 `assert not any("SIGNOFF" …)`；另加 AC-002b 用例：写入 `decision-scope.md` 但档案无 `kind=decide` 行 → 仍然无 SIGNOFF failure（证明标记已惰性） |
| 613–621 | `test_gate_blocks_continue_with_n_zero` | 标记强制执行 → `verdict` 报 `N=0` | **失效**。该夹具里 `mw decide sign` 只写 `authority-change` 行（实测：`kind=decide` 计数 0），廉价判据 → `[]` → 永远看不到 `N=0` | 二选一：① 追加一条 `kind=decide` 行 → `N=1`，断言改为"不再有 SIGNOFF failure"；② 保留 `N=0` 语义则必须在签名后再追加一条 dp25 的 `kind=decide` 行（模拟 auto 路径自身的建议行），让廉价判据放行、`collect().rows` 仍为 0，断言 `N=0` —— ② 才保住这条回归，且它把"判据含 dp25"这一取舍钉死 |
| 623–631 | `test_gate_passes_narrow_with_n_zero` | 标记强制执行 → `verdict(narrow)` 通过 | 廉价判据 → `[]`，断言"过"变成**空过**（检查根本没跑） | 同样追加 dp25 `kind=decide` 行，并直接断言 `advance._decision_signoff_problems(key_dir) == []`（证明真的执行过且通过） |
| 633–646 | `test_gate_blocks_after_the_archive_is_appended` | 有真行 + 标记 | 行为不变（有真行 → 判据放行） | 只删 638 行标记夹具；两条断言保留 |
| 649–659 | `test_gate_blocks_a_missing_machine_line` | 标记强制执行，手写只有 `conclusion:` 的签收文件 | **失效**：没有任何 `kind=decide` 行 → `[]` | 在 654 前加 `_append(project, trigger="t1")`，让完整校验真的跑到机器行解析；两条断言保留 |
| 667–696 | `test_signed_via_line_leaves_the_gate_and_dp_apply_parse_untouched` | 标记强制执行 | 断言仍然过，但是** vacuously**（检查被跳过） | 在 680 前加 `_append(project, trigger="t1")`（`render(facts,…)` 随后重算，sha/counted 自然一致），必要时补一条"检查确实执行"的断言 |

### 5.2 `packages/multi-workers/test_decide_sign_auto.py`

| 行 | 用例 | 改条件后 | 应改成 |
|---|---|---|---|
| 494–501 | `test_disable_lets_the_done_gate_pass` | 仍过（disable 先返回） | 删 498 行标记夹具即可 |
| 526–533 | `test_auto_keeps_the_gate_closed_without_the_file` | **失效**：无 `kind=decide` 行 → 判据 `[]` → 不再出现 `sign-final.md` failure | 先 `_append_true_engine_row(project)`（AC-002：模型参与过、文件缺失 → 必须失败），删 530 行标记夹具 |
| 504–523 | `test_advance_phase_mirrors_are_byte_identical` | 不受逻辑影响，但会**因未跑 `install.py` 而红** | 不改测试；落地时跑 `install.py` 同步 `core|claude/scripts` |

### 5.3 框架自带测试 `.agents/skills/agentic-task/scripts/test_advance_phase.py`

- 行 46–50（`setUp`）与行 414–419 的 done 夹具手写 `evidence/review/sign-final.md`（只有 `conclusion: continue`），且**没有任何档案**。
- 改条件后：没有廉价判据时，这些用例会因缺 `counted_rows`/`rows_sha256` 而集体变红；有廉价判据（档案不存在 → `[]`）才继续绿。这是 §2 插入点"必须在导入之前"的第二个独立证据（第一个是"没装 mw 的项目"）。
- 建议补一个正面用例：造 `_autopilot/decisions.jsonl` 含 1 条该 key 的 `kind=decide` 行 + 缺签收文件 → `check_gate(..., "done")` 出现 `SIGNOFF: MISSING`（把 AC-002 固定在框架侧，而不是只靠 mw 仓库的测试）。

### 5.4 不受影响

- `packages/coding-agent/test/suite/decision-signoff.test.ts`：只覆盖签收文件路径/命令面，未引用 `advance_phase`、无 `decision-scope` 依赖。
- `.claude/scripts/advance_phase.py` 没有测试（安装产物）。

---

## 风险

最容易漏的一处：廉价判据把"没有决策行"变成放行，于是**手写签收文件但没造档案的夹具会静默变绿**（649、667、`test_auto_keeps_the_gate_closed_without_the_file`），而 `test_gate_blocks_continue_with_n_zero` 会真的变红——`mw decide sign` 的 CLI 路径只写 `authority-change` 行，`N=0` 只能靠 dp25 的 `kind=decide` 行才可达。落地时必须同时决定"判据是否含 dp25"，否则这四条测试会在同一个 PR 里给出互相矛盾的信号。

## 行号勘误（对本文三处引用的±1 修正，正文内容不变）

- §1.3 表格：两条既有签收规则（`glob_has_files` + `content_match`）位于 **行 107–121**（引用写成了 108–121）。
- §3.1 括号注：`json` 在 **行 16**，`Path` 在 **行 18**（引用写成 "行 18、19"）。
- §2.1 注：`collect` 排除 dp25 的列表推导是 **`decide_signoff.py:298-308`**（引用写成 299-307）。
