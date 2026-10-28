# 设计证据：任务级依赖载体（`deps:` 卡头）+ V1–V7 校验 + 任务前沿消费（RQ-D4）

> 任务卡：`.agenticdoc/mw-dynamic-concurrency/tasks/T-C-D4-task-deps.md`（sha256 `ce8ebe171dab3bb6d0ffa1589238757a02aa958552610e2814cac7ebf1051893`）
> Key：`mw-dynamic-concurrency` · 角色：research（只读）· 日期：2026-10-14
> 上游：`spec.md` §1.4/AC-008/AC-009/§4 风险 2、`design.md` §3.2（D-103/D-104）
> 取证口径：本仓 `.agenticdoc/` 全量只读扫描 + 源码原文逐行复看；所有计数为本轮实测。

---

## 0. 结论先行（TL;DR）

1. **语法定稿用"松输入/严解析"**：键名 `deps`（ASCII，大小写不敏感，亦接受中文 `依赖`）；值 = `-`/空/`无`/`none`/`—` ⇒ 无依赖；否则按 `,` 与 `、` 切分（兼容 `/`、`+`、YAML flow list `[..]`），每个片段取**前导 id token**（`(T-)?\d{1,3}`），丢弃尾随说明（`（…）`、`· 预估: …`、`**…**`）。**归一化到数字核心**后再 join 卡文件 stem。
2. **`_header_value` 不能复用**（实测 5/5 真实卡返回 `""`）：卡首行是 H1，`_HEADER_RE`（`card_audit.py:82`）在 `card_audit.py:160-162` 直接 `break`。**必须新增独立 `parse_card_deps`**（新建正则 + 卡头区域规则），不能仅"新增一个 pattern 传给 `_header_value`"。
3. **既有 `_plan_task_file_stems` 候选映射对真实语料解析率为 0**：146 个真实 dep id token 里，stem 精确命中 0、`_plan_task_file_stems` 命中 0、**数字核心唯一命中 125**、同核心歧义 10（全在 `agent-team-loop`，该 key 有 `T-01-file-lock` 与 `T-01-task-protocol` 双份编号）、散文 token 11、悬空 0。⇒ AC-009 原文"走既有 `_plan_task_file_stems` 候选映射，不产生假红"**实测不成立**，必须在 join 里补数字核心规则 + 歧义判据。
4. **派发头回显 `deps:` 对 `card_sha256` 中性**：`card_sha256` 哈希的是**卡文件**（`dispatch.py:577` `digest = card_digest(card_file)`），回显写进**派发 task.md**（`dispatch.py:826-871`），两者不同文件 ⇒ 回显不改变任何已记录 sha。**但**给**卡**新增 `deps:` 行会改变卡摘要 ⇒ 该卡既有派发行的 `recorded != current` ⇒ `tampered_cards`（永远红）。本仓已有 3 行正是这个状态（`mw-worktree-junction-guard`），是机制的真实先例。
5. **`frontier_tasks`** = `_plan_task_order` 序下、`deps ⊆ done`、非 done、非在飞、写面可判且不交的 stem 列表；实起 = `前 min(max_workers_per_key − |在飞|, |frontier|)` 个。**任一 V1–V7 问题 ⇒ 该 key 整层回退串行**（`_plan_task_order` 顺序、忽略图），写 timeline——这正是 AC-003/AC-009 的字面要求，避免"静默永锁"。
6. **orphan（plan 未提）默认"无依赖 = 立刻可派"**：理由 = AC-008 明文"无 `deps:` 行 = 无依赖 = 今日行为"，且 434 张卡里 **317 张无任何依赖行**，若默认"依赖全部"会凭空改变 317 张卡的行为并可能与 plan 提及项成环；"保守串行"由写面闸（前置 key）与 orphan-last 排序承担。**"缺失"与"不可解析"必须区别对待**：缺失 ⇒ 空依赖；存在但不可解析 ⇒ 校验问题 ⇒ 串行回退。
7. **落点建议**：`card_audit.py` 加 `parse_card_deps`（叶子模块，与 `parse_card_path`/`parse_card_sha256` 并列）；V1–V7 与前沿放**新模块** `packages/multi-workers/autopilot/task_graph.py`（纯 stdlib、可单测、conductor 只 import 不重造）；`dispatch.py` 回显一行；TS 侧 `mergeCardHeader`（`ui-bridge.ts:2030-2036`）必须**同波**改动（P-021）。回显行插在 `card_sha256:` 之后、`envelope_producer:` 之前，可绕过两侧已冻结的行索引断言（见 §4.1）。

---

## 1. 实测基线（本报告所有数字的口径）

| 量 | 值 | 命令/口径 |
|---|---|---|
| 卡文件 | **434**，覆盖 **43** 个 key（含 `_scratch`） | `python -X utf8` 扫 `.agenticdoc/*/tasks/*.md` |
| 有 `plan.md` 且有 `tasks/` 的 key | **38** | 同上 |
| 带 card_path 的派发 task.md | **70** / 426 | `card_audit.parse_card_path` |
| 带 `deps:` 头行的派发 task.md | **0** / 426 | `^deps\s*:` 正则扫 426 个 `workers/*/task.md` |
| `_workers.parallel` 行 | **426**（`ap-` 前缀 **0** 行；done 389 / needs-clarification 27 / failed 3 / running 7） | 逐行 parse |
| `card_audit` 全库基线 | cards=434 dispatched=70 missing=0 **tampered=3** unlisted=311 unlisted_after=39 | 对 43 key 逐个 `card_audit.audit()` |

---

## 2. 载体语法定稿

### 2.1 现存载体形态（实测 4 种，117/434 卡携带）

| 形态 | 行数 | 卡数 | 原文样例（`文件:行号`） |
|---|---|---|---|
| 独立 bullet `- 依赖:` | 64 | 62(+2 另有 `- 波次:`) | `.agenticdoc/mw-crosskey-risk-escalation/tasks/T-1-CROSSKEY-ESCALATION.md:5` `- 依赖: 无`<br>`.agenticdoc/mw-vision-role/tasks/T-03-parity-refreeze.md:5` `- 依赖: T-01, T-02 · 预估: 60-90min` |
| 嵌入 `- 波次: … · 依赖: …` | 47 | 47 | `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-05-consumption-carrier.md:3` `- 波次: **1** · 依赖: T-01, T-03`<br>`.agenticdoc/mw-gate-verdict-hardening/tasks/T-15-no-silent-row-drop.md:3` `- 波次: **3** · 依赖: 无（本卡是 G5/G6 的起点）` |
| 独立 bullet `- deps:`（YAML flow list） | 12 | 12 | `.agenticdoc/mw-dual-workspace/tasks/002-py-target-config-parity.md:9` `- deps: [001]`<br>`.agenticdoc/mw-dual-workspace/tasks/011-regression-baseline.md:9` `- deps: [001, 002, …, 010]` |
| 裸 `deps:`（无 bullet、无 `---`） | 6 | 6 | `.agenticdoc/agent-team-loop/tasks/T-05-launcher.md:5` `deps: T-02, T-03, T-04`<br>`.agenticdoc/agent-team-loop/tasks/T-03-proxy-multi.md:5` `deps: none` |
| **并集（携带任一形态的卡）** | **117** | **117** | 434 − 117 = **317 张卡无任何依赖行** |

其它实测语法分布（117 行内，可重叠）：`T-NN` 形态 68、`T-N` 形态 16、纯数字 `NNN` 3、`无/none/—/空` 17、flow-list 12、区间 `…` 3、`**加粗**` 9、含解释性括号 57、其它 1。

**散文型反例（必须不能被当成 id 列表）**：
- `.agenticdoc/timi-gpt-pi-routing/tasks/007-build-verify.md:19`（在 `## 输入` 正文章节里，不在卡头区）`- 依赖: Stage 1 全部完成（TS 检查需要零错误）、Stage 2 全部完成`
- `.agenticdoc/mw-vision-role/tasks/T-14-verification-closeout.md:5` `- 依赖: T-01…T-13 全部 · 预估: 60-90min`（**区间**）
- `.agenticdoc/mw-rag-integration/tasks/T-13-MCP-TOOLMAP.md:5` `- 依赖: T-02（adapter）、T-03（fixture + mcp-client）、T-04（tools.ts 调用链）`（**中文顿号 + 括号**）
- `.agenticdoc/mw-vision-role/tasks/T-17-fix-description-optional.md:5` `- 依赖: T-05/T-06（引入该必填参数）· 预估: 20-30min`（**斜杠 = 或**）
- `.agenticdoc/mw-rag-integration-fix/tasks/T-17-DOCS-BUNDLE.md:5` `- 依赖: **T-15 必须先完成**（…）`（**加粗 + 断言式散文**）

### 2.2 语法定稿（MUST）

```
<deps-key>   := "deps" | "依赖"                     # ASCII 大小写不敏感；全角冒号“：”等价
<deps-line>  := [ "[" ] [ "-" SP ] <deps-key> ":" <deps-value>
                | [ "-" SP ] "波次" ":" <any> "·" <deps-key> ":" <deps-value>   # 嵌入形态
<deps-value> := "" | "-" | "—" | "无" | "none"                     # ⇒ 无依赖
                | <item> ( <SEP> <item> )* [ "," ]
<SEP>        := "," | "、" | "+" | "/"                             # “/”“+” 一律按 AND 合取（保守）
<item>       := [ "**" | "[" ] <id> [ "**" | "]" ] [ <说明> ]      # 说明 = "（…）" / "(…)" / "·…" / 任意散文
<id>         := ( "T" | "t" )? "-"? <digits 1..3> ( "-" <slug> )?
                # 归一化输出 = 数字核心 n = int(<digits>)；前缀大小写/前导零/`T-` 有无都不影响同一性
```

判定规则（写进 `parse_card_deps` 的合同）：

| 规则 | 判定 | 依据（真实语料） |
|---|---|---|
| `-` / 空 / `无` / `none` / `—` | **无依赖**（`()`） | 17/117 行 |
| `,` 与 `、` | 分隔符 | 68 行 `,`；`T-21、T-22`（`mw-rag-config-guide/tasks/T-23-VERIFY.md:5`） |
| `/`、`+` | 按 **AND** 合取（偏保守：多算依赖只会更晚放行） | `T-05/T-06`（T-17）；`T-07（…）+ T-12（…）`（`mw-autopilot-slot-capacity/tasks/T-16-attribution-delegation.md:3`） |
| YAML flow list `[001, 002]` | **容忍**（剥离 `[]` 后同规则切分） | 12 张 `mw-dual-workspace` 卡 |
| 尾随解释性括号、`· 预估: …`、`**…**` | **容忍**（每个 item 只取前导 id token，其余丢弃） | 57 行含括号；9 行含加粗 |
| 多个依赖声明行 | 取**元信息区内第一行**；出现第二行 ⇒ 校验问题（防御性） | 实测 0 张卡有两行 |
| 重复 id | 去重（保序） | `_parse_depends_on` 不去重，这里是任务图，去重无歧义 |
| 区间 `…` / `...` / `~` | **拒绝** ⇒ 校验问题 ⇒ 串行回退 | 3 行（`T-01…T-13`、`T-01…T-15、T-17…T-23`）。**不可**只取首 id（会欠声明依赖 ⇒ 过早并行） |
| 无法解析的非 id 片段（如 `Stage 1 全部完成`） | **拒绝** ⇒ 校验问题 ⇒ 串行回退 | `timi-gpt-pi-routing/tasks/007-build-verify.md:19`（且落在正文区，区域规则已先排除） |
| 跨 key 引用（含 `/` 路径或 `key:T-NN`） | **拒绝**（V7） | spec §1.4 明文排除 |
| 同一数字核心映射到 ≥2 个 stem | **拒绝**（歧义，V4b） | `agent-team-loop`：`T-01-file-lock` 与 `T-01-task-protocol` 并存 |

### 2.3 大小写 / 三种写法

- **`T-01` / `01` / `T-1` / `T-001` 全部容忍**，全部归一化到数字核心（`1`）。实测语料三种写法都有（`T-NN` 68、`T-N` 16、纯数字 3、`T-001`-slug 见 `_plan_task_file_stems` 文档串 `T-001-board-params-config-errors`）。
- 键名：`deps` 大小写不敏感（对比：roadmap 表头在 `roadmap.py:_is_header_row` 里先 `lower()`）；`依赖` 同等接受。
- id 前缀 `t-` / `T-` 大小写不敏感（归一化不影响同一性）。

### 2.4 与 `roadmap._parse_depends_on` 逐条对照

原文（`packages/multi-workers/autopilot/roadmap.py:483-495`）：

```
483| def _parse_depends_on(cell: str) -> tuple[str, ...]:
484|     """Parse a depends_on cell: '-' or empty = no deps; comma-separated key
485|     names otherwise. Empty segments (trailing commas) are filtered."""
486|     cell = cell.strip()
487|     if not cell or cell == "-":
488|         return ()
489|     deps: list[str] = []
490|     for part in cell.split(","):
491|         part = part.strip()
492|         if part and part != "-":
493|             deps.append(part)
494|     return tuple(deps)
```

| 维度 | roadmap `_parse_depends_on` | 本设计 `parse_card_deps` | 同/异 |
|---|---|---|---|
| 输入 | **markdown 表格单元格**（已由 `_split_table_row` 切好，`roadmap.py:451`） | **卡头一行**（bullet / 裸 `key:` / 嵌入 `·` 形态） | **异** |
| 载体位置 | `### Keys` 表 `depends_on` 列 | 卡片元信息区（首行 H1 之后、第一条正文之前） | **异** |
| 空 / `-` | `()` | `()`（并扩展 `无`/`none`/`—`） | 同 + 扩展 |
| 分隔符 | 仅 `,` | `,` + `、` + `/` + `+` | **异**（扩） |
| 空白 | `strip()` | `strip()` | 同 |
| 尾随逗号 / 空段 | 过滤（`if part`） | 过滤 | 同 |
| 段内 `-` | 丢弃（`part != "-"`） | 丢弃 | 同 |
| 去重 | **不去重** | **去重（保序）** | **异** |
| 加粗 / 括号 / 区间 / flow list | 不处理（会原样成为"依赖名"⇒ 悬空） | 显式容忍 / 显式拒绝 | **异** |
| 依赖项语义 | **key 名**（`dep in key_stage`，`roadmap.py:558`） | **任务 id** ⇒ 需 id→stem 解析 | **异（本设计的全部难点）** |
| 校验 | `validate_roadmap`：悬空（`:558-561`）、前向 stage（`:562-567`）、自依赖（`:568-571`）、环（`:573-575` + `_find_cycle :596`） | V1–V7（无 stage 轴 ⇒ "前向"换成"计划序/写面"，新增 V5 PM 任务、V6 重试代数、V7 跨 key） | 部分同 |
| 违规后果 | 返回 problem 列表（`validate_roadmap` 非致命；且 conductor 今天**从不调用**——spec §4 风险 6） | **该 key 整层串行回退 + timeline 事件**（AC-003/AC-009） | **异** |

---

## 3. 解析落点

### 3.1 `_header_value` **不能**复用的实测证据

`card_audit.py:129-167` 的扫描体（原文）：

```
143|     for index, raw in enumerate(text.splitlines()[:HEADER_SCAN_LINES]):
144|         line = raw.strip()
145|         if index == 0 and line == "---":
...
156|         if not line:
157|             if seen_header:
158|                 break
159|             continue
160|         match = _HEADER_RE.match(line)
161|         if not match:
162|             break
```

`_HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*)$")`（`card_audit.py:82`）。卡的第一行是 `# …`（H1），不匹配 ⇒ `index=0` 即 `break`。

实测（对 5 张真实卡分别用 `deps` / `- deps:` / `- 依赖:` 三个 pattern 调 `_header_value`）：

```
  mw-dual-workspace/tasks/002-py-target-config-parity.md: deps='' dash_deps='' dash_yilai=''
  agent-team-loop/tasks/T-05-launcher.md:                 deps='' dash_deps='' dash_yilai=''
  mw-vision-role/tasks/T-03-parity-refreeze.md:           deps='' dash_deps='' dash_yilai=''
  mw-autopilot-slot-capacity/tasks/T-05-consumption-carrier.md: deps='' dash_deps='' dash_yilai=''
  mw-dispatch-role-escape/tasks/T-02-...-log.md:          deps='' dash_deps='' dash_yilai=''
[VERIFY] VC-D4-07: header_value_on_cards_all_empty=5/5
```

⇒ **复用方式只能是"改 `_header_value` 的 break 逻辑"（会动到已冻结的 dispatch 解析语义）或"独立实现"**。裁定：**独立实现**（`parse_card_deps` + 卡专用区域规则），共享 `_clean_ref`（`card_audit.py:119`）做引号/注释剥离。

### 3.2 `parse_card_deps` 具体形状（建议原文形态）

```python
# card_audit.py 新增，紧跟 parse_card_sha256（:187）之后
_DEPS_LINE_RE = re.compile(r"^\s*(?:-\s*)?(?:deps|依赖)\s*[:：]\s*(?P<value>.*)$", re.I)
_DEPS_EMBED_RE = re.compile(r"·\s*(?:deps|依赖)\s*[:：]\s*(?P<value>.*)$", re.I)
_CARD_META_HEADING_RE = re.compile(r"^##\s*(元信息|基本信息|任务信息|元数据)\s*$")

def card_metadata_region(text: str) -> list[str]:
    """卡头区间：YAML frontmatter，或 H1 之后（含 ## 元信息/基本信息 小节）到第一条正文为止，
    上限 HEADER_SCAN_LINES。"""

def parse_card_deps(card_md) -> str:
    """读卡头区的 deps/依赖 原始值（与 parse_card_path/parse_card_sha256 并列）。
    未声明 ⇒ ""（= 无依赖，AC-008）。"""
    return _first_region_value(card_md, (_DEPS_LINE_RE, _DEPS_EMBED_RE))

def parse_card_deps_list(card_md) -> tuple[str, ...]:
    """解析后的 id token 序列（保序去重）；不可解析形态原样返回供校验层判 V-问题。"""
```

### 3.3 扫描窗是否够（`HEADER_SCAN_LINES = 40`）

实测（434 张卡）：

```
依赖行所在行号分布: {3: 3, 5: 54, 9: 12, 19: 1}   max = 19
第 40 行以外的依赖行: 0
元信息区结束行: max=12  p90=11  超过 40 的卡: 0
首行 H1: {1: 433, 3: 1}
[VERIFY] VC-D4-06: header_scan_lines=40 max_deps_line=19 metadata_region_max_end=12 deps_lines_beyond_40=0
```

⇒ **40 行足够，余量 2 倍以上**（原 `HEADER_SCAN_LINES=40` 保持不变，无需上调）。注意实测只有 1 张卡 H1 不在第 1 行（`.agenticdoc/mw-guard-form-hardening/tasks/T-05-fixture-and-corpus.md`，H1 在第 3 行，前两行是 `> **状态：已由 T-04 吸收…**` 与空行）——区域规则要对"前导引用块"容错，或直接按"第一个 `# ` 之后"起算。

**关键**：单靠 40 行窗不够，必须叠加"区域边界"，否则正文里的 `- 依赖:` 会被误匹配（真实反例：`timi-gpt-pi-routing/tasks/007-build-verify.md:19` 在 `## 输入` 正文里；不过它以 `（` 与散文成分为值，且从行号看在 40 行内，**只靠行窗会误命中**）。区域规则（H1 / 空行 / `## 元信息|基本信息|任务信息|元数据` / `- k: v` / `k: v`，遇到其它 `## ` 或散文即止）实测把该卡挡在区外。

### 3.4 `- deps:` 与 `deps:` 是否都接受

**都接受**（并且还要接受 `- 依赖:`、`- 波次: … · 依赖: …` 两种真实形态）：

- 独立形态正则 `^\s*(?:-\s*)?(?:deps|依赖)\s*[:：]` 同时覆盖 `- deps: [001]`（12 张）与 `deps: T-02, T-03`（6 张）。
- 嵌入形态必须单独处理：47 张卡把依赖写在 `- 波次: **1** · 依赖: T-01, T-03` 里。**若只支持独立形态，这 47 张卡会静默读成"无依赖"** ⇒ 过早并行（`mw-autopilot-slot-capacity`、`mw-gate-verdict-hardening` 两个 key 会整层失去依赖约束）。

---

## 4. 派发头回显

### 4.1 位置与格式

渲染闭集原文（`packages/multi-workers/autopilot/dispatch.py:826-871`）：

```
826|     lines = [
827|         "---",
828|         f"type: {task_type}",
829|     ]
830|     card = card if isinstance(card, dict) else None
831|     if card is not None:
832|         card_path = str(card.get("path") or "").strip()
833|         card_sha256 = str(card.get("sha256") or "").strip()
834|         if card_path:
835|             lines.append(f"card_path: {card_path}")
836|         if card_sha256:
837|             lines.append(f"card_sha256: {card_sha256}")
838|     if phase:
839|         lines.append(f"phase: {phase}")
...
844|     if card is not None:
...
849|         lines.append(f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}")
...
864|     if deny_globs:
865|         lines.append("deny_globs:")
866|         lines.extend(f"  - '{item}'" for item in deny_globs)
```

**建议改动**：在 `dispatch.py:837` 之后插入

```python
        deps = str(card.get("deps") or "").strip()
        if deps:
            lines.append(f"deps: {deps}")
```

即在 `card_sha256:` 与 `phase:`（`:838-839`）之间。
**理由**：① 与 `card_path`/`card_sha256` 同属"卡派生身份"，语义成组；② 位置**不移动两侧已冻结的行索引断言**——TS 侧 `agent-team-loop.test.ts:5735` 断言 `lines[2]` 为 `card_sha256`、`agent-team-loop-vision-autoroute.test.ts:465` 断言 `headLines[3]` 为 `card_sha256`；Python 侧 `test_mwds_t13_producer_paralysis.py:348-349` 只断言 `type:` < `envelope_producer:` < `origin: conductor` 的相对序。插在 837 之后不改变以上任何一条。③ 也满足 `card=None` 的字节不变（回显整体在 `if card is not None` 分支内）。

TS 侧对称改动（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2030-2036`）：

```
2030| function mergeCardHeader(frontmatter: string, cardPath: string, cardSha256: string): string {
2031| 	const header = frontmatter.replace(/\r?\n$/, "");
2032| 	return (
2033| 		`${header}\ncard_path: ${cardPath}\ncard_sha256: ${cardSha256}\n` +
2034| 		`${ENVELOPE_PRODUCER_KEY}: ${envelopeProducerIdentity()}\n`
2035| 	);
2036| }
```

⇒ 加第 4 个参数 `deps` 并插在 `card_sha256` 后（`deps` 为空串时不插）。调用点 `ui-bridge.ts:2177`（`if (input.card) frontmatter = mergeCardHeader(...)`）需同步传值。**两侧必须同波**（P-021；`mergeCardHeader` 的 docstring `:2026-2029` 已写明"identity line is appended last so the existing positions other suites pin stay fixed"，正是这条纪律的既有先例）。

**回显值格式**：`deps: T-02, T-03, T-04`（规范化的短 id，`", "` 连接）。**不**回显原始散文值——派发头是 YAML-ish 单行，散文会污染解析。原始声明留在卡里，由 `card_sha256` 溯源。

### 4.2 不给依赖时不写行

- 卡无 `deps:`/`依赖:` 行 ⇒ `parse_card_deps` 返回 `""` ⇒ `card["deps"] = ""` ⇒ `if deps:` 为假 ⇒ **零字节**。
- 卡有但值为 `-`/`无`/`none` ⇒ 解析为空 tuple ⇒ 同样不写行。
- 依据：AC-008"无 `deps:` 行 = 无依赖 = 今日行为"；实测 317/434 卡无依赖行，**只有"不写行"才能保住既有渲染字节**（`dispatch.py:822-824` docstring："`card=None` stays byte-identical"）。

### 4.3 对 `card_sha256` 的影响（结论 + 理由 + 实测先例）

**结论：回显（§4.1）对 `card_sha256` 中性；给卡写 `deps:` 才对 `card_sha256` 有影响，且是"使既有 sha 失效"。**

理由（源码原文）：
- `card_sha256` 的来源是**卡文件**：`dispatch.py:577` `digest = card_digest(card_file)`，随后 `:582` `"sha256": digest` 进 `card` 字典，`:837` 渲染进派发头。`dispatch_card` 读的就是 `tasks/<stem>.md`（`:570-573`）。
- 校验方向是"记录值 vs 卡当前值"：`card_audit.py:344-349`
  ```
  344| def has_findings(result: dict, strict: bool = False) -> bool:
  ...
  348|     if result["missing_cards"] or result["tampered_cards"] or result["unlisted_after_boundary"]:
  349|         return True
  ```
  `tampered_cards` 是 **always FAIL**（`card_audit.py:27` 模块 docstring："``missing_cards`` and ``tampered_cards`` are **always** red"）。
- 派发头的任何新增行都在**派发 task.md** 里，与卡摘要无关 ⇒ 回显中性。
- 但**给卡新增 `deps:` 行会改变卡内容 ⇒ 卡摘要变化 ⇒ 该卡既有派发行的 `recorded != current` ⇒ tampered 红**。

**实测先例（同一机制已在仓库里发生 3 次）**：

```
[VERIFY] VC-D4-05: card_audit_baseline keys=43 cards=434 dispatched=70 missing=0 tampered=3 unlisted=311 unlisted_after=39
TAMPER mw-worktree-junction-guard
  workers/wjg-d1-guard-path        card=tasks/T-D1-guard-path-resolution.md
  recorded d8a70be8… current 1d8926f9…
  workers/wjg-d2-cli-registry      card=tasks/T-D2-worktree-cli-registry.md
  workers/wjg-d3-observability     card=tasks/T-D3-observability-harness.md
```

**运维后果与缓解**：
1. `card_audit` 今天**没有运行期消费者**（全仓 grep：只有 `test_mwds_t27_card_audit.py`、`test_mwds_t29_producer_signal.py`、`dispatch-card-injection.test.ts:538-546` 与 CLI 自身；`conductor.py:54` 的 import 列表里无 `card_audit`，`mw.py` 亦无）⇒ 它不会阻塞 tick，是 CLI/doctor 期发现。
2. 纪律：**先写卡（含 `deps:`）再派发**。已有派发行的卡若事后补 `deps:`，该派发行会变 tampered；补完后需要重新派发（`dispatch()` 的 `upsert_worker_row` 会覆盖同 `task_key` 行并写入新 sha，`dispatch.py:1174`）才能恢复一致。
3. 对 **本 key 自身**的直接影响：`card_audit --key mw-dynamic-concurrency` 当前 tampered=0；6 张 `T-C-*` 卡都未声明 `deps:`（T-C-D4 用 `- type:`/`- key:`/`- 唯一证据文件（唯一写面）:` 形态）。**若在 EXECUTE 之前给这 6 张卡补 `deps:` 行，6 个在飞派发（`workers/mdc-rq*`）会立刻变成 6 条 tampered**——这正是本 key 落地时的第一个坑。

---

## 5. V1–V7 校验：实现位置 + 反例

### 5.1 落点裁定

**新建 `packages/multi-workers/autopilot/task_graph.py`**（纯 stdlib），不塞进 `conductor.py`：

| 理由 | 证据 |
|---|---|
| `card_audit.py` 是**叶子模块**，不得反向 import conductor | `card_audit.py:1-2` docstring："Leaf module: stdlib plus the existing ``mw_common`` helper"；`:60/:65` 只 import `mw_common` + `launcher` |
| `conductor.py` 已 356 KB，且 `:54` 一次 import 13 个模块，再加就是环风险 | `conductor.py:54` 的 import 行 |
| 环检测逻辑可直接从 roadmap 泛化，需独立可单测 | `roadmap.py:596-626` `_find_cycle` 的 DFS 体（`:600` 只是 `graph = dependency_graph(roadmap)`，`:605-625` 与 roadmap 类型无关） |

依赖方向：`conductor.py → task_graph.py → card_audit.py → (mw_common, launcher)`，无环。

模块接口（建议）：

```python
# task_graph.py
def deps_by_stem(key_dir: pathlib.Path, stems: list[str]) -> dict[str, frozenset[str]]
def resolve_stem(token: str, stems: list[str]) -> tuple[str | None, str]   # (stem, reason)
def validate_task_graph(nodes: dict[str, frozenset[str]]) -> list[str]      # V1–V7 问题列表
def find_cycle(graph: dict[str, set[str]]) -> list[str] | None              # 泛化自 roadmap._find_cycle
def frontier_tasks(...) -> list[str]
def serial_fallback_order(stems: list[str], plan: str) -> list[str]         # = 今天的 _plan_task_order
```

`id → stem` 解析顺序（**这是 V4 的核心，实测必需**）：

1. **stem 精确命中**（`token in stems`）。
2. **`conductor._plan_task_file_stems(token)` 候选**（`conductor.py:2832-2845`；`T-NN-slug` ⇒ 追加去 `T-` 前缀的候选）。
3. **数字核心唯一命中**：`re.fullmatch(r"(?:T-)?(\d{1,3})", token)` ⇒ `n`，取 `{s ∈ stems | numeric_core(s) == n}`。
   - 恰好 1 个 ⇒ 命中；0 个 ⇒ V1 悬空；≥2 个 ⇒ **歧义**（校验问题）。
4. 全部落空 ⇒ V1 悬空。

**实测为什么必须有第 3 步**（146 个真实 dep id token）：

| 解析阶段 | 命中数 |
|---|---|
| stem 精确 | **0** |
| `_plan_task_file_stems` 候选 | **0** |
| 数字核心唯一 | **125** |
| 同核心歧义 | **10** |
| 散文 token（非 id） | 11 |
| 悬空 | **0** |

`[VERIFY] VC-D4-03: id_tokens=146 resolve_exact_stem=0 resolve_plan_task_file_stems=0 resolve_numeric_unique=125 ambiguous=10 prose=11 dangling=0`

反例（真实）：`.agenticdoc/mw-rag-window-parity/tasks/T-4-VERIFY.md:5` 写 `- 依赖: T-1、T-2、T-3 全部完成`；实际 stem 是 `T-1-SKILL-DIR-PARITY.md` / `T-2-MW-RAG-CMD.md` / `T-3-DOCTOR-RAG-ROW.md`。`_plan_task_file_stems("T-1")` ⇒ `["T-1"]`（`conductor.py:2843` 要求 `^T-\d{2,3}-` 才追加候选）⇒ **若只用既有映射，三处全部假红**。同类：`mw-dual-workspace` 的 `- deps: [001]` 对应 stem `001-ts-target-config`，`_plan_task_file_stems("001")` ⇒ `["001"]` 亦假红。

歧义反例（真实）：`agent-team-loop/tasks/` 同时有 `T-01-file-lock.md` 与 `T-01-task-protocol.md`（`T-02`/`T-03`/`T-04`/`T-05`/`T-06` 亦各两份）。该 key 的卡写 `deps: T-01` ⇒ 核心 1 命中 2 个 ⇒ 必须判歧义（不得静默取字典序第一个）。

### 5.2 V1–V7 表（落点 + 反例输入 + 期望判定）

| # | 判据 | 落点（函数） | 反例输入 | 期望判定 |
|---|---|---|---|---|
| **V1** | 悬空 id（解析不到任何 stem） | `task_graph.resolve_stem` → `validate_task_graph` | 卡 `tasks/T-09-x.md` 写 `deps: T-99`（本 key 无核心 99） | 问题 `deps-dangling:T-99`；该 key 串行回退 + timeline `config` 事件；**不静默永锁** |
| **V2** | 自依赖 | `validate_task_graph`（`dep == base`，对应 `roadmap.py:568-571`） | `.agenticdoc/mw-rag-window-parity/tasks/T-2-MW-RAG-CMD.md` 写 `deps: T-2` | 问题 `deps-self`；串行回退 |
| **V3** | 环 | `task_graph.find_cycle`（泛化 `roadmap.py:596-626`：入参由 `Roadmap` 换成 `dict[str, set[str]]`，DFS 体 `:600-625` 逐行可平移） | A `deps: B`、B `deps: A`；或 A→B→C→A | 问题 `dependency cycle: A -> B -> A`，串行回退 |
| **V4** | plan-only id ↔ 卡文件 stem 不一致（假红防护） | `task_graph.resolve_stem` 第 2、3 步 | (a) plan 写 `T-001-board-params-config-errors`、文件为 `001-board-params-config-errors.md`（`_plan_task_file_stems` 覆盖）；(b) 卡写 `deps: T-1`、文件为 `T-1-SKILL-DIR-PARITY.md`（**只有数字核心能救**）；(c) 卡写 `deps: T-01`、同 key 有 `T-01-file-lock` 与 `T-01-task-protocol`（**歧义**） | (a)(b) 命中，不报问题；(c) 报 `deps-ambiguous:T-01`，串行回退 |
| **V5** | 依赖到"非 worker 执行"的任务（永不会被 conductor family 行收口） | `task_graph` 读目标卡头 `Agent`/`负责 Agent` 值 → `validate_task_graph` | 目标卡头 `- 负责 Agent: PM 窗口`（真实 45 张卡如此，如 `.agenticdoc/mw-dispatch-flow-fixes/tasks/T-01-index-store-latest-active.md` 的 `PM 窗口`） | 问题 `deps-not-conductor-dispatchable:<stem>`；串行回退 |
| **V6** | 重试代数 `-aN` 归一 | `task_graph.resolve_stem`：`re.sub(r"-a\d+$", "", token)` 后重解析；`_family_rows` 已按 base 家族聚合 | 卡写 `deps: T-05-a2`；或缺省 runtime 行的 `task_key = ap-<key>-<stem>-a2` | token 归一为 `T-05`；**容忍**（不报红）；若归一后仍不存在 ⇒ 落 V1 |
| **V7** | 跨 key 任务级依赖 | `validate_task_graph`（token 含 `/`、`\`、`../`、`<key>:`，或解析出的 stem 不属于本 key 的 `tasks/`） | `deps: mw-b/tasks/T-2`、`deps: mw-b:T-2`、`deps: ../other/tasks/x.md` | 问题 `deps-cross-key:<token>`；串行回退（spec §1.4："任务级跨 key 边必须显式拒绝"） |

**V5 的现实约束（必须记账，否则会造出"永远 key 串行"的可用性灾难）**：
- 只有 **141/434** 张卡有 `Agent`/`负责 Agent` 头字段；其中 **PM 45 / worker 56 / TBD 40**，**293 张完全没有该字段**。
  `[VERIFY] VC-D4-09: agent_header_cards=141 pm=45 worker=56 tbd=40 absent=293`
- 因此 V5 必须**只对"显式 PM"报问题**；`TBD`/缺失一律**不报**（不得凭空判定）。若连缺失也报，则每个 key 都会串行回退，功能等于关闭。
- 另一条可选信号（更机械）：`dispatch.REGISTRY` 的 `conductor_dispatchable`（`dispatch.py:58-125`，唯一 `False` 的是 `rag-research`）。但那判的是**派发类型**，而 `execute_loop` 恒以 `"phase-writer"` 派（`conductor.py:1789`），卡头的 `type:` 不参与 ⇒ **卡 `type:` 不是 V5 的可靠来源**（实测只有 69/434 张卡有 `type:`），只能作辅助。

---

## 6. 前沿计算

### 6.1 `frontier_tasks` 精确定义

**输入**

| 符号 | 定义 | 现成来源 |
|---|---|---|
| `stems` | `tasks/*.md` 的 stem 列表（已 sorted） | `conductor.py:1758` `files = sorted(tasks_dir.glob("*.md"))` |
| `order` | `_plan_task_order(stems, plan, deps_by_stem)` | 泛化 `conductor.py:1717-1725` |
| `deps_by_stem: dict[str, frozenset[str]]` | 每张卡的**已解析并已归一化到 stem**的依赖集合；无声明 = `frozenset()` | 新（`parse_card_deps` + `resolve_stem`） |
| `done_stems` | `{s \| s ∈ stems 且 ∃r ∈ _family_rows(rows,key,s): r["status"]=="done"}` | `conductor.py:1767-1769` 的现成判据 |
| `inflight_stems` | `{s \| s ∈ stems 且 ∃r ∈ _family_rows(rows,key,s): _is_in_flight(r)}` | `conductor.py:1770` |
| `write_face_ok(s)` | 该卡写面可判定（A/B 声明齐）且与所有 `inflight_stems` 的写面**不相交** | 前置 key `mw-write-face-guard` 导出谓词（**本 key 不实现**） |
| `cap` | `max(1, int(cfg["max_workers_per_key"]))` | design D-102 |

**定义**

```
frontier_tasks =
    [ s for s in order
      if s ∉ done_stems
      and s ∉ inflight_stems
      and deps_by_stem[s] ⊆ done_stems          # 依赖全部 done（_DEP_SATISFIED = {done, closed-legacy}，conductor.py:64）
      and write_face_ok(s) ]                    # 写面可判且与在飞不交

slots        = max(0, cap - |inflight_stems|)
start_tasks  = frontier_tasks[:slots]
```

`deps_by_stem[s] ⊆ done_stems` 的终态集合与 key 层同源：`_DEP_SATISFIED = frozenset({"done", "closed-legacy"})`（`conductor.py:64`），而**卡级完成态本轮定为"家族行 status == done"**（`conductor.py:1768`），不引入 `closed-legacy`（任务级没有这个状态；`_workers.parallel` 实测只有 done/failed/running/needs-clarification）。

**fail-closed 分支**：`validate_task_graph(nodes)` 非空（任一 V1–V7）⇒ **整 key 串行回退**：

```
serial: start_tasks = first( s ∈ order if s ∉ done_stems and s ∉ inflight_stems )   # 恰好 = 今天的 execute_loop 行为
        + timeline.append("config", key=key, detail="task graph unusable: <problems>; falling back to serial (plan order)")
```

依据：AC-003"在依赖数据或写面数据缺失/不可解析时，**该层**回退到串行（实起 = 1）并写审计行；不得默认放大"；AC-009"任一问题 → 该任务视为依赖未满足（退化为串行）且写 timeline 事件，**不得静默永锁**"。key 级回退（而非逐任务排除）保证进度不被永久阻塞——逐任务排除会让"依赖永不可满足"的任务死锁。

### 6.2 与 `_plan_task_order` / `execute_loop` 的接线形状

现状原文（`conductor.py:1717-1725`）：

```
1717| def _plan_task_order(stems: list[str], plan: str) -> list[str]:
1718|     """Execution order: plan appearance order when parseable, else stem
1719|     lexicographic; plan-unmentioned (orphan) tasks go last (D-111)."""
1720|     if not plan:
1721|         return sorted(stems)
1722|     mentioned = [(plan.find(s), s) for s in stems if s in plan]
1723|     mentioned.sort()
1724|     orphans = sorted(s for s in stems if s not in plan)
1725|     return [s for _, s in mentioned] + orphans
```

接线三处：

**(a) `_plan_task_order` 加可选第三参 `deps_by_stem=None`**，返回"依赖合法序 + plan 出现序 tiebreak + orphan-last"：
- 保持 `:1722` 的 `plan.find(s)` 与 `:1724` orphan-last 作为**稳定排序键**；
- 在 `mentioned` 内部按 `deps` 做稳定拓扑排序（Kahn，同层用 `plan.find` 位置作 tiebreak）；有环时（已由 V3 拦下，正常不可达）退回 `:1725` 原序；
- 签名向后兼容：两参数调用点行为不变（可被既有测试直接锁定）。

补充实测（`plan.find` 是子串匹配，不是词边界匹配）：`_plan_task_order(["T-01","T-011","T-0112"], "see T-01 and T-011 and T-0112 here")` ⇒ `['T-01', 'T-011', 'T-0112']`，位置 `[(4,'T-01'), (13,'T-011'), (23,'T-0112')]`——短 stem 会命中长 stem 的内部。这是既有行为，**不作为本次改动项**，但拓扑排序的 tiebreak 若也用 `plan.find` 会继承同一特性。

**(b) `execute_loop` 的循环体（`conductor.py:1765-1800`）改为"遍历前沿、派最多 slots 个"**：

```
1765|     for stem in _plan_task_order([f.stem for f in files], plan):
1766|         loop = f"exec:{key}:{stem}"
1767|         fam = _family_rows(rows, key, stem)
1768|         if any(r["status"] == "done" for r in fam):
1769|             continue  # task complete
1770|         if any(_is_in_flight(r) for r in fam):
1771|             return False  # per-key serial: wait for the in-flight task
```

- `:1770-1771` 的"见在飞即 `return False`"换成"该 stem 不进前沿"（在飞不是整 key 停摆的理由，而是占名额）；
- 原来的 `return result.ok`（`:1800`）从"派第一个就返回"变成"派到 slots 用尽或前沿耗尽才返回"；`dispatch.dispatch` 返回 `ok=False` 时仍按现状 `mark_stalled`（`:1793-1799`）并停止本 tick 的后续派发（保守）；
- 派发成功后**必须刷新本 tick 的在飞集合**（把刚派的 stem 加入 `inflight_stems`，并把 `slots` 减 1），否则同 tick 会用旧 `rows` 快照重复派同一 `task_key` —— 这与 spec 风险 10（`_row_exists` 看到旧世界）是同一类洞。
- `done` 全部满足时仍走 `:1801-1804` 的 `advance.advance(..., "verify", ...)`。

**(c) `_missing_plan_tasks`（`conductor.py:2848`）不变**：它服务 execute 门禁，与依赖图无关。

### 6.3 orphan（plan 未提）在依赖图里的默认依赖

**结论：orphan 默认 `deps = ∅`（立刻可派），保留 orphan-last 排序与 `:1781-1785` 的 timeline 告警。**

理由（按权重）：

1. **AC-008 是显式合同**："不改变现有卡（无 `deps:` 行 = 无依赖 = 今日行为）"。实测 **317/434 张卡无依赖行**、**12/38 个 key 的 plan 完全不提任何 stem**（`mw-dual-workspace`：plan 3129 字节，12 个 stem 命中 0 ⇒ 今天全部走 orphan-last 词典序）。把"未声明"当"依赖全部"会一次性改变这些卡的行为，直接违背 AC-008。
2. **成环风险**：orphan 若默认"依赖全部其它任务"，则两个 orphan 互为依赖 ⇒ 必然 V3 环 ⇒ 整 key 串行回退（功能退化）。缺失语义没有足够信息来推断边，硬造边只会制造假环。
3. **"保守串行"的正当载体是写面闸，不是依赖图**：真正的"不能并行"来自写面重叠（前置 key 的 A/B 判定），那是机械的、有声明依据的；依赖图不该冒充它。
4. **缺失 ≠ 不可解析**：缺 `deps:` 行 ⇒ 空依赖（AC-008）；**有**依赖行但语法/解析失败（区间、散文、悬空、歧义、环、PM 目标、跨 key）⇒ 校验问题 ⇒ 整 key 串行回退。这条二分是整套设计 fail-closed 的核心。

具体实测量化（`mw-dual-workspace`，本设计最强的动机样本）：

```
plan bytes: 3129
stem in plan?: {12 个 stem 全为 False}
order: ['001-ts-target-config', '002-py-target-config-parity', ..., '012-changelog-wrapup']   # 纯词典序
[VERIFY] VC-D4-10: mw_dual_workspace plan_bytes=3129 stem_hits=0/12 order=lexicographic
```

该 key 的 12 张卡**只**有 `- deps: [001]` 一条机器序（`002` 依赖 `001`、`011` 依赖全部）——今天**完全不被消费**（`_plan_task_order` 只看 plan 文本，而 plan 一个 stem 都没提）。这正是"新增载体"的收益面。

**残余风险（需 PM 决策，见 §7）**：由于现存语料里只有 117/434 张卡带任何依赖行、**0 张带规范 `deps:` 行**，per-key 放开到 N>1 后，绝大多数任务的串行化只能靠写面闸兜底。若写面闸未就绪（前置 key 未 DONE），本 key 的 per-key 层必须保持实起 = 1。

---

## 7. 残留与未验证

1. **写面谓词（`write_face_ok`）未取证**：本报告把它当黑盒输入。`mw-write-face-guard` 的 A/B 判定与"卡写面声明"字段名不在本任务取证范围内，未做任何复看。⇒ `frontier_tasks` 的写面一维**未验证**。
2. **未改任何代码、未跑任何测试**：全部结论来自只读扫描与源码复看；`parse_card_deps` / `task_graph.py` / 回显行 / `execute_loop` 改造都只有设计形态，无实现与红绿验证。
3. **回显行对既有测试的影响未实测**：只做了"位置不移动已冻结索引"的静态论证（`agent-team-loop.test.ts:5735`、`vision-autoroute.test.ts:465`、`test_mwds_t13_producer_paralysis.py:348-349`）。TS `mergeCardHeader` 签名变化（新增第 4 参）会牵动 `ui-bridge.ts:2177` 调用点与相关 parity 语料，实际红绿未跑。
4. **区间 `…` 的处理未定**：本报告裁定"拒绝 ⇒ 串行回退"（3 张卡）。若 PM 希望"展开成显式 id 列表"，需另定展开规则（`T-01…T-13`、`T-01…T-15、T-17…T-23` 两处），并考虑编号空洞。
5. **`/` 与 `+` 语义未与作者确认**：本报告保守裁定"按 AND 合取"（各 1 处）。若作者原意是 OR，会欠声明依赖。
6. **`HEADER_SCAN_LINES=40` 的长期余量**：当前 max 依赖行 19、元信息区 max 12。若未来卡片元信息膨胀到 40 行以上，会静默退化为"无依赖"。建议在 `parse_card_deps` 里加"区域被 40 行截断且未见终止边界"的审计信号（本报告未实现）。
7. **未被验证的实测数值差异**：spec §4 风险 2 记"428 张卡的 `- 依赖:` 35 行、`- 波次: … · 依赖:` 26 行、旧式 `- deps:` 12 文件"；本轮实测为 **434 张卡 / 64 行 / 47 行 / 12 文件**。差异可能来自本轮新增卡片与本 key 的 6 张卡（以及正则口径），**以本报告口径为准**，差异本身未追查。spec 记的"74 处 `负责 Agent: PM`"本轮实测为 45 张卡的头字段显式 PM（另有 1 处散文误命中，见 §5.2 V5）。同类差异：spec 记"428 张卡"，本轮 434。
8. **`deps` 的 TS 读取面**：`status-model.ts`/`monitor.ts` 是否需要展示任务依赖未取证（`spec-dependency-sources` 记 `status-model.ts:444/485/591` 的 `dependsOn` 是 key 级展示）。
9. **`_index.parallel` / claim 与 per-key 并发的交互未测**（spec 风险 3）；本报告所有"在飞"结论都基于 `_workers.parallel` 与 conductor 局部 `rows` 快照。
10. **实测发现本仓 `_workers.parallel` 里 `ap-` 行 = 0**（426 行全为 manual/PM 派发行）。⇒ 本设计的在飞判据（`_family_rows` 基于 `ap-{key}-{stem}`）在**真实队列里目前零样本**，只能在 harness/构造语料里验证；这既是风险（无历史数据可校准），也是机会（无历史包袱）。

---

## 8. 未覆盖面声明

- **未覆盖**：`mw-write-face-guard` 的写面声明格式、A/B 判定算法、与 dispatch 的接入点。
- **未覆盖**：`dispatch.py` 之外的 12 个 `dispatch.dispatch(` 调用点（共 13 处）的逐个影响面（本报告只按 `execute_loop` 一条链取证）。
- **未覆盖**：`_index.parallel` / claim / 单 active 语义与 per-key 并发的交互（spec 风险 3）。
- **未覆盖**：`max_workers_per_key` 配置键的两侧镜像、parity 语料重冻、面板口径（属 RQ-D5）。
- **未覆盖**：TS 侧的 per-key 前沿镜像（本报告只确认 TS 侧**渲染**面 `mergeCardHeader` 需同波改）。
- **未覆盖**：`advance.advance()` 阻塞量化（RQ-D5 / AC-013）。
- **未覆盖**：真实多进程并发下的重复派发证伪（RQ-D3 / AC-011）。
- **未覆盖**：`validate_roadmap` 进 tick（AC-010）的实现与去重策略。
- **未覆盖**：worker 超时/看门狗与并发提高的交互（GC-4）。
- 本报告**未修改任何生产文件**；唯一写入 = 本证据文件（+ 本任务目录的 `progress.md`）。

---

## [VERIFY]

```
[VERIFY] VC-D4-01: cards=434 keys=43 keys_with_plan_and_tasks=38
[VERIFY] VC-D4-02: deps_lines_standalone=64 deps_lines_boci=47 deps_lines_bare=6 union_cards=117 absent_cards=317
[VERIFY] VC-D4-03: id_tokens=146 resolve_exact_stem=0 resolve_plan_task_file_stems=0 resolve_numeric_unique=125 ambiguous=10 prose=11 dangling=0
[VERIFY] VC-D4-04: dispatch_task_md=426 with_card_path=70 with_card_sha256=70 with_deps_header=0
[VERIFY] VC-D4-05: card_audit_baseline keys=43 cards=434 dispatched=70 missing=0 tampered=3 unlisted=311 unlisted_after=39
[VERIFY] VC-D4-06: header_scan_lines=40 max_deps_line=19 metadata_region_max_end=12 deps_lines_beyond_40=0
[VERIFY] VC-D4-07: header_value_on_cards_all_empty=5/5
[VERIFY] VC-D4-08: queue_rows=426 ap_rows=0 done=389 needs-clarification=27 failed=3 running=7 retry_rows=1
[VERIFY] VC-D4-09: agent_header_cards=141 pm=45 worker=56 tbd=40 absent=293
[VERIFY] VC-D4-10: mw_dual_workspace plan_bytes=3129 stem_hits=0/12 order=lexicographic
[VERIFY] VC-D4-11: plan_refs_T-NN-slug=38 resolve_direct=37 resolve_prefix_strip=0 missing=1 key=mw-rag-integration id=T-10-AUDIT
[VERIFY] VC-D4-12: ts_header_index_pins agent-team-loop.test.ts:5735 lines[2]=card_sha256 vision-autoroute.test.ts:465 headLines[3]=card_sha256
[VERIFY] VC-D4-13: tamper_precedent key=mw-worktree-junction-guard tampered=3 recorded_vs_current_mismatch=3
[VERIFY] VC-D4-14: syntax_distribution T-NN=68 T-N=16 NNN=3 none=17 flow_list=12 range=3 bold=9 paren=57 other=1
```

---

## 附录 A：取证命令（可复算）

```powershell
# 卡与依赖行普查
python -X utf8 <TEMP>/mw_d4_probe3.py      # 载体形态计数（standalone 64 / boci 47 / bare 6）
python -X utf8 <TEMP>/mw_d4_probe8.py      # 语法分布（T-NN 68 / T-N 16 / NNN 3 / none 17 / flow-list 12 / 区间 3 / 加粗 9 / 括号 57）
python -X utf8 <TEMP>/mw_d4_probe11.py     # 146 token 的 naive vs numeric 解析对照
python -X utf8 <TEMP>/mw_d4_probe12.py     # 分阶段解析计数（0 / 0 / 125 / 10 / 11 / 0）
python -X utf8 <TEMP>/mw_d4_probe14.py     # 行号分布 + 元信息区边界
python -X utf8 <TEMP>/mw_d4_probe15.py     # 117/434 union
python -X utf8 <TEMP>/mw_d4_probe10.py     # _plan_task_order / _family_rows / _plan_task_file_stems 行为
python -X utf8 <TEMP>/mw_d4_probe13.py     # Agent 头字段分布
# 卡审计全库基线
python -X utf8 packages/multi-workers/autopilot/card_audit.py --root .agenticdoc --key mw-dynamic-concurrency
python -X utf8 packages/multi-workers/autopilot/card_audit.py --root .agenticdoc --key mw-vision-role
```

## 附录 B：本报告引用的源码位置索引

| 文件 | 行 | 内容 |
|---|---|---|
| `card_audit.py` | 78 | `HEADER_SCAN_LINES = 40` |
| `card_audit.py` | 80-83 | `_CARD_PATH_RE` / `_CARD_SHA_RE` / `_HEADER_RE` / `_DRIVE_RE` |
| `card_audit.py` | 119 | `_clean_ref` |
| `card_audit.py` | 129-167 | `_header_value`（`:143` 扫描窗、`:160-162` 非头行 break） |
| `card_audit.py` | 170-187 | `parse_card_path` / `parse_card_sha256` |
| `card_audit.py` | 258-341 | `audit()` |
| `card_audit.py` | 344-349 | `has_findings`（tampered/missing/unlisted_after = 永远红） |
| `roadmap.py` | 483-495 | `_parse_depends_on` |
| `roadmap.py` | 528-575 | `validate_roadmap` 依赖判据（悬空 `:558-561`、前向 `:562-567`、自依赖 `:568-571`、环 `:573-575`） |
| `roadmap.py` | 596-626 | `_find_cycle`（DFS 体 `:605-625`） |
| `roadmap.py` | 647-656 | `dependency_graph` |
| `conductor.py` | 64 | `_DEP_SATISFIED` |
| `conductor.py` | 1698-1704 | `_family_rows`（`-aN` 家族正则 `:1702-1703`） |
| `conductor.py` | 1717-1725 | `_plan_task_order`（orphan-last `:1724-1725`） |
| `conductor.py` | 1737-1805 | `execute_loop`（done `:1768`、串行闸 `:1770-1771`、orphan 告警 `:1781-1785`、retry `:1786-1787`、派发 `:1788-1799`、return `:1800`） |
| `conductor.py` | 2832-2845 | `_plan_task_file_stems` |
| `conductor.py` | 3539-3540 | `_is_in_flight` |
| `conductor.py` | 3560-3561 | `_deps_satisfied` |
| `dispatch.py` | 58-125 | `DispatchType` / `REGISTRY`（`conductor_dispatchable`） |
| `dispatch.py` | 556-586 | `dispatch_card`（`:577` `card_digest(card_file)`、`:582` `"sha256"`） |
| `dispatch.py` | 826-871 | `render_task_md` 头闭集（`:831-837` 卡字段、`:838-842` phase/images/model、`:849` producer、`:864-866` deny_globs） |
| `dispatch.py` | 952-955 | `task_key_for`（`ap-{owner}-{stem}`） |
| `ui-bridge.ts` | 2026-2036 | `mergeCardHeader`（TS 侧头合并，需同波加 `deps`） |
| `ui-bridge.ts` | 2177 | `mergeCardHeader` 调用点 |
