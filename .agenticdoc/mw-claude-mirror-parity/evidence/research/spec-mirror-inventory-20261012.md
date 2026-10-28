# SPEC 证据：权威脚本与分发副本全量清点（RQ-1）

- key：`mw-claude-mirror-parity`｜阶段：SPEC｜日期：2026-10-12｜RQ-1
- worker：`mwp-rq1c-mirror-inventory`｜类型：research（只读）
- 唯一写入：`.agenticdoc/mw-claude-mirror-parity/evidence/research/spec-mirror-inventory-20261012.md`
- 后端：Windows / bash 后端 PowerShell 5.1（无 Git bash）；python 3.14.3（`C:/Users/wenbozhou/AppData/Local/Python/pythoncore-3.14-64/python.exe`）；node v24.19.0；ripgrep 15.2.0
- 纪律：实测优先，本节所有数字均来自本机命令原始输出；临时脚本写在 worker 目录（`.tmp/` 被写面守卫禁止，见 §7）

## 0. 结论摘要

1. **权威 = `.agents/skills/agentic-task/scripts/**`（16 个 .py）**；`.agents/skills/agentic-task/{claude,core}/scripts/**` 是 `install.py:sync_script_mirrors()` 从 `scripts/` 逐字节覆写出来的镜像（`install.py:30,41-68`）。
2. 全仓同名副本共 **6 处目录 / 96 个 .py 文件**（不含 worker 自己的合成夹具）：`core/scripts`、`claude/scripts`、`.claude/scripts`、`packages/multi-workers/.tmp/agentic-task/{scripts,core/scripts,claude/scripts}`。其中 **`claude/scripts` 与 `core/scripts` 互为逐字节相同**；`.tmp` 三份互为逐字节相同。
3. **门禁语义缺口只落在 `update_index.py` 一个文件上**：6 个副本目录里 `update_index.py` 全部缺 `RESERVED_INDEX_NAMES` / `key_name_refusal`（AC-006/T-16 键名门禁）与 `normalize_key` 比较，删除量 149 到 155 行；其余 15 个文件在 `core/scripts`、`claude/scripts`、`.claude/scripts` 三处要么逐字节相同，要么只有少量注释/断言级差异。
4. **运行时「真正执行权威还是副本」取决于消费者，实测两者都有**：
   - pi 侧 PM 工具 `advance_phase`（`pm/ui-bridge.ts:2345` 经 `shared/agentic-scripts.ts:45`）解析出的目录实测为 **`H:/git/Multi-Workers/.claude/scripts`（副本）**，且端到端跑出的行为就是**无键名门禁的旧副本行为**（§4.3）。
   - mw autopilot（`packages/multi-workers/autopilot/advance.py:154,170`）经 `detect_root.py --json` 的 `PLATFORM_DIR` 实测为 **`H:/git/Multi-Workers/.agents/skills/agentic-task`（权威）**（§4.4）。
5. `.claude/scripts/advance_phase.py` 与权威**逐字节相同**，但 `advance_phase.py:599` 用 `Path(__file__).parent / "update_index.py"` 调同目录兄弟脚本，所以在 pi 侧链路上「新 advance_phase + 旧 update_index」被混用：门禁通过后写 `_index.parallel` 的那一步走的是无键名门禁的副本（§4.3、§4.5）。

## 1. 权威表：`.agents/skills/agentic-task/scripts/**`

命令（逐个文件，字节 + sha256）：

```powershell
Get-ChildItem .agents/skills/agentic-task/scripts -File | ForEach-Object { $_.Name, $_.Length, (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
```

| 文件 | 字节 | sha256 | `^def`/`^class` 符号数 |
|---|---|---|---|
| `advance_phase.py` | 26852 | `9427abe2ecc0366b31a861241e38644a2f0e828e376488336b6dbd0d511bc63f` | 12 |
| `audit_phase.py` | 8270 | `bc82f305320d396da75586c13ed295cc6ed2a904524d507f7b0feeb7e6a85a4b` | 6 |
| `check_mermaid.py` | 5569 | `b80af059ffdf879f57571dadc418e424f563edb39d34031a9e95a5f3a1f13c6f` | 4 |
| `detect_root.py` | 11608 | `369a45d3add686a29d251362667c31ab20c04d7ca9f849023220caaf99d3cd86` | 9 |
| `guard_pm_state.py` | 1540 | `a5f29401d375cecaf6b60b4e8d683b69c6065f8908dd766dab4cf407ae3e4062` | 2 |
| `migrate_patterns.py` | 8551 | `44cdc967de87b459b921a27461b9497f4201d7399b1df958b51ca5a83dfd821e` | 7 |
| `sync_framework.py` | 9010 | `d574718e0340d1301426a49d5906dcc8a66b6be4644773da86a3f2d54e8a2be9` | 15 |
| `test_advance_phase.py` | 26479 | `769d4aa28fcb54df73dabd3024074a49ac13ded5920cf7b8e833da58511de3dc` | 6 |
| `test_audit_phase.py` | 10741 | `b42e92e9f34a7f8f966b67261ebb68ca452bb44911aa8d7e7bdcb7834cfd90f5` | 3 |
| `test_detect_root.py` | 5449 | `feed5771143b4f3f13175aa6a31a9e8d9d648b65913c093c82be75cacf20b1e0` | 2 |
| `test_install.py` | 4254 | `ce3d905d33fce8036577b1b1a7b3266d69847770dfba875189f62ebcfa2ee340` | 2 |
| `test_migrate_patterns.py` | 7431 | `d8ec462d4640103f65dfc385b91e2a8c109f5d91a7983de027440f7c23757f1b` | 2 |
| `test_sync_framework.py` | 3752 | `65344a27ebdd548f471dc4c5a16d6eb76e75b441fedb9b067b159b51cf34474a` | 2 |
| `test_update_index.py` | 11195 | `f68b630e4f2cbb3dd472b2fcf2d15fd00aebfbcf2e2e2e229ca25d27b0f67faf` | 3 |
| `update_index.py` | 28884 | `6bc10453390b9908fdeabf5fca0d19bfe7f145ea7429f36c3d40db0c038c7400` | 24 |
| `verify_project_memory.py` | 5372 | `e07a2f69b5d2b7419ec8ab30d78573356602bb01fd21598bd00a02ea38ba5c83` | 4 |

（`scripts/` 下无子目录文件、无其它扩展名文件；只有 16 个 `.py`，另有 `__pycache__/`、`.pytest_cache/` 两个目录。）

### 1.1 权威文件符号表（行号 + 原始签名行）

**`advance_phase.py`**（26852 字节）

```
35:def now_ts() -> str:
99:def find_root():
114:def _strip_comments(text: str) -> str:
119:def _has_table_data(path: Path) -> bool:
141:def _section_nonempty(spec_text: str, section_kw: str) -> bool:
150:def _section_body(text: str, section_kw: str) -> str:
174:def _goal_established(root: Path) -> bool:
191:def check_gate(key_dir: Path, target: str):
292:def update_pm_state(key_dir: Path, key: str, target_phase: str):
426:def _git_short_head(cwd: Path) -> str:
443:def append_project_log(root: Path, key: str, summary: str = "—", supersedes: str = "—", ts: str = None):
499:def main():
```

**`audit_phase.py`**（8270 字节）

```
43:def _pm_state_phase(key_dir: Path) -> str | None:
59:def _index_phase(root: Path, key: str) -> str | None:
84:def audit_key(root: Path, key: str) -> tuple[bool, list[str]]:
144:def _iter_keys(root: Path) -> list[str]:
164:def cmd_all(root: Path) -> int:
183:def main() -> int:
```

**`check_mermaid.py`**（5569 字节）

```
34:def _extract_blocks(text: str):
54:def _check_block(body):
104:def check_mermaid_file(path):
120:def main():
```

**`detect_root.py`**（11608 字节）

```
59:def detect_platform_dir() -> str:
110:def _is_local(platform_dir: str) -> bool:
121:def _read_code_workspace(ws_file: Path) -> str | None:
133:def _scan_ide_config(start: Path) -> tuple[str, str] | None:
151:def _scan_project_markers(start: Path) -> tuple[str, str] | None:
171:def _scan_specific_markers(start: Path, markers: list[str]) -> tuple[str, str] | None:
189:def prefer_cwd_project(root: str, method: str) -> tuple[str, str]:
205:def detect_project_root(platform_dir: str) -> tuple[str, str]:
252:def main() -> int:
```

**`guard_pm_state.py`**（1540 字节）

```
15:def _advance_phase_path() -> str:
20:def main():
```

**`migrate_patterns.py`**（8551 字节）

```
43:def find_root() -> Path | None:
56:def _rel(root: Path, p: Path) -> str:
61:def _free_conflict_dst(dst: Path, reserved: set[str]) -> Path:
75:def _prune_empty_dirs(src_dir: Path) -> bool:
98:def migrate(root: Path, dry_run: bool = False) -> dict:
162:def _render(result: dict) -> str:
193:def main() -> int:
```

**`sync_framework.py`**（9010 字节）

```
36:class CommandResult:
43:class SyncResult:
52:def run_command(cmd, cwd=None, check=True, capture_output=False, text=True) -> CommandResult:
66:def read_manifest(project: Path) -> dict[str, str]:
85:def find_project_root(start: Path) -> Path:
97:def copy_tree(src: Path, dst: Path) -> None:
105:def sync_installed_to_repo(
139:def repo_status(repo: Path, runner: Runner) -> str:
148:def current_branch(repo: Path, runner: Runner) -> str:
157:def installed_differs(project: Path, repo: Path, runner: Runner) -> bool:
171:def run_tests(repo: Path, runner: Runner) -> None:
185:def reinstall(project: Path, repo: Path, runner: Runner) -> None:
190:def commit_and_push(repo: Path, message: str, remote: str, branch: str | None, runner: Runner) -> None:
197:def sync_framework(
237:def main() -> int:
```

**`test_advance_phase.py`**（26479 字节）

```
27:def _v(vc, **kv):
31:class MemoryExtTest(unittest.TestCase):
313:class TemplateDriftTest(unittest.TestCase):
387:class DoneSummaryContractTest(unittest.TestCase):
446:class ClaimStubUpgradeTest(unittest.TestCase):
544:class FindRootCwdFirstTest(unittest.TestCase):
```

**`test_audit_phase.py`**（10741 字节）

```
27:def _v(vc, **kv):
31:def _write(path: Path, text: str):
36:class AuditPhaseTest(unittest.TestCase):
```

**`test_detect_root.py`**（5449 字节）

```
9:class DetectRootTests(unittest.TestCase):
77:class PreferCwdProjectTests(unittest.TestCase):
```

**`test_install.py`**（4254 字节）

```
24:def _v(vc, **kv):
29:class SyncScriptMirrorsTest(unittest.TestCase):
```

**`test_migrate_patterns.py`**（7431 字节）

```
23:def _v(vc, **kv):
27:class MigrateTest(unittest.TestCase):
```

**`test_sync_framework.py`**（3752 字节）

```
8:class FakeRunner:
24:class SyncFrameworkTests(unittest.TestCase):
```

**`test_update_index.py`**（11195 字节）

```
22:def _v(vc, **kv):
26:class ClaimInterfaceTest(unittest.TestCase):
155:class CommandKeyGateTest(unittest.TestCase):
```

**`update_index.py`**（28884 字节）

```
108:def normalize_key(key: str) -> str:
118:def key_name_refusal(key: str) -> tuple[str, str] | None:
162:def _key_name_error(key: str) -> int | None:
177:def now_ts_min() -> str:
181:def now_claim_id() -> str:
189:def _pid_is_gone(pid: int) -> bool:
220:def claim_is_stale_local(claim_id: str) -> bool:
234:def _index_lock(root: Path, retries: int = 10, base_delay: float = 0.05):
264:def find_root() -> Path | None:
281:def _parse_row(line: str) -> dict | None:
306:def _row_line(key: str, status: str, phase: str, claim_id: str,
311:def read_index(index_path: Path) -> list[dict]:
325:def _serialize_rows(rows: list[dict]) -> str:
335:def _write_index_atomic(index_path: Path, mutate_fn) -> None:
375:def _ensure_index(index_path: Path) -> None:
385:def _update_pm_state_claim(key_dir: Path, claim_id: str) -> None:
447:def _audit_after_claim(root: Path, key: str) -> None:
478:def cmd_claim(root: Path, key: str, force: bool,
542:def cmd_set_phase(root: Path, key: str, phase: str) -> int:
569:def cmd_set_meta(root: Path, key: str, desc: str | None, deps: str | None) -> int:
598:def cmd_release(root: Path, key: str) -> int:
629:def cmd_get_claim(root: Path, key: str) -> int:
646:def cmd_list(root: Path, as_json: bool) -> int:
668:def main() -> int:
```

**`verify_project_memory.py`**（5372 字节）

```
15:def _find_agenticdoc() -> Path | None:
35:def check(vc, cond, **info):
42:def has(path, *needles):
70:def full_rebuild(keys):
```

## 2. 副本表（路径 / 字节 / sha256 / 差异类型）

判定规则（脚本 `_tmp_cmp2.py`，逐文件与权威同名文件比）：

- `IDENTICAL`：原始字节相同（sha256 相同）
- `FORMAT-ONLY`：UTF-8 解码、去 BOM、CRLF/CR 归一化后相同（即只差换行符或 BOM）
- `SEMANTIC(add/del/chg)`：归一化后仍不同；数字 = `difflib.SequenceMatcher` 的插入 / 删除 / 替换行数

原始输出（完整、逐文件）：

```
## .agents\skills\agentic-task\scripts
   advance_phase.py            26852 9427abe2ecc0366b AUTHORITATIVE
   audit_phase.py               8270 bc82f305320d396d AUTHORITATIVE
   check_mermaid.py             5569 b80af059ffdf879f AUTHORITATIVE
   detect_root.py              11608 369a45d3add686a2 AUTHORITATIVE
   guard_pm_state.py            1540 a5f29401d375ceca AUTHORITATIVE
   migrate_patterns.py          8551 44cdc967de87b459 AUTHORITATIVE
   sync_framework.py            9010 d574718e0340d130 AUTHORITATIVE
   test_advance_phase.py       26479 769d4aa28fcb54df AUTHORITATIVE
   test_audit_phase.py         10741 b42e92e9f34a7f8f AUTHORITATIVE
   test_detect_root.py          5449 feed5771143b4f3f AUTHORITATIVE
   test_install.py              4254 ce3d905d33fce803 AUTHORITATIVE
   test_migrate_patterns.py     7431 d8ec462d4640103f AUTHORITATIVE
   test_sync_framework.py       3752 65344a27ebdd548f AUTHORITATIVE
   test_update_index.py        11195 f68b630e4f2cbb3d AUTHORITATIVE
   update_index.py             28884 6bc10453390b9908 AUTHORITATIVE
   verify_project_memory.py     5372 e07a2f69b5d2b741 AUTHORITATIVE

## .agents\skills\agentic-task\core\scripts
   advance_phase.py            26852 9427abe2ecc0366b IDENTICAL
   audit_phase.py               8270 bc82f305320d396d IDENTICAL
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              11608 369a45d3add686a2 IDENTICAL
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8551 44cdc967de87b459 IDENTICAL
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       26479 769d4aa28fcb54df IDENTICAL
   test_audit_phase.py         10741 b42e92e9f34a7f8f IDENTICAL
   test_detect_root.py          5449 feed5771143b4f3f IDENTICAL
   test_install.py              4254 ce3d905d33fce803 IDENTICAL
   test_migrate_patterns.py     7431 d8ec462d4640103f IDENTICAL
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py         7118 407a550d078fb68d SEMANTIC(add=0 del=89 chg=0)
   update_index.py             22492 6ea8a1ea0300aaca SEMANTIC(add=0 del=149 chg=8)
   verify_project_memory.py     5372 e07a2f69b5d2b741 IDENTICAL

## .agents\skills\agentic-task\claude\scripts
   advance_phase.py            26852 9427abe2ecc0366b IDENTICAL
   audit_phase.py               8270 bc82f305320d396d IDENTICAL
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              11608 369a45d3add686a2 IDENTICAL
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8551 44cdc967de87b459 IDENTICAL
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       26479 769d4aa28fcb54df IDENTICAL
   test_audit_phase.py         10741 b42e92e9f34a7f8f IDENTICAL
   test_detect_root.py          5449 feed5771143b4f3f IDENTICAL
   test_install.py              4254 ce3d905d33fce803 IDENTICAL
   test_migrate_patterns.py     7431 d8ec462d4640103f IDENTICAL
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py         7118 407a550d078fb68d SEMANTIC(add=0 del=89 chg=0)
   update_index.py             22492 6ea8a1ea0300aaca SEMANTIC(add=0 del=149 chg=8)
   verify_project_memory.py     5372 e07a2f69b5d2b741 IDENTICAL

## .claude\scripts
   advance_phase.py            26852 9427abe2ecc0366b IDENTICAL
   audit_phase.py               7876 e3b5fdf2f2754857 SEMANTIC(add=0 del=0 chg=5)
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              11608 369a45d3add686a2 IDENTICAL
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8551 44cdc967de87b459 IDENTICAL
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       26479 769d4aa28fcb54df IDENTICAL
   test_audit_phase.py          9343 7fe419ffabbb35ec SEMANTIC(add=0 del=22 chg=3)
   test_detect_root.py          5449 feed5771143b4f3f IDENTICAL
   test_install.py              4254 ce3d905d33fce803 IDENTICAL
   test_migrate_patterns.py     7431 d8ec462d4640103f IDENTICAL
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py         5671 cb4600a8902ab6fe SEMANTIC(add=0 del=113 chg=0)
   update_index.py             22026 0b8f7128158d0945 SEMANTIC(add=0 del=155 chg=8)
   verify_project_memory.py     5372 e07a2f69b5d2b741 IDENTICAL

## packages\multi-workers\.tmp\agentic-task\scripts
   advance_phase.py            26521 4111bff403bc4c8b SEMANTIC(add=0 del=0 chg=11)
   audit_phase.py               8083 a147bec9e9d88475 SEMANTIC(add=0 del=0 chg=5)
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              10766 bfcfe25698b02c7b SEMANTIC(add=0 del=17 chg=0)
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8637 247ef5d9daa5f066 SEMANTIC(add=0 del=0 chg=9)
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       25755 51dbdf55c4ff2e16 SEMANTIC(add=0 del=19 chg=0)
   test_audit_phase.py          9538 275b74cd0b9a3f13 SEMANTIC(add=0 del=22 chg=3)
   test_detect_root.py          3012 670d9d59d538d491 SEMANTIC(add=0 del=58 chg=0)
   test_install.py              4350 296cbfdac5ba5614 FORMAT-ONLY(crlf=True)
   test_migrate_patterns.py     7596 f781f6aab95d2028 FORMAT-ONLY(crlf=True)
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py         5803 a809852f20ef563a SEMANTIC(add=0 del=113 chg=0)
   update_index.py             21820 b803ee9b2259525d SEMANTIC(add=0 del=155 chg=17)
   verify_project_memory.py     4838 866a1a717afba250 SEMANTIC(add=0 del=0 chg=13)

## .tmp\rq3c-fake\agentic-task\scripts
   advance_phase.py            26852 9427abe2ecc0366b IDENTICAL
   audit_phase.py               8270 bc82f305320d396d IDENTICAL
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              11608 369a45d3add686a2 IDENTICAL
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8551 44cdc967de87b459 IDENTICAL
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       26479 769d4aa28fcb54df IDENTICAL
   test_audit_phase.py         10741 b42e92e9f34a7f8f IDENTICAL
   test_detect_root.py          5449 feed5771143b4f3f IDENTICAL
   test_install.py              4254 ce3d905d33fce803 IDENTICAL
   test_migrate_patterns.py     7431 d8ec462d4640103f IDENTICAL
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py        11195 f68b630e4f2cbb3d IDENTICAL
   update_index.py             28884 6bc10453390b9908 IDENTICAL
   verify_project_memory.py     5372 e07a2f69b5d2b741 IDENTICAL

## .tmp\rq3c-fake\project\.claude\scripts
   advance_phase.py            26852 9427abe2ecc0366b IDENTICAL
   audit_phase.py               8270 bc82f305320d396d IDENTICAL
   check_mermaid.py             5569 b80af059ffdf879f IDENTICAL
   detect_root.py              11608 369a45d3add686a2 IDENTICAL
   guard_pm_state.py            1540 a5f29401d375ceca IDENTICAL
   migrate_patterns.py          8551 44cdc967de87b459 IDENTICAL
   sync_framework.py            9010 d574718e0340d130 IDENTICAL
   test_advance_phase.py       26479 769d4aa28fcb54df IDENTICAL
   test_audit_phase.py         10741 b42e92e9f34a7f8f IDENTICAL
   test_detect_root.py          5449 feed5771143b4f3f IDENTICAL
   test_install.py              4254 ce3d905d33fce803 IDENTICAL
   test_migrate_patterns.py     7431 d8ec462d4640103f IDENTICAL
   test_sync_framework.py       3752 65344a27ebdd548f IDENTICAL
   test_update_index.py        11195 f68b630e4f2cbb3d IDENTICAL
   update_index.py             28884 6bc10453390b9908 IDENTICAL
   verify_project_memory.py     5372 e07a2f69b5d2b741 IDENTICAL
```

### 2.1 按副本目录汇总

| 副本目录 | 文件数 | 逐字节相同 | 仅格式差异 | 语义差异 | 语义差异涉及文件 |
|---|---|---|---|---|---|
| `.agents/skills/agentic-task/claude/scripts` | 16 | 14 | 0 | 2 | `update_index.py`(del149,chg8)、`test_update_index.py`(del89) |
| `.agents/skills/agentic-task/core/scripts` | 16 | 14 | 0 | 2 | 同上（与 `claude/scripts` 互为逐字节相同） |
| `.claude/scripts`（**pi 侧活副本**） | 16 | 12 | 0 | 4 | `update_index.py`(del155,chg8)、`audit_phase.py`(chg5)、`test_update_index.py`(del113)、`test_audit_phase.py`(del22,chg3) |
| `packages/multi-workers/.tmp/agentic-task/scripts` | 16 | 6 | 2 | 8 | `update_index.py`(del155,chg17)、`advance_phase.py`(chg11)、`audit_phase.py`(chg5)、`detect_root.py`(del17)、`migrate_patterns.py`(chg9)、`verify_project_memory.py`(chg13)、`test_advance_phase.py`(del19)、`test_detect_root.py`(del58)、`test_audit_phase.py`(del22,chg3)、`test_update_index.py`(del113)；`test_install.py`/`test_migrate_patterns.py` 为 CRLF 格式差异 |
| `packages/multi-workers/.tmp/agentic-task/core/scripts` | 16 | 6 | 2 | 8 | 与上一行逐字节相同 |
| `packages/multi-workers/.tmp/agentic-task/claude/scripts` | 16 | 6 | 2 | 8 | 与上一行逐字节相同 |

补充事实：

- `.agents/skills/agentic-task/claude/scripts` 与 `.../core/scripts` **16/16 逐字节相同**（实测：逐文件 SHA256 比对，无 DIFF 输出）。
- `packages/multi-workers/.tmp/agentic-task/{scripts,core/scripts,claude/scripts}` 三份也互为逐字节相同。
- `.tmp` 系列大小为 21820（update_index.py）与 26521（advance_phase.py），**小于**权威的 28884 / 26852 ⇒ 该套是更早的快照，不是分叉新增。
- `.claude/scripts/update_index.py` 为 22026 字节，比 `.tmp` 的 21820 大、比 `claude/scripts` 的 22492 小 ⇒ `.claude` 是第三套独立历史版本（三者互不相同）。

### 2.2 活副本 `.claude/scripts` 的完整语义差异（逐 hunk 原始输出）

```diff
=== FULL DIFF .claude/scripts ===
#### .claude/scripts/update_index.py  vs  auth/update_index.py
--- auth/update_index.py
+++ .claude/scripts/update_index.py
@@ -6,8 +6,2 @@
   Phase  — project phase: SPEC / DESIGN / PLAN / TASKS / EXECUTE / VERIFY / DONE / —
-           A freshly claimed row carries '—' (this script) or 'SPEC' (the TS client,
-           agent-team-loop's IndexStore.claim); pm-state's claim stub carries 'init'.
-           All three mean "not started yet": audit_phase.py treats init/'—'/'' as
-           pending (nothing to audit), so the two-source consistency check only judges
-           real phases and the first advance_phase.py call normalizes both files to an
-           upper-case phase.
   Deps   — comma-separated dependency key names (or —)
@@ -57,119 +51,2 @@
 TS_MIN_FMT = "%Y-%m-%d %H:%M"
-
-
-# ---------------------------------------------------------------------------
-# Key identity (AC-006 / RQ-5)
-#
-# Same name gate as the TS `shared/index-store.ts` `keyNameRefusal`: Python and
-# TS cannot physically share the function, so this is a same-semantics copy
-# pinned by `test_update_index_key_refusal.py` (golden table diffed against the
-# real TS module through node; node missing = fail, never skip).
-# ---------------------------------------------------------------------------
-
-# Reserved `.agenticdoc/` root entries that name framework files/dirs, not
-# AgenticTask key namespaces (RQ-5's 12 names + `_impl_gate.log` +
-# `_incidents`). Stored lower-case; membership is tested through normalize_key.
-RESERVED_INDEX_NAMES = (
-    "_scratch",
-    ".mw",
-    "_index.parallel",
-    "_index.md",
-    "_workers.parallel",
-    "_workers.stale.parallel",
-    "_workers.acked",
-    "_autopilot",
-    "_project_log.md",
-    "_arch_snapshot.md",
-    "_pitfalls.md",
-    ".agenticdoc",
-    "_impl_gate.log",
-    "_incidents",
-)
-RESERVED_INDEX_NAME_SET = frozenset(RESERVED_INDEX_NAMES)
-
-# JS `String.prototype.trim` whitespace set. Python `str.strip()` covers most
-# of it but misses U+FEFF (which JS trims) and strips \x1c-\x1f / \x85 (which
-# JS does not); the explicit set keeps both sides equal on hostile input
-# (same set as mw_common._JS_TRIM_CHARS, T-08 precedent).
-_JS_TRIM_CHARS = (
-    "\t\n\v\f\r \u00a0\ufeff\u2028\u2029"
-    "\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
-    "\u202f\u205f\u3000"
-)
-
-# Shape of a usable key name: alnum first char, then alnum / `.` / `_` / `-`.
-KEY_MAX_LENGTH = 64
-_KEY_SHAPE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
-_KEY_ILLEGAL_CHARS_RE = re.compile(r'[\u0000-\u001f\u007f:<>"|?*]')
-_KEY_PATH_SEP_RE = re.compile(r"[/\\]")
-_KEY_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
-
-
-def normalize_key(key: str) -> str:
-    """Comparison form of a key: JS-trimmed and lower-cased (TS normalizeKey).
-
-    Windows filesystems are case-insensitive, so `MW-KEY` and `mw-key` name
-    the SAME directory; reads/lookups normalize while stored bytes keep their
-    first-written casing (no migration).
-    """
-    return key.strip(_JS_TRIM_CHARS).lower()
-
-
-def key_name_refusal(key: str) -> tuple[str, str] | None:
-    """Stable (code, message) of a refused key name, or None when usable.
-
-    Same decision tree and stable codes as the TS `keyNameRefusal`
-    (shared/index-store.ts): empty-key | reserved-key-name | key-path-escape |
-    key-illegal-shape. Every claim entry point must refuse on a non-None
-    result; `_scratch` is reserved here too (owner-exempt in the TS guard,
-    never claimable).
-    """
-    trimmed = key.strip(_JS_TRIM_CHARS)
-    if not trimmed:
-        return ("empty-key", "the key is empty")
-    if normalize_key(trimmed) in RESERVED_INDEX_NAME_SET:
-        return (
-            "reserved-key-name",
-            f"'{trimmed}' is a reserved framework name, not an AgenticTask key namespace",
-        )
-    if trimmed in (".", ".."):
-        return ("key-path-escape", f"'{trimmed}' escapes the .agenticdoc root")
-    if _KEY_PATH_SEP_RE.search(trimmed) or _KEY_DRIVE_PREFIX_RE.match(trimmed):
-        return (
-            "key-path-escape",
-            f"'{trimmed}' contains a path separator or drive prefix",
-        )
-    if len(trimmed) > KEY_MAX_LENGTH:
-        return (
-            "key-illegal-shape",
-            f"the key is {len(trimmed)} chars (max {KEY_MAX_LENGTH})",
-        )
-    if trimmed.endswith("."):
-        return ("key-illegal-shape", f"'{trimmed}' ends with '.'")
-    if _KEY_ILLEGAL_CHARS_RE.search(trimmed):
-        return (
-            "key-illegal-shape",
-            f"'{trimmed}' contains a control, ADS or shell metacharacter",
-        )
-    if not _KEY_SHAPE_RE.fullmatch(trimmed):
-        return (
-            "key-illegal-shape",
-            f"'{trimmed}' does not match ^[A-Za-z0-9][A-Za-z0-9._-]*$",
-        )
-    return None
-
-
-def _key_name_error(key: str) -> int | None:
-    """Gate a key name before any disk write: rc 1 + stderr when refused.
-
-    Shared by every command that could create/touch an index row (T-16), so a
-    reserved / illegal / escaping name is refused uniformly (DD-07b/DD-07c)
-    instead of only on `claim`. `None` = name is usable; callers keep going.
-    """
-    refusal = key_name_refusal(key)
-    if refusal is None:
-        return None
-    code, message = refusal
-    print(f"ERROR: refused key name ({code}): {message}", file=sys.stderr)
-    return 1
 
@@ -479,12 +356,2 @@
               desc: str = "—", deps: str = "—") -> int:
-    # Key name gate (AC-006): reserved/illegal names never reach the index, so
-    # `claim _index.parallel` / `claim _tmp` / `claim ../x` cannot create an
-    # active row in (or outside) a framework namespace. `_scratch` is refused
-    # here too: usable as an owner key, never claimable.
-    refusal = key_name_refusal(key)
-    if refusal is not None:
-        code, message = refusal
-        print(f"ERROR: refused key name ({code}): {message}", file=sys.stderr)
-        return 1
-
     index_path = root / INDEX_FILE
@@ -494,3 +361,3 @@
     rows_now = read_index(index_path)
-    existing = next((r for r in rows_now if normalize_key(r["key"]) == normalize_key(key)), None)
+    existing = next((r for r in rows_now if r["key"] == key), None)
     if existing and existing["status"] == "active" and not force:
@@ -514,6 +381,6 @@
         for r in rows:
-            if normalize_key(r["key"]) != normalize_key(key) and r["status"] == "active":
+            if r["key"] != key and r["status"] == "active":
                 r["status"] = "idle"
                 r["updated"] = updated
-        row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)
+        row = next((r for r in rows if r["key"] == key), None)
         if row:
@@ -543,7 +410,2 @@
     """Update the Phase column for a key. Creates row if absent (idle)."""
-    # T-16: name gate before `_ensure_index`, so a refused name is rc=1 with
... truncated

#### .claude/scripts/audit_phase.py  vs  auth/audit_phase.py
--- auth/audit_phase.py
+++ .claude/scripts/audit_phase.py
@@ -34,7 +34,3 @@
 
-# pm-state 中"尚未开始"的占位 phase（claim 桩 / 初始态），无事可审计。
-# 'SPEC' 刻意不在列：pm-state 写 SPEC 表示已进入 spec 阶段，门禁必须真查。
-# 索引列的两个占位（update_index.py claim 写 '—'，TS 客户端 agent-team-loop 的
-# IndexStore.claim 写 'SPEC'）都对应 pm-state 的 pending 态，所以两源一致性检查
-# 在 pending 时短路——divergence 只在真实相位上判定，新 claim 的 key 不误报。
+# pm-state 中"尚未开始"的占位 phase（claim 桩 / 初始态），无事可审计
 PENDING_PHASES = {"(pending)", "init", "—", ""}

#### .claude/scripts/test_update_index.py  vs  auth/test_update_index.py
--- auth/test_update_index.py
+++ .claude/scripts/test_update_index.py
@@ -129,115 +129,2 @@
 
-    def test_vc030_claim_phase_placeholders_are_pending(self):
-        # 新 claim 的 key 在两个文件里各有一个"尚未开始"占位：索引列 '—'（本脚本）
-        # 与 pm-state 桩 'init'（TS 客户端 IndexStore.claim 则把索引列写成 'SPEC'）。
-        # 三者必须都被 audit_phase 当 pending：否则新 key 会被误判两源分叉，或在
-        # 毫无证据时被重放 spec 门禁而误报 FAIL。
-        import audit_phase as au
-        key_dir = self.root / "k-new"
-        with contextlib.redirect_stdout(io.StringIO()), \
-                contextlib.redirect_stderr(io.StringIO()) as err:
-            rc = ui.cmd_claim(self.root, "k-new", force=False)
-        self.assertEqual(rc, 0)
-        self.assertNotIn("[audit] WARNING", err.getvalue())  # pending → 不告警
-        c = (key_dir / "pm-state.md").read_text(encoding="utf-8")
-        self.assertIn("- Claim-Id: ", c)
-        self.assertIn("- Phase: init", c)
-        rows = ui.read_index(self.root / "_index.parallel")
-        row = next(r for r in rows if r["key"] == "k-new")
-        self.assertEqual(row["phase"], "—")
-        for pending in ("init", "—", ""):
-            self.assertIn(pending, au.PENDING_PHASES)
-        self.assertNotIn("SPEC", au.PENDING_PHASES)  # SPEC = 已进入 spec，必须真查
-        _v("VC-030", index_phase=row["phase"], pm_state_phase="init",
-           pending_all=True, claim_audit_silent=True)
-
-
-class CommandKeyGateTest(unittest.TestCase):
-    """T-16 (AC-006/DD-07c): set-phase / set-meta / release / get-claim share the
-    key-name gate and normalize key comparison (Python <-> TS direction).
-
-    The 4 commands previously compared keys byte-exact and bypassed the name
-    gate: `set-phase _index.parallel EXECUTE` created a framework-name row and
-    `set-phase MW-KEY` appended a second, case-variant row next to `mw-key`.
-    """
-
-    BAD_NAMES = ("_index.parallel", "_SCRATCH", "_tmp", "trailing.", "../x", "a/b", "", "   ")
-
-    def setUp(self):
-        self.tmp = Path(tempfile.mkdtemp())
-        self.root = self._fresh_root()
-
-    def tearDown(self):
-        shutil.rmtree(self.tmp, ignore_errors=True)
-
-    def _fresh_root(self):
-        root = Path(tempfile.mkdtemp(dir=self.tmp)) / ".agenticdoc"
-        root.mkdir()
-        return root
-
-    def _run(self, command, key):
-        out = io.StringIO()
-        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
-            if command == "set-phase":
-                rc = ui.cmd_set_phase(self.root, key, "EXECUTE")
-            elif command == "set-meta":
-                rc = ui.cmd_set_meta(self.root, key, desc="cmd-desc", deps=None)
-            elif command == "release":
-                rc = ui.cmd_release(self.root, key)
-            elif command == "get-claim":
-                rc = ui.cmd_get_claim(self.root, key)
-            else:
-                raise AssertionError(command)
-        return rc, out.getvalue()
-
-    def test_vc031_write_commands_refuse_bad_names_without_writing(self):
-        for command in ("set-phase", "set-meta", "release"):
-            for key in self.BAD_NAMES:
-                self.root = self._fresh_root()
-                rc, _ = self._run(command, key)
-                self.assertEqual(rc, 1, f"{command} {key!r}")
-                self.assertFalse((self.root / "_index.parallel").exists(), f"{command} {key!r} wrote the index")
-                self.assertEqual(list(self.root.iterdir()), [], f"{command} {key!r} created files")
-        _v("T-16", write_cmds_refuse_bad_names="PASS", index_untouched="true")
-
-    def test_vc032_get_claim_refuses_bad_names(self):
-        for key in self.BAD_NAMES:
-            self.root = self._fresh_root()
-            rc, _ = self._run("get-claim", key)
-            self.assertEqual(rc, 1, f"get-claim {key!r}")
-        _v("T-16", get_claim_refuses_bad_names="PASS")
-
-    def test_vc033_case_variant_commands_normalize_to_first_written_row(self):
-        root = self._fresh_root()
-        (root / "_index.parallel").write_text(
-            "| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |\n",
-            encoding="utf-8",
-        )
-        self.root = root
-        rc, out = self._run("get-claim", "MW-KEY")
-        self.assertEqual(rc, 0)
-        self.assertEqual(out.strip(), "other-host:4242")
-        for command in ("set-phase", "set-meta", "release"):
-            rc, _ = self._run(command, "MW-KEY")
-            self.assertEqual(rc, 0, command)
-            rows = ui.read_index(root / "_index.parallel")
-            self.assertEqual([r["key"] for r in rows], ["mw-key"], f"{command} appended a case-variant row")
-        rows = ui.read_index(root / "_index.parallel")
-        self.assertEqual(rows[0]["status"], "idle")
-        _v("T-16", case_variant_rows=len(rows), stored=rows[0]["key"], duplicate="false")
-
-    def test_vc034_legal_names_accepted_by_every_command(self):
-        for command in ("set-phase", "set-meta", "release", "get-claim"):
-            root = self._fresh_root()
-            (root / "_index.parallel").write_text(
-                "| mw-cmd | idle | SPEC | — | — | — | 2026-10-12 00:00 |\n",
-                encoding="utf-8",
-            )
-            self.root = root
-            rc, _ = self._run(command, "mw-cmd")
-            self.assertEqual(rc, 0, command)
-            rows = ui.read_index(root / "_index.parallel")
-            self.assertEqual([r["key"] for r in rows], ["mw-cmd"], command)
-        _v("T-16", legal_names_accepted="PASS")
-
 

#### .claude/scripts/test_audit_phase.py  vs  auth/test_audit_phase.py
--- auth/test_audit_phase.py
+++ .claude/scripts/test_audit_phase.py
@@ -3,5 +3,4 @@
 
-覆盖 AG-001..AG-008：绕过脚本检测（mw-worker-timeout-convergence 案例复刻）、
-合规 key 通过、无 pm-state / 占位 phase 跳过（含跨写入器占位容差）、--all 批量、
-claim 挂点自动审计。
+覆盖 AG-001..AG-006：绕过脚本检测（mw-worker-timeout-convergence 案例复刻）、
+合规 key 通过、无 pm-state / 占位 phase 跳过、--all 批量、claim 挂点自动审计。
 在 tempdir 沙箱内运行，不污染真实 .agenticdoc。
@@ -193,24 +192,2 @@
 
-    def test_ag008_claimed_key_pending_is_not_divergence(self):
-        # 跨写入器容差：新 claim 的 key 可能是"本脚本的索引 '—' + 桩 init"，也可能
-        # 是"TS 客户端（agent-team-loop）的索引 'SPEC' + 桩 init"。两种组合都必须在
-        # pending 短路下通过，不得报 INDEX-DIVERGENCE，也不得重放 spec 门禁。
-        kd = self.root / "k-claimed"
-        _write(kd / "pm-state.md",
-               "# PM State: k-claimed\n\n## Section 1: Snapshot\n- Key: k-claimed\n"
-               "- Claim-Id: HOST:4242\n- Phase: init\n")
-        for placeholder in ("—", "SPEC"):
-            _write(self.root / "_index.parallel",
-                   "# Index Parallel\n\n"
-                   "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\n"
-                   "|-----|--------|-------|---------|------|------|---------|\n"
-                   f"| k-claimed | active | {placeholder} | HOST:4242 |  |  | 2026-09-23 19:00 |\n")
-            passed, lines = au.audit_key(self.root, "k-claimed")
-            text = "\n".join(lines)
-            self.assertTrue(passed, text)
-            self.assertIn("nothing to audit yet", text)
-            self.assertNotIn("INDEX-DIVERGENCE", text)
-        _v("AG-008", index_dash="pass", index_spec="pass",
-           divergence_reported=False, spec_gate_replayed=False)
-
 
```

要点（从上面的 hunk 直接读出）：

1. `.claude/scripts/update_index.py` 整段缺失权威 `update_index.py:60-176` 的区块：`RESERVED_INDEX_NAMES`（14 个保留名）、`RESERVED_INDEX_NAME_SET`、`_JS_TRIM_CHARS`、`KEY_MAX_LENGTH`、`_KEY_SHAPE_RE`/`_KEY_ILLEGAL_CHARS_RE`/`_KEY_PATH_SEP_RE`/`_KEY_DRIVE_PREFIX_RE`、`normalize_key()`、`key_name_refusal()`、`_key_name_error()`。
2. `cmd_claim`（权威 `update_index.py:478`）里调 `key_name_refusal()` 的那 6 行守卫整段缺失；行匹配从 `normalize_key(r["key"]) == normalize_key(key)` 退回为 `r["key"] == key`。
3. `cmd_set_phase`（权威 `:542`）、`cmd_set_meta`（权威 `:569`）、`cmd_release`（权威 `:598`）、`cmd_get_claim`（权威 `:629`）的 `_key_name_error()` 守卫同样整段缺失。
4. `.claude/scripts/audit_phase.py` 的差异仅 5 行替换：缺少权威 `audit_phase.py:35-38` 关于「`SPEC` 刻意不在 PENDING_PHASES 内」的注释；`PENDING_PHASES` 字面值本身仍为 `{"(pending)", "init", "—", ""}`（即行为无差异，只有注释差异）。
5. `.claude/scripts/test_update_index.py` 缺 `CommandKeyGateTest`（T-16/VC-031..034）与 `test_vc030_claim_phase_placeholders_are_pending`；`.claude/scripts/test_audit_phase.py` 缺 `test_ag008_claimed_key_pending_is_not_divergence`。也就是说**活副本连回归断言都缺**，不能靠跑它的测试发现缺口。

## 3. 门禁符号矩阵（`rg -c` 计数）

实测命令（PowerShell 循环，逐个文件逐符号 `rg -c -F`）：

```powershell
$roots = @('.agents\skills\agentic-task\scripts', '.agents\skills\agentic-task\core\scripts', '.agents\skills\agentic-task\claude\scripts', '.claude\scripts', 'packages\multi-workers\.tmp\agentic-task\scripts', 'packages\multi-workers\.tmp\agentic-task\core\scripts', 'packages\multi-workers\.tmp\agentic-task\claude\scripts', '.tmp\rq3c-fake\agentic-task\scripts', '.tmp\rq3c-fake\agentic-task\core\scripts', '.tmp\rq3c-fake\agentic-task\claude\scripts', '.tmp\rq3c-fake\project\.claude\scripts')
foreach ($p in 'caseVariantOf','keyNameRefusal','RESERVED_INDEX_NAMES','foreignLiveClaimRefusal','def set_phase','def cmd_claim') {
  foreach ($r in $roots) { rg -c -F -- $p $r }
}
```

扫描规模：**176 个 (目录, 文件) 行 x 6 个符号 = 1056 次计数**。其中只有 **11 行**存在任一非零计数，其余 **165 行**六个符号全为 0（脚本内断言，见 `_tmp_build3.py`）。

### 3.1 非零行（原始计数）

| 文件 | caseVariantOf | keyNameRefusal | RESERVED_INDEX_NAMES | foreignLiveClaimRefusal | def set_phase | def cmd_claim |
|---|---|---|---|---|---|---|
| `.agents\skills\agentic-task\scripts\update_index.py` | 0 | 2 | 2 | 0 | 0 | 1 |
| `.agents\skills\agentic-task\core\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `.agents\skills\agentic-task\claude\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `.claude\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `packages\multi-workers\.tmp\agentic-task\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `packages\multi-workers\.tmp\agentic-task\core\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `packages\multi-workers\.tmp\agentic-task\claude\scripts\update_index.py` | 0 | 0 | 0 | 0 | 0 | 1 |
| `.tmp\rq3c-fake\agentic-task\scripts\update_index.py` | 0 | 2 | 2 | 0 | 0 | 1 |
| `.tmp\rq3c-fake\agentic-task\core\scripts\update_index.py` | 0 | 2 | 2 | 0 | 0 | 1 |
| `.tmp\rq3c-fake\agentic-task\claude\scripts\update_index.py` | 0 | 2 | 2 | 0 | 0 | 1 |
| `.tmp\rq3c-fake\project\.claude\scripts\update_index.py` | 0 | 2 | 2 | 0 | 0 | 1 |

### 3.2 逐符号结论

- `caseVariantOf`：**所有 .py 副本全为 0**。该名字只存在于 TypeScript 侧：`packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts:249,253,330`、`pm/ui-bridge.ts:352,353`（实测 `rg -n --no-ignore -F caseVariantOf .` 原始命中）。它不是 python 门禁符号，所以「副本缺 caseVariantOf」不是缺口。
- `foreignLiveClaimRefusal`：**所有 .py 副本全为 0**。同样只存在于 TypeScript 侧：`pm/ui-bridge.ts:277`（定义）、`:1916`、`:2343`、`:2445`（调用点）。
- `keyNameRefusal`（camelCase）：只在**权威** `scripts/update_index.py` 出现 2 次，且**两处都是注释/文档串**（`:63`、`:121`），不是代码。真正的 python 实现是 snake_case `key_name_refusal()`（权威 `:118` 定义，`:169`、`:484` 调用）。`.agents/.../core/scripts`、`.agents/.../claude/scripts`、其余六处副本目录的 `update_index.py` 计数均为 0：`.agents/skills/agentic-task/core/scripts`、`.agents/skills/agentic-task/claude/scripts`、`.claude/scripts`、`packages/multi-workers/.tmp/agentic-task/scripts`、`packages/multi-workers/.tmp/agentic-task/core/scripts`、`packages/multi-workers/.tmp/agentic-task/claude/scripts` ⇒ **连函数带注释整体缺失**。
- `RESERVED_INDEX_NAMES`：只有权威 `scripts/update_index.py`（`:72` 定义、`:88` 使用）和 `.tmp/rq3c-fake` 夹具（RQ-3 刚装出来的新鲜副本）为 2；其余 6 个分发副本目录全为 0。
- `def set_phase`：**全仓 0**。函数真名是 `def cmd_set_phase`（权威 `update_index.py:542`，五个 update_index 副本都有 2 处 `cmd_set_phase` 命中）。所以在「副本是否缺 set_phase 门禁」这个问题上，正确的计数符号应当是 `cmd_set_phase` 或 `_key_name_error`。
- `def cmd_claim`：**所有 11 个副本目录的 `update_index.py` 都各 1 处命中**（函数体存在），差异不在函数是否存在，而在函数体内是否调 `key_name_refusal`（§2.2）。

### 3.3 门禁函数存在性（对 count 为 0 的补充核对）

`key_name_refusal` / `_key_name_error` / `normalize_key` 三个 python 门禁符号在六个分发副本目录里的计数（`rg -c -F`）：

| 副本 `update_index.py` | `def key_name_refusal` | `def _key_name_error` | `def normalize_key` | `RESERVED_INDEX_NAMES` |
|---|---|---|---|---|
| `.agents\skills\agentic-task\scripts\update_index.py` | 1 | 1 | 1 | 2 |
| `.agents\skills\agentic-task\core\scripts\update_index.py` | 0 | 0 | 0 | 0 |
| `.agents\skills\agentic-task\claude\scripts\update_index.py` | 0 | 0 | 0 | 0 |
| `.claude\scripts\update_index.py` | 0 | 0 | 0 | 0 |
| `packages\multi-workers\.tmp\agentic-task\scripts\update_index.py` | 0 | 0 | 0 | 0 |
| `packages\multi-workers\.tmp\agentic-task\core\scripts\update_index.py` | 0 | 0 | 0 | 0 |
| `packages\multi-workers\.tmp\agentic-task\claude\scripts\update_index.py` | 0 | 0 | 0 | 0 |

## 4. 消费者 / 活链（含「谁被真正执行」实测）

### 4.1 任务给定坐标的核对（含一处路径纠正）

| 任务给定坐标 | 核对结果 |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2345` | **存在且正确**：`const result = runAgenticScript(projectDir, "advance_phase.py", args);` |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/agentic-scripts.ts:21-30` | **路径错误**：`pm/` 目录下无此文件（`packages/coding-agent/src/extensions/agent-team-loop/pm/` 只有 goal-reader.ts / pm-orchestrator.ts / state-manager.ts / task-dispatcher.ts / ui-bridge.ts）。真实路径是 `packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts`，解析逻辑在 `:17-30`（`agenticScriptsDir`）。 |

`rg` 原始输出（确认 `agentic-scripts.ts` 只存在于 `shared/`）：

```
packages\coding-agent\src\extensions\agent-team-loop\pm\ui-bridge.ts:9:import { runAgenticScript } from "../shared/agentic-scripts.ts";
```

活链调用点原始输出：

```
packages\coding-agent\src\extensions\agent-team-loop\pm\ui-bridge.ts:9:import { runAgenticScript } from "../shared/agentic-scripts.ts";
packages\coding-agent\src\extensions\agent-team-loop\pm\ui-bridge.ts:2345:			const result = runAgenticScript(projectDir, "advance_phase.py", args);
packages\coding-agent\src\extensions\agent-team-loop\shared\agentic-scripts.ts:21:export function agenticScriptsDir(projectDir: string): string | null {
packages\coding-agent\src\extensions\agent-team-loop\shared\agentic-scripts.ts:45:export function runAgenticScript(
packages\coding-agent\src\extensions\agent-team-loop\shared\agentic-scripts.ts:51:	const dir = agenticScriptsDir(projectDir);
```

### 4.2 两种消费者的解析顺序（代码坐标）

**A) pi 侧（PM 工具 `advance_phase`）** — `packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts`：

- `:9` `import { PYTHON_EXE } from "./mw-runner.ts";`（`PYTHON_EXE` = win32 ? `python` : `python3`，见 `shared/mw-runner.ts:12`）
- `:21-32` `agenticScriptsDir(projectDir)`：候选顺序固定为 1) `{projectDir}/.claude/scripts`，2) `{projectDir}/.agents/skills/agentic-task/claude/scripts`；`:27` 用 `fs.existsSync(dir/advance_phase.py)` 作为采纳条件，**先到先得 ⇒ 副本优先**
- `:45-53` `runAgenticScript()` 调 `agenticScriptsDir()`；`:62-70` 以 `spawnSync(PYTHON_EXE, ["-X","utf8", script, ...args])` 执行 `path.join(dir, scriptName)`
- 调用点唯一：`pm/ui-bridge.ts:2345`（工具名 `advance_phase`，注册于 `pm/ui-bridge.ts:2259`）

**B) mw autopilot 侧（conductor 的唯一推进通道）** — `packages/multi-workers/autopilot/advance.py`：

- `:62-88` `_candidates(project_root)`：1) `.agentic-framework` 的 `repo=` 行，2) `{project_root}/.agents/skills/agentic-task`
- `:91-117` `_probe_detect_root()`：对候选跑 `scripts/detect_root.py --json`，取输出的 `PLATFORM_DIR`，并要求 `PROJECT_ROOT` 等于目标项目根
- `:120-136` `locate_platform_dir()`、`:139-147` `advance_script()` 返回 `PLATFORM_DIR/scripts/advance_phase.py`；`:150-194` `advance()` 以 `spawnSync` 风格的 `subprocess.run` 执行它
- 同源第二个脚本入口：`packages/multi-workers/autopilot/conductor.py:2207-2210` 取 `advance.locate_platform_dir(project_root)/"scripts"/"update_index.py"`

`rg` 原始输出：

```
131:    candidates = _candidates(project_root)
154:        script = locate_platform_dir(project_root) / _SCRIPTS / "advance_phase.py"
174:        script = advance_script(project_root)
```

注意：`detect_root.py` 的 `PLATFORM_DIR` 由**被调用的脚本自身位置**推出（`detect_root.py:63-77`：`Path(__file__).resolve().parent.parent`），所以「谁先被调用，谁就把自己宣布成 PLATFORM_DIR」。两条链路的分叉点不在 detect_root，而在**谁去调 detect_root**。

### 4.3 实测 A：pi 侧真正执行的是**副本** `.claude/scripts`

探针：`_tmp_probe_runtime.mjs`（直接 `import` 真实模块 `shared/agentic-scripts.ts`，调 `agenticScriptsDir()` 与 `runAgenticScript()`）。

命令与原始输出：

```
node --experimental-strip-types H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\workers\mwp-rq1c-mirror-inventory\_tmp_probe_runtime.mjs

MEASURED agenticScriptsDir: H:\git\Multi-Workers\.claude\scripts
MATCHES .claude/scripts : true
RESOLVED advance_phase.py sha=9427abe2ecc0366b IDENTICAL_TO_AUTH=true
RESOLVED update_index.py sha=0b8f7128158d0945 IDENTICAL_TO_AUTH=false
RESOLVED audit_phase.py sha=e3b5fdf2f2754857 IDENTICAL_TO_AUTH=false
RESOLVED detect_root.py sha=369a45d3add686a2 IDENTICAL_TO_AUTH=true
RESOLVED check_mermaid.py sha=b80af059ffdf879f IDENTICAL_TO_AUTH=true
RESOLVED sync_framework.py sha=d574718e0340d130 IDENTICAL_TO_AUTH=true
RESOLVED guard_pm_state.py sha=a5f29401d375ceca IDENTICAL_TO_AUTH=true
RESOLVED migrate_patterns.py sha=44cdc967de87b459 IDENTICAL_TO_AUTH=true
RESOLVED verify_project_memory.py sha=e07a2f69b5d2b741 IDENTICAL_TO_AUTH=true
E2E runAgenticScript(update_index.py get-claim _scratch) ok=true
E2E output: "—"
```

（脚本自身以 `createHash("sha256")` 对「解析出的文件」与「权威同名文件」同时取摘要再比较。）

**端到端判别实验**：选一个「副本与权威答案不同且只读」的调用 —— `update_index.py get-claim _scratch`。

- 权威有 AC-006 键名门禁 ⇒ `_scratch` 属保留名，必须 rc=1 拒绝。
- `.claude/scripts` 副本无门禁 ⇒ 走读逻辑，索引里没有该行 ⇒ 打印 `—` 且 rc=0。

```
python -X utf8 .agents/skills/agentic-task/scripts/update_index.py get-claim _scratch
rc=1
ERROR: refused key name (reserved-key-name): '_scratch' is a reserved framework name, not an AgenticTask key namespace

python -X utf8 .claude/scripts/update_index.py get-claim _scratch
rc=0
—
```

而**通过真实消费者链路** `runAgenticScript(projectDir, "update_index.py", ["get-claim", "_scratch"])` 得到的输出是 `ok=true` / `output="—"`（见上面 node 原始输出的最后两行）—— 即**运行时确实执行了 `.claude/scripts/update_index.py` 这个无门禁副本**，而不是权威脚本。

同链路逐文件摘要比对（node 原始输出已含）：

| 脚本 | 解析出（`.claude/scripts`）sha256 前缀 | 与权威相同 |
|---|---|---|
| `advance_phase.py` | `9427abe2ecc0366b` | 是 |
| `update_index.py` | `0b8f7128158d0945` | **否** |
| `audit_phase.py` | `e3b5fdf2f2754857` | **否**（仅注释） |
| `detect_root.py` | `369a45d3add686a2` | 是 |
| `check_mermaid.py` | `b80af059ffdf879f` | 是 |
| `sync_framework.py` | `d574718e0340d130` | 是 |
| `guard_pm_state.py` | `a5f29401d375ceca` | 是 |
| `migrate_patterns.py` | `44cdc967de87b459` | 是 |
| `verify_project_memory.py` | `e07a2f69b5d2b741` | 是 |

### 4.4 实测 B：mw autopilot 侧真正执行的是**权威** `.agents/skills/agentic-task/scripts`

探针：`_tmp_probe_autopilot.py`（`sys.path` 注入 `packages/multi-workers`，调真实的 `autopilot.advance.locate_platform_dir()` / `advance_script()`）。

```
python H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\workers\mwp-rq1c-mirror-inventory\_tmp_probe_autopilot.py

AUTOPILOT locate_platform_dir: H:\git\Multi-Workers\.agents\skills\agentic-task
AUTOPILOT advance_script: H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\advance_phase.py
AUTOPILOT is authority: True

$ python -X utf8 .agents/skills/agentic-task/scripts/detect_root.py --json
rc=0
{"PLATFORM_DIR": "H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task", "PROJECT_ROOT": "H:\\git\\Multi-Workers", "AGENTICDOC_ROOT": "H:\\git\\Multi-Workers\\.agenticdoc", "method": "agenticdoc:platform_dir"}
```

`.agentic-framework`（决定 `_candidates` 第一候选）内容：

```
framework=AgenticTask
repo=H:\git\Multi-Workers\.agents\skills\agentic-task
commit=d7004d0
installed_at=2026-09-22T08:33:11.405351+00:00
claude=H:\git\Multi-Workers\.claude
codex_scope=project
codex_skill=H:\git\Multi-Workers\.agents\skills\agentic-task
```

⇒ autopilot 的 `advance_script()` = `H:/git/Multi-Workers/.agents/skills/agentic-task/scripts/advance_phase.py`（权威），与 pi 侧结论相反。

### 4.5 「谁被真正执行」汇总与混用风险

| 消费者 | 代码坐标 | 实测执行的目录 | 权威/副本 |
|---|---|---|---|
| pi PM 工具 `advance_phase` | `pm/ui-bridge.ts:2345` | `H:/git/Multi-Workers/.claude/scripts` | **副本** |
| mw autopilot 推进 | `autopilot/advance.py:154` | `H:/git/Multi-Workers/.agents/skills/agentic-task/scripts` | 权威 |
| mw autopilot set-phase 后核对 | `autopilot/conductor.py:2210` | 同 autopilot（权威） | 权威 |
| Claude Code 平台文档命令 `{PLATFORM_DIR}/scripts/*` | `.claude/agents/agentic-pm.md:44,50,77`；`.claude/commands/{agentic.md:27,36,52,68,70, pm-key.md:29,45,53,56,62,64,80}`；`.claude/skills/**` | `{PLATFORM_DIR}` 由 `detect_root.py` 推导 ⇒ 从 `.claude/scripts/detect_root.py` 启动时是 `.claude/scripts`（副本） | 副本 |

**混用风险（实测支撑）**：pi 侧链路里 `advance_phase.py` 是权威字节（同摘要），但它 `:599` 用 `Path(__file__).parent / "update_index.py"` 调**同目录**兄弟脚本 ⇒ 在 `.claude/scripts` 下执行时调用的是 `.claude/scripts/update_index.py`（无键名门禁）。也就是说一次 `advance_phase` 工具调用里：门禁判定走权威字节、`_index.parallel` 相位写回走副本字节。另一个方向（autopilot）全程走权威。因此**同一个 key 的相位可能被两条链路各自写入，行为不一致**。

## 5. 分发点清单（谁把权威复制成副本）

### 5.1 `.agents/skills/agentic-task/install.py`（6818 B，sha256 `b2b54149854b7b2b5bca0661acefa8719c532d56589dce78aec785e8f811d3ae`）

关键坐标：

| 行号 | 内容 |
|---|---|
| `install.py:28` | `ROOT = Path(__file__).resolve().parent`（=`.agents/skills/agentic-task`，权威树根） |
| `install.py:29` | `CLAUDE_DIRS = ("commands", "agents", "skills", "scripts")` |
| `install.py:30` | `MIRROR_SCRIPT_DIRS = ("claude/scripts", "core/scripts")` |
| `install.py:33-38` | `copy_tree()`：`rmtree(dst)` 后 `copytree(src, dst)`（**整目录替换、无 ignore 规则**；源不存在则抛 `FileNotFoundError`） |
| `install.py:41` | `def sync_script_mirrors(root=None) -> list[Path]:`（权威 → 镜像，正向同步） |
| `install.py:55-65` | 遍历 `MIRROR_SCRIPT_DIRS`；对 `scripts/` 下每个 `is_file()` 条目，若目标字节相同则跳过，否则 `dst.write_bytes(f.read_bytes())` |
| `install.py:71` | `def install_claude(project: Path) -> Path:` |
| `install.py:73-76` | `claude_dst = project/".claude"`；对 `CLAUDE_DIRS` 每个名字 `copy_tree(ROOT/"claude"/name, claude_dst/name)` |
| `install.py:157` | `synced = sync_script_mirrors()`（`main()` 第一步，先同步镜像再安装） |
| `install.py:166` | `claude_path = install_claude(project)` |

原始源码（`install.py:41-78`）：

```python
  41	def sync_script_mirrors(root: Path | None = None) -> list[Path]:
  42	    """Re-sync claude/scripts/ and core/scripts/ from scripts/ (canonical).
  43	
  44	    The mirrors exist only for the Claude adapter install and the core tree;
  45	    they hold no adapter-specific content, so a byte-diff overwrite is always
  46	    safe. Files present only in a mirror are never deleted; non-files
  47	    (e.g. __pycache__) are ignored. Returns the mirror files actually
  48	    rewritten so callers can demand a commit & push.
  49	    """
  50	    root = (root or ROOT).resolve()
  51	    src = root / "scripts"
  52	    changed: list[Path] = []
  53	    if not src.is_dir():
  54	        return changed
  55	    for rel in MIRROR_SCRIPT_DIRS:
  56	        mirror = root / rel
  57	        if not mirror.parent.is_dir():
  58	            continue  # partial layout without this tree
  59	        for f in sorted(src.iterdir()):
  60	            if not f.is_file():
  61	                continue
  62	            dst = mirror / f.name
  63	            if dst.is_file() and dst.read_bytes() == f.read_bytes():
  64	                continue
  65	            dst.parent.mkdir(parents=True, exist_ok=True)
  66	            dst.write_bytes(f.read_bytes())
  67	            changed.append(dst)
  68	    return changed
  69	
  70	
  71	def install_claude(project: Path) -> Path:
  72	    claude_dst = project / ".claude"
  73	    claude_dst.mkdir(parents=True, exist_ok=True)
  74	    for name in CLAUDE_DIRS:
  75	        copy_tree(ROOT / "claude" / name, claude_dst / name)
  76	
  77	    return claude_dst
  78	
```

**被复制文件清单（正向同步 `scripts/` → `claude/scripts/` + `core/scripts/`）**：`scripts/` 下的**全部 16 个 `.py` 普通文件**，逐个同路径落地。复制循环只检查 `f.is_file()`，**没有扩展名过滤**（理论上 `scripts/` 下任何普通文件都会被复制；当前实测 `scripts/` 下只有这 16 个 `.py`，另有 `__pycache__/`、`.pytest_cache/` 两个目录被 `is_file()` 跳过）。

| 源（权威） | 目标 1 | 目标 2 |
|---|---|---|
| `.agents/skills/agentic-task/scripts/advance_phase.py` | `.agents/skills/agentic-task/claude/scripts/advance_phase.py` | `.agents/skills/agentic-task/core/scripts/advance_phase.py` |
| `.agents/skills/agentic-task/scripts/audit_phase.py` | `.agents/skills/agentic-task/claude/scripts/audit_phase.py` | `.agents/skills/agentic-task/core/scripts/audit_phase.py` |
| `.agents/skills/agentic-task/scripts/check_mermaid.py` | `.agents/skills/agentic-task/claude/scripts/check_mermaid.py` | `.agents/skills/agentic-task/core/scripts/check_mermaid.py` |
| `.agents/skills/agentic-task/scripts/detect_root.py` | `.agents/skills/agentic-task/claude/scripts/detect_root.py` | `.agents/skills/agentic-task/core/scripts/detect_root.py` |
| `.agents/skills/agentic-task/scripts/guard_pm_state.py` | `.agents/skills/agentic-task/claude/scripts/guard_pm_state.py` | `.agents/skills/agentic-task/core/scripts/guard_pm_state.py` |
| `.agents/skills/agentic-task/scripts/migrate_patterns.py` | `.agents/skills/agentic-task/claude/scripts/migrate_patterns.py` | `.agents/skills/agentic-task/core/scripts/migrate_patterns.py` |
| `.agents/skills/agentic-task/scripts/sync_framework.py` | `.agents/skills/agentic-task/claude/scripts/sync_framework.py` | `.agents/skills/agentic-task/core/scripts/sync_framework.py` |
| `.agents/skills/agentic-task/scripts/test_advance_phase.py` | `.agents/skills/agentic-task/claude/scripts/test_advance_phase.py` | `.agents/skills/agentic-task/core/scripts/test_advance_phase.py` |
| `.agents/skills/agentic-task/scripts/test_audit_phase.py` | `.agents/skills/agentic-task/claude/scripts/test_audit_phase.py` | `.agents/skills/agentic-task/core/scripts/test_audit_phase.py` |
| `.agents/skills/agentic-task/scripts/test_detect_root.py` | `.agents/skills/agentic-task/claude/scripts/test_detect_root.py` | `.agents/skills/agentic-task/core/scripts/test_detect_root.py` |
| `.agents/skills/agentic-task/scripts/test_install.py` | `.agents/skills/agentic-task/claude/scripts/test_install.py` | `.agents/skills/agentic-task/core/scripts/test_install.py` |
| `.agents/skills/agentic-task/scripts/test_migrate_patterns.py` | `.agents/skills/agentic-task/claude/scripts/test_migrate_patterns.py` | `.agents/skills/agentic-task/core/scripts/test_migrate_patterns.py` |
| `.agents/skills/agentic-task/scripts/test_sync_framework.py` | `.agents/skills/agentic-task/claude/scripts/test_sync_framework.py` | `.agents/skills/agentic-task/core/scripts/test_sync_framework.py` |
| `.agents/skills/agentic-task/scripts/test_update_index.py` | `.agents/skills/agentic-task/claude/scripts/test_update_index.py` | `.agents/skills/agentic-task/core/scripts/test_update_index.py` |
| `.agents/skills/agentic-task/scripts/update_index.py` | `.agents/skills/agentic-task/claude/scripts/update_index.py` | `.agents/skills/agentic-task/core/scripts/update_index.py` |
| `.agents/skills/agentic-task/scripts/verify_project_memory.py` | `.agents/skills/agentic-task/claude/scripts/verify_project_memory.py` | `.agents/skills/agentic-task/core/scripts/verify_project_memory.py` |

**第二跳（安装到项目）**：`install_claude()` 把 `.agents/skills/agentic-task/claude/{commands,agents,skills,scripts}` 整目录 `copytree` 到 `<project>/.claude/{commands,agents,skills,scripts}`。对本仓库这个「项目」而言目标就是 `H:/git/Multi-Workers/.claude/scripts/*`。

覆盖规则与副作用（源码直读）：

- `sync_script_mirrors`：**幂等**（字节相同即跳过）、**不删除**镜像中「多出来」的文件（只遍历源侧）、跳过非文件（`__pycache__` 不会被正向同步进去）。
- `install_claude`（经 `copy_tree`）：`rmtree` 整目录后 `copytree`，**目标侧多余文件会被删掉**，且 `copytree` 无 ignore ⇒ 会把镜像里的 `__pycache__/`、`.pytest_cache/` **一起搬进** `<project>/.claude/scripts/`。（与 RQ-3 `evidence/research/spec-distribution-path-20261012.md` §5.2 的实测一致，此处只给坐标，不重复实验。）

### 5.2 `.agents/skills/agentic-task/scripts/sync_framework.py`（9010 B）

坐标（`rg -n` 原始输出）：

```
30:CLAUDE_DIRS = ("commands", "agents", "skills", "scripts")
97:def copy_tree(src: Path, dst: Path) -> None:
105:def sync_installed_to_repo(
116:        copy_tree(claude_root / name, repo / "claude" / name)
121:        copy_tree(codex_skill, repo)
159:        [PYTHON, str(repo / "diff-installed.py"), str(project)],
171:def run_tests(repo: Path, runner: Runner) -> None:
185:def reinstall(project: Path, repo: Path, runner: Runner) -> None:
186:    runner([PYTHON, str(repo / "install.py"), str(project)], cwd=repo)
187:    runner([PYTHON, str(repo / "diff-installed.py"), str(project)], cwd=repo)
208:    if not (repo / "install.py").is_file():
```

要点：

- `:105-121` `sync_installed_to_repo()` 是**反向**通道：`copy_tree(project/.claude/<dir>, repo/claude/<dir>)`（`:116`），即把「已安装副本」覆盖回「仓库镜像」。**当 `.claude/scripts` 是旧版本时，这一步会把旧版本提交进仓库镜像**。
- `:185-187` `reinstall()`：先跑 `repo/install.py`（正向重建镜像 + 重装项目），再跑 `diff-installed.py` 校验。注意 `sync_framework()`（`:197-234`）的顺序是 `sync_installed_to_repo` → `run_tests` → `commit_and_push` → `reinstall`，**提交发生在正向重建之前**。
- `:171-178` `run_tests()` 的测试根是三份镜像目录 `repo/core/scripts`、`repo/claude/scripts`、`repo/scripts`，用 `unittest discover -p 'test_*.py'`。
- `:157-159` 用 `diff-installed.py` 的退出码作为「已安装是否不同」的判据（rc=1 视为不同）。

### 5.3 `diff-installed.py`（对照工具，非复制器）

实测（只读）：

```
$ python .agents/skills/agentic-task/diff-installed.py .
rc=1
AgenticTask installed differences found:
- claude/scripts: changed file audit_phase.py
- claude/scripts: changed file test_audit_phase.py
- claude/scripts: changed file test_update_index.py
- claude/scripts: changed file update_index.py
```

⇒ 独立确认 §2 的结论：`.claude/scripts` 与仓库镜像 `claude/scripts` 有 **4 个文件不同**（`update_index.py`、`audit_phase.py`、`test_update_index.py`、`test_audit_phase.py`），与 §2.2 的语义差异文件集合完全一致。

**盲区（coordinate）**：`diff-installed.py:73-78` 的 `compare_claude()` 只比 `repo/claude/<dir>` 与 `<project>/.claude/<dir>`，**从不比 `repo/scripts/` 与 `repo/claude/scripts/`**。因此权威 `scripts/update_index.py`（28884 B）与 `claude/scripts/update_index.py`（22492 B）之间的缺口对它不可见 —— 而当前恰好存在这个缺口。`install.py:157` 的正向 `sync_script_mirrors()` 才是这个缺口的唯一修理工。

### 5.4 Multi-Workers 侧入口（`packages/multi-workers/mw.py`）

```
60:_TMP_AGENTICTASK = _SCRIPT_DIR / ".tmp" / "agentic-task"
61:_DEFAULT_AGENTICTASK_REMOTE = "https://github.com/wenbocode/AgenticTask.git"
62:_DEFAULT_AGENTICTASK_BRANCH = "master"
4113:def _checkout_framework_dir() -> pathlib.Path:
4125:def _resolve_framework_source(sync_source: str | None) -> pathlib.Path:
4554:def _install_framework(
4564:    installer = source / "install.py"
4659:        source = _resolve_framework_source(args.sync_agentictask)
4660:        ok, msg = _install_framework(project_dir, source=source, codex_scope=args.codex_scope)
5200:def _resolve_framework_source_readonly() -> pathlib.Path | None:
5477:            ok, msg = _install_framework(project_dir, source=source)
```

要点：

- `mw.py:60` `_TMP_AGENTICTASK = _SCRIPT_DIR / ".tmp" / "agentic-task"`（框架缓存，`.gitignore` 命中 `packages/multi-workers/.tmp/`）。
- `mw.py:4113-4122` `_checkout_framework_dir()` 返回 `_repo_root()/.agents/skills/agentic-task`。
- `mw.py:4125-4147` `_resolve_framework_source()` 顺序：`--sync-agentictask` 目录 → 本检出自带的 `.agents/skills/agentic-task`（有 `install.py` 即采用）→ `.tmp/agentic-task` 缓存（缺则自动 clone）。在本仓库中第一优先命中 ⇒ **分发源头就是权威树**。
- `mw.py:4554-4581` `_install_framework()` 以 `sys.executable <source>/install.py <project> --codex-scope <scope>` 子进程调用分发器（`:4564` `installer = source / "install.py"`）；`cmd_init` 在 `:4659-4660`（以及 `:5477`）调用它。

### 5.5 `.agents/skills/agentic-task/` 与 `.claude/` 的版本控制状态（分发可追溯性）

```
$ git -C .agents/skills/agentic-task rev-parse HEAD
d0834ae800ad5459e7bf5da09cb6c1f0397de3ee
$ git -C .agents/skills/agentic-task log --oneline -3
d0834ae audit: pin cross-writer pending-phase placeholders (index '—'/'SPEC' vs stub 'init')
d7004d0 advance: resolve .agenticdoc from cwd first (framework installed outside project)
e9360db docs: expand skill trigger words to cover implementation entry gate (non-trivial implementation)
$ git -C .agents/skills/agentic-task status --porcelain -- scripts
 M scripts/test_update_index.py
 M scripts/update_index.py
$ git -C .agents/skills/agentic-task diff --stat HEAD -- scripts
 scripts/test_update_index.py |  89 +++++++++++++++++++++++
 scripts/update_index.py      | 165 ++++++++++++++++++++++++++++++++++++++++---
 2 files changed, 246 insertions(+), 8 deletions(-)
$ git -C .agents/skills/agentic-task show HEAD:scripts/update_index.py | Select-String -SimpleMatch key_name_refusal | Measure-Object
Count = 0
$ git -C packages/multi-workers/.tmp/agentic-task rev-parse HEAD
fa97ed6dd70266a95118826d79782bdacc7e5349
$ git -C .agents/skills/agentic-task merge-base --is-ancestor fa97ed6dd70266a95118826d79782bdacc7e5349 HEAD
rc=0
```

`rc_anc=0` 表示 `.tmp` 缓存的 HEAD **是**权威树 HEAD 的祖先（即缓存确实更旧）。

`git -C .claude`（本仓库的已安装副本自带的 git 仓）实测：

```
$ git -C .claude ls-files scripts
scripts/__pycache__/advance_phase.cpython-314.pyc
scripts/__pycache__/check_mermaid.cpython-314.pyc
scripts/advance_phase.py
scripts/check_mermaid.py
scripts/guard_pm_state.py
scripts/test_advance_phase.py
scripts/verify_project_memory.py
$ git -C .claude status --porcelain | Select-String update_index
?? scripts/__pycache__/test_update_index.cpython-314.pyc
?? scripts/__pycache__/update_index.cpython-314.pyc
?? scripts/test_update_index.py
?? scripts/update_index.py
$ git check-ignore -v .claude/scripts/update_index.py
.gitignore:21:.claude/	.claude/scripts/update_index.py
```

⇒ 结论性事实：**`.claude/scripts/update_index.py`（活副本、无门禁）在 `.claude` 自带仓里是 untracked，在外层仓库里被 `.gitignore:21` 忽略。** 也就是说这个缺口在两层 git 里都不可见，只能靠 `diff-installed.py` 或本次清点发现。

### 5.6 分发点汇总表

| 分发点 | 坐标 | 方向 | 落地目标 |
|---|---|---|---|
| 权威 → 仓库镜像 | `install.py:41`（`sync_script_mirrors`，由 `:157` 调用） | 正向 | `.agents/skills/agentic-task/{claude,core}/scripts/*` |
| 仓库镜像 → 项目 | `install.py:71`（`install_claude`，由 `:166` 调用） | 正向 | `<project>/.claude/{commands,agents,skills,scripts}/*` |
| 项目 → 仓库镜像 | `sync_framework.py:116`（`sync_installed_to_repo`） | **反向** | `<repo>/claude/<dir>/*` |
| 重建（正向重跑） | `sync_framework.py:186`（`reinstall`） | 正向 | 先 `install.py` 再 `diff-installed.py` |
| mw 安装器入口 | `mw.py:4554-4581`（`_install_framework`），源解析 `mw.py:4125` | 正向 | 调 `<source>/install.py <project>` |
| 缓存刷新 | `mw.py:4113/4213`（`pull-agentictask`） | 拉取 | `packages/multi-workers/.tmp/agentic-task`（权威的祖先提交） |
| 安装校验 | `diff-installed.py:73-78` | 只读比对 | `repo/claude/<dir>` vs `<project>/.claude/<dir>`（盲区：不比 `repo/scripts`） |

## 6. 未验证怀疑清单

每条给「怀疑 + 为什么没验证 + 验证方法」。

1. **`.claude/scripts/update_index.py`（22026 B）是哪一次动作留下的，不可考。** 它在 `.claude` 自带仓里是 untracked（`git -C .claude ls-files scripts` 无此文件）、在外层仓被 `.gitignore:21` 忽略 ⇒ 两层 git 都没有它的历史，也没有祖先提交可以二分。验证方法：下次在真实仓库跑 `install.py .` 之前先记录 sha256（`0b8f7128158d0945...`）与 mtime，跑完再比。
2. **权威树自身是未提交状态（WIP）。** `git -C .agents/skills/agentic-task show HEAD:scripts/update_index.py` 里 `key_name_refusal` 命中数 = 0，而工作区命中 = 3（1 定义 + 2 调用）⇒ AC-006 门禁只活在工作区。⇒「权威」目前不是可发布状态；分发（`install.py:157`）会把未提交门禁带进仓库镜像，但 `.tmp`/clone 路径（祖先提交）拿不到。未验证的是「门禁是否/何时被提交」——本任务禁止 git 写操作，无法推进。验证方法：另行提交并重跑本清单。
3. **`.tmp` 缓存与仓库镜像是否同源同版本：只能证明「更旧」，不能证明「就是两者之一的副本」。** 实测 `.tmp` 三份互为逐字节相同、HEAD `fa97ed6` 是权威 HEAD `d0834ae` 的祖先（`merge-base --is-ancestor` rc=0），但它是当初 `_pull_via_copy` 还是 `_pull_via_git` 落地的没有记录（现在带 `.git`）。验证方法：查 `.agentic-framework` 历史或 `mw pull-agentictask` 日志。
4. **`__pycache__` 被 `copytree` 搬进 `.claude/scripts`，但「旧 `.pyc` 是否会被执行」未验证。** 事实：`.claude/scripts/__pycache__/update_index.cpython-314.pyc` 存在（且 `.claude/scripts/.pytest_cache/` 存在），而 `install_claude`（`install.py:73-76`）经 `copy_tree` 走 `copytree` 无 ignore 规则。CPython 的 `__pycache__` 失效判据是「源 mtime+size」，理论上不会执行陈旧 pyc，但本任务未做该实验。验证方法：把 `update_index.py` 的 mtime 改成比 pyc 更早再直接执行，观察是否加载 pyc。
5. **「一次标准安装能否在本仓库修好 `.claude/scripts`」未在真实仓库验证。** 该动作会写 `.claude/`、`.agents/skills/agentic-task/{claude,core}/scripts`，全部在本人写面之外（§7.1），因此只采信 RQ-3 的合成夹具证据（`.tmp/rq3c-fake/project/.claude/scripts/*` 与权威逐字节相同）。验证方法：在真实仓库按 RQ-3 给的唯一正确命令执行一次，再跑 `diff-installed.py .`（期望 rc=0）。
6. **`.tmp/rq3c-fake/**` 是兄弟 worker 的合成夹具，不是分发点，且其残留未被本人清理。** 证据：`.agenticdoc/mw-claude-mirror-parity/workers/mwp-rq3c-distribution-path/`（`task.md`/`report.md`/`progress.md`/`worker.log`）与其 `report.md` 全文＝`evidence/research/spec-distribution-path-20261012.md`；夹具时间戳 2026-10-12 15:34-15:35。它的 4 套 scripts 目录与权威**逐字节相同**（§2 表），因为它由权威工作区拷贝得到。未验证：清理责任归属（本人不越权删他人目录）。
7. **`caseVariantOf` / `foreignLiveClaimRefusal` 在 python 侧无对应物，是否为「缺口」取决于 SPEC 意图。** 实测：`.py` 全仓 0 命中；定义只在 `packages/coding-agent/src/extensions/agent-team-loop/{shared/index-store.ts:249,253,330, pm/ui-bridge.ts:277,352,353}`。若 SPEC 要求 python 侧镜像 TS 门禁，则这两个符号从来不在 python 命名空间内 ⇒ 不构成副本缺口。这属于 RQ-2 语义判定范围，本人只给计数。
8. **只验证了构建产物中的两处 bundle 携带同一解析顺序，未做全量产物比对。** 实测 `packages/coding-agent/dist/extensions/agent-team-loop/shared/agentic-scripts.js:22` 与 `packages/multi-workers/dist/extensions/agent-team-loop.js:19868` 都是 `path.join(projectDir, ".claude", "scripts")` 优先（各 2 处 `agenticScriptsDir` 命中）。未验证：其它 dist 入口或旧 bundle 是否同版本（禁止 `npm run build`，无法重生成比对）。
9. **`.agentic-framework` 标记的 `commit=d7004d0` 与权威树 HEAD `d0834ae` 不一致，但未验证有无消费者比较这两个值。** 已读代码：`autopilot/advance.py:51-66 _marker_repo()` 只读 `repo=` 行、忽略 `commit=`；`install.py:181-193` 写 marker 时取 `git rev-parse --short HEAD`。⇒ 标记陈旧无功能影响，但「谁在别处消费 `commit=`」未穷尽搜索（只搜了 `packages/**/*.py` 与 `packages/coding-agent/src`）。

## 7. 复现与临时产物

### 7.1 写面守卫实测（影响后续 worker 的操作方式）

任务允许「临时脚本写 `.tmp/`」，但本机运行期守卫直接拒绝，原始报错：

```
$ New-Item -ItemType Directory -Force -Path .tmp | Out-Null; @'print("x")'@ | Set-Content .tmp\probe.py
write-scope: blocked bash write to .tmp: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\workers\mwp-rq1c-mirror-inventory or H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\evidence
```

⇒ 本次所有临时脚本改写到任务目录 `.../workers/mwp-rq1c-mirror-inventory/_*`，证据文件写到 `evidence/research/`（两者都在 allowed 集合内）。

**附带发现（守卫假阳性，供后续 worker 参考）**：用 PowerShell 单引号 here-string（`@' ... '@`）写脚本时，若脚本文本里出现 `->`，守卫的 shell 分词器会把 `@'` 与文本中第一个 `'` 配成字符串，剩下的 `->` 被当作 `>` 重定向，重定向目标被误判成写目标而 block。原始报错：

```
$ ... @' ... print(root, '->', 0 if files is None else len(files)) ... '@ | Set-Content <worker-dir>\_probe3.py
write-scope: blocked bash write to , 0 if files is None else len(files))
@: outside the worker write surface [rule=scope]; allowed: <taskDir> or <evidenceDir>
```

⇒ 规避方式：here-string 内不要出现 `>`（含 `->`/`=>`），本题所有生成脚本均已遵守（符号表里的 `->` 由脚本从 JSON 读出，不在命令行文本中）。

第二个操作坑：**本机 PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写入 UTF-8 BOM**（实测：用它写出的临时脚本以 `EF BB BF` 开头；python 读入时多出 `U+FEFF`）。本题的最终证据文件已彻底去除该字符（全文 `U+FEFF` 计数 = 0），行尾统一为 LF、无 BOM。

### 7.2 复现方式（临时脚本用后即删，源码内联于下）

本次实跑命令（按报告顺序）：

```powershell
# 1) 全量 sha/bytes/符号：脚本遍历 11 个目录，读 bytes 后 hashlib.sha256 + 正则 ^(def |class |async def )
# 2) 副本差异分类：同名字节比对；不等则去 BOM + CRLF 归一化再比；仍不等则 difflib.SequenceMatcher 统计 add/del/chg
# 3) 门禁符号矩阵：rg -c -F (见 §3 的 PowerShell 循环)
# 4) pi 侧运行时解析（探针源码见下）
node --experimental-strip-types _tmp_probe_runtime.mjs
# 5) mw autopilot 侧运行时解析（探针源码见下）
python _tmp_probe_autopilot.py
# 6) 只读端到端判别
python -X utf8 .agents/skills/agentic-task/scripts/update_index.py get-claim _scratch
python -X utf8 .claude/scripts/update_index.py get-claim _scratch
# 7) 安装一致性对照（只读）
python .agents/skills/agentic-task/diff-installed.py .
# 8) detect_root 原始输出（只读）
python -X utf8 .agents/skills/agentic-task/scripts/detect_root.py --json
```

未执行（均被纪律或写面禁止）：`npm run check`、任何 build、全量 vitest/pytest、任何 git 写操作、真实仓库上的 `install.py .`。

### 7.3 两个运行时探针源码（内联存档）

`_tmp_probe_runtime.mjs`（pi 侧；直接 import 真实模块，无 spawn 打桩）：

```javascript
import * as fs from "node:fs";
import * as path from "node:path";
import { createHash } from "node:crypto";

const projectDir = "H:\\git\\Multi-Workers";
const mod = await import("file:///H:/git/Multi-Workers/packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts");

const dir = mod.agenticScriptsDir(projectDir);
console.log("MEASURED agenticScriptsDir:", dir);
console.log("MATCHES .claude/scripts :", dir === path.join(projectDir, ".claude", "scripts"));

const AUTH = path.join(projectDir, ".agents", "skills", "agentic-task", "scripts");
for (const name of ["advance_phase.py", "update_index.py", "audit_phase.py", "detect_root.py", "check_mermaid.py", "sync_framework.py", "guard_pm_state.py", "migrate_patterns.py", "verify_project_memory.py"]) {
  const resolved = path.join(dir, name);
  const auth = path.join(AUTH, name);
  const rh = createHash("sha256").update(fs.readFileSync(resolved)).digest("hex");
  const ah = createHash("sha256").update(fs.readFileSync(auth)).digest("hex");
  console.log("RESOLVED", name, "sha=" + rh.slice(0, 16), "IDENTICAL_TO_AUTH=" + (rh === ah));
}

// End-to-end: drive the REAL consumer path with a read-only command whose answer
// differs between the stale copy (no key-name gate) and the authoritative script.
const res = mod.runAgenticScript(projectDir, "update_index.py", ["get-claim", "_scratch"]);
console.log("E2E runAgenticScript(update_index.py get-claim _scratch) ok=" + res.ok);
console.log("E2E output:", JSON.stringify(res.output));
```

`_tmp_probe_autopilot.py`（mw autopilot 侧；调真实 `autopilot.advance`）：

```python
import pathlib, sys
sys.path.insert(0, r"H:\git\Multi-Workers\packages\multi-workers")
from autopilot import advance

pr = pathlib.Path(r"H:\git\Multi-Workers")
plat = advance.locate_platform_dir(pr)
print("AUTOPILOT locate_platform_dir:", plat)
print("AUTOPILOT advance_script:", advance.advance_script(pr))
print("AUTOPILOT is authority:", advance.advance_script(pr) == pr / ".agents" / "skills" / "agentic-task" / "scripts" / "advance_phase.py")
```

### 7.4 本次写入的文件

唯一证据文件：`.agenticdoc/mw-claude-mirror-parity/evidence/research/spec-mirror-inventory-20261012.md`（本文件）。

文件属性：UTF-8 无 BOM、LF 行尾（与同目录其他 RQ 证据文件一致；生成过程中先写 LF，最后统一归一化为 LF）。

任务目录内的一次性脚本已按纪律删除，删除清单（内容即 §7.2/§7.3 所述逻辑，探针源码已内联存档）：

- `_tmp_inv.py`：权威/副本遍历 → `_tmp_inv.json`（字节/sha256/符号/行尾/BOM）
- `_tmp_cmp.py` / `_tmp_cmp2.py`：副本差异分类（含 `.tmp/rq3c-fake` 两个夹具目录）
- `_tmp_diffs.py` / `_tmp_diffs2.py`：逐 hunk 差异文本（输出 `_tmp_diffs.txt` / `_tmp_diffs2.txt`）
- `_tmp_tab.py`：权威表/符号表渲染
- `_tmp_build1..6.py`：本报告分块生成
- `_probe1.py` / `_probe2.py` / `_probe3.py`：写面守卫行为探针（§7.1）

另外：`progress.md` 为 worker_file 写入的进度笔记；`trace.log` / `run.json` / `task.md` / `worker.log` 由 harness 维护，本人未改。

