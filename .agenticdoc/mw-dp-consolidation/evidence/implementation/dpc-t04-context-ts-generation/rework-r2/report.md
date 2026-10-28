# dpc-t04-context-ts-generation — 测试-only R2（原逻辑 T04 一次有界新尝试）

卡：`.agenticdoc/mw-dp-consolidation/tasks/isolated/T04-context-ts-generation-r2.md`
（文件 SHA256 = `80d2d2ec0b62515f36e041bb394dc4cbf16a0fec3b825e1a3a16de7992960064`，
与 dispatch envelope 的 `card_sha256` 一致；7939 B）。人工批准：
`evidence/implementation/t04-r2-approval-20261026.md`（用户对“仅测试定点返工”问项答“继续推进”）。
本报告是本尝试唯一报告；原 T04 的 report/run/output/日志/PM 记录均未改动。

## 结论

- **状态：done（本卡允许面内完成），未做语义交接、未声明 S1/L2/QG/签收/TS 编译通过。**
- 唯一产品改动是允许面内的 `test_decide_registry_ts_lock.py`：四旧 case 边界从
  `glob("dp*.json")` + `len == 4` 改为“四旧文件按名存在 + 整个 case 目录逐文件 add/delete/rewrite 零变化”，
  并新增 12 个测试（1 个真实共存回归 + 11 个 fixture/负例安全测试）。
- **真实 behavior red 成立**：新增共存回归调用原真实检查路径，在**未修改原 assert** 时失败于
  `assert 12 == 4`（`test_decide_registry_ts_lock.py:371`，`01b-red-coexistence.log` rc=1）；
  **green 成立**：`-k` 单跑 1 passed（rc=0），完整 assigned 文件 47 passed（rc=0，连跑两次）。
- 实际执行的两只读生成模式（非 fake）：`--check` rc=0/stdout 空/stderr 空；`--stdout` 文本与磁盘 TS 同源
  （LF 折叠后 20629 B 完全相等，磁盘 bytes == `render().encode("utf-8")`）。磁盘 TS 仍为
  `8c316042…`，四只读 peer、T03 测试、T11 三个 consumer、四旧 case、原 T04 112 份证据、
  主树 git status 全部逐字节不变；1864 份镜像中只有允许测试改变。
- 已发生的**越面写事件 1 次（已清理并留史）**：我自己直接运行 parity 脚本（未走最小环境）在产品镜像
  写出 4 个 `.pyc` + 2 个 `__pycache__` 目录；已删除并复跑，终态镜像无 pyc。

## 证据

### 1. 真实 red → green（同一测试文件，同一真实检查路径）

| 阶段 | 命令（最小 env，见下） | rc | 结果 | 日志 |
| --- | --- | --- | --- | --- |
| 基线（原文件未改） | `pytest -q test_decide_registry_ts_lock.py` | 1 | 1 failed, 34 passed（**卡外旧债**，见残留 §1） | `logs/00a-baseline-35-no-utf8-locale-gbk.log` |
| 基线（UTF-8 模式） | 同上 | 0 | 35 passed | `logs/00b-baseline-35-utf8.log` |
| 仅加共存回归（原 assert 未修） | `-k "not test_case_dir_boundary_accepts_legacy_and_active_cases_together"` | 0 | 35 passed, 1 deselected（证明 `_case_dir()` 抽取行为中性） | `logs/01a-neutral-others.log` |
| **red** | `-k test_case_dir_boundary_accepts_legacy_and_active_cases_together` | 1 | **1 failed**：`assert 12 == 4` at `test_decide_registry_ts_lock.py:371` | `logs/01b-red-coexistence.log` |
| **green（单测）** | 同上 | 0 | 1 passed | `logs/02-green-coexistence.log`（修前排版）/`logs/02c-green-coexistence-final.log`（终态） |
| 中间失败（我自己新测试的 bug，非产品缺陷） | 全量 | 1 | 4 failed（`pytest.raises` 正则词序、模拟 subprocess 对 `--check` 也返回 stdout） | `logs/03a-green-assigned-attempt1.log` |
| 中间失败 2 | 全量 | 1 | 2 failed（模拟 writer 在两次调用里重复 `unlink` → ENOENT） | `logs/03b-green-assigned-attempt2.log` |
| **green（完整 assigned）** | `pytest -q test_decide_registry_ts_lock.py` | 0 | **47 passed**（35 原 + 12 新），连跑两次 | `logs/03e-green-assigned-final.log`、`logs/03f-green-assigned-final-rerun.log` |

red 的性质：不是 `pytest.raises` 包住既有缺陷，也不是自建替代 helper —— 失败点是**产品测试本体**
`test_check_and_stdout_modes_write_nothing` 里未被修改的 `assert len(legacy_cases) == 4`，
输入是 4 旧 + 8 活动（T05 固定八名）的合法 coexist 目录。负例里的“预期拒绝”全部是 green 安全测试，
不是业务 PASS。

### 2. 实际生产 `--check` / `--stdout` 与字节同源（非 fake）

`logs/04d-gen-parity-final.log`（rc=0）+ `logs/gen-parity.json` + `logs/gen-stdout.bytes`：

- 静态核绑定（全部 `True`）：`gen.__file__`、`gen._REPO_ROOT`、`gen.output_path()`、
  `decision_context.__file__`、`decision_points.__file__` 都在
  `implementation-worktree` 内；`_REPO_ROOT == <worktree>`；子进程 argv =
  `[sys.executable, "scripts/gen_decide_registry_ts.py"]`，cwd = `<worktree>/packages/multi-workers`。
- `--check`：rc=0，stdout = `b""`，stderr = `""`。
- `--stdout`：rc=0；raw 21324 B，其中 695 个 CRLF（Windows 文本模式 stdout 的 `\n`→`\r\n` 翻译）；
  **LF 折叠后 == 磁盘 20629 B 完全相等**；磁盘 bytes == `render().encode("utf-8")`（`8c316042…`，未变）。
- 明确区分：`--stdout` 走 `sys.stdout` 文本模式（CRLF）+ 读取侧 `text=True` 通用换行/本地码页解码，
  是文本见证；写入路径 `newline="\n"`，LF-only 磁盘字节才是字节见证。
- TS **未编译**（未跑 tsc / `npm run check` / build / install），本条只证明字节与 render 同源。

### 3. 保护面前后核对（`before/state.json` vs `after/state.json`，见 `logs/06-summary.json`）

- 四只读 peer 全部不变：`decision_context.py c6f5783c…`、`decision_points.py 78e72e03…`、
  `scripts/gen_decide_registry_ts.py e454cefd…`、`decide_registry.json cc017e34…`、
  `decide-registry.generated.ts 8c316042…`。
- 四旧 case 字节不变：`dp1 3131c02f…`、`dp2 a03e1a29…`、`dp3 82ff47e5…`、`dp25 bda25144…`；
  目录列表前后都是 `['dp1.json','dp2.json','dp25.json','dp3.json']`（本任务**没有**写任何产品 case）。
- 其他守卫不变：`test_decide_registry_contract.py c0e35cf1…`（T03）、`test_decision_context.py 109af0bb…`（无主，只读）、
  T11 `pm/decision-tool.ts 3c1388f5…`、`pm/triage-client.ts 70551a67…`、`shared/decide-policy.ts 572ff5fd…`。
- 整镜像：before 1864 / after 1864；`changed = [packages/multi-workers/test_decide_registry_ts_lock.py]`，
  `added = []`，`removed = []`。
- 原 T04 证据：before 112 / after 112，`delta = []`（本报告与脚本都在新子目录 `rework-r2/**`）。
- 主树 `git status --porcelain`：before/after 均 259 行、17186 B，逐字节相同（未揽他人 dirty、未写 live 源码）。
- 与 PM 11:50Z 新鲜 before 逐字节一致（`before/state.json` + `logs/06-summary.json.pm_cross_check`）：
  五文件 SHA 全部 same（含原测试 `9603a817…`）；镜像 1864、原证据 112 也一致。

### 4. 本尝试 before / after（允许测试本身）

- before：`9603a817d725f6bf16c4ab0e9b554ab2ca1d756c4fb66f5bd3cc4f6c828e635b`，22960 B，
  CRLF 0 / bare LF 599（LF-only），599 行。
- after：`26eb0493164bd4ae28c6d1c86b770eaa7d09e4aad90c715009c9262e704c26a2`，34713 B，
  CRLF 0 / bare LF 862（LF-only，**未整文件换行/格式化**），862 行。
- full diff：`after/full.diff`（3 hunks，+279 / −16 行）；摘要 `after/diff-summary.json`。
- 字节副本：`before/allowed-test.bytes.py`、`after/allowed-test.bytes.py`。

### 5. 运行环境（最小、证据本地）

`scripts/run_min.py` 统一构造：`HOME=USERPROFILE=rework-r2/env/home`、
`TEMP=TMP=rework-r2/env/temp`（pytest `tmp_path` 落在此处）、`PYTHONDONTWRITEBYTECODE=1`、
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，
并剔除 `PI_*`/`MW_*`/provider/credential-shaped env（不继承 provider/worker/project 配置）。
pytest 一律 `-p no:cacheprovider`。未跑真实 HTTP / 决策 CLI / 服务探针 / 卡外测试。

### 6. 越面写事件（含已清理，全部留史）

1. **`__pycache__` 事件（唯一真实越面写，已清理）**：我在第一次运行 `scripts/gen_parity.py` 时**直接**
   用 shell 的 python（未走 `run_min.py`，即没有 `PYTHONDONTWRITEBYTECODE=1`），导入产品模块导致在产品镜像写出：
   `packages/multi-workers/__pycache__/{decision,decision_context,decision_points}.cpython-314.pyc`、
   `packages/multi-workers/scripts/__pycache__/gen_decide_registry_ts.cpython-314.pyc`。
   由 `capture_state.py after` 与 before 的镜像清单对比发现；四文件 SHA/字节/mtime 记录在
   `logs/05-pyc-out-of-face-write.json`；随后删除 4 个 pyc 与 2 个空 `__pycache__` 目录，
   改用 `run_min.py` + `python -B` 复跑（`logs/04c`、`logs/04d`）。
   终态：镜像 1864 文件、`rglob('*.pyc') == []`、`rglob('__pycache__') == []`。
   历史留痕（清空前快照目录 `after-with-pyc-history/`）保留，不因此声称“永未越面写”。
2. **失败写尝试（无效果）**：第一次带 `--basetemp=tmp/base` 的 pytest 尝试会去
   `packages/multi-workers/tmp/base` 建目录（相对 cwd），实测 `FileNotFoundError`（`parents=False`）失败，
   未产生任何文件；已核实 `Test-Path tmp == False`，之后一律删掉该参数，只依赖证据内 `TEMP`。
3. 其余写入均在允许面：允许测试文件 + `rework-r2/**`。

### 7. 真实读到 EOF 的范围（hash 不替代阅读）

| 文件 | 行/字节 | 读取方式 |
| --- | --- | --- |
| `test_decide_registry_ts_lock.py`（改前） | 599 行 / 22960 B | 一次整读到 EOF |
| `scripts/gen_decide_registry_ts.py` | 505 行 / 21280 B | 一次整读到 EOF |
| `decision_context.py` | 323 行 / 13784 B | 一次整读到 EOF |
| `decision_points.py` | 7102 行 / 305745 B | 7 段读（offset 1/1001/2101/3201/4301/5401/6501）到 EOF |
| `T05-eight-cases.md`、`T04-context-ts-generation-r2.md`、批准文件、PM `check.json` | — | 整读 |

未读（明确声明，不称全源审计）：`decide_registry.json`（894 行）只做字节/哈希比对，未逐行读；
`decision.py`（被 context/points 传递导入）未读；PM handoff `report.md` 正文未逐行读（读了其
`check.json`、批准文件与 before-bytes 并做字节核对）；本卡以外的 T01–T03/T06–T36 卡与测试未读。

## 改动清单

产品改动（唯一）：

- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_ts_lock.py`
  - 新增 `# 0. The case-directory boundary` 段：`LEGACY_CASE_FILES`（四旧精确名）、
    `ACTIVE_CASE_FILES`（由 `dpts.ACTIVE_DP_IDS` 派生的八个 T05 文件名）、`_case_dir()`、
    `_sha256_file()`、`_case_snapshot()`（四旧缺一即拒；返回**整个目录**逐文件哈希）、
    `_assert_case_dir_unchanged()`（add/remove/change 三类都拒）、
    `_assert_bytes_unchanged()`（TS/JSON 字节见证）、`_build_case_fixture()`（证据内私有 fixture：
    真实四旧字节 + 合成的八活动 case 字节）。
  - `test_check_and_stdout_modes_write_nothing`：只替换边界实现（`glob+len==4` → 按名存在 + 全目录快照 +
    前后零变化；TS/JSON 改用 `_assert_bytes_unchanged`），并扩写 docstring 说明“整体 protect 整个 case 目录、
    四旧 + 八活动共存合法”。**两只读模式的调用与 `--stdout == before.decode()` 断言原样保留，未改断言强度。**
  - 新增 12 个测试：
    `test_case_dir_boundary_accepts_legacy_and_active_cases_together`（真实共存回归，调用真实检查体，
    并核对产品 case 目录未被这一次运行写过）；
    `test_case_dir_snapshot_requires_every_legacy_file`（缺 dp25）；
    `test_case_dir_boundary_refuses_a_changed_case_set`（5 参数：加活动/加外来文件/改活动/删活动/改旧）；
    `test_case_dir_boundary_refuses_a_deleted_legacy_case`；
    `test_boundary_refuses_a_command_that_writes_active_cases`、
    `..._rewrites_a_legacy_case`、`..._deletes_a_legacy_case`（模拟 writer 经**真实检查体**被拒；
    明确标注 fake 只证明 fixture/守卫不放水，不替代真实 generation parity）；
    `test_artifact_byte_guard_refuses_ts_and_json_drift`（fixture 副本上的 TS/JSON 漂移被拒）。
  - 无 `skip`/`xfail`，无删除既有保护：原 35 个测试全部保留（其中 34 个逐字节未动，1 个只改边界实现与 docstring）。

证据（全部在 `rework-r2/**`，未动原 T04 证据）：

- `report.md`（本文件）
- `scripts/capture_state.py`、`scripts/run_min.py`、`scripts/gen_parity.py`、`scripts/make_diff.py`、`scripts/summarize.py`
- `before/`（`allowed-test.bytes.py`、`state.json`=五文件 + 四旧 case + 守卫 + 1864 镜像 + 112 原证据清单、`live-git-status.txt`）
- `after/`（同结构 + `full.diff`、`diff-summary.json`）、`after-pre-format/`（终态排版前的中间快照）、
  `after-with-pyc-history/`（pyc 事件时点快照）
- `logs/`（00a…04d 全部原始 stdout/stderr/rc、`gen-parity.json`、`gen-stdout.bytes`、
  `05-pyc-out-of-face-write.json`、`06-summary.json`）
- `env/`（私有 HOME/TEMP；pytest tmp 也在此）、`tmp/`、`fixtures/`（空）

## 残留与未验证

1. **卡外旧债：`--stdout` 断言的 locale 依赖（真实存在，未修）**。原测试
   `subprocess.run(..., text=True)` 未传 `encoding`，父进程按本地码页解码子进程 stdout；本机默认 GBK，
   生成的模块含 UTF-8 的 em dash 与中文 note → 读取线程 `UnicodeDecodeError`，`stdout` 变 `None`，
   `assert printed.stdout == before.decode("utf-8")` 失败（`logs/00a-…log`，发生在**未改动的原文件**上，
   与本次改动无关）。因此本尝试所有 green 都在 UTF-8 模式
   （`PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`，与 PM 11:24Z 的 35 passed 同一前提）下取得；
   裸跑验收命令在本机仍会红。建议由后续获批卡在处理该断言时显式 `encoding="utf-8"`
   —— 这属于“卡外旧债”，**不在本卡授权范围内，我未修**。
2. **T05 未派发**：八活动 case 的**业务有效性/字节**未被本任务证明，共存只用到合成标记
   （`{"_synthetic": true, "case": "<name>.json"}`）；四旧 + 八活动的合法性是“阶段合法性”判断，
   不是 T05 产物验收。
3. **TS 未编译**：未跑 tsc / `npm run check` / build / install；生成 TS 只证明与 `render()` 字节同源
   （Windows stdout CRLF 与磁盘 LF 已分述）。真实 `biome` formatter 等价性未验（原属 T32）。
4. 未做：`lgtm`/L2/VC/QG/签收/phase gate 判定；未跑卡外任何测试文件；未做全活树/全源审计，
   未证明“无人工 writer”，未用 mtime/空队列作证明。
5. 原 `dp4-failure-handling` 决策服务仍是 UNAVAILABLE/input-incomplete（PM 11:24Z 记录），
   本卡**未重问、未绕通道、未修活桥、未伪造 receipt**；本次由具体人工批准提供有界处理权限。
6. 预算/时间：本卡未给分钟预算，未私设 timeout、未重置预算、未申请新授权；有界收口时未记录剩余预算（null/未知）。
7. 历史 pyc 事件（§证据 6.1）虽已清理，仍作为越面写历史保留；清空后的镜像快照见
   `after-with-pyc-history/`。清理动作本身是对产品镜像的删除操作，已在报告中显式登记。

## 上下文来源

- 项目目标 `.agenticdoc/goal.md:5`；本卡 `tasks/isolated/T04-context-ts-generation-r2.md`（SHA `80d2d2ec…`）
  与 worker 派发卡 `workers/dpc-t04-context-ts-generation-r2/task.md`（SHA `8de0a3ea…`）。
- 人工批准：`evidence/implementation/t04-r2-approval-20261026.md`（用户原文“继续推进”，
  仅批准测试文件定点返工）。
- PM 实证与新鲜 before：`evidence/implementation/t04-pm-handoff-20261026/{report.md,check.json,probe.json,probe.py,pm-green.log}`
  与 `evidence/implementation/t04-r2-pre-dispatch-20261026/{check.json,before-bytes/…}`；
  本次五文件 before 与其逐字节相同（`logs/06-summary.json.pm_cross_check`）。
- 读过的协作文本：`tasks/isolated/T05-eight-cases.md`（八 case 固定名与“四旧只读”）、
  原 T04 卡 `tasks/isolated/T04-context-ts-generation.md`（五产品面，本卡未沿用其权限）。
- 源码：允许测试（改前全文）、`scripts/gen_decide_registry_ts.py`、`decision_context.py`、
  `decision_points.py`（均读到 EOF）、`decide_registry.json`（仅字节/哈希）。
- 运行事实：本报告 `logs/**`、`before/**`、`after/**`（全部为本次真实 rc/stdout/stderr 与字节记录）。
