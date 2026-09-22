# 调研证据：framework 改动面 / 同步路径 / 测试落点

> 日期：2026-09-22
> 关联：design.md D-101/D-102/D-104/D-106/D-107
> 方法：read 全文（install.py / diff-installed.py / agent-scripts.ts / 既有测试）

## 1. framework repo 布局（H:\git\Multi-Workers\.agents\skills\agentic-task）

```
scripts/            canonical 源（13 个脚本 + 8 个 test_*.py）
claude/scripts/     mirror（install.py::sync_script_mirrors 从 scripts/ 覆盖）
core/scripts/       mirror（同上）
install.py          同步 mirror + 复制 claude/{commands,agents,skills,scripts} 到 <project>/.claude + clone 仓库到 <project>/.agents/skills/agentic-task + 写 .agentic-framework
diff-installed.py   漂移报告（local changes / HEAD 对比 / .claude 差异）
```

实测三处 `scripts` 逐字节一致：`advance_phase.py`、`detect_root.py`、`update_index.py`、`migrate_patterns.py`、`verify_project_memory.py` 的 hash 在 `scripts` = `claude/scripts` = `core/scripts`。

`install.py` 关键行为（read 全文确认）：

- `sync_script_mirrors()`：先跑，按字节覆盖 mirror，不删 mirror 独有文件；改动需 commit & push。
- `install_codex()`：目标已是 clone → `git pull --ff-only`；否则 `git clone <origin>`。`ROOT.resolve() == dst` 时 skip（mw 自装场景）。
- 写 marker：`repo=<ROOT>`、`commit=<short HEAD>`。

⇒ 修复流程：改 `scripts/` → `python install.py <project>`（自动同步 mirror + pull/写 marker）→ push 上游。

## 2. 调用方清单

| 调用方 | 脚本路径 | cwd | argv |
|--------|---------|-----|------|
| mw conductor | `autopilot/advance.py::advance()` 经 `locate_platform_dir()` | `project_root` | `[sys.executable, script, key, phase]`（现无 `-X utf8`） |
| mw 定位 | `advance.py::locate_platform_dir()` 调 `detect_root.py` | `project_root` | `[sys.executable, detect, "--json"]`（现无 `-X utf8`） |
| pi 扩展 | `shared/agent-scripts.ts::runAgenticScript()` | `projectDir` | `[PYTHON_EXE, script, ...args]`（现无 `-X utf8`） |

pi 扩展的脚本查找顺序（read 全文）：`<project>/.claude/scripts/advance_phase.py` → `<project>/.agents/skills/agentic-task/claude/scripts/advance_phase.py`。两者都在项目内，现状 root 解析恰好正确，但同样脆（一旦 install 布局变化就错），且中文诊断同样 mojibake。

## 3. 测试落点

framework 自带（`scripts/`）：

- `test_detect_root.py`：用 `tempfile.TemporaryDirectory(dir=Path.cwd().anchor)` 建临时项目——适合加「cwd 专扫优先」用例。
- `test_advance_phase.py` / `test_update_index.py` / `test_migrate_patterns.py`：直接 import 脚本模块，适合加 `find_root()` 双用例。
- 脚本测试用 `sys.path.insert(0, Path(__file__).parent)` import 同目录模块，无需打包。

mw（`packages/multi-workers/`）：

- `test_autopilot_conductor.py` 已有 `locate_platform_dir` / `advance_script` / `invalidate_script_cache` 的引用与 fake framework harness —— AC-003/004/005/006 的落点。
- pytest 入口：仓库根 `./test.sh` 或包内 vitest/pytest（见 AGENTS.md）。

## 4. 同步顺序风险

AC-003 的 fail-loud 一旦上线，任何「项目内副本 + marker clone 都不是当前项目根」的项目会被拒 advance。当前已知受影响：E2Feature（marker clone = mw clone）。⇒ D-107：framework 先发 + E2Feature 同步完成，再上 mw fail-loud。

## 5. dist bundle

pi 扩展改动需重建 `packages/coding-agent/dist`（agent-team-loop bundle）。本 key 只改一行 argv，dist 重建随 `npm run check` / 既有 build 流程；不做额外发布动作。
