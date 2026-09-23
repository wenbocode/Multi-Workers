# Validation runs: mw-ue-toolchain（2026-09-21）

> 执行环境: Windows / PowerShell 5.1 / Python 3.14；临时脚本与日志用后即删，本文件为结论留底（P-001：控制台输出不作为证据载体）。

## 1. 单元/集成测试（hermetic）

```
$ cd packages/multi-workers && python -m pytest test_toolchain_cli.py -q
..............                                                           [100%]
14 passed in 0.93s

$ python -m pytest -q
..                                                                       [100%]
722 passed, 9 deselected in 70.89s
```

722 = 既有 708 + 本 key 14。9 deselected 为套件既有标记，非本 key 引入。

## 2. 全仓检查

```
$ npm run check
check-exit=0
```

本 key 无 TS 改动；biome/tsgo 等全链通过。

## 3. 真机冒烟（fabricated dual 项目，`python -c` 模拟工具链命令）

fixtures：`<tmp>/control/.agenticdoc/target.yml`（mode=dual，game 指向 `<tmp>/game`，toolchain.build_editor=`cmd /c echo ...`）、`game/Source/ProjEditor.Target.cs`、`--watch game/AssetImportGate.cpp`（CRLF 内容）。

```
$ mw.py ue-toolchain targets --project <control>
- ProjEditor (editor) — <game>\Source\ProjEditor.Target.cs
[mw ue-toolchain] editor targets end in 'Editor'; use them for incremental editor builds

$ mw.py ue-toolchain run build_editor --project <control> --watch <file> --args=-MaxParallelActions=16
[mw ue-toolchain] run: cmd /c echo [5/5] Simulating UE incremental build -MaxParallelActions=16
[mw ue-toolchain] dir: <control>\.mw\toolchain-runs\20260921-204041-build_editor
[mw ue-toolchain] exit=0 seconds=0.0 error_lines=0 watched_drift=0/1 — OK

$ mw.py ue-toolchain hash <file>
79fa0bcf...  <file>
```

## 4. CLI 派发层验证（单测绕过 argparse，必须实跑）

```
PASS: mw.py ue-toolchain --help        (rc=0)
PASS: mw.py ue-toolchain run ping      (rc=0)
PASS: mw.py ue-toolchain targets       (rc=0)
PASS: mw.py toolchain run ping         (rc=2，未知子命令——旧动词正确拒绝，无别名)
```

## 5. 失败用例真机复现记录（过程证据）

- argparse REMAINDER：`run build_editor --project X` → `--project` 被吞 → 弃 REMAINDER 改 `--args`（evidence/research/design-cli-shape）。
- argparse 负号值：`--args "-MaxParallelActions=16"` → 被当未知旗标 → 等号形式写入 help 文本。
- drift 判定：子命令 exit 0 但 `--watch` 文件被命令自身 append → mw rc=1、watched_drift_count=1（单测 test_watch_drift_fails_even_on_exit_zero 覆盖）。
