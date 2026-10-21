# T-17: 分组里把临时目录/测试夹具折叠成 `(test fixtures)`（coding）

- Key: mw-usage-monitor
- type: coding
- 对应：spec §16（R24–R26 / AC-031–AC-033）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机级 usage 监控，看真实消耗分布）。
- 现状问题：`by project` 用会话 header 的 `cwd` 当项目名，pi 测试套件的一次性目录因此各占一行：
  7 天窗口里 `pi-runtime-suite-*` / `pi-2860-*` / `pi-runtime-cwd-a|b-*` / `pi-runtime-events-*` / `pytest-of-*`
  共 27 个分组、37 runs、48 calls（占 76065 calls 的 0.06%），把真实项目挤出视野。
  真实条目举例：`H:\git\E2Feature`（63 runs）、`H:\git\Multi-Workers`（61 runs）、`E:\CLI_workspace\OverCode`。
- 关键代码位置：
  - `packages/multi-workers/usage.py:759 _project_name`（分组显示名：现在返回 `_basename`）——分组名在
    `usage.py:1506` 的 `names["project"] = _project_name(unit["project"])` 处取用；
  - `packages/multi-workers/usage.py:743 _project_matches`（`--project` 过滤，接受全路径或 basename）；
  - `packages/multi-workers/usage.py:1404/1416`（worker 会话 unit 的 project 取值）、`:1473`（claude unit）；
  - 明细行取值在 `_run_detail_row` / `_pm_detail_row`（约 `usage.py:1223` / `:1273`），本任务不改它们（R25）。

## 要求

1. **`usage.py` 新增常量与判定**：
   - `FIXTURE_LABEL = "(test fixtures)"`（模块级，组名固定字符串）。
   - `_is_fixture_project(value) -> bool`：`_norm` 后
     (a) basename 以 `pi-runtime-` 开头（大小写不敏感），或
     (b) 规范化路径（`\` → `/`，casefold，去尾 `/`）落在于以下任一临时根之下或等于它：
     `tempfile.gettempdir()`、`/tmp`、`/var/folders`、`C:\Windows\Temp`（Windows 上会话 cwd 可能是
     `C:\Users\WENBOZ~1\AppData\Local\Temp\...` 短名，与 `gettempdir()` 的长名不同——两种写法都要命中，
     用「包含 `/appdata/local/temp/`」「包含 `/windows/temp/`」这类归一化子串判定即可）。
   - `_project_name`：fixture → `FIXTURE_LABEL`，否则保持现有 basename 行为（空值仍是 `UNKNOWN_LABEL`）。
2. **`_project_matches`（R26）**：`wanted` 等于 `FIXTURE_LABEL`（大小写/空白不敏感）时，只有 fixture 行匹配；
   非 fixture 行一律不匹配。`wanted` 是真实路径/basename 时保持现有语义（夹具的**原始路径**仍可被精确过滤，
   但真实项目的 basename 不得把夹具行捞进来——即非 fixture 判定优先）。
3. **不改事实层（R25）**：`runs[]` / 明细行的 `project` 仍是原始路径，文本/HTML 明细表仍显示原始 basename；
   只有分组表（JSON `groups.project` 与文本 `by project`）折叠。
4. **`test_usage.py` 新增用例**（用现有合成 fixture 风格，别读本机真实数据）：
   - 两个夹具会话（一个 cwd 在 `%TEMP%\pi-runtime-suite-...`、一个在 `%TEMP%\pytest-of-x\pytest-1\...`）
     加一个真实项目：`groups.project` 只有一个 `(test fixtures)`，其 `calls`/`runs` 是两者之和；真实项目条目数值不变（AC-031）；
   - 同一数据 `runs[]` 里两条夹具行的 `project` 仍是各自不同原始路径（AC-032）；
   - `--project "(test fixtures)"` 只返回夹具，`--project <真实项目 basename>` 不含夹具行（AC-033）；
   - `_is_fixture_project` 的边界：`H:\git\Multi-Workers` False、`/tmp/x` True、`C:\Users\U\AppData\Local\Temp\pi-runtime-cwd-a-1` True、
     basename `pi-runtime-foo` 在任意目录下 True。
5. **README**（`packages/multi-workers/README.md`，`## 用量统计（mw stats）` 节内锚点插入）：
   在 `by project` 描述处加一句：临时目录（`%TEMP%` / `/tmp` / `/var/folders` / `C:\Windows\Temp`）与
   `pi-runtime-*` 目录在分组表里折叠为 `(test fixtures)`，`--detail` 与 `runs[].project` 仍显示原始路径。
6. **CHANGELOG**（`packages/multi-workers/CHANGELOG.md`）：在 mw-usage-monitor 的 `### Added` bullet（`static HTML report` 那条）
   **末尾追加一句**（不新建 bullet）。

## 写入允许面

- `packages/multi-workers/usage.py`（`_project_name` / `_project_matches` 附近 + 新常量/新函数；**不要动** build_report 的聚合与明细行取值）
- `packages/multi-workers/test_usage.py`
- `packages/multi-workers/README.md`（仅 `## 用量统计（mw stats）` 节）
- `packages/multi-workers/CHANGELOG.md`（仅该 bullet）
- `.agenticdoc/mw-usage-monitor/workers/um-t17-fixture-fold/report.md`

## 并发警告（必读）

`README.md` / `CHANGELOG.md` 里有**其它会话未提交的改动**（`mw decide` / claims，数千行）。只做精确锚点编辑，
禁止 `write` 整文件、禁止格式化；锚点找不到就停下汇报。`usage.py` 是纯自己的文件，可正常编辑。

## 写入禁止面

- `packages/multi-workers/mw.py`、`launcher.py`、`test_stats_cli.py`、`packages/coding-agent/**`
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_usage.py -q
python mw.py stats --since 7d --json | python -c "import sys,json;d=json.load(sys.stdin);print([g['name'] for g in d['groups']['project']][:8])"
python mw.py stats --since 7d --json --project "(test fixtures)" | python -c "import sys,json;print(json.load(sys.stdin)['runs_total'])"
python mw.py stats --since 7d --json --project E2Feature | python -c "import sys,json;d=json.load(sys.stdin);print(sorted({r['project'] for r in d['runs']}))"
```

期望：pytest 全绿；分组名里只剩一个 `(test fixtures)`（不再有 `pi-runtime-*` / `pytest-of-*` / `Temp`）；
夹具过滤的 `runs_total` 等于夹具 runs 数；`--project E2Feature` 的明细只出现 E2Feature 路径。

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：4 条验收命令真实输出、`git diff --numstat usage.py test_usage.py README.md CHANGELOG.md`。

## 改动历史

- 2026-10-21 创建（PM）：临时目录与 `pi-runtime-*` 在 `by project` 里折叠成 `(test fixtures)`。
