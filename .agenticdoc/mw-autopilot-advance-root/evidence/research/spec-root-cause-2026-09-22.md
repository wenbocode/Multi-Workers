# 调研证据：autopilot phase-advance 通道整体不可用（根因链实测）

> 日期：2026-09-22
> 关联：spec.md AC-001/002/003/006、design.md D-101..D-103
> 方法：read 文件全文 + Python 实跑（不采信搜索片段）

## 0. 现象

autopilot conductor 每 4s 对每个 artifact 就绪的 key 发一次 advance，全部 `exit=1`：

```
advance  feature-params-service  spec->design exit=1
         GATE BLOCKED: cannot advance to 'design'
         Current phase: init
         - MISSING: spec.md ...
```

detail 被截断到 200 字符，只看到 2 条缺项；真实情况是「跑到了错误的项目根」。

## 1. 三跳根因（逐跳实测）

### 跳 1：marker repo 指向项目外的 framework clone

`H:\git\E2Feature\.agentic-framework`：

```
framework=AgenticTask
repo=H:\git\Multi-Workers\.agents\skills\agentic-task
commit=a06b4a2
codex_skill=H:\git\E2Feature\.agents\skills\agentic-task
```

`packages/multi-workers/autopilot/advance.py::locate_platform_dir()` 候选顺序 = `[marker_repo, project/.agents/skills/agentic-task]`，**marker 在前**；命中即用，且只取 `detect_root.py --json` 的 `PLATFORM_DIR`，**丢掉 `PROJECT_ROOT`**。

### 跳 2：framework 的 find_root 只看 __file__

`advance_phase.py::find_root()`：

```python
p = Path(__file__).resolve()
for ancestor in [p.parent.parent.parent] + list(p.parents):
    candidate = ancestor / ".agenticdoc"
    if candidate.is_dir():
        return candidate
```

framework 装在项目外时，从 `H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\` 向上命中的是 **mw 仓库自己的** `.agenticdoc`（Multi-Workers 本身也是 AgenticTask 项目）。

实测（cwd=E2Feature）：

```
$ python H:/git/Multi-Workers/.agents/skills/agentic-task/scripts/detect_root.py --json
{"PLATFORM_DIR": "H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task",
 "PROJECT_ROOT": "H:\\git\\Multi-Workers",
 "AGENTICDOC_ROOT": "H:\\git\\Multi-Workers\\.agenticdoc",
 "method": "agenticdoc:platform_dir"}

$ python -c "... runpy advance_phase.py; print(find_root())"
H:\git\Multi-Workers\.agenticdoc
```

### 跳 3：错误 key_dir 被 mkdir，门禁报 init

`advance_phase.py` 在 key_dir 不存在时 `mkdir(parents=True)`，于是在错误仓库留下空 key 目录，随后门禁按「Current phase: init / MISSING: spec.md」报错——诊断指向的表象与真实根因完全不同。

实测残留（本次修复前清理）：

| 位置 | 时间 | 成因 |
|------|------|------|
| `H:\git\Multi-Workers\.agenticdoc\feature-params-service\`（空） | 11:59:17 | `key_dir.mkdir(parents=True)` |
| `H:\git\Multi-Workers\.agenticdoc\feature-viewer-mvp\`（空） | 12:01:30 | 同上 |

## 2. 不是版本问题

三份副本 sha256 完全一致（含 `.claude/scripts`、`.agents/skills/.../scripts`、mw clone 的 `scripts`）：

```
4111BFF403BC4C8B8766D771E37116FA8CD472D41854BEB2A4CF04C46549ACCA  advance_phase.py
BFCFE25698B02C7B9EEAEEA763702D8D485ADFC46480FF14BA527D3BC994EAC1  detect_root.py
```

框架 repo 根 `scripts/` 与 `claude/scripts`、`core/scripts` 亦逐字节一致（`install.py::sync_script_mirrors` 保证）。⇒ 问题是「跑了哪一份 / 从哪个 cwd 解析」，不是「哪一版」。

## 3. 同源面（只修 advance_phase 不够）

`__file__` 向上找根的写法还出现在：

- `update_index.py:141` `find_root()`
- `migrate_patterns.py:43` `find_root()`
- `verify_project_memory.py:15` `ROOT = Path(__file__).resolve().parent.parent.parent`

`detect_root.py::detect_project_root()` 第 1 步 `agenticdoc:platform_dir` 同样以 PLATFORM_DIR 为锚 ⇒ 被当作「权威探测」时也会报错根（见 §1 跳 2 输出）。

## 4. 编码缺陷实测

mw wrapper 用 `subprocess.run(..., encoding="utf-8", errors="replace")`；子进程 stdio 编码实测：

```
$ python -c "import sys;print(sys.stdout.encoding)"
gbk
$ python -c "import subprocess,sys; p=subprocess.run([sys.executable,'-c','import sys;print(sys.stdout.encoding)'],capture_output=True); print(p.stdout)"
b'gbk\r\n'
```

⇒ 中文门禁诊断按 cp936 写出、按 utf-8 解码 ⇒ 全文 `?`（即 detail 里的 `??`）。

## 5. 结论

- 主修 = D-101（framework root 定位 cwd 优先）+ D-102（detect_root PROJECT_ROOT cwd 优先）。
- 防守 = D-103（mw 候选一致性校验，fail-loud）+ D-104（`-X utf8`）。
- 否证 = D-105（候选重排：项目内副本 a06b4a2 落后 marker clone e9360db）。
