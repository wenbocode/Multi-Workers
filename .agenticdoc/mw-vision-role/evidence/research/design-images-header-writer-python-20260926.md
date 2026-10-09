# Research: task.md `images:` 头 — Python 写侧精确改法（RQ-D3 / AC-007, AC-009）

## TL;DR
- Python 唯一渲染器：`packages/multi-workers/autopilot/dispatch.py:253 render_task_md(...) -> str`；生产调用点只有 `dispatch.py:514`（`dispatch()` 内），其余 15 处全在测试里。新增 `images` 参数后**零个现有调用点需要显式传值**（全部可默认）。
- 插入位：`:300` 的 `if phase:` 块之后、`:301` 的 `if model:` 之前 → 满足 AC-007 的 `type < phase < images < model`。
- 零字节：**不能**用 `if images is not None:`（AC-009 明确要求 `images=""` 也逐字节不变）；用真值判断 `if images:`，只写 `images: yes`（`images: no` 由 TS 派发面写，design §4.1 只要求 Python 写 yes）。
- 卡里点名的 4 处 golden/逐字节断言**不需要重冻**（都不传 images，默认即零字节）；但 `test_autopilot_readcap_injection.py:898 test_render_task_md_signature_shape` 会红——必须把 `"images"` 加进 `extra` 期望列表。
- conductor 永不写 `images:`：`packages/multi-workers` 全树（含测试）`grep -i image` **零命中**，`conductor.py` 的 12 个 `dispatch.dispatch(` 点全是字面量类型 → 该头只由 TS 派发面/PM 写入。

## 决策问题（卡片 Q1..Q6）
Q1 签名/返回/全部调用点与 task_type；Q2 头顺序与插入位、零字节保证；Q3 读侧 5 点解析契约与冲击；Q4 golden 断言形态与是否重冻；Q5 conductor 是否产生该头；Q6 冻结渲染器回归范式的可复制用法。

## 调研方法与出处
全量读 `autopilot/dispatch.py`、`autopilot/conductor.py`、`autopilot/state.py`、`launcher.py`、`mw.py`、`worker/worker-mode.ts`、`pm/task-dispatcher.ts`、`pm/ui-bridge.ts`；全量读 `test_rag_phase.py`、`test_autopilot_readcap_injection.py`、`test_autopilot_dispatch.py`、`test_autopilot_conductor_exec.py`、`test_rag_launcher.py`。只读，未改源码/spec；仅 grep / Get-FileHash 等无副作用命令。锚点 2026-09-26 工作区。

## 发现

### Q1 签名、返回类型、全部调用点
`dispatch.py:253-268` 完整签名（原文折行）：
```python
def render_task_md(task_type: str, prompt: str, *, loop: str, attempt: int,
    read_scope: Sequence[str] = (), deny_globs: Sequence[str] = (),
    read_file_cap: int | None = None, read_byte_cap: int | None = None,
    model: str = "", phase: str = "", profile_block: str | None = None,
    rag_config: dict | None = None, task_meta: dict | None = None) -> str:
```
直接调用点与 task_type：
| 调用点 | task_type | 需显式传 images? |
|---|---|---|
| `dispatch.py:514`（生产，唯一） | `dispatch()` 形参（`dispatch.py:413`） | 否，默认 |
| `test_rag_phase.py:51 / :54 / :63` | `"verifier"` | 否 |
| `test_autopilot_dispatch.py:76 / :99` | `"verifier"` / `"repair"` | 否 |
| `test_autopilot_readcap_injection.py:248`（`render_caps` 助手） | 默认 `"reviewer"`（覆盖：`:557/:750`=verifier、`:801/:857`=reviewer） | 否 |
| `test_autopilot_readcap_injection.py:257`（`head_render`，冻结渲染器） | 默认 `"reviewer"` | 否 |
| `test_rag_launcher.py:135/332/338/344/353/355/365/414/479` | 全部 `"coding"` | 否 |
间接生产调用（都经 `dispatch()`，均无 images）：`conductor.py:607`(roadmap-writer)、`:995/:1033/:1170/:3099`(phase-writer)、`:1065`(verifier)、`:1663/:1699/:1728/:1765/:1812`(reviewer)、`:1804`(repair)。
结论：`images` 必须可选且默认零字节；没有任何现有调用点被迫改动，只有新测试显式传值。

### Q2 头渲染顺序与插入位（`dispatch.py:295-318` 原文摘录）
```python
    lines = ["---", f"type: {task_type}"]
    if phase: lines.append(f"phase: {phase}")
    if model: lines.append(f"model: {model}")
    lines += ["origin: conductor", f"loop: {loop}", f"attempt: {attempt}"]
    if read_scope: ...   # 非空才写；之后两 cap（is not None）与 deny_globs（非空）
    lines += ["---", "", prompt.strip(), ""]
```
恒定输出 `---/type/origin/loop/attempt`；`phase`/`model` 真值才写；两个 cap `is not None` 才写。`images:` 必须落在 `:300`（`if phase:` 块）与 `:301`（`if model:`）之间，这是代码里唯一能实现 `phase < images < model` 的位置。零字节口径 = 真值判断 `if images:`（None / `""` / False 都不进分支）。

### Q3 读侧 5 点解析契约
| 读点 | 范围/方式 | 行序要求 | 缺失默认 | 新行影响 |
|---|---|---|---|---|
| `worker/worker-mode.ts:268 parseTaskMd` | **整文件** `split("\n")` 逐行 `trimmed.startsWith("k:")` 前缀扫描 | 无 | `taskType="default"`，其余 `undefined` | 无 `images:` 分支 → 忽略；`images:` 不是 `- ` 列表项且位于 `read_scope:` 块之前，不截断列表 |
| `autopilot/state.py:153 parse_task_labels` | 仅 frontmatter（首行 `---` 到下一个 `---`），正则 `^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$` | 无 | `{}` | `images` 成未消费 label；消费者只读 attempt/loop/origin/type → 无影响 |
| `launcher.py:143 _read_task_md_fields` | **整文件** `re.MULTILINE` 正则 `^type:` / `^model:` | 无 | `("", "")` | 忽略 `images:` |
| `mw.py:1786 _rag_task_meta` | **整文件**逐行前缀扫描（`_rag_read_lines`=splitlines），首命中 | 无 | `{"type":"","phase":""}` | 忽略；不与 `type:`/`phase:` 相撞 |
| `pm/task-dispatcher.ts:115 parseRagTaskMeta` | **整内容** `^type:[ \t]*(.+?)[ \t]*$` / `^phase:`（`m` 标志，首个匹配） | 无 | `undefined` | 忽略 |
结论：5 点全是键前缀/整内容正则，均不要求行序，`images:` 只多一个键，既有行为不变。

### Q4 golden 清单与真实断言形态
- `test_rag_phase.py:36-60`：`GOLDEN` 是**整文件字符串字面量**（:36-47）；`:57 assertEqual(omitted, explicit_empty)`、`:58 assertEqual(omitted, self.GOLDEN)` = 整文件相等；`:60 assertNotIn("phase:", omitted)`。`:63-68`：`assertIn("type: verifier\nphase: DESIGN\n")` 子串 + `assertEqual(text.replace("phase: DESIGN\n",""), GOLDEN)` 整文件（去掉注入行后相等）。
- `test_autopilot_readcap_injection.py:636-637`（VC-007）与 `:657-658`（VC-008）：`content.encode("utf-8") == expected.encode("utf-8")` = **整文件逐字节相等**，`expected = head_render()` 来自 `_head_module()` 冻结渲染器。
- `test_autopilot_dispatch.py:75`：`assert "type: verifier" in lines` 等 = **行成员/子串**；`:98`：`assert "read_scope:" not in text`、`assert "model:" not in text` = **子串缺失**。
- `test_autopilot_conductor_exec.py:939-960`：`_dcr_task_body()`（:707）用 `text.split("---\n", 2)` 剥 frontmatter，`assert body == expected.strip()` = **仅 body 相等**，frontmatter 不参与。
重冻结论：4 处**都不需要重冻**——它们都不传 `images`，默认零字节即输出逐字节不变。真正会红的是 `test_autopilot_readcap_injection.py:898 test_render_task_md_signature_shape`：`:906 assert extra == ["read_file_cap", "read_byte_cap"]` 比较 worktree 与冻结渲染器的参数差集，新增后须改成 `["read_file_cap", "read_byte_cap", "images"]`。另注：`:885 test_baseline_left_end_bound` 把外部冻结副本 sha256 钉到 git HEAD，本机实测 frozen=`219E80…`（无 caps）≠ HEAD=`A17333…`（有 caps），**该断言现状即为红**，与 images 无关，零字节断言不要挂它。

### Q5 conductor 是否写 `images:`
不会。证据：(1) `packages/multi-workers` 全树（含 tests）`grep -i image` 0 命中；(2) `conductor.py` 12 个 `dispatch.dispatch(` 的 task_type 全是字面量（roadmap-writer/phase-writer/verifier/reviewer/repair），无 vision、无图片输入；(3) `dispatch()`（`:409-425`）与 `REGISTRY` 条目（`:67-68`）无 image 字段；(4) design 待确认 7 明说 conductor 派发点无内容检测入口、Python 侧无能力门禁与自动路由。结论：**conductor 永不写 `images:`，因此该头只由 TS 派发面/PM 写入**（除非 DESIGN 给 `dispatch()` 加 images 透传，见结论映射 3）。

### Q6 可复用的冻结渲染器回归范式
`test_autopilot_readcap_injection.py:165-186 _head_module()` + `:254-258 head_render()` + `:636` 逐字节比较即现成范式，可复制用法：
```python
def _pre_images_module() -> types.ModuleType:
    data = HEAD_DISPATCH.read_bytes() if HEAD_DISPATCH.is_file() else _git("show", f"HEAD:{DISPATCH_RELATIVE}")
    m = types.ModuleType("_images_dispatch_head"); m.__file__ = "git HEAD:dispatch.py"
    sys.modules[m.__name__] = m
    exec(compile(data.decode("utf-8"), m.__file__, "exec"), m.__dict__)
    return m

def test_images_undeclared_zero_bytes():
    kw = dict(loop="L", attempt=1, read_scope=["src"])
    live  = dispatch.render_task_md("verifier", "do it", images=None, **kw)
    empty = dispatch.render_task_md("verifier", "do it", images="",  **kw)
    head  = _pre_images_module().render_task_md("verifier", "do it", **kw)
    assert live == empty == head and "images:" not in live
```
注意：`git show HEAD:...` 仅在 images 改动**未提交**时等于改造前；提交后 HEAD 含 images，比较退化为恒真——须像 readcap T-001 一样先冻结副本。且如上，`:898` 签名断言须同步。

## 结论 → 决策映射
1. 推荐签名（镜像 `phase: str = ""` 的真值/字符串口径，满足 AC-009 的 `images=""`）：
```diff
     model: str = "",
     phase: str = "",
+    images: str | None = None,
     profile_block: str | None = None,
```
2. 推荐渲染（唯一合法位置，`type < phase < images < model`）：
```diff
     if phase:
         lines.append(f"phase: {phase}")
+    if images:  # None/"" -> 零字节（AC-009）；声明时写 images: yes|no
+        lines.append(f"images: {images}")
     if model:
         lines.append(f"model: {model}")
```
禁忌：`if images is not None:` 会让 `images=""` 渲染 `images: no`，违反 AC-009。若 DESIGN 坚持 `images: bool | None = None`，必须用同一性判断 `if images is True: … / elif images is False: …`（`""` 两者皆非 → 零字节）。
3. 调用点：`dispatch.py:514` 保持默认（conductor 不写）→ Q5 的"conductor 永不写"自动成立。若后续要让 conductor 的 `type: vision` 任务带 `images: yes`（AC-019 张力），再给 `dispatch()` 加 `images` 透传。
4. 测试：4 处 golden 不动；`test_autopilot_readcap_injection.py:906` 的 `extra` 期望加 `"images"`；按 Q6 新增零字节用例（禁用 `not.toContain` 式空断言）。
5. 读侧 5 点现有解析对新增行免疫，兼容性无需改动；`images` 的实际消费属 design 新增业务代码。

[VERIFY] `render_task_md` 生产调用点唯一：`dispatch.py:514`；全仓其余 15 处直接调用均在测试（`test_rag_phase.py:51/54/63`、`test_autopilot_dispatch.py:76/99`、`test_autopilot_readcap_injection.py:248/257`、`test_rag_launcher.py:135/332/338/344/353/355/365/414/479`）
[VERIFY] `images:` 插入位 = `dispatch.py:300`（`if phase:` 块）与 `:301`（`if model:`）之间；零字节须用真值判断，`if images is not None:` 违反 AC-009 的 `images=""` 子句
[VERIFY] 现有 4 处 golden/逐字节断言不传 `images`、无需重冻；唯一会红的是 `test_autopilot_readcap_injection.py:898/906` 的签名 `extra` 期望
[VERIFY] conductor 永不写 `images:`：`packages/multi-workers` 全树 `grep -i image` 零命中 + `conductor.py` 12 个字面量 task_type 派发点
[VERIFY] `test_baseline_left_end_bound`（`test_autopilot_readcap_injection.py:885`）本机现状为红（frozen 219E80… ≠ HEAD A17333…），不可作为 images 零字节证据链
