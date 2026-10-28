# RQ-2 证据：权威与副本的语义层差异（分发包镜像门禁一致性）

- key：`mw-claude-mirror-parity`｜阶段：SPEC｜日期：2026-10-12
- 权威（authoritative）：`H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py`（28884 B，sha256(RAW)=`6bc10453390b9908fdeabf5fca0d19bfe7f145ea7429f36c3d40db0c038c7400`）
- 副本（mirror）：`H:\git\Multi-Workers\.claude\scripts\update_index.py`（22026 B，sha256(RAW)=`0b8f7128158d0945b498adb05320df85d3fa3e6e14d68951abb31decbb111772`）
- golden 语料：`H:\git\Multi-Workers\packages\multi-workers\test_update_index_key_refusal.py`（66 行 `CASES` + 18 行 `COMMAND_CASES` + `caseVariantOf` 用例）
- 环境：Windows + PowerShell 5.1（本机 bash 后端）、python 3.14.3、node v24.19.0
- 只读声明：未写任何仓内既有文件；唯一写入是本文件。临时脚本位于 `H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\workers\mwp-rq2c-mirror-semantics\scratch\`。
- 副本加载方式：`importlib.util.spec_from_file_location` 按路径加载；副本先复制到上述 scratch 目录再加载（**未复制进任何产品目录**，未在 `.claude/scripts/` 产生 `__pycache__`：加载时 `sys.dont_write_bytecode = True` + `PYTHONDONTWRITEBYTECODE=1`）。
- 写面守卫实测（本机阻止仓内 `.tmp/`）：`write-scope: blocked bash write to .tmprq2c: outside the worker write surface [rule=scope]`，故临时脚本改落 worker scratch 目录；所有 fixture 建在系统临时目录（`mwgf-rq2-*`），进程退出即删。

## §0 测量方法（可复现，全部实测）

| 编号 | 目的 | 命令 |
|---|---|---|
| M1 | 66 行表 + 18 行命令表两侧跑一次；stub 模式判定「是否越过门禁进入写盘路径」；真实 FS 落盘结果；caseVariantOf 用例 | `python -X utf8 <worker>/scratch/p_parity.py` |
| M2 | golden 语料自证（权威侧，证明「权威判定 = 表期望 = TS」） | `cd packages/multi-workers; python -X utf8 -m pytest -q -s -p no:cacheprovider test_update_index_key_refusal.py` |
| M3 | 分歧成因（行级 diff 块 + 重建实验） | `python -X utf8 <worker>/scratch/p_lineage.py` |
| M4 | 格式分档（RAW 字节 / 行尾 / BOM / AST） | `python -X utf8 <worker>/scratch/p_format.py` |
| M5 | 格式档 worked example（原始输出） | `python -X utf8 <worker>/scratch/p_fmt_example.py` |
| M6 | item 4：门禁函数直呼 + 真实 CLI（6 场景 × 2 侧） | `python -X utf8 <worker>/scratch/p_cli.py` |
| M7 | 符号计数 | `Select-String -Path <file> -Pattern <symbol> -SimpleMatch`（见 §4.1 原始输出） |

口径说明（避免误读）：
- **权威判定** = `key_name_refusal(key)` 返回的稳定 code（`None` = 允许使用）。
- **副本判定** = 副本无 `key_name_refusal`（`ABSENT`），故用两步实测：① stub 模式（把 `_ensure_index` / `_write_index_atomic` / `_update_pm_state_claim` 三个写盘 seam 换成记录器）判定「是否在写盘前拒绝」；② 真实 FS 运行（系统临时目录）记录 rc / 索引行 / 越界写入。
- 真实 FS 运行对「解析后目标逃出 fixture 临时根」的输入（`C:\x`、`\\server\share`、`a:b`、含 NUL）只做 stub 判定，避免意外写网络路径或非临时盘（表中标 `skipped (unsafe target)`）；这 4 行的 stub 判定与其它行一致（`rc0/hooks3`，即未拒绝）。

## §1 ①「行号 → 权威判定 vs 副本判定」对照表与计数

计数（M1 原始输出 `{"total": 66, "auth_table_ok": 66, "mirror_table_ok": 11, "decision_equal": 11}`）：

- `rows_total` = **66**（golden `CASES` 全量）
- `rows_equal` = **11**（副本与权威判定相同；恰好是 11 个合法名）
- `rows_diff` = **55**（全部应拒行：14 保留名 + 5 保留名大小写变体 + 8 前缀名 + 9 路径/驱动器前缀 + 4 空名 + 15 非法 shape）
- 权威侧 `auth_table_ok` = **66/66**（与 golden 表期望一致；M2 同时证明 TS 侧 66/66）
- 副本侧 `mirror_table_ok` = **11/66**（只有合法名一档符合期望）
- 命令表（18 行，`cmd_set_phase`）：rc 相同 **3**（合法名 3 行），rc 分歧 **15**
- caseVariantOf 等价用例：权威 **1 行**（`['mw-key']`，`claim_id` 被接管），副本 **2 行**（`['mw-key', 'MW-KEY']`，重复行且原行 claim_id 保留旧值）
- 权威真实 FS 侧：51 个应拒行实测 `rc=1` 且 `created=[]`（零写入）；另 4 行（`C:\x`、`\\server\share`、`a:b`、含 NUL）出于安全未真实运行（stub 判定 `rc1/hooks0`）。合计 55 个应拒行 = 51 实测 + 4 stub，与 M2 的 `[VERIFY] claim_refused=55 index_untouched=true` 一致
- 副本 real-FS 侧：66 行全部触达写盘路径（stub `hooks3`），其中 **48 行 `rc=0` 写成功**、**14 行抛未捕获异常**（`r03`/`rc02` FileExistsError、`l08`/`m02`/`s03` FileNotFoundError、`m03`/`s06`-`s11`/`s14`/`s16` OSError，全部**已先创建 `.agenticdoc/_index.parallel`**）、4 行因安全原因跳过真实运行
### 1.1 逐行判定表（golden 表 66 行；权威 vs 副本）

- rows_total = **66**
- rows_equal（副本与权威判定相同）= **11**
- rows_diff（分歧）= **55**
- rows_auth_matches_table = **66/66**（权威判定 == golden 表期望 == TS）
- rows_mirror_matches_table = **11/66**（副本判定 == 表期望，仅合法名那一档）

| 行 | key | 类别 | expected | 权威 key_name_refusal | 副本 key_name_refusal | 权威 claim(stub) | 副本 claim(stub) | 副本 claim(真实 FS) | 一致 |
|---|---|---|---|---|---|---|---|---|---|
| r01 | `_scratch` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r02 | `.mw` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r03 | `_index.parallel` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC FileExistsError; idx=True | **否** |
| r04 | `_index.md` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r05 | `_workers.parallel` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r06 | `_workers.stale.parallel` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r07 | `_workers.acked` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r08 | `_autopilot` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r09 | `_project_log.md` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r10 | `_arch_snapshot.md` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r11 | `_pitfalls.md` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r12 | `.agenticdoc` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r13 | `_impl_gate.log` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| r14 | `_incidents` | reserved | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| rc01 | `_SCRATCH` | reserved-case | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| rc02 | `_Index.Parallel` | reserved-case | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC FileExistsError; idx=True | **否** |
| rc03 | `.MW` | reserved-case | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| rc04 | `.AgenticDoc` | reserved-case | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| rc05 | `_WORKERS.PARALLEL` | reserved-case | reserved-key-name | reserved-key-name | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p01 | `_tmp` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p02 | `.hidden` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p03 | `_` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p04 | `-lead` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p05 | `~x` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p06 | `-----` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p07 | `_work` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| p08 | `.agentic` | prefix | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| l01 | `mw-ok` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l02 | `mw.fresh-2` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l03 | `MW-Key` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l04 | `a` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l05 | `A1_b.c-2` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l06 | `x_9` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l07 | `key-0` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l08 | `  mw-ok  ` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | EXC FileNotFoundError; idx=True | 是 |
| l09 | `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l10 | `\ufeffmw-ok` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| l11 | `0` | legal | —(允许) | —(允许) | ABSENT(无此函数) | rc0/hooks3 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | 是 |
| e01 | `a/b` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=5; escaped=1 | **否** |
| e02 | `a\\b` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=5; escaped=1 | **否** |
| e03 | `../x` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=3 | **否** |
| e04 | `..` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=3; escaped=2 | **否** |
| e05 | `.` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=3; escaped=1 | **否** |
| e06 | `C:x` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| e07 | `C:\\x` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | skipped (unsafe target) | **否** |
| e08 | `\\\\server\\share` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | skipped (unsafe target) | **否** |
| m01 | `` | empty | empty-key | empty-key | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=unreadable; created=3; escaped=1 | **否** |
| m02 | `   ` | empty | empty-key | empty-key | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC FileNotFoundError; idx=True | **否** |
| m03 | `\t` | empty | empty-key | empty-key | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| m04 | `\ufeff` | empty | empty-key | empty-key | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| s01 | `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| s02 | `trailing.` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| s03 | `a...` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC FileNotFoundError; idx=True | **否** |
| s04 | `a b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| s05 | `a:b` | path | key-path-escape | key-path-escape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | skipped (unsafe target) | **否** |
| s06 | `a*b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s07 | `a?b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s08 | `a"b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s09 | `a<b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s10 | `a>b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s11 | `a\|b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s12 | `a\x00b` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | skipped (unsafe target) | **否** |
| s13 | `a\x7fb` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=1; created=4; escaped=1 | **否** |
| s14 | `a\nb` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |
| s15 | `\x85mw-ok` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | rc=0; idx=True; rows=unreadable; created=4; escaped=1 | **否** |
| s16 | `a\x1cb` | shape | key-illegal-shape | key-illegal-shape | ABSENT(无此函数) | rc1/hooks0 | rc0/hooks3 | EXC OSError; idx=True | **否** |

### 1.2 caseVariantOf 等价用例（大小写变体 claim）

| 侧 | rc | 行数 | 存储 keys | rows[0].claim_id == now_claim_id() | 模块有 caseVariantOf |
|---|---|---|---|---|---|
| auth | 0 | 1 | ['mw-key'] | True | False |
| mirror | 0 | 2 | ['mw-key', 'MW-KEY'] | False | False |

### 1.3 命令族（set-phase，18 行 fixture 表）

| 行 | key | expected | 权威 set-phase | 副本 set-phase | 一致 |
|---|---|---|---|---|---|
| k01 | `_index.parallel` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_index.parallel'] | **否** |
| k02 | `_workers.parallel` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_workers.parallel'] | **否** |
| k03 | `_incidents` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_incidents'] | **否** |
| k04 | `.mw` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['.mw'] | **否** |
| k05 | `_SCRATCH` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_SCRATCH'] | **否** |
| k06 | `_Index.Parallel` | reserved-key-name | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_Index.Parallel'] | **否** |
| k07 | `_tmp` | key-illegal-shape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['_tmp'] | **否** |
| k08 | `trailing.` | key-illegal-shape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['trailing.'] | **否** |
| k09 | `a b` | key-illegal-shape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['a b'] | **否** |
| k10 | `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` | key-illegal-shape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'] | **否** |
| k11 | `../x` | key-path-escape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['../x'] | **否** |
| k12 | `a/b` | key-path-escape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['a/b'] | **否** |
| k13 | `C:\\x` | key-path-escape | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=['C:\\x'] | **否** |
| k14 | `` | empty-key | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=[] | **否** |
| k15 | `   ` | empty-key | rc=1; idx=False; rows=0 | rc=0; idx=True; rows=[] | **否** |
| k16 | `mw-cmd-1` | —(允许) | rc=0; idx=True; rows=1 | rc=0; idx=True; rows=['mw-cmd-1'] | 是 |
| k17 | `mw-cmd-2` | —(允许) | rc=0; idx=True; rows=1 | rc=0; idx=True; rows=['mw-cmd-2'] | 是 |
| k18 | `MW-CMD-3` | —(允许) | rc=0; idx=True; rows=1 | rc=0; idx=True; rows=['MW-CMD-3'] | 是 |

- command rows_total = **18**，rc 相同 = **3**，rc 分歧 = **15**

### 1.4 权威侧真实 FS 原始行为（55 行应拒 → rc=1 且零写入）

M1 的 `auth_real` 字段：51 行 `{rc: 1, exc: None, created: [], index_exists: False}`（另 4 行为 stub，见上），即键名门禁在 `_ensure_index` 之前返回，磁盘零触碰（golden 的 `test_reserved_names_refuse_before_any_filesystem_write` 断言同一事实）。合法名 11 行中 10 行 `{rc: 0, created: [.agenticdoc/_index.parallel, .agenticdoc/<key>, .agenticdoc/<key>/pm-state.md, .mw]}`（`.mw` 是 `_index_lock` 的锁目录，位于 `.agenticdoc` 的父目录，两侧一致，非逃逸）；第 11 行 `l08`（`"  mw-ok  "`，门禁判定为「允许」）在**权威与副本上同样** `FileNotFoundError`（Windows 会去掉目录名尾空格，随后写 `pm-state.md` 失败）——见 §5 第 5 条。

## §2 ② 分歧成因：权威有而副本缺的代码段，以及「历史落后 / 语义分歧」判定

**判定：历史落后（stale revision）——不是语义分歧。** 三条独立证据：

1. **副本独有逻辑 = 0。** M3 的行级 diff 只有两类：`delete`（权威独有块）与 `replace`（8 处 `normalize_key(...)` 包装被去掉）。`insert`（副本独有）块数 = **0**，`other-replace`（非 `normalize_key` 解释的替换）块数 = **0**，重建失败项 = **0**。
2. **重建实验逐字节相同。** 取权威文本，删除其独有块 + 去掉 8 处 `normalize_key(...)` 包装 ⇒ sha256(LF)=`53730b9a0fbc9e3136acff5c482ca9407d03772cb29e08397b27cafbf6368410`，与副本 sha256(LF) **完全相同**（`byte_identical=True`）。即副本 = 权威的严格子集（少门禁、少 6 行模块 docstring），不含任何自己的判断逻辑。
3. **血统单调（每级只增不减）。** 同 basename 家族的版本链：
   - `packages/multi-workers/.tmp/agentic-task/scripts/update_index.py`（21820 B；旧版 `find_root`：只从 `__file__` 上溯）
   - `H:\git\Multi-Workers\.claude\scripts\update_index.py`（22026 B；`find_root` 已改为 cwd 优先，仍无门禁、缺 6 行 docstring）
   - `H:\git\Multi-Workers\.agents\skills\agentic-task\claude\scripts\update_index.py` 与 `...\core\scripts\update_index.py`（22492 B，两者字节相同；补回 6 行 docstring，仍无门禁；与 `.claude` 副本的差异 = **仅 docstring，T4**）
   - `H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py`（28884 B；加入键名门禁 + 大小写归一；与 `.claude` 副本 = **T5，AST 不同**）
   上级的每一份文本都是下级的超集（副本独有行 = 0），说明 `.claude` 副本是同一文件较早的同步产物，而不是有人刻意改写的分叉。

**副本缺的代码段（权威坐标，`<authoritative>:<lines>`）：**

| 缺失内容 | 权威行区间 | 语义作用 |
|---|---|---|
| 模块 docstring 的 Phase 说明段（6 行） | `update_index.py:7-12` | 文档，无行为 |
| Key identity 块（117 行）：`RESERVED_INDEX_NAMES`(14 名) / `RESERVED_INDEX_NAME_SET` / `_JS_TRIM_CHARS` / `KEY_MAX_LENGTH=64` / `_KEY_SHAPE_RE` / `_KEY_ILLEGAL_CHARS_RE` / `_KEY_PATH_SEP_RE` / `_KEY_DRIVE_PREFIX_RE` / `normalize_key()` / `key_name_refusal()` / `_key_name_error()` | `update_index.py:58-174` | 键名门禁本体 + 大小写归一 |
| `cmd_claim` 门禁调用块（`claim _index.parallel` / `claim _tmp` / `claim ../x` 在 `_ensure_index` 之前被拒） | `update_index.py:480-489` | 拒绝保留/非法/逃逸名 |
| `cmd_set_phase` 门禁调用块（T-16：门禁在 `_ensure_index` 之前，拒绝 = rc1 + 零写入） | `update_index.py:544-548` | 同上 |
| `cmd_set_meta` 门禁调用块 | `update_index.py:571-574` | 同上 |
| `cmd_release` 门禁调用块 | `update_index.py:599-604` | 同上 |
| `cmd_get_claim` 门禁调用块 | `update_index.py:630-636` | 读路径同样拒绝 |
| 8 处 `normalize_key(r["key"]) == normalize_key(key)` → 副本为裸 `r["key"] == key` | `:495`（claim 预检）、`:515`、`:518`（claim mutate）、`:554`（set-phase）、`:580`（set-meta）、`:609`、`:616`（release）、`:638`（get-claim） | 大小写变体行识别（`caseVariantOf` 的 Python 侧等价） |

**「语义分歧」的严格反证**：如果把 `normalize_key` 差异单独看，它确实是行为差异（副本按字节比较键名），但该差异的成因是**同一处门禁块被整体删除**——`normalize_key` 的定义也在缺失块里，副本无法调用它。因此 55 行判定分歧 + 全部大小写变体分歧都被「历史落后」一条解释；无需假设副本有意保留旧行为（spec §8 P-01 的第二种可能被实测排除）。

**git 溯源不可用（重要限制，见 §5）**：`.claude/` 与 `.agents/` 都被忽略，`git ls-files` 不含任何 `update_index.py`：

```text
$ git check-ignore -v .claude/scripts/update_index.py
.gitignore:21:.claude/	.claude/scripts/update_index.py
$ git check-ignore -v .agents/skills/agentic-task/scripts/update_index.py
.gitignore:57:.agents/	.agents/skills/agentic-task/scripts/update_index.py
$ git ls-files | grep update_index.py
(无输出)
```

所以「历史落后」是从**文本包含关系 + 单调血统链 + 零副本独有逻辑**推断，不是 commit 级证据。
### 2. 分歧成因：权威有而副本缺的代码块（作者侧重建）

- 权威：`H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py`（28884 B，737 行，sha256(LF)=547e1ef9ade9e34f）
- 副本：`H:\git\Multi-Workers\.claude\scripts\update_index.py`（22026 B，582 行，sha256(LF)=53730b9a0fbc9e31）
- 重建实验：删除权威独有的块 + 去掉 8 处 `normalize_key(...)` 包装 ⇒ sha256(LF)=53730b9a0fbc9e31，与副本逐字节相同 = **True**
- 副本独有（MIRROR-ONLY）块数 = **0**，`other-replace` 块数 = **0**，重建失败项 = **0**

| 块 | 权威行区间 | 副本行区间 | 权威行数 | 类型 | 首行 |
|---|---|---|---|---|---|
| delete | 7-12 | 7-6 | 6 | module-docstring | `           A freshly claimed row carries '—' (this script) or 'SPEC' (the TS client,` |
| delete | 58-174 | 52-51 | 117 | gate-module-block | `` |
| delete | 480-489 | 357-356 | 10 | gate-call | `    # Key name gate (AC-006): reserved/illegal names never reach the index, so` |
| replace | 495-495 | 362-362 | 1 | normalize_key-unwrapped | `    existing = next((r for r in rows_now if normalize_key(r["key"]) == normalize_key(key)), None)` |
| replace | 515-515 | 382-382 | 1 | normalize_key-unwrapped | `            if normalize_key(r["key"]) != normalize_key(key) and r["status"] == "active":` |
| replace | 518-518 | 385-385 | 1 | normalize_key-unwrapped | `        row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)` |
| delete | 544-548 | 411-410 | 5 | gate-call | `    # T-16: name gate before `_ensure_index`, so a refused name is rc=1 with` |
| replace | 554-554 | 416-416 | 1 | normalize_key-unwrapped | `        row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)` |
| delete | 571-574 | 433-432 | 4 | gate-call | `    # T-16: same name gate + normalize comparison as set-phase.` |
| replace | 580-580 | 438-438 | 1 | normalize_key-unwrapped | `        row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)` |
| delete | 599-604 | 457-456 | 6 | gate-call | `    # T-16: name gate before `_ensure_index` (refused = rc 1, zero writes) and` |
| replace | 609-609 | 461-461 | 1 | normalize_key-unwrapped | `    if not any(normalize_key(r["key"]) == normalize_key(key) for r in rows_now):` |
| replace | 616-616 | 468-468 | 1 | normalize_key-unwrapped | `        row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)` |
| delete | 630-636 | 482-481 | 7 | gate-call | `    # T-16: read-only path still shares the name gate and the normalize` |
| replace | 638-638 | 483-483 | 1 | normalize_key-unwrapped | `    row = next((r for r in rows if normalize_key(r["key"]) == normalize_key(key)), None)` |

## §3 ③ 格式差异分档（字节不同但语义相同的副本）

分档判据（两两比较同一 basename 的副本，全部基于 **RAW 字节**）：

| 档 | 判据 | 含义 |
|---|---|---|
| T0 | `sha256(RAW)` 相同 | 字节相同 |
| T1 | 仅 CRLF/LF 不同（归一化行尾后 sha256 相同） | 纯行尾差异 |
| T2 | 仅 BOM / 空行 / 行尾空白不同 | 纯格式差异（本轮 **0 对**） |
| T3 | AST 相同（注释/空白差，docstring 计入） | 注释级漂移 |
| T4 | 去掉 docstring 后 AST 相同 | docstring 级漂移 |
| T5 | AST 不同 | 语义分歧 |

实测分布（M4，全部家族两两）：
```json
{"T0": 176, "T1": 33, "T3": 12, "T4": 2, "T5": 113}
```

结论要点：
- **BOM：全部副本 = False**（`bom=False`，无 UTF-8 BOM）。**T2 = 0 对**。
- **T1 = 33 对**：确实存在「字节不同、语义（含注释/docstring）完全相同」的副本对，且集中出现在 `packages/multi-workers/.tmp/agentic-task/**` 测试 bundle（CRLF）与 skill 家族（LF）之间——见下方 worked example，归一化后 `diff_lines=0`。
- **T4 = 2 对**：`update_index.py` 的 `B-claude-installed` 与 `C-skill-claude`/`D-skill-core`：仅差 6 行模块 docstring（`+`/`-` 原文见 worked example）。即「只比字节」会把 docstring 漂移与门禁漂移混为一谈。
- **T5 = 113 对**，其中 `update_index.py` 的权威 ↔ `.claude` 副本就是 T5（AST 不同，`diff_lines=215`）。**因此「字节不同但语义相同」这一档不能解释键名门禁缺口**（spec P-03 的误报担心在本族不成立；反之，若一致性检查只看字节，会把 T1/T4 两档当作失败——AC-002 需要给出档位而不是单一 hash）。
- **行尾策略在同一目录内按文件混用**：`H:\git\Multi-Workers\.claude\scripts\update_index.py` 是 CRLF（`crlf=582, bare_lf=0`），同目录 `H:\git\Multi-Workers\.claude\scripts\audit_phase.py` 是裸 LF（`crlf=0, bare_lf=207`）；`.agents/skills/agentic-task/scripts/` 同样混用（`update_index.py` CRLF=737，`audit_phase.py` LF=211）。任何「行尾统一」假设都不成立。
- 与门禁无关但影响分档判读：`advance_phase.py` 在 A/B/C/D 四地 **T0 字节相同**（sha256=`9427abe2ecc0366b…`），所以缺口**只在 `update_index.py`**（以及 RQ-1 覆盖的其它脚本，本 RQ 不展开）。

### 3.1 格式档 worked example 原始输出（M5）

```text
### T1-line-endings
  H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\test_install.py
    bytes=4254 crlf=0 bare_lf=96 bom=False
    sha256(raw)=ce3d905d33fce8036577b1b1a7b3266d69847770dfba875189f62ebcfa2ee340
    sha256(normalized line endings)=ce3d905d33fce8036577b1b1a7b3266d69847770dfba875189f62ebcfa2ee340
  H:\git\Multi-Workers\packages\multi-workers\.tmp\agentic-task\scripts\test_install.py
    bytes=4350 crlf=96 bare_lf=0 bom=False
    sha256(raw)=296cbfdac5ba561473dd4cdd4eb9f7efdd69ad57a507ecea9610303e749970dc
    sha256(normalized line endings)=ce3d905d33fce8036577b1b1a7b3266d69847770dfba875189f62ebcfa2ee340
  raw_equal=False  normalized_equal=True  diff_lines=0

### T1-line-endings
  H:\git\Multi-Workers\.claude\scripts\audit_phase.py
    bytes=7876 crlf=0 bare_lf=207 bom=False
    sha256(raw)=e3b5fdf2f2754857fffda92496e482fc41c479dd549c4d2df444f26a48c23409
    sha256(normalized line endings)=e3b5fdf2f2754857fffda92496e482fc41c479dd549c4d2df444f26a48c23409
  H:\git\Multi-Workers\packages\multi-workers\.tmp\agentic-task\scripts\audit_phase.py
    bytes=8083 crlf=207 bare_lf=0 bom=False
    sha256(raw)=a147bec9e9d88475c46c1e947bfe8cadf2fabddc4c290aad3454f92dbefc193f
    sha256(normalized line endings)=e3b5fdf2f2754857fffda92496e482fc41c479dd549c4d2df444f26a48c23409
  raw_equal=False  normalized_equal=True  diff_lines=0

### T4-docstring-only
  H:\git\Multi-Workers\.claude\scripts\update_index.py
    bytes=22026 crlf=582 bare_lf=0 bom=False
    sha256(raw)=0b8f7128158d0945b498adb05320df85d3fa3e6e14d68951abb31decbb111772
    sha256(normalized line endings)=53730b9a0fbc9e3136acff5c482ca9407d03772cb29e08397b27cafbf6368410
  H:\git\Multi-Workers\.agents\skills\agentic-task\claude\scripts\update_index.py
    bytes=22492 crlf=588 bare_lf=0 bom=False
    sha256(raw)=6ea8a1ea0300aaca8bef01d3d1beb4f5358a99a8c41db5ad015d15eca370371d
    sha256(normalized line endings)=f8b55558dcdcffe77cf275d04483f6a892c1ea8963600d8c755d94825d10e50e
  raw_equal=False  normalized_equal=False  diff_lines=11
  --- diff (normalized text, first 24 lines) ---
  --- H:\git\Multi-Workers\.claude\scripts\update_index.py
  +++ H:\git\Multi-Workers\.agents\skills\agentic-task\claude\scripts\update_index.py
  @@ -6,2 +6,8 @@
     Phase  — project phase: SPEC / DESIGN / PLAN / TASKS / EXECUTE / VERIFY / DONE / —
  +           A freshly claimed row carries '—' (this script) or 'SPEC' (the TS client,
  +           agent-team-loop's IndexStore.claim); pm-state's claim stub carries 'init'.
  +           All three mean "not started yet": audit_phase.py treats init/'—'/'' as
  +           pending (nothing to audit), so the two-source consistency check only judges
  +           real phases and the first advance_phase.py call normalizes both files to an
  +           upper-case phase.
     Deps   — comma-separated dependency key names (or —)

### T5-semantic
  H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py
    bytes=28884 crlf=737 bare_lf=0 bom=False
    sha256(raw)=6bc10453390b9908fdeabf5fca0d19bfe7f145ea7429f36c3d40db0c038c7400
    sha256(normalized line endings)=547e1ef9ade9e34f968eca9ddf599bee35ef548e95944d5bb3f12cea012f72c0
  H:\git\Multi-Workers\.claude\scripts\update_index.py
    bytes=22026 crlf=582 bare_lf=0 bom=False
    sha256(raw)=0b8f7128158d0945b498adb05320df85d3fa3e6e14d68951abb31decbb111772
    sha256(normalized line endings)=53730b9a0fbc9e3136acff5c482ca9407d03772cb29e08397b27cafbf6368410
  raw_equal=False  normalized_equal=False  diff_lines=215
  --- diff (normalized text, first 24 lines) ---
  --- H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py
  +++ H:\git\Multi-Workers\.claude\scripts\update_index.py
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

```
## §4 ④ 关键问题实测：只装 `.claude/scripts` 副本 ⇒ key 名门禁是否实际失效？

**结论：实际失效（fail-open，不是「弱化」而是「不存在」）。** 副本里既没有 Python 侧门禁函数，也没有 TS 侧门禁符号（`.claude` 下没有任何 `.ts` 文件），且运行时解析路径**优先**指向 `.claude/scripts`。

### 4.1 门禁函数/符号在副本里不存在（M6 + M7）

- `hasattr(mirror, "key_name_refusal")` = **False**，`hasattr(mirror, "RESERVED_INDEX_NAMES")` = **False**；权威侧同为 True。
- 直接调用副本门禁函数 ⇒ `AttributeError: module 'rq2_mirror_attr' has no attribute 'key_name_refusal'`（原始输出见 §4.4）。
- 符号计数（`Select-String -SimpleMatch`，计数 = 匹配行数）：

```text
symbol: key_name_refusal          authoritative=3   .claude/scripts=0  claude/scripts=0  core/scripts=0
symbol: RESERVED_INDEX_NAMES      authoritative=2   .claude/scripts=0  claude/scripts=0  core/scripts=0
symbol: normalize_key             authoritative=11  .claude/scripts=0  claude/scripts=0  core/scripts=0
symbol: _key_name_error           authoritative=5   .claude/scripts=0  claude/scripts=0  core/scripts=0
symbol: keyNameRefusal            authoritative=2   .claude/scripts=0  claude/scripts=0  core/scripts=0
symbol: caseVariantOf             authoritative=0   .claude/scripts=0  claude/scripts=0  core/scripts=0
.claude/scripts/*.py tree-wide: key_name_refusal=0 keyNameRefusal=0 caseVariantOf=0 RESERVED_INDEX_NAMES=0
.claude 下的 .ts 文件数 = 0
```

- 直接调用（M6 `reachable` 检查）：副本 `cmd_set_phase` 存在且可调用（`<function cmd_set_phase at 0x…>`）——**入口在、门禁不在**，这正是「门禁不存在」而非「入口缺失」的形态。

### 4.2 真实 CLI 实测（6 场景 × 2 侧，原始输出见 §4.3）

| 场景（cwd = 临时项目根，argv 与 `advance_phase.py:602` 同形） | 副本 rc / 结果 | 权威 rc / 结果 |
|---|---|---|
| `set-phase MW-KEY EXECUTE`（已存在 `mw-key` 行） | rc=0；索引变成 **2 行**：`mw-key`(active) + `MW-KEY`(idle EXECUTE) ⇒ 大小写变体重复行（`caseVariantOf` 缺口） | rc=0；仍是 **1 行**，`mw-key` 的 phase 改为 EXECUTE |
| `set-phase _index.parallel EXECUTE` | rc=0；把保留名当 key 写进 `_index.parallel`：`\| _index.parallel \| idle \| EXECUTE \| …` | rc=1；`ERROR: refused key name (reserved-key-name)`，零写入（目录里只有 `.agenticdoc`） |
| `claim _SCRATCH --force` | rc=0；`OK: claimed '_SCRATCH'`，创建 `.agenticdoc/_SCRATCH/pm-state.md` + active 行 | rc=1；`refused key name (reserved-key-name)`，零写入 |
| `claim ../esc --force` | rc=0；写 `esc/pm-state.md`（**在 `.agenticdoc` 之外**）+ active 行 | rc=1；`refused key name (key-path-escape)`，零写入 |
| `get-claim MW-KEY`（已存在 `mw-key` 行） | rc=0；输出 `—`（找不到行） | rc=0；输出 `other-host:4242` |
| `release MW-KEY`（已存在 `mw-key` 行） | rc=0；`WARN: key 'MW-KEY' not found in index, nothing to release.` ⇒ 该行保持 active（释放失败但 rc=0） | rc=0；`OK: released 'MW-KEY'`，`mw-key` 行变为 idle |

补充的副本单侧损害（M1，全部在系统临时目录实测，无外围写入）：

| 输入（保留/非法/逃逸） | 副本结果 | 备注 |
|---|---|---|
| 14 个保留名（`_scratch`、`.mw`、`_index.md`、`_workers.parallel`、`_autopilot`、`_project_log.md`、…） | `rc=0`，建 `pm-state.md` 命名空间目录 + active 行 | 门禁完全缺失 |
| 5 个保留名大小写变体（`_SCRATCH`、`_Index.Parallel`、`.MW`、`.AgenticDoc`、`_WORKERS.PARALLEL`） | 同上一律 rc=0 写入 | Windows 大小写不敏感放大 |
| `_index.parallel`（claim） | `FileExistsError`（`_index.parallel` 已存在）——但**已先由 `_ensure_index` 创建该文件** | golden 的 `test_reserved_names_refuse_before_any_filesystem_write` 正是在防这个 |
| `../x` / `..` | 写 `.agenticdoc` 之外的 `x/pm-state.md` / `pm-state.md` | 路径逃逸落盘（对照：权威 rc=1 且 `escaped=false`） |
| `a/b`、`a\b` | 在 `.agenticdoc` 内建嵌套目录 `a/b/pm-state.md`，索引行 key 记为 `a/b` | 语义不一致的命名空间 |
| `\x85mw-ok` | rc=0 写入，但**读回 0 行**（`read_index` 用 `str.splitlines()`，U+0085 被当作换行 ⇒ 行被拆断） | 索引行损坏/丢失 |
| `trailing.` | 目录被 Windows 归一化为 `trailing`，索引里却记 `trailing.` | 索引与文件系统不一致 |
| `a*b` `a?b` `a"b` `a<b` `a>b` `a\|b` `a\nb` `a\x1cb` `"   "` `"a..."` `\t` | 未捕获 `OSError/FileNotFoundError`（rc 非 0 的 traceback），且 `.agenticdoc/_index.parallel` 已创建 | 半写入状态 |

> 「副本侧 66 行全部触达写盘路径」的机器判据：stub 模式把 `_ensure_index` / `_write_index_atomic` / `_update_pm_state_claim` 换成记录器后，副本 66 行全部 `rc=0, hooks=[3 个 seam 都被调用]`；权威 55 行 `rc=1, hooks=[]`、11 行合法名 `rc=0, hooks=3`。见 §1.1 表的两列 `claim(stub)`。

### 4.3 活链坐标（谁在跑副本）

| 坐标 | 内容 |
|---|---|
| `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\shared\agentic-scripts.ts:21-25` | `agenticScriptsDir`：`candidates[0] = <project>/.claude/scripts`（**第 23 行**），`candidates[1] = <project>/.agents/skills/agentic-task/claude/scripts`（**第 24 行**）——**两级候选都无门禁**（前者缺门禁，后者是 22492 B 的无门禁模板） |
| `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\shared\agentic-scripts.ts:45,67` | `runAgenticScript` → `spawnSync(PYTHON_EXE, ["-X","utf8", script, ...args])`，`cwd=projectDir` |
| `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\pm\ui-bridge.ts:2345` | `const result = runAgenticScript(projectDir, "advance_phase.py", args)`（advance_phase 工具） |
| `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\pm\ui-bridge.ts:2339-2343` | 上游只做 `foreignLiveClaimRefusal(indexStore, trimmedKey)`（跨 key 活 claim 守卫；判定函数定义在 `ui-bridge.ts:277`），**不做键名门禁**；key 直接进 argv（`ui-bridge.ts:2336` `const args = [trimmedKey, target]`） |
| `H:\git\Multi-Workers\.claude\scripts\advance_phase.py:599-602` | `index_script = Path(__file__).parent / "update_index.py"`；`subprocess.run([sys.executable, str(index_script), "set-phase", key, target.upper()])` ⇒ 同目录副本 |
| `H:\git\Multi-Workers\.claude\scripts\update_index.py:409`（`cmd_set_phase`）/ `:355`（`cmd_claim`） | 副本命令入口，无门禁；`_ensure_index` 在入口第一步（`:410` / `:356`）⇒ 门禁即使存在也已晚于写盘 |

注：`advance_phase.py` 在 `.agents/skills/agentic-task/scripts`、`.claude/scripts`、`.../claude/scripts`、`.../core/scripts` 四处**字节相同**（T0，sha256=`9427abe2ecc0366b…`），所以「只装 `.claude/scripts`」的缺口**唯一来自 `update_index.py`**（其它脚本的差异见 RQ-1）。

### 4.4 原始输出（M6/M7，verbatim）

```text
=== direct calls (importlib.util.spec_from_file_location, in-process) ===
[mirror_hasattr] has_key_name_refusal=False has_RESERVED_INDEX_NAMES=False
    value=None
    exception=AttributeError: module 'rq2_mirror_attr' has no attribute 'key_name_refusal'
[auth_hasattr] has_key_name_refusal=True has_RESERVED_INDEX_NAMES=True
    value=<function key_name_refusal at 0x00000129FE535A60>
    exception=None
[mirror_call_reserved] has_key_name_refusal=False has_RESERVED_INDEX_NAMES=False
    value=None
    exception=AttributeError: module 'rq2_mirror_call' has no attribute 'key_name_refusal'
[auth_call_reserved] has_key_name_refusal=True has_RESERVED_INDEX_NAMES=True
    value=('reserved-key-name', "'_SCRATCH' is a reserved framework name, not an AgenticTask key namespace")
    exception=None
[auth_call_caseVariant] has_key_name_refusal=True has_RESERVED_INDEX_NAMES=True
    value=None
    exception=None
[mirror_cmd_set_phase_attr] has_key_name_refusal=False has_RESERVED_INDEX_NAMES=False
    value=<function cmd_set_phase at 0x00000129FE59C460>
    exception=None

=== CLI runs (python <script> <args>, cwd=<temp project root>) ===
[set-phase-MW-KEY] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'set-phase', 'MW-KEY', 'EXECUTE']
    rc = 0
    stdout = "OK: set phase 'MW-KEY' -> EXECUTE"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |', '| MW-KEY | idle | EXECUTE | — | — | — | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel', '.mw']
[set-phase-MW-KEY] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'set-phase', 'MW-KEY', 'EXECUTE']
    rc = 0
    stdout = "OK: set phase 'MW-KEY' -> EXECUTE"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | active | EXECUTE | other-host:4242 |  |  | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel', '.mw']
[set-phase-reserved-index] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'set-phase', '_index.parallel', 'EXECUTE']
    rc = 0
    stdout = "OK: set phase '_index.parallel' -> EXECUTE"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| _index.parallel | idle | EXECUTE | — | — | — | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel', '.mw']
[set-phase-reserved-index] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'set-phase', '_index.parallel', 'EXECUTE']
    rc = 1
    stdout = ''
    stderr = "ERROR: refused key name (reserved-key-name): '_index.parallel' is a reserved framework name, not an AgenticTask key namespace"
    index rows = []
    files = ['.agenticdoc']
[claim-_SCRATCH] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'claim', '_SCRATCH', '--force']
    rc = 0
    stdout = "OK: claimed '_SCRATCH' with ClaimId=WENBOZHOU-PC4:139700"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| _SCRATCH | active | — | WENBOZHOU-PC4:139700 | — | — | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/_SCRATCH', '.agenticdoc/_SCRATCH/pm-state.md', '.agenticdoc/_index.parallel', '.mw']
[claim-_SCRATCH] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'claim', '_SCRATCH', '--force']
    rc = 1
    stdout = ''
    stderr = "ERROR: refused key name (reserved-key-name): '_SCRATCH' is a reserved framework name, not an AgenticTask key namespace"
    index rows = []
    files = ['.agenticdoc']
[claim-path-escape] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'claim', '../esc', '--force']
    rc = 0
    stdout = "OK: claimed '../esc' with ClaimId=WENBOZHOU-PC4:92856"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| ../esc | active | — | WENBOZHOU-PC4:92856 | — | — | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel', '.mw', 'esc', 'esc/pm-state.md']
[claim-path-escape] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'claim', '../esc', '--force']
    rc = 1
    stdout = ''
    stderr = "ERROR: refused key name (key-path-escape): '../esc' contains a path separator or drive prefix"
    index rows = []
    files = ['.agenticdoc']
[get-claim-MW-KEY] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'get-claim', 'MW-KEY']
    rc = 0
    stdout = '—'
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel']
[get-claim-MW-KEY] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'get-claim', 'MW-KEY']
    rc = 0
    stdout = 'other-host:4242'
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel']
[release-MW-KEY] side=mirror
    argv = ['python', 'H:\\git\\Multi-Workers\\.claude\\scripts\\update_index.py', 'release', 'MW-KEY']
    rc = 0
    stdout = ''
    stderr = "WARN: key 'MW-KEY' not found in index, nothing to release."
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |']
    files = ['.agenticdoc', '.agenticdoc/_index.parallel']
[release-MW-KEY] side=authoritative
    argv = ['python', 'H:\\git\\Multi-Workers\\.agents\\skills\\agentic-task\\scripts\\update_index.py', 'release', 'MW-KEY']
    rc = 0
    stdout = "OK: released 'MW-KEY'"
    stderr = ''
    index rows = ['| Key | Status | Phase | ClaimId | Deps | Desc | Updated |', '| mw-key | idle | SPEC | — |  |  | 2026-10-12 15:38 |']
    files = ['.agenticdoc', '.agenticdoc/MW-KEY', '.agenticdoc/MW-KEY/pm-state.md', '.agenticdoc/_index.parallel', '.mw']
```
## §5 ⑤ 未验证/怀疑清单（不写成结论）

1. **「历史落后」缺 commit 级证据**：`.claude/`（`.gitignore:21`）与 `.agents/`（`.gitignore:57`）都被忽略，`git ls-files` 无任何 `update_index.py`，因此无法给出「副本 = 权威的哪个提交」。判定依据是「副本独有逻辑 = 0 + 重建逐字节相同 + 血统单调」，对「有人手工剥掉门禁但保留 6 行更旧 docstring」这种构造无法在证据上完全排除（概率极低，因为剥门禁者更可能保留 docstring 而不是删掉它）。
2. **未跑 `advance_phase.py` 端到端**（需要 pm-state.md + phase 门禁证据 fixture）。替代实测：CLI argv 与 `advance_phase.py:602` 完全同形（`set-phase <key> <PHASE>`）。**未实测**：advance_phase.py 自身的 phase 门禁是否会在键名之前先拦下恶意 key（若拦下，则 `set-phase` 的 fail-open 在端到端里被部分掩盖；`claim` 路径无此掩盖）。
3. **未实测重同步后的副本内容**（`install.py` / `sync_framework.py` 行为、覆盖规则、幂等性）——RQ-3 范围；本报告只证明「当前副本缺门禁」与「差异成因」。
4. **平台差异未测**：本次是 Windows（文件名大小写不敏感 / 尾点与尾空格归一化），多数「索引与 FS 不一致」的实测后果（`trailing.`、`  mw-ok  `、`_Index.Parallel`）是 Windows 特有放大。Linux/macOS 下副本同样无门禁（函数不存在这一点与平台无关），但落盘行为会不同。
5. **权威侧自身的两处非门禁缺陷（非本 key 范围，未展开）**：① `claim "  mw-ok  "`（l08，权威门禁判定为「允许」）在**权威与副本上都会** `FileNotFoundError`（Windows 尾空格目录名），且索引文件已创建——即「合法名」档里存在不往返的输入；② 权威 `release MW-KEY` 会按请求 casing 新建 `.agenticdoc/MW-KEY/pm-state.md`（存储 casing 未回写）。两者不是镜像分歧（两侧相同或同因），但会影响 AC-004 的分歧统计口径：本报告的 `rows_equal` 只判「拒绝/允许」这一个维度，不含「允许后的行为是否健康」。
6. **TS 侧未重跑**：本 RQ 不重复测量 TS `keyNameRefusal`（golden 语料自身在 M2 中以 node 实测 `ts_vs_table=66/66`、`py_ts_code_diff=66/66 equal=true`）；但**未测**「用户项目里 TS 侧是否还有第二道门禁」——按 §4.3 的坐标，`advance_phase` 工具路径上没有键名门禁。
7. **`.tmp/agentic-task/**` 这套 bundle 的分发地位未判定**：本报告把它作为「同 basename 家族」纳入格式分档（它是 T1/T5 差异的主要来源），但它的消费者与是否属于「分发副本」由 RQ-1 口径裁定。
8. **副本真实 FS 运行对 4 行做了安全跳过**（`C:\x`、`\\server\share`、`a:b`、含 NUL）：只给了 stub 判定（未拒绝、触达写盘 seam），没有实际落盘证据（防网络路径/非临时盘写入）。这 4 行的「fail-open」结论强度低于其余 62 行。

## §A 原始测量输出（供复核）

### A.1 M1（两侧语料比对）stdout

```text
{"total": 66, "auth_table_ok": 66, "mirror_table_ok": 11, "decision_equal": 11}
{"auth_key_name_refusal": true, "mirror_key_name_refusal": false, "auth_RESERVED_INDEX_NAMES": true, "mirror_RESERVED_INDEX_NAMES": false, "auth__key_name_error": true, "mirror__key_name_error": false, "ts_RESERVED_INDEX_NAMES_len": 14}
{"auth": {"rc": 0, "exc": null, "row_count": 1, "keys": ["mw-key"], "claim_id_matches_now": true, "caseVariantOf_attr": false}, "mirror": {"rc": 0, "exc": null, "row_count": 2, "keys": ["mw-key", "MW-KEY"], "claim_id_matches_now": false, "caseVariantOf_attr": false}}
```

### A.2 M2（golden 语料自证 = 权威判定即表期望，含 TS 侧）

```text
[VERIFY] table: cases=66 categories=7 reserved=14
[VERIFY] py_vs_table=66/66
[VERIFY] ts_vs_table=66/66
[VERIFY] py_ts_code_diff=66/66 equal=true
[VERIFY] reserved_constant_parity=14 equal=true
[VERIFY] claim_refused=55 index_untouched=true
[VERIFY] reserved_index_parallel: rc=1 disk_untouched=true
[VERIFY] path_escape: rc=1 escaped=false
[VERIFY] legal_unoccupied: rc=0 row_written=true
[VERIFY] scratch: py_gate=reserved ts_guard_allow=true claim_rc=1
[VERIFY] case_variant: rows=1 stored=mw-key duplicate=false
[VERIFY] command_table: cases=18 reserved=4
[VERIFY] command_py_vs_table=18/18
[VERIFY] command_ts_vs_table=18/18
[VERIFY] command_py_ts_code_diff=18/18 equal=true
[VERIFY] command_refused=45 index_untouched=true
[VERIFY] get_claim_refused=15
[VERIFY] command_path_escape: rc=1 escaped=false
[VERIFY] command_legal_accepted=12
[VERIFY] command_case_variant: rows=1 stored=mw-key duplicate=false
[VERIFY] case_variant_audit: field=mw-key caller_audit=1 rows=1
23 passed in 1.00s
```

（命令：`cd packages/multi-workers; python -X utf8 -m pytest -q -s -p no:cacheprovider test_update_index_key_refusal.py`；`-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1` 保证不在仓内留下 pytest 缓存/字节码：`git status --porcelain -- packages/multi-workers` 无输出。）

### A.3 M3 重建实验原始输出

```text
authoritative: H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\update_index.py bytes=28884 lines=737
mirror:        H:\git\Multi-Workers\.claude\scripts\update_index.py bytes=22026 lines=582
reconstruction.sha256_lf = 53730b9a0fbc9e3136acff5c482ca9407d03772cb29e08397b27cafbf6368410
mirror.sha256_lf         = 53730b9a0fbc9e3136acff5c482ca9407d03772cb29e08397b27cafbf6368410
byte_identical = True
problems = 0
block kinds: {"identical": 16, "module-docstring": 1, "gate-module-block": 1, "gate-call": 5, "normalize_key-unwrapped": 8}
```

### A.4 M4 分档统计原始输出

```text
{"T0": 176, "T1": 33, "T3": 12, "T4": 2, "T5": 113}
```

### A.5 复现脚本清单（位于 `H:\git\Multi-Workers\.agenticdoc\mw-claude-mirror-parity\workers\mwp-rq2c-mirror-semantics\scratch\`）

| 脚本 | 作用 |
|---|---|
| `p_parity.py` | M1：加载 golden 语料 + 权威（就地）+ 副本（scratch 路径加载），跑 66 行表的 stub/真实 FS 判定、caseVariantOf 用例、18 行命令表；输出 `scratch/out/parity_raw.json` |
| `p_lineage.py` | M3：行级 diff 块分类 + 重建实验；输出 `scratch/out/lineage.json` |
| `p_format.py` | M4：RAW 字节/行尾/BOM/AST 分档；输出 `scratch/out/format_tiers.json` |
| `p_fmt_example.py` | M5：T1/T4/T5 worked example 原始输出；输出 `scratch/out/format_examples.txt` |
| `p_cli.py` | M6：门禁函数直呼 + 6 场景真实 CLI（两侧）；输出 `scratch/out/cli_raw.json` |
| `p_render.py` | 把上述 JSON 渲染成本文件的表格 |